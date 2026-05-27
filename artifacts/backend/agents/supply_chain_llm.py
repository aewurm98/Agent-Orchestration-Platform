"""
Supply Chain v2 LLM layers (spec §3 Edge Agents + §4 Meta-Optimizer / Director).

Two async entry points, each making a real OpenAI call and returning a parsed,
validated decision — or raising a ValidationError when the output violates
the Pydantic schema.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from pydantic import BaseModel, Field, root_validator, parse_obj_as

log = logging.getLogger(__name__)

EDGE_MODEL = "gpt-4o-mini"
DIRECTOR_MODEL = "gpt-4o-mini"


def _client():
    # Reuse the shared OpenAI client wiring
    from agents.meta_optimizer import _get_client
    return _get_client()


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:]).rstrip("`").strip()
    return raw


# ── Pydantic Models for Edge Agent (Spec §3.2) ──────────────────────────────

class EdgeDecision(BaseModel):
    action: str
    target_node_id: Optional[str] = None
    ticks: Optional[int] = None
    discount_percent: Optional[float] = None
    amount: Optional[float] = None

    @root_validator(pre=True)
    def validate_action_fields(cls, values):
        action = values.get("action")
        if action == "reroute":
            if "target_node_id" not in values or not values["target_node_id"]:
                raise ValueError("reroute requires target_node_id")
        elif action == "wait":
            ticks = values.get("ticks")
            if ticks is None or int(ticks) <= 0:
                raise ValueError("wait requires positive ticks")
        elif action == "liquidate_cargo":
            dp = values.get("discount_percent")
            if dp is None or not (0.0 <= float(dp) <= 1.0):
                raise ValueError("liquidate_cargo requires discount_percent in 0.0-1.0")
        elif action == "bribe_node":
            if "target_node_id" not in values or not values["target_node_id"]:
                raise ValueError("bribe_node requires target_node_id")
            amount = values.get("amount")
            if amount is None or float(amount) < 0.0:
                raise ValueError("bribe_node requires non-negative amount")
        elif action == "ignore":
            pass
        elif action is None:
            raise ValueError("action field is required")
        else:
            raise ValueError(f"unknown action {action}")
        return values


# ── Pydantic Models for Director / Meta-Optimizer (Spec §4.1) ────────────────

class DirectorAction(BaseModel):
    action: str
    node_type: Optional[str] = None
    type: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    count: Optional[int] = None
    start_node_id: Optional[str] = None
    group_id: Optional[str] = None
    trait: Optional[str] = None
    new_value: Optional[str] = None
    node_id: Optional[str] = None
    price_mod: Optional[float] = None

    @root_validator(pre=True)
    def validate_director_action(cls, values):
        action = values.get("action")
        if action == "build_infrastructure":
            ntype = values.get("node_type") or values.get("type")
            if ntype not in ("Micro_Fulfillment", "Mega_Warehouse", "Toll_Road"):
                raise ValueError(f"invalid node_type {ntype}")
            x = values.get("x")
            y = values.get("y")
            if x is None or y is None or not (0 <= int(x) < 20) or not (0 <= int(y) < 20):
                raise ValueError(f"invalid coordinates ({x}, {y})")
        elif action == "spawn_fleet":
            count = values.get("count")
            if count is None or int(count) <= 0:
                raise ValueError("spawn_fleet requires positive count")
        elif action == "mutate_persona":
            trait = values.get("trait")
            if trait not in ("Risk_Tolerance", "Greed", "risk_tolerance", "risk"):
                raise ValueError(f"invalid trait {trait}")
            val = values.get("new_value")
            if val not in ("Low", "Medium", "High"):
                raise ValueError(f"invalid new_value {val}")
        elif action == "adjust_incentives":
            mod = values.get("price_mod")
            if mod is None or not (0.5 <= float(mod) <= 3.0):
                raise ValueError("adjust_incentives requires price_mod in 0.5-3.0")
        elif action in ("ignore", ""):
            pass
        elif action is None:
            raise ValueError("action field is required")
        else:
            raise ValueError(f"unknown action {action}")
        return values


# ── Edge agent brain (spec §3.3 / §3.4) ───────────────────────────────────────

_EDGE_SYSTEM = """You are the autonomous navigation and trading brain for Transport Vehicle {agent_id}.
You operate within a 20x20 supply chain grid. 

YOUR GOAL: 
Maximize your individual ledger balance by delivering cargo while minimizing operating costs and delays.

GAME MECHANICS & PHYSICS:
- Upkeep: You pay $5 for every tick you exist. 
- Movement: Highways cost $1/tick. Off-road costs $3/tick.
- Time Penalty: You have encountered an exception. Making this decision will cost you exactly 1 Tick of time and $5 in upkeep.
- Exceptions: Your programmatic autopilot has failed. You must choose a manual override action.

YOUR BEHAVIORAL TRAITS (Assigned by the Meta-Optimizer):
- Risk Tolerance: {trait_risk}
- Greed vs Reliability: {trait_greed}
*You MUST roleplay and base your strategic decisions heavily on these traits.*

YOUR ACTION SPACE (TOOLS):
You must resolve the exception by calling exactly one of these tools:
1. `reroute(target_node_id: str)`
2. `wait(ticks: int)`
3. `liquidate_cargo(discount_percent: float)`
4. `bribe_node(target_node_id: str, amount: float)`
5. `ignore()`

Failure to use a tool, or hallucinating a tool, will result in an automatic 5-tick penalty.

Respond with a single JSON object matching one of these tool calls, with no surrounding text or formatting other than a JSON block:
{{"action": "reroute", "target_node_id": "<node_id>"}}
{{"action": "wait", "ticks": <int>}}
{{"action": "liquidate_cargo", "discount_percent": <float 0.0-1.0>}}
{{"action": "bribe_node", "target_node_id": "<node_id>", "amount": <float>}}
{{"action": "ignore"}}"""


def _edge_user_prompt(ctx: dict) -> str:
    entities = "\n".join(f"  - {e}" for e in ctx.get("local_entities", [])) or "  (none)"
    return (
        f"CURRENT STATUS:\n"
        f"- Current Tick: {ctx['tick']}\n"
        f"- Grid Position: {tuple(ctx['pos'])}\n"
        f"- Ledger Balance: ${ctx['ledger']}\n"
        f"- Cargo: {ctx['cargo']}/50 units (Health: {ctx['cargo_health']}%)\n"
        f"- Intended Destination: {ctx['target']}\n\n"
        f"🚨 EXCEPTION TRIGGERED: {ctx['exception_type']}\n{ctx['exception_detail']}\n\n"
        f"LOCAL RADAR (Entities within 5 cells):\n{entities}\n\n"
        f"TASK:\n"
        f"Analyze the exception, review your local radar, apply your behavioral traits, and execute exactly ONE tool call."
    )


async def resolve_edge_exception(ctx: dict) -> Optional[dict]:
    """Return one validated override decision, or None on failure."""
    try:
        client = _client()
        system = _EDGE_SYSTEM.format(
            agent_id=ctx["agent_id"],
            trait_risk=ctx.get("risk", "Medium"),
            trait_greed=ctx.get("greed", "Medium"),
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
        parsed_json = json.loads(raw)
        validated = EdgeDecision.parse_obj(parsed_json)
        return validated.dict(exclude_none=True)
    except Exception as exc:
        log.warning("edge LLM failed or validation error (%s)", exc)
        raise exc


# ── Director / Meta-Optimizer (spec §4.2 / §4.3) ──────────────────────────────

_DIRECTOR_SYSTEM = """You are the Meta-Optimizer, the global orchestrator of a real-time, 20x20 grid-based supply chain simulation.
The simulation is currently PAUSED. You must analyze the global digest and execute structural changes.

YOUR OBJECTIVE:
Maximize the Global Liquidity Score (GLS) over the 500-tick episode.
GLS = Total Fulfullment Revenue - (CapEx + OpEx + Penalties)

GAME MECHANICS & PHYSICS:
1. The Environment: A 20x20 continuous grid. Moving across highways costs $1/tick. Off-road terrain costs $3/tick.
2. Nodes (Fixed & Mutable):
   - Suppliers: Generate raw cargo. (Fixed)
   - Warehouses: Buffer inventory with strict capacity limits. Charge $2/tick holding fees. (Mutable: You can build more).
   - Demand Zones: Consume inventory. Unfulfilled demand generates stacking cash penalties. (Fixed)
3. Edge Agents (Trucks):
   - Capacity: 50 units. 
   - Upkeep: $5/tick just to exist, plus movement costs.
   - Behavior: Agents operate on programmatic A* routing but utilize an LLM brain during exceptions. Their decisions are governed by their Persona Traits.

YOUR ACTION SPACE (TOOLS):
You may call one or more of the following tools to evolve the simulation:
1. `build_infrastructure(type: str, x: int, y: int)`
2. `mutate_persona(group_id: str, trait: str, new_value: str)`
3. `spawn_fleet(count: int, start_node_id: str)`
4. `adjust_incentives(node_id: str, price_mod: float)`

INSTRUCTIONS:
1. Review the CURRENT GLOBAL DIGEST below.
2. Identify gridlock, stockouts, or capital inefficiencies.
3. Output your strategy strictly by invoking the provided JSON tools. You may invoke multiple tools. If the network is healthy, you may choose to output no tools and save your capital.

Respond with a JSON array containing zero or more tool calls (with no surrounding text or formatting other than a JSON block):
[
  {{"action": "build_infrastructure", "node_type": "Micro_Fulfillment|Mega_Warehouse|Toll_Road", "x": <int>, "y": <int>}},
  {{"action": "mutate_persona", "group_id": "<truck_id>|all", "trait": "Risk_Tolerance|Greed", "new_value": "Low|Medium|High"}},
  {{"action": "spawn_fleet", "count": <int>, "start_node_id": "<node_id>"}},
  {{"action": "adjust_incentives", "node_id": "<node_id>", "price_mod": <float>}}
]"""


def _director_user_prompt(digest: dict) -> str:
    alerts = "\n".join(f"  - {a}" for a in digest.get("alerts", []))
    personas = "\n".join(f"  - {p['id']}: risk={p['risk']}, greed={p['greed']}" for p in digest.get("fleet_personas", []))
    return (
        f"CURRENT GLOBAL DIGEST:\n"
        f"- Current Tick: {digest['tick']} / 500\n"
        f"- GLS: ${digest['gls']} (Trend: {digest['gls_trend_pct']}% since last intervention)\n"
        f"- Active Fleet: {digest['fleet_count']} trucks\n"
        f"- Available Capital: ${digest['capital']}\n\n"
        f"SYSTEM BOTTLENECKS & ALERTS:\n{alerts}\n\n"
        f"FLEET PERSONA STATES:\n{personas}\n\n"
        f"TASK:\n"
        f"Deploy capital, mutate agent psychology, or adjust economic incentives to clear bottlenecks and maximize GLS. Output your structured JSON tool calls now."
    )


async def run_director(digest: dict) -> Optional[list[dict]]:
    """Return a validated list of director tool calls, or None on failure."""
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
        parsed_json = json.loads(raw)
        validated_list = parse_obj_as(list[DirectorAction], parsed_json)
        return [v.dict(exclude_none=True) for v in validated_list]
    except Exception as exc:
        log.warning("director LLM failed or validation error (%s)", exc)
        raise exc
