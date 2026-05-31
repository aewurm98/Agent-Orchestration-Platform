"""
Manufacturing v3 LLM Meta-Optimizer (spec §5).

The Factory Executive AI receives a telemetry digest each generation boundary
and returns a JSON array of exactly 3 candidate genomes. The (mu + lambda) EA in
`evolution.manufacturing_v3_evolution` evaluates the candidates against the
incumbent and keeps the best.

Provider: Anthropic (reuses the shared client wiring in agents.meta_optimizer).
Robustness: any parse / API / validation failure falls back to MATH mutations so
the evolutionary loop never stalls.
"""
from __future__ import annotations

import json
import logging
import random
from typing import Optional

from game_envs.manufacturing_v3.genome import (
    ManufacturingV3Genome,
    MACHINE_IDS,
    EDGE_IDS,
)

log = logging.getLogger(__name__)

# Widened from the spec's 3 to give the (mu+lambda) EA more shots per generation —
# random/conservative single-knob steps stall on the flow-graph's ridgy plateau, so
# we ask the model for a larger, more diverse offspring pool each boundary.
N_CANDIDATES = 6
_DEFAULT_MODEL = "claude-sonnet-4-6"  # latest Sonnet — strong reasoning, faster/cheaper than Opus
# "low" keeps each generation ~15s on Sonnet (high/medium balloon to 40-90s of thinking,
# which defeats the speed downgrade). The explicit diversity guidance in the system
# prompt carries the exploration; raise to "medium" if you want deeper search per gen.
_EFFORT = "low"
_MAX_TOKENS = 8000                   # headroom for adaptive thinking + N_CANDIDATES JSON objects

# ── System prompt (verbatim from spec §5.1) ──────────────────────────────────
SYSTEM_PROMPT = """You are the Factory Executive AI. Your objective is to optimize a continuous flow manufacturing graph to maximize overall Profit (Fitness).

THE FACTORY GRAPH (DAG):
- Nodes (Machines): [molding, wire_drawing, assembly, packaging]
- Edges (Logistics): Transport items between nodes.

ECONOMICS:
- Revenue: +$1000 per finished product.
- Penalties: -$200 per unfulfilled order at the end of the episode.
- Costs: High machine capacities and wide edge bandwidths incur massive exponential per-tick OpEx. Do not over-provision!
- Maintenance: 'low' is cheap but causes frequent downtime (delays). 'high' is expensive but ensures steady flow.

YOUR TASK:
Analyze the telemetry provided by the User. Look at the Queue sizes and Utilization rates to find bottlenecks.
- If a machine's input queue is huge but its utilization is near 100%, it needs more capacity.
- If a machine's output queue is huge, the downstream edge bandwidth needs upgrading.
- If orders are being missed but the factory is mostly idle, increase the order_intake_rate.
- Do not increase capacities uniformly. Balance the flow to minimize OpEx waste.

EXPLORATION (important — small single-knob nudges stall the search):
- Make coordinated, multi-parameter moves when the bottleneck calls for it. Example: if assembly is the bottleneck, raise BOTH its capacity AND its outbound edge bandwidth in the same candidate, and lift order_intake_rate to feed the new throughput.
- Make the 6 candidates genuinely DIVERSE — they should explore different regions, not 6 minor variations of the incumbent. Aim for a spread such as:
  * one BOLD throughput push (large order_intake_rate increase + scale the binding stages to match),
  * one OpEx TRIM (cut over-provisioned capacities/bandwidths whose machines sit idle, keeping fulfilment high),
  * one BOTTLENECK FIX (reallocate capacity/bandwidth from slack stages to the constrained one),
  * one MAINTENANCE experiment (try a different maintenance_policy and rebalance),
  * plus a couple of larger-step variations combining the above.
- Profit per fulfilled order dominates fixed OpEx, so when the factory is healthy, pushing order_intake_rate up (with matching capacity) is usually the biggest lever — be ambitious with it.

OUTPUT FORMAT:
Return a JSON array containing exactly 6 distinct candidate configuration objects matching this schema. No markdown formatting, no conversational text.

[
  {
    "reasoning": "<1-2 sentence chain-of-thought diagnosing the primary bottleneck>",
    "machine_capacities": {
      "molding": <int 1-50>,
      "wire_drawing": <int 1-50>,
      "assembly": <int 1-50>,
      "packaging": <int 1-50>
    },
    "edge_bandwidths": {
      "in_to_molding": <int 1-50>,
      "in_to_wire": <int 1-50>,
      "molding_to_assembly": <int 1-50>,
      "wire_to_assembly": <int 1-50>,
      "assembly_to_packaging": <int 1-50>,
      "packaging_to_out": <int 1-50>
    },
    "maintenance_policy": "<low|medium|high>",
    "order_intake_rate": <int 1-100>
  }
]"""

# Edge that carries each machine's OUTPUT downstream — used to flag output pileups.
_DOWNSTREAM_EDGE: dict[str, str] = {
    "molding": "molding_to_assembly",
    "wire_drawing": "wire_to_assembly",
    "assembly": "assembly_to_packaging",
    "packaging": "packaging_to_out",
}


def build_user_prompt(metrics: dict, genome: ManufacturingV3Genome, history: list[dict]) -> str:
    """Render the telemetry digest user prompt (spec §5.2)."""
    lines: list[str] = []
    lines.append("CURRENT FACTORY TELEMETRY (Episode length: 500 ticks)")
    lines.append("")

    # 1. Historical trend (last 3 generations)
    lines.append("1. HISTORICAL TREND (Last 3 Generations)")
    recent = history[-3:]
    if recent:
        for h in recent:
            lines.append(
                f"- Gen {h.get('generation', '?')}: "
                f"Fitness = ${h.get('fitness', 0):,.0f} | "
                f"Throughput = {h.get('throughput', 0)} units | "
                f"OpEx = ${h.get('opex', 0):,.0f}"
            )
    else:
        lines.append("- (no history yet — this is the first generation)")
    lines.append("")

    # 2. Current episode performance
    gen = history[-1].get("generation", "?") if history else "?"
    lines.append(f"2. CURRENT EPISODE PERFORMANCE (Gen {gen})")
    lines.append(f"- Orders Received: {metrics.get('orders_received', 0)}")
    lines.append(f"- Orders Fulfilled: {metrics.get('orders_fulfilled', 0)}")
    lines.append(
        f"- Orders Missed: {metrics.get('orders_missed', 0)} "
        f"({'Penalty incurred' if metrics.get('orders_missed', 0) else 'no penalty'})"
    )
    lines.append(f"- Total OpEx spent: ${metrics.get('total_opex', 0):,.0f}")
    lines.append("")

    # 3. Bottleneck diagnostics
    lines.append("3. BOTTLENECK DIAGNOSTICS (Average over episode)")
    diag = metrics.get("node_diagnostics", {})
    lines.append("Nodes (Machines):")
    for mid in MACHINE_IDS:
        d = diag.get(mid, {})
        util = d.get("utilization", 0.0)
        warn = "  <-- WARNING: High Utilization" if util >= 0.90 else ""
        lines.append(
            f"- {mid+':':<13} Utilization = {util*100:.0f}% | "
            f"Avg Input Queue = {d.get('avg_input_queue', 0.0)} | "
            f"Avg Output Queue = {d.get('avg_output_queue', 0.0)}{warn}"
        )
    lines.append("")
    lines.append("Edges (Logistics Transport Rates):")
    bandwidths = genome.edge_bandwidths
    # Flag an edge as low-bandwidth when its upstream machine has a large output pileup.
    starved_edges = set()
    for mid, eid in _DOWNSTREAM_EDGE.items():
        if diag.get(mid, {}).get("avg_output_queue", 0.0) >= 5.0:
            starved_edges.add(eid)
    for eid in EDGE_IDS:
        warn = "   <-- WARNING: Low Bandwidth Output" if eid in starved_edges else ""
        lines.append(f"- {eid}: {bandwidths[eid]}/tick{warn}")
    lines.append("")

    # 4. Current genome
    lines.append("4. CURRENT GENOME")
    lines.append(json.dumps(genome.to_dict(), separators=(", ", ": ")))
    lines.append("")
    lines.append(
        "Based on the Diagnostics, identify the current bottleneck, adjust the "
        "capacities to smooth the flow, and output the new JSON array of 6 diverse candidates."
    )
    return "\n".join(lines)


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("\n")
        raw = "\n".join(parts[1:])
        raw = raw.rstrip()
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]
    return raw.strip()


def _anthropic_text(response) -> str:
    out = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            out.append(text)
    return "".join(out).strip()


def _first_json_value(raw: str):
    """Decode the first JSON array/object in `raw`, tolerating surrounding prose.

    The model is instructed to emit only JSON, but a stray sentence before/after
    must not crash the EA. We locate the first ``[``/``{`` and use ``raw_decode``
    so trailing text is ignored rather than fatal ("Extra data").
    """
    raw = _strip_fences(raw)
    start = next((i for i, ch in enumerate(raw) if ch in "[{"), -1)
    if start == -1:
        raise ValueError(f"no JSON object/array found in response: {raw[:120]!r}")
    return json.JSONDecoder().raw_decode(raw, start)[0]


def parse_candidates(raw: str, base: ManufacturingV3Genome) -> list[ManufacturingV3Genome]:
    """Parse the model's JSON array into validated genomes. Raises on malformed JSON."""
    data = _first_json_value(raw)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError(f"expected a JSON array, got {type(data).__name__}")
    candidates: list[ManufacturingV3Genome] = []
    reasonings: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        candidates.append(base.apply_delta(item))
        reasonings.append(str(item.get("reasoning", "")))
    if not candidates:
        raise ValueError("no valid candidate objects in response")
    # stash reasoning on the genome objects for trace display
    for g, r in zip(candidates, reasonings):
        setattr(g, "_reasoning", r)
    return candidates


def math_candidates(
    base: ManufacturingV3Genome,
    n: int = N_CANDIDATES,
    rng: Optional[random.Random] = None,
) -> list[ManufacturingV3Genome]:
    """Deterministic MATH fallback: n distinct perturbations of the incumbent."""
    rng = rng or random.Random()
    out = []
    for _ in range(n):
        g = base.mutate(rng)
        setattr(g, "_reasoning", "MATH fallback mutation")
        out.append(g)
    return out


async def query_candidates(
    genome: ManufacturingV3Genome,
    metrics: dict,
    history: list[dict],
    *,
    model: str = _DEFAULT_MODEL,
    rng: Optional[random.Random] = None,
) -> list[ManufacturingV3Genome]:
    """Ask the LLM for 3 candidate genomes; fall back to MATH on any failure.

    Always returns at least one valid, fully-clamped genome.
    """
    try:
        from agents.meta_optimizer import _get_anthropic_client

        client = _get_anthropic_client()
        user_prompt = build_user_prompt(metrics, genome, history)
        response = await client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            # Adaptive thinking lets Opus 4.7 reason through the bottleneck before
            # proposing moves; effort tunes how hard it works (raise to "xhigh"/"max"
            # for deeper search, lower to "medium" to cut per-generation latency).
            thinking={"type": "adaptive"},
            output_config={"effort": _EFFORT},
            # System prompt is static across every generation — mark it cacheable.
            # (Currently below Opus 4.7's 4096-token cache floor, so this is a no-op
            # until the prompt grows; harmless and future-proof.)
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = _anthropic_text(response)
        candidates = parse_candidates(raw, genome)
        log.info("v3 meta-optimizer returned %d candidate(s)", len(candidates))
        return candidates
    except Exception as exc:  # noqa: BLE001 — never let the EA loop crash
        log.warning("v3 meta-optimizer failed (%s) — using MATH fallback", exc)
        return math_candidates(genome, N_CANDIDATES, rng)
