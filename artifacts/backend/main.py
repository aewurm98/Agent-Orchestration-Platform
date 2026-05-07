import asyncio
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Optional

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.orchestrator import run_orchestrator, run_one_generation
from game_envs.supply_chain import SupplyChainEnv
from game_envs.disaster_relief import DisasterReliefEnv
from game_envs.peer_agents import PeerAgentsEnv
from game_envs.manufacturing import ManufacturingEnvLegacy
from game_envs.manufacturing_v2 import ManufacturingEnvV2
from game_envs.manufacturing_v2.scenarios import FIRST_FACTORY_CONFIG
from state.db import init_db, save_workflow, get_workflows, save_trace, get_traces, WorkflowIn, TraceIn
from api.mfg_router import router as mfg_router, set_env as mfg_set_env

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(mfg_router)

SCENARIOS: dict[str, type] = {
    "supply_chain":    SupplyChainEnv,
    "disaster_relief": DisasterReliefEnv,
    "peer_agents":     PeerAgentsEnv,
    "manufacturing":   ManufacturingEnvV2,
}

SCENARIO_LABEL_MAP: dict[str, str] = {
    "Supply Chain":    "supply_chain",
    "Disaster Relief": "disaster_relief",
    "Peer Agents":     "peer_agents",
    "Manufacturing":   "manufacturing",
    "supply_chain":    "supply_chain",
    "disaster_relief": "disaster_relief",
    "peer_agents":     "peer_agents",
    "manufacturing":   "manufacturing",
}

NODE_METADATA: dict[str, dict] = {
    "orchestrator": {
        "system_prompt": "You are the master orchestrator. Delegate tasks to worker agents and synthesise results to meet the scenario objective.",
        "tools": ["plan_subtasks", "assign_agent", "merge_results", "escalate_hitl"],
    },
    "evaluator": {
        "system_prompt": "You are the CLEAR evaluator. Score agent outputs on Correctness, Latency, Efficiency, Adaptability, and Reliability.",
        "tools": ["score_output", "compute_fitness", "flag_anomaly"],
    },
    "worker_1": {
        "system_prompt": "You are a specialist worker. Execute assigned subtasks and return structured results.",
        "tools": ["query_env", "act_in_env", "report_result"],
    },
    "worker_2": {
        "system_prompt": "You are a specialist worker focused on edge-case handling and redundancy.",
        "tools": ["query_env", "act_in_env", "report_result", "request_clarification"],
    },
    "supply_agent": {
        "system_prompt": "You manage supply-side inventory and replenishment orders to minimise stockouts.",
        "tools": ["check_stock", "place_order", "forecast_demand"],
    },
    "demand_agent": {
        "system_prompt": "You forecast demand signals and route goods to high-priority destinations.",
        "tools": ["read_demand", "reroute_shipment", "update_forecast"],
    },
    "planner_1": {
        "system_prompt": "You oversee the full manufacturing pipeline. Balance WIP, prevent starvation and overflow, approve finished goods release.",
        "tools": ["query_pipeline_status", "query_worker_status", "reallocate_materials",
                  "set_production_target", "dispatch_order", "broadcast_to_stage",
                  "approve_release", "escalate"],
    },
    "worker_raw_materials": {
        "system_prompt": "You operate the Raw Materials stage. Maximize utilization, minimize idle ticks, flag problems early.",
        "tools": ["process_batch", "inspect_input", "request_replenishment",
                  "report_issue", "rework_output", "idle"],
    },
    "worker_intermediates": {
        "system_prompt": "You operate the Intermediates stage. Maximize utilization, minimize idle ticks, flag problems early.",
        "tools": ["process_batch", "inspect_input", "request_replenishment",
                  "report_issue", "rework_output", "idle"],
    },
    "worker_finished_product": {
        "system_prompt": "You operate the Finished Product stage. Maximize utilization, minimize idle ticks, flag problems early.",
        "tools": ["process_batch", "inspect_input", "request_replenishment",
                  "report_issue", "rework_output", "idle"],
    },
}

_node_action_history: dict[str, list[str]] = {}

active_run: dict[str, object] = {}
simulation_task: Optional[asyncio.Task] = None


def _normalise_scenario(raw: str) -> str:
    return SCENARIO_LABEL_MAP.get(raw, raw.lower().replace(" ", "_"))


def _record_action(node_id: str, action: str) -> list[str]:
    buf = _node_action_history.setdefault(node_id, [])
    buf.append(action)
    if len(buf) > 3:
        buf.pop(0)
    return list(buf)


def _build_dag_update(orch_state: dict, scenario: str) -> dict:
    topology = orch_state.get("topology", {})
    topo_node_ids: list[str] = topology.get("nodes", [])
    topo_edges: list = topology.get("edges", [])
    generation: int = orch_state.get("generation", 0)
    fitness: float = orch_state.get("current_fitness", 0.0)

    if not topo_node_ids:
        topo_node_ids = {
            "supply_chain":    ["orchestrator", "evaluator", "supply_agent", "demand_agent"],
            "disaster_relief": ["orchestrator", "evaluator", "worker_1", "worker_2"],
            "peer_agents":     ["orchestrator", "evaluator", "worker_1", "worker_2"],
            "manufacturing":   ["planner_1", "worker_raw_materials", "worker_intermediates", "worker_finished_product"],
        }.get(scenario, ["orchestrator", "evaluator", "worker_1", "worker_2"])

    statuses = ["active", "idle", "evolved"]
    dag_nodes = []
    for role in topo_node_ids:
        meta = NODE_METADATA.get(role, {"system_prompt": "", "tools": []})
        action = f"[Gen {generation}] {role}: fitness={fitness:.3f}"
        last_actions = _record_action(role, action)
        dag_nodes.append({
            "id": role,
            "label": role.replace("_", " ").title(),
            "status": "active" if role in ("orchestrator", "planner_1") else random.choice(statuses),
            "ctx_util": round(random.uniform(0.3, 0.9), 2),
            "system_prompt": meta["system_prompt"],
            "tools": meta["tools"],
            "last_actions": last_actions,
        })

    dag_edges = []
    for edge in topo_edges:
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            src, tgt = edge
            edge_key = f"{src}->{tgt}"
            grpo = orch_state.get("edge_scores", {}).get(edge_key, round(random.uniform(0.1, 0.9), 3))
            dag_edges.append({
                "source": src,
                "target": tgt,
                "payload_size": random.randint(64, 1024),
                "grpo_score": round(grpo, 3),
            })

    return {"nodes": dag_nodes, "edges": dag_edges}


async def simulation_loop(scenario: str, mode: str, run_id: str) -> None:
    """
    Main simulation loop.
    - Game env ticks every 500 ms; emits game_state_update each tick.
    - Every LANGGRAPH_TICK_INTERVAL ticks a LangGraph generation step runs.
    """
    LANGGRAPH_TICK_INTERVAL = 5

    # ── Manufacturing v2 loop ─────────────────────────────────────────────────
    if scenario == "manufacturing":
        from agents.manufacturing_policies import ScriptedGreedyPolicy
        from agents import manufacturing_roles
        from agents.manufacturing_roles import run_manufacturing_v2_step

        env = ManufacturingEnvV2(FIRST_FACTORY_CONFIG)
        mfg_set_env(env)
        manufacturing_roles.set_active_env_v2(env)

        policy = ScriptedGreedyPolicy()
        game_tick_counter = 0
        metrics_interval = 5

        orch_state: dict = {
            "scenario": scenario,
            "objective": "Maximise manufacturing profit by coordinating 5 specialized agent types on a grid world",
            "agent_configs": [
                {"agent_id": aid, "role": a.role.value}
                for aid, a in env.world.agents.items()
            ],
            "topology": {
                "nodes": list(env.world.agents.keys()),
                "edges": [
                    ("management_1", aid)
                    for aid in env.world.agents.keys() if aid != "management_1"
                ] + [
                    (aid, "management_1")
                    for aid in env.world.agents.keys() if aid != "management_1"
                ],
            },
            "current_fitness": 0.0,
            "parent_fitness": 0.0,
            "topology_diff": "+0/0 edges",
            "latency": 0.0,
            "cost": 0.0,
            "generation": 0,
            "max_generations": 999,
            "hitl_pending": False,
            "confidence": 1.0,
            "edge_scores": {},
            "checkpoint_key": "",
            "run_id": run_id,
            "traces": [],
        }
        trace_cursor = 0

        while active_run.get("running"):
            speed_mult = float(active_run.get("speed_multiplier", 1.0))

            scripted_actions = policy.get_all_actions(env.world)
            tick_result = env.world.tick_advance(scripted_actions)
            game_state = env.to_json()

            await sio.emit("game_state_update", game_state)
            await sio.emit("tick_update", game_state)

            for alert in tick_result.get("alerts", []):
                await sio.emit("alert", alert)

            for ar in tick_result.get("action_results", []):
                await sio.emit("agent_action", {
                    "run_id": run_id,
                    **ar,
                    "timestamp": time.time(),
                })

            game_tick_counter += 1

            if game_tick_counter % metrics_interval == 0:
                await sio.emit("metrics_update", env.get_metrics())
                orch_state = await run_one_generation(orch_state)
                generation: int = orch_state.get("generation", 0)
                current_fitness: float = env.get_fitness()
                parent_fitness: float = orch_state.get("parent_fitness", current_fitness * 0.9)
                orch_state["current_fitness"] = current_fitness
                orch_state["parent_fitness"] = parent_fitness

                await sio.emit("fitness_update", {
                    "generation": generation,
                    "parent_fitness": round(parent_fitness, 4),
                    "best_fitness": round(current_fitness, 4),
                    "mutation_type": "scripted",
                    "topology_diff": f"+{game_tick_counter}/0 ticks",
                    "cost_per_task": round(random.uniform(0.001, 0.05), 5),
                    "latency": round(random.uniform(0.2, 1.5), 3),
                })

                dag_payload = _build_dag_update(orch_state, scenario)
                await sio.emit("dag_update", dag_payload)

                llm_traces = await run_manufacturing_v2_step(generation, env)
                for trace in llm_traces:
                    payload = {
                        "run_id": run_id,
                        "role": trace.get("role", "system"),
                        "content": trace.get("content", ""),
                        "timestamp": trace.get("timestamp", time.time()),
                    }
                    for field_name in ("agent_name", "agent_role", "action", "parameters", "reasoning"):
                        if field_name in trace:
                            payload[field_name] = trace[field_name]
                    await sio.emit("agent_thought", payload)
                    await asyncio.sleep(0.05)

            if env.done:
                await sio.emit("game_over", {
                    "run_id": run_id,
                    "metrics": env.get_metrics(),
                    "fitness": env.get_fitness(),
                    "fitness_vector": env.get_fitness_vector(),
                    "ticks": env.tick_count,
                })
                active_run["running"] = False
                break

            tick_sleep = max(0.05, 0.5 / max(speed_mult, 0.1))
            await asyncio.sleep(tick_sleep)

        return

    # ── All other scenarios ───────────────────────────────────────────────────
    env_cls = SCENARIOS.get(scenario, SupplyChainEnv)
    env = env_cls()

    orch_state: dict = await run_orchestrator(
        scenario=scenario,
        run_id=run_id,
        max_generations=1,
    )

    game_tick_counter = 0
    trace_cursor = 0

    while active_run.get("running"):
        game_state = env.step(env.random_action())
        await sio.emit("game_state_update", game_state.to_json())
        game_tick_counter += 1

        if not active_run.get("running"):
            break

        if game_tick_counter % LANGGRAPH_TICK_INTERVAL == 0:
            orch_state = await run_one_generation(orch_state)

            generation: int = orch_state.get("generation", 0)
            current_fitness: float = orch_state.get("current_fitness", 0.0)
            parent_fitness: float = orch_state.get("parent_fitness", 0.0)
            latency: float = orch_state.get("latency", random.uniform(0.2, 1.5))
            cost: float = orch_state.get("cost", random.uniform(0.001, 0.05))
            topology_diff: str = orch_state.get("topology_diff", "+0/0 edges")
            mutation_type: str = (
                orch_state.get("agent_configs", [{}])[0].get("mutation_type", "semantic")
                if orch_state.get("agent_configs") else "semantic"
            )

            await sio.emit("fitness_update", {
                "generation": generation,
                "parent_fitness": round(parent_fitness, 4),
                "best_fitness": round(current_fitness, 4),
                "mutation_type": mutation_type,
                "topology_diff": topology_diff,
                "cost_per_task": round(cost, 5),
                "latency": round(latency, 3),
            })

            all_traces = orch_state.get("traces", [])
            new_traces = all_traces[trace_cursor:]
            trace_cursor = len(all_traces)
            for trace in new_traces:
                payload = {
                    "run_id": run_id,
                    "role": trace.get("role", "system"),
                    "content": trace.get("content", ""),
                    "timestamp": trace.get("timestamp", time.time()),
                }
                for field_name in ("agent_name", "agent_role", "stage", "action", "parameters", "reasoning"):
                    if field_name in trace:
                        payload[field_name] = trace[field_name]

                await sio.emit("agent_thought", payload)
                await asyncio.sleep(0.12)

            dag_payload = _build_dag_update(orch_state, scenario)
            await sio.emit("dag_update", dag_payload)

            await sio.emit("generation_complete", {
                "gen_id": generation,
                "parent_fitness": round(parent_fitness, 4),
                "child_fitness": round(current_fitness, 4),
                "mutation_type": mutation_type,
            })

            await save_trace(TraceIn(
                run_id=run_id,
                generation=generation,
                agent_role="orchestrator",
                content=f"Generation {generation} complete. Fitness: {current_fitness:.4f}",
            ))

            if mode == "hitl" and orch_state.get("hitl_pending"):
                await sio.emit("hitl_request", {
                    "run_id": run_id,
                    "generation": generation,
                    "plan": f"Mutate topology using {mutation_type} strategy",
                    "confidence": round(orch_state.get("confidence", 0.5), 2),
                    "proposed_action": f"Prune {random.randint(1, 3)} low-scoring edges and crossover top agents",
                })
                await asyncio.sleep(5)

        await asyncio.sleep(0.5)


@app.post("/api/scenario/start")
async def start_scenario(payload: dict) -> dict:
    global simulation_task
    scenario = _normalise_scenario(payload.get("scenario", "supply_chain"))
    mode = payload.get("mode", "autonomous")
    run_id = f"run_{int(time.time())}"

    if simulation_task and not simulation_task.done():
        simulation_task.cancel()

    _node_action_history.clear()
    active_run.clear()
    active_run["running"] = True
    active_run["run_id"] = run_id
    active_run["scenario"] = scenario
    simulation_task = asyncio.create_task(simulation_loop(scenario, mode, run_id))
    return {"status": "started", "run_id": run_id, "scenario": scenario}


@app.post("/api/scenario/stop")
async def stop_scenario() -> dict:
    global simulation_task
    active_run["running"] = False
    if simulation_task and not simulation_task.done():
        simulation_task.cancel()
    return {"status": "stopped"}


@app.get("/api/workflows")
async def list_workflows() -> dict:
    workflows = await get_workflows()
    return {"workflows": workflows}


@app.post("/api/workflows/save")
async def save_current_workflow(payload: dict) -> dict:
    wf = WorkflowIn(
        name=payload.get("name", "Untitled"),
        scenario=payload.get("scenario", active_run.get("scenario", "supply_chain")),
        best_fitness=payload.get("best_fitness", 0.0),
        topology=payload.get("topology", {}),
    )
    saved = await save_workflow(wf)
    return {"workflow": saved}


@app.post("/api/workflows/{workflow_id}/apply")
async def apply_workflow(workflow_id: str) -> dict:
    from state.db import get_workflow_by_id
    wf = await get_workflow_by_id(workflow_id)
    if wf is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "workflow_id": workflow_id,
        "scenario": wf.get("scenario", "supply_chain"),
        "topology": wf.get("topology", {}),
        "best_fitness": wf.get("best_fitness", 0.0),
    }


@app.get("/api/traces/{run_id}")
async def get_run_traces(run_id: str) -> dict:
    traces = await get_traces(run_id)
    return {"traces": traces}


@app.get("/api/healthz")
async def health() -> dict:
    return {"status": "ok"}


@sio.event
async def connect(sid: str, environ: dict, auth: Optional[dict] = None) -> None:
    print(f"Client connected: {sid}")
    from api.mfg_router import get_env
    try:
        env = get_env()
        if env is not None and active_run.get("scenario") == "manufacturing":
            state = env.to_json()
            await sio.emit("game_state_update", state, to=sid)
            await sio.emit("tick_update", state, to=sid)
            await sio.emit("metrics_update", env.get_metrics(), to=sid)
    except Exception:
        pass


@sio.event
async def disconnect(sid: str) -> None:
    print(f"Client disconnected: {sid}")


@sio.event
async def hitl_response(sid: str, data: dict) -> None:
    print(f"HITL response from {sid}: {data}")
    if data.get("action") == "stop":
        active_run["running"] = False
    elif data.get("action") == "override":
        print(f"Human override constraint: {data.get('constraint')}")


@sio.event
async def scenario_select(sid: str, data: dict) -> None:
    print(f"Scenario selected: {data}")


@sio.event
async def start_evolution(sid: str, data: dict) -> None:
    print(f"Start evolution requested by {sid}")


async def _handle_set_speed(sid: str, data: dict) -> None:
    multiplier = float(data.get("multiplier", 1.0))
    active_run["speed_multiplier"] = multiplier
    print(f"Manufacturing speed set to {multiplier}x")


async def _handle_pause(sid: str, data: dict) -> None:
    active_run["running"] = False
    print(f"Manufacturing paused by {sid}")


async def _handle_resume(sid: str, data: dict) -> None:
    global simulation_task
    if not active_run.get("running"):
        scenario = active_run.get("scenario", "manufacturing")
        run_id = active_run.get("run_id", f"run_{int(time.time())}")
        active_run["running"] = True
        simulation_task = asyncio.create_task(simulation_loop(scenario, "autonomous", run_id))
    print(f"Manufacturing resumed by {sid}")


# Spec-compliant event names
@sio.event
async def set_speed(sid: str, data: dict) -> None:
    await _handle_set_speed(sid, data)


@sio.event
async def pause(sid: str, data: dict) -> None:
    await _handle_pause(sid, data)


@sio.event
async def resume(sid: str, data: dict) -> None:
    await _handle_resume(sid, data)


# Legacy names kept for backward compatibility
@sio.event
async def mfg_set_speed(sid: str, data: dict) -> None:
    await _handle_set_speed(sid, data)


@sio.event
async def mfg_pause(sid: str, data: dict) -> None:
    await _handle_pause(sid, data)


@sio.event
async def mfg_resume(sid: str, data: dict) -> None:
    await _handle_resume(sid, data)


@sio.event
async def mfg_action(sid: str, data: dict) -> None:
    """Human-in-the-loop: forward a manual action for a specific agent."""
    from api.mfg_router import get_env
    env = get_env()
    agent_id = data.get("agent_id")
    action_type = data.get("type", "wait")
    params = data.get("params", {})
    if agent_id and agent_id in env.world.agents:
        env.world.agents[agent_id].action_buffer.insert(0, {"type": action_type, "params": params})
        await sio.emit("agent_action", {
            "agent_id": agent_id,
            "action": action_type,
            "params": params,
            "ok": True,
            "message": "Manual action queued",
            "run_id": active_run.get("run_id", ""),
        }, to=sid)


app_with_socket = socketio.ASGIApp(sio, app)
