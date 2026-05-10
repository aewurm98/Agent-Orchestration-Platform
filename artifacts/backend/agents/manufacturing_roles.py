"""
Manufacturing agent roles: LLM-powered agents for both legacy (3-stage) and v2 (grid) environments.

Workers see only their own stage (legacy) or their visibility radius (v2).
Planners/Management agents have broader context.

Module-level singletons hold env reference, message board, and planner query cache.
Call set_active_env(env) for legacy mode, set_active_env_v2(env) for grid mode.

Edge credit assignment:
  _pending_message_log maps edge_key → list of (sent_tick, profit_at_send, shipped_at_send).
  sweep_edge_scores(tick) is called every 5 ticks to bump/drop _edge_scores.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional, TYPE_CHECKING

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from game_envs.manufacturing_v2.env import ManufacturingEnvV2

log = logging.getLogger(__name__)

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        openai_key = os.environ.get("OPENAI_API_KEY")
        integration_base = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
        integration_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        if openai_key:
            _openai_client = AsyncOpenAI(api_key=openai_key)
        elif integration_base and integration_key:
            _openai_client = AsyncOpenAI(
                base_url=integration_base,
                api_key=integration_key,
            )
        else:
            raise RuntimeError(
                "No OpenAI credentials found. "
                "Set OPENAI_API_KEY or configure the Replit OpenAI AI Integration."
            )
    return _openai_client

_env = None
_env_v2: Optional["ManufacturingEnvV2"] = None

_message_board: dict[str, list[dict]] = {}
_planner_cache: dict[str, dict] = {}
_worker_state_cache: dict[str, dict] = {}

# Edge credit assignment state
# Maps edge_key (e.g. "planner_1->worker_raw_materials") to list of
# (sent_tick, profit_at_send, shipped_at_send) tuples.
_pending_message_log: dict[str, list[tuple[int, float, int]]] = {}

# Module-level edge scores — updated by sweep_edge_scores(), read by orchestrator
_edge_scores: dict[str, float] = {}


def set_active_env(env) -> None:
    global _env, _openai_client
    _env = env
    _openai_client = None
    _message_board.clear()
    _planner_cache.clear()
    _worker_state_cache.clear()


def set_active_env_v2(env: "ManufacturingEnvV2") -> None:
    global _env_v2, _openai_client
    _env_v2 = env
    _openai_client = None
    _message_board.clear()
    _planner_cache.clear()
    _worker_state_cache.clear()
    _pending_message_log.clear()


def _current_economy_snapshot() -> tuple[float, int, float]:
    """Return (current_profit, shipped_count, cumulative_penalties) from the active v2 env."""
    if _env_v2 is not None:
        econ = _env_v2.world.economy
        return econ.pl.profit, econ._finished_items_shipped, econ.pl.penalties
    return 0.0, 0, 0.0


def _post_to_inbox(agent_id: str, message: dict) -> None:
    """Post a message to an agent's inbox and record it in the edge credit log."""
    _message_board.setdefault(agent_id, []).append(message)

    sender = message.get("from")
    if sender and _env_v2 is not None:
        edge_key = f"{sender}->{agent_id}"
        tick = _env_v2.world.tick
        profit, shipped, penalties = _current_economy_snapshot()
        # Tuple: (sent_tick, profit_at_send, shipped_at_send, penalty_at_send)
        _pending_message_log.setdefault(edge_key, []).append((tick, profit, shipped, penalties))


def _read_inbox(agent_id: str) -> list[dict]:
    msgs = _message_board.get(agent_id, [])
    _message_board[agent_id] = []
    return msgs


def sweep_edge_scores(tick: int) -> None:
    """
    Credit assignment sweep — called every 5 ticks.

    For each pending message log entry (sent_tick, profit_at_send, shipped_at_send,
    penalty_at_send): compare current economy state to the snapshot at send time.

    - If profit grew OR shipped items increased since the message was sent:
      bump A_{u→v} by 0.05 (capped at 1.0) — message preceded a good outcome.
    - If cumulative penalties increased since the message was sent:
      drop A_{u→v} by 0.05 (floored at 0.0) — message was active during a penalty.

    Entries older than 5 ticks are consumed (regardless of outcome) and removed.
    """
    if _env_v2 is None:
        return

    current_profit, current_shipped, current_penalties = _current_economy_snapshot()
    stale_threshold = 5

    for edge_key in list(_pending_message_log.keys()):
        remaining = []
        for entry in _pending_message_log[edge_key]:
            # Support both 3-tuple (legacy) and 4-tuple (with penalty)
            if len(entry) == 4:
                sent_tick, profit_at_send, shipped_at_send, penalty_at_send = entry
            else:
                sent_tick, profit_at_send, shipped_at_send = entry
                penalty_at_send = 0.0

            age = tick - sent_tick
            if age < stale_threshold:
                remaining.append(entry)
                continue

            # Evaluate outcome over the 5-tick window
            profit_grew = current_profit > profit_at_send
            shipped_grew = current_shipped > shipped_at_send
            penalty_increased = current_penalties > penalty_at_send

            current_score = _edge_scores.get(edge_key, 0.5)
            if profit_grew or shipped_grew:
                new_score = min(1.0, current_score + 0.05)
            elif penalty_increased:
                new_score = max(0.0, current_score - 0.05)
            else:
                new_score = current_score
            _edge_scores[edge_key] = round(new_score, 4)

        _pending_message_log[edge_key] = remaining


def init_edge_scores(scores: dict[str, float]) -> None:
    """Seed module-level edge scores from orchestrator state."""
    _edge_scores.clear()
    _edge_scores.update(scores)


ROLE_INCENTIVES = {
    "procurement": (
        "You are a Procurement agent on a factory floor grid. "
        "Your goal: purchase raw materials (raw_ore, raw_silicon) from the Loading Dock, "
        "carry them to machines that need inputs, and manage budget efficiently. "
        "Monitor which machines need inputs and prioritize accordingly. "
        "Available actions: purchase, pickup, drop, deliver_to_machine, go_to, wait."
    ),
    "operations": (
        "You are an Operations/Floor Worker on a factory floor grid. "
        "Your goal: move items between machines, load machines with inputs, unload finished outputs, "
        "and keep production flowing. Pick up items and deliver them to the right machines. "
        "Available actions: pickup, drop, load_machine, unload_machine, start_machine, go_to, pickup_nearest, deliver_to_machine, wait."
    ),
    "engineering": (
        "You are an Engineering/Maintenance agent on a factory floor grid. "
        "Your goal: repair broken machines immediately, diagnose machines at risk of failure, "
        "and optimize machine speed settings based on production bottlenecks. "
        "Available actions: repair, set_speed, diagnose, go_to, wait."
    ),
    "sales": (
        "You are a Sales agent on a factory floor grid. "
        "Your goal: collect finished products from the Packaging machine output, "
        "carry them to the Shipping Dock, and sell them. Check orders regularly. "
        "Available actions: sell, pickup, drop, pickup_nearest, go_to, check_orders, wait."
    ),
    "management": (
        "You are a Management agent with full map visibility. "
        "Your goal: make strategic decisions — hire agents when bottlenecked, "
        "fire idle agents to save budget, assign tasks, view financials, "
        "and optimize machine speeds at key bottlenecks. "
        "You can also call update_policy to change the floor-worker scripted rules in real time — "
        "for example lowering the replenishment_urgency_threshold when buffers run dry often, "
        "or raising management_hire_ops_budget_floor to be more conservative about hiring. "
        "Valid rules for update_policy: replenishment_urgency_threshold (int, default 3), "
        "operations_pickup_radius (int or null), engineering_idle_repair_trigger (int, default 0), "
        "management_hire_engineer_threshold (int, default 1), management_hire_ops_budget_floor (int, default 300). "
        "Available actions: hire, fire, assign_task, view_financials, set_budget_allocation, update_policy, wait."
    ),
}

_RESPONSE_SCHEMA = """
Respond with a single JSON object:
{
  "action": "<action_name>",
  "params": { ... },
  "reasoning": "<one or two sentence explanation>"
}
Only use actions from the provided list. Do not add extra keys.
"""


async def _call_llm_v2(
    agent_id: str,
    role: str,
    observation: dict,
    available_actions: list[str],
) -> dict:
    incentive = ROLE_INCENTIVES.get(role, "You are a factory agent. Act to maximize production efficiency.")
    if role == "management":
        action_list = list(available_actions[:20]) + ["update_policy"]
    else:
        action_list = list(available_actions[:20])
    skill_list = json.dumps(action_list)
    system_prompt = (
        f"{incentive}\n\n"
        f"Available actions: {skill_list}\n\n"
        f"{_RESPONSE_SCHEMA}"
    )
    obs_summary = {
        "tick": observation.get("tick"),
        "budget": observation.get("budget"),
        "position": {"row": observation.get("agent", {}).get("row"), "col": observation.get("agent", {}).get("col")},
        "inventory": [i.get("type") for i in observation.get("inventory", [])],
        "visible_machines": {
            mid: {
                "type": m.get("type"),
                "state": m.get("state"),
                "row": m.get("row"),
                "col": m.get("col"),
                "input_queue_len": m.get("input_queue_len"),
                "output_queue_len": m.get("output_queue_len"),
            }
            for mid, m in (observation.get("visible_machines") or {}).items()
        },
        "visible_items": [
            {"type": i.get("type"), "row": i.get("row"), "col": i.get("col")}
            for i in (observation.get("visible_items") or [])[:5]
        ],
        "active_orders": [
            {"id": o.get("id"), "remaining": o.get("remaining"), "deadline_tick": o.get("deadline_tick")}
            for o in (observation.get("active_orders") or [])[:3]
        ],
        "grid_cell": observation.get("grid_cell"),
        "messages": observation.get("messages", [])[-2:],
    }
    user_message = f"Current observation (tick {obs_summary['tick']}):\n{json.dumps(obs_summary, indent=2)}"

    try:
        response = await _get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=384,
            temperature=0.5,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        return parsed
    except Exception as exc:
        log.error("LLM call failed for %s (%s): %s", agent_id, role, exc)
        return {
            "action": "wait",
            "params": {},
            "reasoning": f"LLM call failed: {exc}",
        }


async def run_manufacturing_v2_step(generation: int, env: "ManufacturingEnvV2") -> list[dict]:
    """
    Run one LLM reasoning step for a subset of agents (not all — too many API calls).
    Returns trace dicts for socket.io emission.

    Every 5 ticks, also runs sweep_edge_scores() to update credit assignment.
    """
    if env is None:
        return []

    traces: list[dict] = []
    now = time.time()

    tick = env.world.tick
    if tick > 0 and tick % 5 == 0:
        sweep_edge_scores(tick)

    LLM_AGENTS_PER_STEP = ["management_1", "procurement_1"]

    for agent_id in LLM_AGENTS_PER_STEP:
        agent = env.world.agents.get(agent_id)
        if agent is None:
            continue
        if agent.is_standby:
            continue

        observation = env.get_observation(agent_id)
        available_actions = env.get_action_space(agent_id)

        parsed = await _call_llm_v2(
            agent_id=agent_id,
            role=agent.role.value,
            observation=observation,
            available_actions=available_actions,
        )

        action = parsed.get("action", "wait")
        params = parsed.get("params", {})
        reasoning = parsed.get("reasoning", "")

        if action == "update_policy" and agent.role.value == "management":
            from agents.manufacturing_policies import apply_policy_override
            rule = params.get("rule", "")
            value = params.get("value")
            ok, msg = apply_policy_override(rule, value)
            # Post broadcast to all workers so edges from management_1 are tracked
            for target_id in list(_env_v2.world.agents.keys()) if _env_v2 else []:
                if target_id != agent_id:
                    _post_to_inbox(target_id, {
                        "type": "policy_broadcast",
                        "from": agent_id,
                        "rule": rule,
                        "value": value,
                        "timestamp": now,
                    })
            traces.append({
                "run_id": f"gen_{generation}",
                "role": agent.role.value,
                "content": f"[{agent_id}] update_policy({params}) → {msg}",
                "timestamp": now,
                "agent_name": agent_id,
                "agent_role": agent.role.value,
                "action": action,
                "parameters": params,
                "reasoning": reasoning,
            })
            continue

        if action not in ("wait", "idle", "update_policy"):
            agent.action_buffer.insert(0, {"type": action, "params": params})
            # Record the directed message edge for credit assignment
            target = params.get("target_agent") or params.get("agent_id")
            if target and target in (env.world.agents if env else {}):
                _post_to_inbox(target, {
                    "type": action,
                    "from": agent_id,
                    "params": params,
                    "timestamp": now,
                })

        traces.append({
            "run_id": f"gen_{generation}",
            "role": agent.role.value,
            "content": f"[{agent_id}] {action}({params})",
            "timestamp": now,
            "agent_name": agent_id,
            "agent_role": agent.role.value,
            "action": action,
            "parameters": params,
            "reasoning": reasoning,
        })

    return traces


WORKER_INCENTIVE = (
    "You are a factory floor Worker. "
    "Your goals: maximize utilization of your stage, minimize idle ticks, "
    "flag problems early by reporting issues, and request replenishment before your input buffer runs dry. "
    "Never process more than your throughput capacity allows. "
    "If blocked, idle() and report_issue."
)

PLANNER_INCENTIVE = (
    "You are a factory floor Planner/Manager overseeing the full three-stage pipeline. "
    "Your goals: balance WIP across all three stages, prevent starvation (empty input buffers) "
    "and overflow (output buffers piling up), minimize end-to-end cycle time, "
    "and approve finished goods release when the output buffer has sufficient stock. "
    "You do NOT automatically have global state — query_pipeline_status() to get it. "
    "Act on inbox messages from Workers promptly."
)

WORKER_SKILLS = [
    {"name": "process_batch", "description": "Consume from input buffer, produce to output buffer.", "parameters": {"quantity": "integer"}},
    {"name": "inspect_input", "description": "Sample-check incoming materials and report quality status.", "parameters": {}},
    {"name": "request_replenishment", "description": "Send a replenishment request upstream or to the Planner.", "parameters": {"urgency": "string — low | medium | high"}},
    {"name": "report_issue", "description": "Send a flagged problem to the Planner inbox.", "parameters": {"description": "string"}},
    {"name": "rework_output", "description": "Reprocess defective units sitting in the output buffer.", "parameters": {"quantity": "integer"}},
    {"name": "idle", "description": "Do nothing this tick.", "parameters": {}},
]

PLANNER_SKILLS = [
    {"name": "query_pipeline_status", "description": "Fetch live WIP, throughput, and buffer levels for all three stages.", "parameters": {}},
    {"name": "query_worker_status", "description": "Fetch current state and last action of a specific worker.", "parameters": {"worker_id": "string"}},
    {"name": "reallocate_materials", "description": "Move raw material allocation between stages.", "parameters": {"from_stage": "string", "to_stage": "string", "quantity": "integer"}},
    {"name": "set_production_target", "description": "Update the batch size target for a stage.", "parameters": {"stage": "string", "target_units": "integer"}},
    {"name": "dispatch_order", "description": "Send a direct instruction message to a Worker.", "parameters": {"worker_id": "string", "instruction": "string"}},
    {"name": "broadcast_to_stage", "description": "Send a message to all Workers at a given stage.", "parameters": {"stage": "string", "message": "string"}},
    {"name": "approve_release", "description": "Authorize finished goods to leave the output buffer.", "parameters": {"quantity": "integer"}},
    {"name": "escalate", "description": "Surface an unresolvable issue to the system log.", "parameters": {"description": "string"}},
    {
        "name": "update_policy",
        "description": (
            "Modify a scripted floor-worker policy rule in real time. "
            "Valid rules: replenishment_urgency_threshold (int), operations_pickup_radius (int|null), "
            "engineering_idle_repair_trigger (int), management_hire_engineer_threshold (int), "
            "management_hire_ops_budget_floor (int)."
        ),
        "parameters": {"rule": "string", "value": "any"},
    },
]

_LEGACY_RESPONSE_SCHEMA = """
Respond with a single JSON object:
{
  "action": "<skill_name>",
  "parameters": { ... },
  "reasoning": "<one or two sentence explanation>",
  "message": "<optional string for communication skills>"
}
Only use skills from the provided list. Do not add extra keys.
"""

_VALID_WORKER_ACTIONS: frozenset[str] = frozenset(s["name"] for s in WORKER_SKILLS)
_VALID_PLANNER_ACTIONS: frozenset[str] = frozenset(s["name"] for s in PLANNER_SKILLS)


def _build_worker_context(agent_id: str, stage_name: str) -> dict:
    if _env is None:
        return {}
    snap = _env.get_stage_snapshot(stage_name)
    inbox = _read_inbox(agent_id)
    return {
        "stage": stage_name,
        "input_buffer_depth": snap.get("input_buffer", 0),
        "material_type": snap.get("material_type", "unknown"),
        "worker_state": snap.get("worker_state", "idle"),
        "output_buffer_depth": snap.get("output_buffer", 0),
        "throughput_capacity": snap.get("throughput_capacity", 0),
        "target_units_per_tick": snap.get("target_units", 0),
        "inbox": inbox,
    }


def _build_planner_context(agent_id: str) -> dict:
    if _env is None:
        return {}
    inbox = _read_inbox(agent_id)
    last_query = _planner_cache.pop(agent_id, {})
    targets = {}
    for sname in ["raw_materials", "intermediates", "finished_product"]:
        snap = _env.get_stage_snapshot(sname)
        targets[sname] = snap.get("target_units", 0)
    return {
        "inbox": inbox,
        "last_query_results": last_query if last_query else "(no query results yet — use query_pipeline_status to get pipeline data)",
        "current_production_targets": targets,
    }


def _dispatch_worker_skill(agent_id: str, stage_name: str, action: str, parameters: dict) -> str:
    if _env is None:
        return "env not initialised"
    if action not in _VALID_WORKER_ACTIONS:
        log.warning("Worker %s chose unknown action %r — falling back to idle", agent_id, action)
        return json.dumps({"ok": False, "error": f"unknown action '{action}'"})
    if action == "process_batch":
        result = _env.process_batch(stage_name, parameters.get("quantity", 10))
        return json.dumps(result)
    elif action == "inspect_input":
        result = _env.inspect_input(stage_name)
        return json.dumps(result)
    elif action == "request_replenishment":
        urgency = parameters.get("urgency", "medium")
        _post_to_inbox("planner_1", {"type": "replenishment_request", "from": agent_id, "stage": stage_name, "urgency": urgency, "timestamp": time.time()})
        return f"Replenishment request ({urgency}) sent to Planner."
    elif action == "report_issue":
        desc = parameters.get("description", "unspecified issue")
        _post_to_inbox("planner_1", {"type": "issue_report", "from": agent_id, "stage": stage_name, "description": desc, "timestamp": time.time()})
        return f"Issue reported to Planner: {desc}"
    elif action == "rework_output":
        result = _env.rework_output(stage_name, parameters.get("quantity", 5))
        return json.dumps(result)
    elif action == "idle":
        snap = _env.get_stage_snapshot(stage_name)
        _worker_state_cache[agent_id] = {"stage": stage_name, "state": snap, "last_action": "idle"}
        return "Agent idle this tick."
    return f"Unknown worker skill: {action}"


def _dispatch_planner_skill(agent_id: str, action: str, parameters: dict) -> str:
    if action == "update_policy":
        from agents.manufacturing_policies import apply_policy_override
        rule = parameters.get("rule", "")
        value = parameters.get("value")
        ok, msg = apply_policy_override(rule, value)
        log.info("Planner update_policy: %s", msg)
        return msg
    if _env is None:
        return "env not initialised"
    if action not in _VALID_PLANNER_ACTIONS:
        log.warning("Planner %s chose unknown action %r — falling back to query", agent_id, action)
        return json.dumps({"ok": False, "error": f"unknown action '{action}'"})
    if action == "query_pipeline_status":
        result = _env.query_pipeline_status()
        _planner_cache[agent_id] = {"query_pipeline_status": result, "fetched_at": time.time()}
        return "Pipeline status fetched — available in next tick context."
    elif action == "query_worker_status":
        worker_id = parameters.get("worker_id", "")
        stage_name = worker_id.replace("worker_", "")
        live_snap = _env.get_stage_snapshot(stage_name) if _env else {}
        last_action_info = _worker_state_cache.get(worker_id, {})
        result = {"worker_id": worker_id, "live_stage_snapshot": live_snap, "last_action": last_action_info.get("last_action")}
        _planner_cache[agent_id] = {"query_worker_status": result, "fetched_at": time.time()}
        return f"Worker status for {worker_id} fetched."
    elif action == "reallocate_materials":
        result = _env.reallocate_materials(parameters.get("from_stage", ""), parameters.get("to_stage", ""), parameters.get("quantity", 0))
        return json.dumps(result)
    elif action == "set_production_target":
        result = _env.set_production_target(parameters.get("stage", ""), parameters.get("target_units", 10))
        return json.dumps(result)
    elif action == "dispatch_order":
        worker_id = parameters.get("worker_id", "")
        instruction = parameters.get("instruction", "")
        _post_to_inbox(worker_id, {"type": "dispatch_order", "from": agent_id, "instruction": instruction, "timestamp": time.time()})
        return f"Order dispatched to {worker_id}: {instruction}"
    elif action == "broadcast_to_stage":
        stage = parameters.get("stage", "")
        message = parameters.get("message", "")
        _post_to_inbox(f"worker_{stage}", {"type": "broadcast", "from": agent_id, "stage": stage, "message": message, "timestamp": time.time()})
        return f"Broadcast to {stage}: {message}"
    elif action == "approve_release":
        result = _env.approve_release(parameters.get("quantity", 0))
        return json.dumps(result)
    elif action == "escalate":
        desc = parameters.get("description", "unspecified")
        log.warning("ESCALATION from planner: %s", desc)
        return f"Escalated: {desc}"
    return f"Unknown planner skill: {action}"


async def _call_llm(role_label: str, incentive: str, skills: list[dict], context: dict) -> dict:
    skill_list = json.dumps(skills, indent=2)
    system_prompt = f"{incentive}\n\nAvailable skills:\n{skill_list}\n\n{_LEGACY_RESPONSE_SCHEMA}"
    user_message = f"Current context (this tick):\n{json.dumps(context, indent=2)}"
    try:
        response = await _get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=512,
            temperature=0.7,
        )
        raw = response.choices[0].message.content or "{}"
        return json.loads(raw)
    except Exception as exc:
        log.error("LLM call failed for %s: %s", role_label, exc)
        safe_action = "query_pipeline_status" if "Planner" in role_label else "idle"
        return {"action": safe_action, "parameters": {}, "reasoning": f"LLM call failed: {exc}"}


WORKER_AGENTS = [
    {"agent_id": "worker_raw_materials",  "role": "worker", "stage": "raw_materials"},
    {"agent_id": "worker_intermediates",  "role": "worker", "stage": "intermediates"},
    {"agent_id": "worker_finished_product", "role": "worker", "stage": "finished_product"},
]
PLANNER_AGENTS = [
    {"agent_id": "planner_1", "role": "planner"},
]
ALL_MANUFACTURING_AGENT_CONFIGS = WORKER_AGENTS + PLANNER_AGENTS


async def run_manufacturing_step(generation: int) -> list[dict]:
    """Legacy: Run one tick of manufacturing agents via LLM calls (3-stage pipeline)."""
    if _env is None:
        return []

    traces: list[dict] = []
    now = time.time()

    for cfg in WORKER_AGENTS:
        agent_id = cfg["agent_id"]
        stage = cfg["stage"]
        context = _build_worker_context(agent_id, stage)
        parsed = await _call_llm(role_label=f"Worker/{stage}", incentive=WORKER_INCENTIVE, skills=WORKER_SKILLS, context=context)
        action = parsed.get("action", "idle")
        parameters = parsed.get("parameters", {})
        reasoning = parsed.get("reasoning", "")
        skill_result = _dispatch_worker_skill(agent_id, stage, action, parameters)
        _worker_state_cache[agent_id] = {"stage": stage, "last_action": action, "last_parameters": parameters, "skill_result": skill_result}
        traces.append({
            "run_id": f"gen_{generation}",
            "role": "worker",
            "content": f"[{stage}] {action}({parameters}) → {skill_result}",
            "timestamp": now,
            "agent_name": agent_id,
            "agent_role": "worker",
            "stage": stage,
            "action": action,
            "parameters": parameters,
            "reasoning": reasoning,
        })

    for cfg in PLANNER_AGENTS:
        agent_id = cfg["agent_id"]
        context = _build_planner_context(agent_id)
        parsed = await _call_llm(role_label="Planner", incentive=PLANNER_INCENTIVE, skills=PLANNER_SKILLS, context=context)
        action = parsed.get("action", "query_pipeline_status")
        parameters = parsed.get("parameters", {})
        reasoning = parsed.get("reasoning", "")
        skill_result = _dispatch_planner_skill(agent_id, action, parameters)
        traces.append({
            "run_id": f"gen_{generation}",
            "role": "planner",
            "content": f"Planner {action}({parameters}) → {skill_result}",
            "timestamp": now,
            "agent_name": agent_id,
            "agent_role": "planner",
            "action": action,
            "parameters": parameters,
            "reasoning": reasoning,
        })

    return traces
