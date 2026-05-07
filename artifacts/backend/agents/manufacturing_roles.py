"""
Manufacturing agent roles: Worker and Planner, each powered by gpt-4o-mini.

Workers see only their own stage.
Planners start with limited visibility and must invoke query skills.

Module-level singletons hold env reference, message board, and planner query cache.
Call set_active_env(env) before each simulation run.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from openai import AsyncOpenAI

log = logging.getLogger(__name__)

# ── Replit-managed OpenAI client (lazy singleton) ────────────────────────────

_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(
            base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
            api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "_DUMMY_API_KEY_"),
        )
    return _openai_client

# ── Module-level shared state ────────────────────────────────────────────────

_env = None  # ManufacturingEnv instance, set by main.py

# per-agent inbox: agent_id -> list of message dicts
_message_board: dict[str, list[dict]] = {}

# planner query cache: planner_id -> last query result dict
_planner_cache: dict[str, dict] = {}

# worker last state cache: worker_id -> last state dict (for planner queries)
_worker_state_cache: dict[str, dict] = {}


def set_active_env(env) -> None:
    global _env, _openai_client
    _env = env
    _openai_client = None  # reset so client re-reads env vars on next call
    _message_board.clear()
    _planner_cache.clear()
    _worker_state_cache.clear()


def _post_to_inbox(agent_id: str, message: dict) -> None:
    _message_board.setdefault(agent_id, []).append(message)


def _read_inbox(agent_id: str) -> list[dict]:
    msgs = _message_board.get(agent_id, [])
    _message_board[agent_id] = []  # clear on read
    return msgs


# ── Incentive strings ────────────────────────────────────────────────────────

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

# ── Skill registries ─────────────────────────────────────────────────────────

WORKER_SKILLS = [
    {
        "name": "process_batch",
        "description": "Consume from input buffer, produce to output buffer.",
        "parameters": {"quantity": "integer — number of units to process"},
    },
    {
        "name": "inspect_input",
        "description": "Sample-check incoming materials and report quality status.",
        "parameters": {},
    },
    {
        "name": "request_replenishment",
        "description": "Send a replenishment request upstream or to the Planner.",
        "parameters": {"urgency": "string — low | medium | high"},
    },
    {
        "name": "report_issue",
        "description": "Send a flagged problem to the Planner inbox.",
        "parameters": {"description": "string — description of the problem"},
    },
    {
        "name": "rework_output",
        "description": "Reprocess defective units sitting in the output buffer.",
        "parameters": {"quantity": "integer — units to rework"},
    },
    {
        "name": "idle",
        "description": "Do nothing this tick. Valid when blocked or waiting.",
        "parameters": {},
    },
]

PLANNER_SKILLS = [
    {
        "name": "query_pipeline_status",
        "description": "Fetch live WIP, throughput, and buffer levels for all three stages. Result appears in next tick context.",
        "parameters": {},
    },
    {
        "name": "query_worker_status",
        "description": "Fetch current state and last action of a specific worker.",
        "parameters": {"worker_id": "string — e.g. worker_raw_materials"},
    },
    {
        "name": "reallocate_materials",
        "description": "Move raw material allocation between stages.",
        "parameters": {
            "from_stage": "string — stage name",
            "to_stage": "string — stage name",
            "quantity": "integer",
        },
    },
    {
        "name": "set_production_target",
        "description": "Update the batch size target for a stage.",
        "parameters": {"stage": "string — stage name", "target_units": "integer"},
    },
    {
        "name": "dispatch_order",
        "description": "Send a direct instruction message to a Worker.",
        "parameters": {"worker_id": "string", "instruction": "string"},
    },
    {
        "name": "broadcast_to_stage",
        "description": "Send a message to all Workers at a given stage.",
        "parameters": {"stage": "string — stage name", "message": "string"},
    },
    {
        "name": "approve_release",
        "description": "Authorize finished goods to leave the output buffer.",
        "parameters": {"quantity": "integer"},
    },
    {
        "name": "escalate",
        "description": "Surface an unresolvable issue to the system log.",
        "parameters": {"description": "string"},
    },
]


# ── Context builders ─────────────────────────────────────────────────────────

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
    last_query = _planner_cache.get(agent_id, {})
    targets = {}
    for sname in ["raw_materials", "intermediates", "finished_product"]:
        snap = _env.get_stage_snapshot(sname)
        targets[sname] = snap.get("target_units", 0)
    return {
        "inbox": inbox,
        "last_query_results": last_query if last_query else "(no query results yet — use query_pipeline_status to get pipeline data)",
        "current_production_targets": targets,
    }


# ── Skill dispatchers ────────────────────────────────────────────────────────

def _dispatch_worker_skill(
    agent_id: str, stage_name: str, action: str, parameters: dict
) -> str:
    if _env is None:
        return "env not initialised"

    if action == "process_batch":
        result = _env.process_batch(stage_name, parameters.get("quantity", 10))
        return json.dumps(result)

    elif action == "inspect_input":
        result = _env.inspect_input(stage_name)
        return json.dumps(result)

    elif action == "request_replenishment":
        urgency = parameters.get("urgency", "medium")
        msg = {
            "type": "replenishment_request",
            "from": agent_id,
            "stage": stage_name,
            "urgency": urgency,
            "timestamp": time.time(),
        }
        _post_to_inbox("planner_1", msg)
        return f"Replenishment request ({urgency}) sent to Planner."

    elif action == "report_issue":
        desc = parameters.get("description", "unspecified issue")
        msg = {
            "type": "issue_report",
            "from": agent_id,
            "stage": stage_name,
            "description": desc,
            "timestamp": time.time(),
        }
        _post_to_inbox("planner_1", msg)
        return f"Issue reported to Planner: {desc}"

    elif action == "rework_output":
        result = _env.rework_output(stage_name, parameters.get("quantity", 5))
        return json.dumps(result)

    elif action == "idle":
        snap = _env.get_stage_snapshot(stage_name)
        _worker_state_cache[agent_id] = {"stage": stage_name, "state": snap, "last_action": "idle"}
        return "Agent idle this tick."

    return f"Unknown worker skill: {action}"


def _dispatch_planner_skill(
    agent_id: str, action: str, parameters: dict
) -> str:
    if _env is None:
        return "env not initialised"

    if action == "query_pipeline_status":
        result = _env.query_pipeline_status()
        _planner_cache[agent_id] = {"query_pipeline_status": result, "fetched_at": time.time()}
        return "Pipeline status fetched — available in next tick context."

    elif action == "query_worker_status":
        worker_id = parameters.get("worker_id", "")
        cache = _worker_state_cache.get(worker_id, {})
        result = {"worker_id": worker_id, "cached_state": cache}
        _planner_cache[agent_id] = {"query_worker_status": result, "fetched_at": time.time()}
        return f"Worker status for {worker_id} fetched."

    elif action == "reallocate_materials":
        result = _env.reallocate_materials(
            parameters.get("from_stage", ""),
            parameters.get("to_stage", ""),
            parameters.get("quantity", 0),
        )
        return json.dumps(result)

    elif action == "set_production_target":
        result = _env.set_production_target(
            parameters.get("stage", ""), parameters.get("target_units", 10)
        )
        return json.dumps(result)

    elif action == "dispatch_order":
        worker_id = parameters.get("worker_id", "")
        instruction = parameters.get("instruction", "")
        msg = {
            "type": "dispatch_order",
            "from": agent_id,
            "instruction": instruction,
            "timestamp": time.time(),
        }
        _post_to_inbox(worker_id, msg)
        return f"Order dispatched to {worker_id}: {instruction}"

    elif action == "broadcast_to_stage":
        stage = parameters.get("stage", "")
        message = parameters.get("message", "")
        worker_id = f"worker_{stage}"
        msg = {
            "type": "broadcast",
            "from": agent_id,
            "stage": stage,
            "message": message,
            "timestamp": time.time(),
        }
        _post_to_inbox(worker_id, msg)
        return f"Broadcast to {stage}: {message}"

    elif action == "approve_release":
        result = _env.approve_release(parameters.get("quantity", 0))
        return json.dumps(result)

    elif action == "escalate":
        desc = parameters.get("description", "unspecified")
        log.warning("ESCALATION from planner: %s", desc)
        return f"Escalated: {desc}"

    return f"Unknown planner skill: {action}"


# ── LLM caller ───────────────────────────────────────────────────────────────

_RESPONSE_SCHEMA = """
Respond with a single JSON object:
{
  "action": "<skill_name>",
  "parameters": { ... },
  "reasoning": "<one or two sentence explanation>",
  "message": "<optional string for communication skills>"
}
Only use skills from the provided list. Do not add extra keys.
"""


async def _call_llm(
    role_label: str,
    incentive: str,
    skills: list[dict],
    context: dict,
) -> dict:
    skill_list = json.dumps(skills, indent=2)
    system_prompt = (
        f"{incentive}\n\n"
        f"Available skills:\n{skill_list}\n\n"
        f"{_RESPONSE_SCHEMA}"
    )
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
        return {
            "action": "idle",
            "parameters": {},
            "reasoning": f"LLM call failed: {exc}",
        }


# ── Main entry point ─────────────────────────────────────────────────────────

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
    """
    Run one tick of manufacturing agents via LLM calls.
    Returns a list of enriched trace dicts for the Socket.IO agent_thought event.
    """
    if _env is None:
        return []

    traces: list[dict] = []
    now = time.time()

    # Workers first
    for cfg in WORKER_AGENTS:
        agent_id = cfg["agent_id"]
        stage = cfg["stage"]
        context = _build_worker_context(agent_id, stage)

        parsed = await _call_llm(
            role_label=f"Worker/{stage}",
            incentive=WORKER_INCENTIVE,
            skills=WORKER_SKILLS,
            context=context,
        )

        action = parsed.get("action", "idle")
        parameters = parsed.get("parameters", {})
        reasoning = parsed.get("reasoning", "")

        skill_result = _dispatch_worker_skill(agent_id, stage, action, parameters)

        _worker_state_cache[agent_id] = {
            "stage": stage,
            "last_action": action,
            "last_parameters": parameters,
            "skill_result": skill_result,
        }

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

    # Planner
    for cfg in PLANNER_AGENTS:
        agent_id = cfg["agent_id"]
        context = _build_planner_context(agent_id)

        parsed = await _call_llm(
            role_label="Planner",
            incentive=PLANNER_INCENTIVE,
            skills=PLANNER_SKILLS,
            context=context,
        )

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
            "stage": None,
            "action": action,
            "parameters": parameters,
            "reasoning": reasoning,
        })

    return traces
