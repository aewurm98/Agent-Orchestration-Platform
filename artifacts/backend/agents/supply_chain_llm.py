"""
Supply Chain v2 LLM layers (spec §3 Edge Agents + §4 Meta-Optimizer / Director).

Two async entry points, each making a real OpenAI call and returning a parsed,
validated decision — or None on any failure so the caller falls back to the
deterministic heuristics baked into SupplyChainEnv.  This keeps the simulation
fully runnable without API credentials.

  resolve_edge_exception(context) -> dict | None   # one truck's override action
  run_director(digest)            -> list[dict] | None  # global tool calls
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

EDGE_MODEL = "gpt-4o-mini"
DIRECTOR_MODEL = "gpt-4o-mini"

_VALID_EDGE_ACTIONS = {"reroute", "wait", "liquidate_cargo", "bribe_node", "ignore"}
_VALID_DIRECTOR_ACTIONS = {"build_infrastructure", "mutate_persona", "spawn_fleet", "adjust_incentives"}


def _client():
    # Reuse the shared OpenAI client wiring (handles Replit AI integration too).
    from agents.meta_optimizer import _get_client
    return _get_client()


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:]).rstrip("`").strip()
    return raw


# ── Edge agent brain (spec §3.3 / §3.4) ───────────────────────────────────────

_EDGE_SYSTEM = """You are the autonomous navigation and trading brain for Transport Vehicle {agent_id}.
You operate within a 20x20 supply chain grid.

YOUR GOAL:
Maximize your individual ledger balance by delivering cargo while minimizing operating costs and delays.

GAME MECHANICS & PHYSICS:
- Upkeep: You pay $5 for every tick you exist.
- Movement: Highways cost $1/tick. Off-road costs $3/tick.
- Time Penalty: This decision costs you exactly 1 Tick of time and $5 in upkeep.
- Exceptions: Your programmatic autopilot has failed. You must choose a manual override action.

YOUR BEHAVIORAL TRAITS (Assigned by the Meta-Optimizer):
- Risk Tolerance: {risk}
- Greed vs Reliability: {greed}
You MUST base your strategic decisions heavily on these traits.

YOUR ACTION SPACE — resolve the exception by calling exactly ONE tool. Reply with a single JSON object, no markdown:
{{"action": "reroute", "target_node_id": "<node>"}}
{{"action": "wait", "ticks": <int>}}
{{"action": "liquidate_cargo", "discount_percent": <0.0-1.0>}}
{{"action": "bribe_node", "target_node_id": "<node>", "amount": <float>}}
{{"action": "ignore"}}
Failure to use a valid tool results in a penalty."""


def _edge_user_prompt(ctx: dict) -> str:
    entities = "\n".join(f"  - {e}" for e in ctx.get("local_entities", [])) or "  (none)"
    return (
        f"CURRENT STATUS:\n"
        f"- Tick: {ctx['tick']}\n"
        f"- Grid Position: {tuple(ctx['pos'])}\n"
        f"- Ledger Balance: ${ctx['ledger']}\n"
        f"- Cargo: {ctx['cargo']}/50 units (Health: {ctx['cargo_health']}%)\n"
        f"- Intended Destination: {ctx['target']}\n\n"
        f"\U0001F6A8 EXCEPTION TRIGGERED: {ctx['exception_type']}\n{ctx['exception_detail']}\n\n"
        f"LOCAL RADAR (entities within 5 cells):\n{entities}\n\n"
        f"Known node ids: {ctx.get('nodes')}\n\n"
        "Analyze the exception, apply your behavioral traits, and execute exactly ONE tool call as JSON."
    )


def _validate_edge(decision: dict, ctx: dict) -> Optional[dict]:
    if not isinstance(decision, dict):
        return None
    action = decision.get("action")
    if action not in _VALID_EDGE_ACTIONS:
        return None
    nodes = set(ctx.get("nodes", []))
    if action == "reroute" and decision.get("target_node_id") not in nodes:
        return None
    if action == "bribe_node" and decision.get("target_node_id") not in nodes:
        return None
    return decision


async def resolve_edge_exception(ctx: dict) -> Optional[dict]:
    """Return one validated override decision, or None to use the fallback."""
    try:
        client = _client()
        system = _EDGE_SYSTEM.format(
            agent_id=ctx["agent_id"], risk=ctx.get("risk", "Medium"), greed=ctx.get("greed", "Medium"),
        )
        resp = await client.chat.completions.create(
            model=EDGE_MODEL,
            max_completion_tokens=200,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": _edge_user_prompt(ctx)},
            ],
        )
        raw = _strip_fences(resp.choices[0].message.content or "")
        return _validate_edge(json.loads(raw), ctx)
    except Exception as exc:
        log.warning("edge LLM failed (%s) — fallback", exc)
        return None


# ── Director / Meta-Optimizer (spec §4.2 / §4.3) ──────────────────────────────

_DIRECTOR_SYSTEM = """You are the Meta-Optimizer, the global orchestrator of a real-time, 20x20 grid-based supply chain simulation.
The simulation is currently PAUSED. Analyze the global digest and execute structural changes.

YOUR OBJECTIVE:
Maximize the Global Liquidity Score (GLS) over the 500-tick episode.
GLS = Total Revenue - (CapEx + OpEx + Penalties)

GAME MECHANICS:
- 20x20 grid. Highways cost $1/tick to traverse, off-road $3/tick.
- Suppliers generate raw cargo (fixed). Demand Zones consume inventory; unfulfilled demand stacks $50/tick penalties (fixed).
- Warehouses buffer inventory with strict capacity and $2/tick holding fees (you can build more).
- Trucks: 50-unit capacity, $5/tick upkeep, cargo spoils 1%/tick. Personas govern their exception decisions.

YOUR ACTION SPACE — reply with a JSON array of zero or more tool calls (no markdown):
[{"action":"build_infrastructure","node_type":"Micro_Fulfillment|Mega_Warehouse|Toll_Road","x":<int 0-19>,"y":<int 0-19>},
 {"action":"spawn_fleet","count":<int>,"start_node_id":"<node>"},
 {"action":"mutate_persona","group_id":"all|<truck_id>","trait":"Risk_Tolerance|Greed","new_value":"Low|Medium|High"},
 {"action":"adjust_incentives","node_id":"<node>","price_mod":<float 0.5-3.0>}]
Costs: Micro_Fulfillment $5000 (cap 100), Mega_Warehouse $20000 (cap 500), Toll_Road $1000, each truck $2000.
If the network is healthy you may return an empty array [] to conserve capital."""


def _director_user_prompt(digest: dict) -> str:
    alerts = "\n".join(f"  - {a}" for a in digest.get("alerts", []))
    personas = ", ".join(f"{p['id']}(R:{p['risk']}/G:{p['greed']})" for p in digest.get("fleet_personas", []))
    node_ids = [n["id"] for n in digest.get("nodes", [])]
    return (
        f"CURRENT GLOBAL DIGEST:\n"
        f"- Tick: {digest['tick']} / 500\n"
        f"- GLS: ${digest['gls']} (trend {digest['gls_trend_pct']}% since last intervention)\n"
        f"- Active Fleet: {digest['fleet_count']} trucks\n"
        f"- Available Capital: ${digest['capital']}\n\n"
        f"SYSTEM BOTTLENECKS & ALERTS:\n{alerts}\n\n"
        f"FLEET PERSONAS: {personas}\n"
        f"NODE IDS: {node_ids}\n\n"
        "Deploy capital, mutate psychology, or adjust incentives to clear bottlenecks and maximize GLS. "
        "Output your JSON array of tool calls now."
    )


def _validate_director(actions: Any) -> Optional[list[dict]]:
    if not isinstance(actions, list):
        return None
    valid = [a for a in actions if isinstance(a, dict) and a.get("action") in _VALID_DIRECTOR_ACTIONS]
    return valid


async def run_director(digest: dict) -> Optional[list[dict]]:
    """Return a validated list of director tool calls, or None to use the fallback."""
    try:
        client = _client()
        resp = await client.chat.completions.create(
            model=DIRECTOR_MODEL,
            max_completion_tokens=400,
            messages=[
                {"role": "system", "content": _DIRECTOR_SYSTEM},
                {"role": "user", "content": _director_user_prompt(digest)},
            ],
        )
        raw = _strip_fences(resp.choices[0].message.content or "")
        return _validate_director(json.loads(raw))
    except Exception as exc:
        log.warning("director LLM failed (%s) — fallback", exc)
        return None
