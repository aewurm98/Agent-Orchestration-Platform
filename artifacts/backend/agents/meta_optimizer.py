"""
LLM Meta-Optimizer: builds an episode digest from world logs and queries a
language model to propose the next-generation genome configuration.

Scenario-adaptive: system prompt and genome schema differ per scenario so the
LLM receives domain-appropriate context regardless of which game is running.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI

log = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        openai_key = os.environ.get("OPENAI_API_KEY")
        integration_base = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        integration_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        if openai_key:
            _client = AsyncOpenAI(api_key=openai_key)
        elif integration_base and integration_key:
            _client = AsyncOpenAI(base_url=integration_base, api_key=integration_key)
        else:
            raise RuntimeError(
                "No OpenAI credentials found. "
                "Set OPENAI_API_KEY or configure the Replit OpenAI AI Integration."
            )
    return _client


# ---------------------------------------------------------------------------
# Scenario-adaptive genome schemas
# ---------------------------------------------------------------------------

_GENOME_SCHEMAS: dict[str, dict] = {
    "manufacturing": {
        # Spec §4.2 — full Factory Meta-Optimizer system prompt. When present this
        # replaces the generic prompt scaffold built in _build_system_prompt.
        "system_prompt": (
            "You are the Factory Meta-Optimizer, an AI architect managing a continuous "
            "manufacturing simulation.\n"
            "The simulation operates on a fixed 12x12 spatial grid.\n"
            "Your goal is to maximize the overall Fitness Score over a mini-batch of "
            "stochastic episodes (1000 ticks each).\n\n"
            "FITNESS TARGET & ECONOMICS:\n"
            "The final Fitness Score is a weighted calculation:\n"
            "(50% Profit) + (30% Throughput) - (15% Missed Orders) - (5% Idle Agents) + (5% Machine Util).\n"
            "- Revenues: Standard Product (+$200), Rush Order (+$300), Scrap (+$5).\n"
            "- OpEx: Agent Wages (Eng: $5/t, Sales: $4/t, Proc: $3/t, Ops: $2/t), Material Costs, Machine Power.\n"
            "- Penalties: Late Delivery (-$20/t), Missed Order (-$50 flat).\n\n"
            "THE PRODUCTION DAG:\n"
            "1. Raw Ore -> Smelter -> Ingot\n"
            "2. Raw Silicon -> Circuit Fab -> Circuit\n"
            "3. Ingot -> Stamping Press -> Stamped Part\n"
            "4. (Stamped Part x2 + Circuit x1) -> Assembly -> Subassembly\n"
            "5. Subassembly -> QC Station -> Inspected Unit\n"
            "6. Inspected Unit -> Packaging -> Finished Product\n\n"
            "PHYSICS & TRADEOFFS:\n"
            "- Agents physically move items on the grid.\n"
            "- Too many agents = pathfinding traffic jams and bloated wage costs.\n"
            "- Too few agents = idle machines and supply chain bottlenecks.\n"
            "- Speed Multipliers: 'low' (slow, cheap, reliable), 'normal', 'high' (fast, 2x power cost, 2.5x fail rate).\n"
            "- High failure rates require more Engineering agents to repair broken machines, draining wages.\n\n"
            "YOUR ACTION SPACE (mutate_genome):\n"
            "Output a single JSON object setting the ENTIRE genome for the next generation.\n"
            "1. Agent Counts: procurement (1-5), operations (1-8), engineering (1-3), sales (1-4).\n"
            "2. Machine Speeds: map all 6 machine IDs ('smelter_1','circuit_fab_1','press_1','assembly_1','qc_1','packaging_1') to 'low', 'normal', or 'high'.\n"
            "3. Order Arrival Rate (5.0 to 30.0). Lower = orders arrive faster. WARNING: accepting too "
            "many orders when your pipeline is slow causes catastrophic Late/Missed penalties."
        ),
        "description": (
            "A manufacturing factory grid where agents of five specialised roles "
            "(procurement, operations, engineering, sales, management) coordinate to "
            "purchase raw materials, process them through six machines "
            "(smelter, circuit_fab, press, assembly, qc, packaging), and ship "
            "finished goods against time-limited customer orders."
        ),
        "parameters": {
            "agent_counts.procurement": "integer 1–5 — agents that ferry raw materials from the loading dock",
            "agent_counts.operations": "integer 1–8 — floor workers that move items between machines",
            "agent_counts.engineering": "integer 1–3 — maintenance agents that repair broken machines",
            "agent_counts.sales": "integer 1–4 — agents that deliver finished products against orders",
            "machine_speeds.*": "string low|normal|high — low: slow/cheap/reliable, high: fast/2× power/2.5× fail",
            "order_arrival_rate": "float 5.0–30.0 — avg ticks between order arrivals (lower = more orders)",
        },
        "return_format": """{
  "reasoning": "<1-2 sentence explanation>",
  "agent_counts": {"procurement": <int|omit>, "operations": <int|omit>, "engineering": <int|omit>, "sales": <int|omit>},
  "machine_speeds": {"smelter_1": "<low|normal|high|omit>", "circuit_fab_1": "...", "press_1": "...", "assembly_1": "...", "qc_1": "...", "packaging_1": "..."},
  "order_arrival_rate": <float|null>
}""",
    },

    "supply_chain": {
        "description": (
            "A supply chain network of nodes managing inventory replenishment across "
            "multiple stages to meet stochastic demand while minimising stockout "
            "rate and carrying costs."
        ),
        "parameters": {
            "reorder_threshold": "integer 1–20 — stock level that triggers a reorder",
            "buffer_size": "integer 10–100 — max inventory buffer per node",
            "urgency_multiplier": "float 1.0–3.0 — scaling factor applied to urgent orders",
        },
        "return_format": """{
  "reasoning": "<1-2 sentence explanation>",
  "reorder_threshold": <int|null>,
  "buffer_size": <int|null>,
  "urgency_multiplier": <float|null>
}""",
    },

    "disaster_relief": {
        "description": (
            "Multi-agent disaster relief coordination where teams allocate across "
            "search-and-rescue, medical, and logistics roles to maximise survivors "
            "reached within a fixed time budget, subject to resource constraints."
        ),
        "parameters": {
            "rescue_team_size": "integer 1–5 — number of search-and-rescue agents",
            "medical_team_size": "integer 1–4 — number of medical agents",
            "logistics_agents": "integer 0–3 — number of supply/logistics agents",
            "risk_tolerance": "float 0.0–1.0 — willingness to enter high-risk zones (1=high risk)",
        },
        "return_format": """{
  "reasoning": "<1-2 sentence explanation>",
  "rescue_team_size": <int|null>,
  "medical_team_size": <int|null>,
  "logistics_agents": <int|null>,
  "risk_tolerance": <float|null>
}""",
    },

    "peer_agents": {
        "description": (
            "Competitive multi-agent resource allocation where agents bid for shared "
            "resources. The genome controls cooperation incentives, exploration "
            "behaviour, and inter-agent communication budget."
        ),
        "parameters": {
            "cooperation_weight": "float 0.0–1.0 — weight on cooperative vs competitive payoff (1=fully cooperative)",
            "exploration_rate": "float 0.0–0.5 — probability of choosing a random action",
            "communication_budget": "integer 0–5 — max messages per tick per agent",
        },
        "return_format": """{
  "reasoning": "<1-2 sentence explanation>",
  "cooperation_weight": <float|null>,
  "exploration_rate": <float|null>,
  "communication_budget": <int|null>
}""",
    },
}


def _build_system_prompt(scenario: str) -> str:
    schema = _GENOME_SCHEMAS.get(scenario, _GENOME_SCHEMAS["supply_chain"])
    param_lines = "\n".join(
        f"  • {k}: {v}" for k, v in schema["parameters"].items()
    )
    # Scenario-specific full prompt (spec §4.2) takes precedence when provided;
    # the JSON return contract and loop rules are always appended.
    if schema.get("system_prompt"):
        return (
            f"{schema['system_prompt']}\n\n"
            "RESPONSE FORMAT — reply ONLY with a single JSON object, no markdown fences:\n"
            f"{schema['return_format']}\n\n"
            "RULES:\n"
            "  1. Omit any key (except 'reasoning') you do not want to change.\n"
            "  2. All numeric values must satisfy the stated bounds.\n"
            "  3. Prefer small incremental changes; avoid large jumps.\n"
            "  4. If fitness is improving, continue in the same direction.\n"
            "  5. If stagnating (stagnation_counter > 0), try a different parameter axis.\n"
            "  6. Never return an empty JSON — always include 'reasoning' and at least one parameter."
        )
    return (
        f"You are a meta-optimizer for a multi-agent {scenario.replace('_', ' ')} simulation.\n\n"
        f"SCENARIO: {schema['description']}\n\n"
        "YOUR TASK: Given the current genome and episode performance metrics, propose the "
        "next-generation genome that you believe will improve fitness.\n\n"
        f"TUNABLE PARAMETERS:\n{param_lines}\n\n"
        "RESPONSE FORMAT — reply ONLY with a single JSON object, no markdown fences:\n"
        f"{schema['return_format']}\n\n"
        "RULES:\n"
        "  1. Omit any key (except 'reasoning') you do not want to change.\n"
        "  2. All numeric values must satisfy the stated bounds.\n"
        "  3. Prefer small incremental changes; avoid large jumps.\n"
        "  4. If fitness is improving, continue in the same direction.\n"
        "  5. If stagnating (stagnation_counter > 0), try a different parameter axis.\n"
        "  6. Never return an empty JSON — always include 'reasoning' and at least one parameter."
    )


# ---------------------------------------------------------------------------
# Digest builder
# ---------------------------------------------------------------------------

def build_episode_digest(state: dict, env: Any) -> dict:
    """Compact performance summary from the current episode for the LLM prompt."""
    digest: dict[str, Any] = {
        "generation": state.get("generation", 0),
        "boundary_mode": state.get("boundary_mode", "INTRA"),
        "current_fitness": round(float(state.get("current_fitness", 0.0)), 4),
        "parent_fitness": round(float(state.get("parent_fitness", 0.0)), 4),
        "accepted_fitness": round(float(state.get("accepted_fitness", 0.0)), 4),
        "stagnation_counter": state.get("stagnation_counter", 0),
        "fitness_history": [round(f, 4) for f in state.get("fitness_history", [])[-8:]],
    }

    scenario = state.get("scenario", "manufacturing")

    # Spec §3.1/§4.3: prefer the averaged mini-batch metrics when present (INTER
    # mode) so the digest reflects the 3-seed aggregate, not one lucky episode.
    mb_metrics = state.get("minibatch_metrics") or {}
    if scenario == "manufacturing" and mb_metrics:
        digest["env_metrics"] = {
            "episodes": len(mb_metrics.get("seeds", [])) or 3,
            "ticks_each": mb_metrics.get("ticks"),
            "avg_profit": mb_metrics.get("avg_profit"),
            "avg_revenue": mb_metrics.get("avg_revenue"),
            "avg_penalties": mb_metrics.get("avg_penalties"),
            "avg_throughput": mb_metrics.get("avg_throughput"),
            "orders_fulfilled": mb_metrics.get("avg_orders_fulfilled"),
            "orders_missed": mb_metrics.get("avg_orders_missed"),
            "miss_rate": mb_metrics.get("miss_rate"),
            "machine_utilization": mb_metrics.get("avg_machine_utilization"),
            "agent_idle_ratio": mb_metrics.get("avg_agent_idle_ratio"),
        }
    elif scenario == "manufacturing" and env is not None and hasattr(env, "world"):
        try:
            econ = env.world.economy
            pl = econ.pl
            fulfilled = getattr(econ, "_orders_fulfilled", 0)
            missed = getattr(econ, "_orders_missed", 0)
            digest["env_metrics"] = {
                "tick": env.world.tick,
                "profit": round(float(pl.profit), 2),
                "revenue": round(float(pl.total_revenue), 2),
                "penalties": round(float(pl.penalties), 2),
                "orders_fulfilled": fulfilled,
                "orders_missed": missed,
                "miss_rate": round(missed / max(fulfilled + missed, 1), 3),
                "budget": round(float(env.world.economy.budget), 2),
                "items_shipped": getattr(econ, "_finished_items_shipped", 0),
            }
        except Exception:
            digest["env_metrics"] = {}
    else:
        digest["env_metrics"] = {}

    return digest


def _build_user_prompt(state: dict, env: Any, digest: dict) -> str:
    genome = state.get("genome_config", {})
    clean_genome = {k: v for k, v in genome.items() if not k.startswith("_")}
    genome_str = json.dumps(clean_genome, indent=2) if clean_genome else "(empty — using defaults)"
    digest_str = json.dumps(digest, indent=2)
    return (
        f"CURRENT GENOME:\n{genome_str}\n\n"
        f"EPISODE DIGEST:\n{digest_str}\n\n"
        "Propose the next genome to maximise fitness."
    )


# ---------------------------------------------------------------------------
# LLM query
# ---------------------------------------------------------------------------

async def query_meta_optimizer(state: dict, env: Any) -> dict:
    """
    Query the LLM meta-optimizer and return a parsed genome delta dict.
    Falls back to an empty dict (no-op) on any error so the loop never crashes.
    """
    scenario = state.get("scenario", "manufacturing")
    try:
        client = _get_client()
        digest = build_episode_digest(state, env)
        system_prompt = _build_system_prompt(scenario)
        user_prompt = _build_user_prompt(state, env, digest)

        print(f"[LLM meta_optimizer] querying model for scenario={scenario}")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_completion_tokens=512,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        print(f"[LLM meta_optimizer] raw response length={len(raw)}")

        # Strip markdown fences if model added them anyway
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]).rstrip("`").strip()

        delta = json.loads(raw)
        log.info("Meta-optimizer [%s] proposed: %s", scenario, delta)
        return delta

    except Exception as exc:
        log.warning("Meta-optimizer LLM call failed (%s) — falling back to no-op", exc)
        return {}


# ---------------------------------------------------------------------------
# Delta application
# ---------------------------------------------------------------------------

def apply_genome_delta(genome_config: dict, delta: dict, scenario: str) -> dict:
    """
    Merge a meta-optimizer delta into the current genome_config dict.
    Validates bounds and ignores malformed fields; never raises.
    """
    if not delta:
        return dict(genome_config)

    updated = dict(genome_config)

    if scenario == "manufacturing":
        try:
            from evolution.manufacturing_genome import MIN_AGENT_COUNTS, MAX_AGENT_COUNTS
        except ImportError:
            MIN_AGENT_COUNTS = {}
            MAX_AGENT_COUNTS = {}

        # --- agent_counts ---
        if "agent_counts" in delta and isinstance(delta["agent_counts"], dict):
            counts = dict(updated.get("agent_counts", {}))
            for role, val in delta["agent_counts"].items():
                if val is None:
                    continue
                try:
                    clamped = max(
                        MIN_AGENT_COUNTS.get(role, 0),
                        min(MAX_AGENT_COUNTS.get(role, 5), int(val)),
                    )
                    counts[role] = clamped
                except (TypeError, ValueError):
                    pass
            updated["agent_counts"] = counts

        # --- machine_speeds ---
        if "machine_speeds" in delta and isinstance(delta["machine_speeds"], dict):
            speeds = dict(updated.get("machine_speeds", {}))
            valid = {"low", "normal", "high"}
            for mid, speed in delta["machine_speeds"].items():
                if isinstance(speed, str) and speed.lower() in valid:
                    speeds[mid] = speed.lower()
            updated["machine_speeds"] = speeds

        # --- order_arrival_rate ---
        oar = delta.get("order_arrival_rate")
        if oar is not None:
            try:
                updated["order_arrival_rate"] = max(5.0, min(30.0, float(oar)))
            except (TypeError, ValueError):
                pass

    else:
        # Generic scenarios: copy any non-null, non-reasoning field
        for key, val in delta.items():
            if key == "reasoning" or val is None:
                continue
            updated[key] = val

    # Preserve LLM reasoning for trace display
    reasoning = delta.get("reasoning", "")
    if reasoning:
        updated["_llm_reasoning"] = str(reasoning)

    return updated
