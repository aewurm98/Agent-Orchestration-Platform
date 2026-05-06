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
from state.db import init_db, save_workflow, get_workflows, save_trace, get_traces, WorkflowIn, TraceIn

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

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

# Canonical scenario keys used throughout the backend
SCENARIOS: dict[str, type] = {
    "supply_chain": SupplyChainEnv,
    "disaster_relief": DisasterReliefEnv,
    "peer_agents": PeerAgentsEnv,
}

# Map human-readable labels (sent from the frontend selector) → canonical keys
SCENARIO_LABEL_MAP: dict[str, str] = {
    "Supply Chain":    "supply_chain",
    "Disaster Relief": "disaster_relief",
    "Peer Agents":     "peer_agents",
    "supply_chain":    "supply_chain",
    "disaster_relief": "disaster_relief",
    "peer_agents":     "peer_agents",
}

# Per-node metadata used to enrich dag_update payloads
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
}

# In-memory circular buffer of the last 3 actions per node (populated during simulation)
_node_action_history: dict[str, list[str]] = {}

active_run: dict[str, object] = {}
simulation_task: Optional[asyncio.Task] = None


def _normalise_scenario(raw: str) -> str:
    """Convert a human label or snake_case key to a canonical scenario key."""
    return SCENARIO_LABEL_MAP.get(raw, raw.lower().replace(" ", "_"))


def _record_action(node_id: str, action: str) -> list[str]:
    """Append action to the last-3 buffer for a node and return the buffer."""
    buf = _node_action_history.setdefault(node_id, [])
    buf.append(action)
    if len(buf) > 3:
        buf.pop(0)
    return list(buf)


def _build_dag_update(orch_state: dict, scenario: str) -> dict:
    """Convert LangGraph orchestrator state into a typed dag_update payload."""
    topology = orch_state.get("topology", {})
    topo_node_ids: list[str] = topology.get("nodes", [])
    topo_edges: list = topology.get("edges", [])
    generation: int = orch_state.get("generation", 0)
    fitness: float = orch_state.get("current_fitness", 0.0)

    # Default roles when topology is not yet populated
    if not topo_node_ids:
        topo_node_ids = {
            "supply_chain":    ["orchestrator", "evaluator", "supply_agent", "demand_agent"],
            "disaster_relief": ["orchestrator", "evaluator", "worker_1", "worker_2"],
            "peer_agents":     ["orchestrator", "evaluator", "worker_1", "worker_2"],
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
            "status": "active" if role == "orchestrator" else random.choice(statuses),
            "ctx_util": round(random.uniform(0.3, 0.9), 2),
            "system_prompt": meta["system_prompt"],
            "tools": meta["tools"],
            "last_actions": last_actions,
        })

    # Build edges from topology (tuples/lists) + enriched GRPO scores
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
    - Runs a game environment for real-time game_state_update ticks.
    - Calls LangGraph run_orchestrator / run_one_generation each generation so
      the StateGraph is genuinely wired end-to-end.
    - Emits dag_update, fitness_update, agent_thought, generation_complete from
      the LangGraph orchestrator state.
    """
    env_cls = SCENARIOS.get(scenario, SupplyChainEnv)
    env = env_cls()

    # ── Generation 0: full LangGraph episode (goal_intake → topology_init → one cycle)
    orch_state: dict = await run_orchestrator(
        scenario=scenario,
        run_id=run_id,
        max_generations=1,
    )

    while active_run.get("running"):
        # ── Game env ticks (real-time grid animation) ──────────────────────
        for _tick in range(5):
            if not active_run.get("running"):
                break
            action = env.random_action()
            game_state = env.step(action)
            await sio.emit("game_state_update", game_state.to_json())
            await asyncio.sleep(0.4)

        if not active_run.get("running"):
            break

        # ── LangGraph single-generation step ───────────────────────────────
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
        # fitness_update from LangGraph evaluate() output
        await sio.emit("fitness_update", {
            "generation": generation,
            "parent_fitness": round(parent_fitness, 4),
            "best_fitness": round(current_fitness, 4),
            "mutation_type": mutation_type,
            "topology_diff": topology_diff,
            "cost_per_task": round(cost, 5),
            "latency": round(latency, 3),
        })

        # agent_thoughts — emit each trace individually with a short delay to
        # simulate incremental streaming cadence in the TracePanel
        new_traces = orch_state.get("traces", [])[-4:]
        for trace in new_traces:
            await sio.emit("agent_thought", {
                "run_id": run_id,
                "role": trace.get("role", "system"),
                "content": trace.get("content", ""),
                "timestamp": trace.get("timestamp", time.time()),
            })
            await asyncio.sleep(0.12)  # 120 ms between thoughts for visible streaming

        # dag_update built from LangGraph topology + metadata
        dag_payload = _build_dag_update(orch_state, scenario)
        await sio.emit("dag_update", dag_payload)

        # generation_complete summary
        await sio.emit("generation_complete", {
            "gen_id": generation,
            "parent_fitness": round(parent_fitness, 4),
            "child_fitness": round(current_fitness, 4),
            "mutation_type": mutation_type,
        })

        # Persist trace to DB
        await save_trace(TraceIn(
            run_id=run_id,
            generation=generation,
            agent_role="orchestrator",
            content=f"Generation {generation} complete. Fitness: {current_fitness:.4f}",
        ))

        # HITL: trigger if mode=hitl and confidence below threshold
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
    """Apply a saved workflow topology — returns its scenario so the frontend can start it."""
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


app_with_socket = socketio.ASGIApp(sio, app)
