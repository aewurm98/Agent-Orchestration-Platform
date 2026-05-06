import asyncio
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Optional

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.orchestrator import run_orchestrator
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
    "Supply Chain": "supply_chain",
    "Disaster Relief": "disaster_relief",
    "Peer Agents": "peer_agents",
    "supply_chain": "supply_chain",
    "disaster_relief": "disaster_relief",
    "peer_agents": "peer_agents",
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


def _build_dag_nodes(generation: int, fitness: float, scenario: str) -> list[dict]:
    """Build enriched DAG node payloads including tools and last_actions."""
    node_roles = {
        "supply_chain": ["orchestrator", "evaluator", "supply_agent", "demand_agent"],
        "disaster_relief": ["orchestrator", "evaluator", "worker_1", "worker_2"],
        "peer_agents": ["orchestrator", "evaluator", "worker_1", "worker_2"],
    }.get(scenario, ["orchestrator", "evaluator", "worker_1", "worker_2"])

    nodes = []
    for role in node_roles:
        meta = NODE_METADATA.get(role, {"system_prompt": "", "tools": []})
        action = f"[Gen {generation}] {role}: fitness={fitness:.3f}"
        last_actions = _record_action(role, action)
        nodes.append({
            "id": role,
            "label": role.replace("_", " ").title(),
            "status": random.choice(["active", "idle", "evolved"]) if role != "orchestrator" else "active",
            "ctx_util": round(random.uniform(0.3, 0.9), 2),
            "system_prompt": meta["system_prompt"],
            "tools": meta["tools"],
            "last_actions": last_actions,
        })
    return nodes


async def simulation_loop(scenario: str, mode: str, run_id: str) -> None:
    env_cls = SCENARIOS.get(scenario, SupplyChainEnv)
    env = env_cls()
    generation = 0
    parent_fitness = 0.5
    tick = 0

    while active_run.get("running"):
        for tick in range(5):
            if not active_run.get("running"):
                break
            action = env.random_action()
            state = env.step(action)
            await sio.emit("game_state_update", state.to_json())
            await asyncio.sleep(0.4)

        latency = random.uniform(0.2, 1.5)
        cost = random.uniform(0.001, 0.05)
        success_rate = env.get_objective_value()
        fitness = success_rate / max(latency * cost, 1e-6)
        fitness = round(min(fitness, 1000.0), 4)
        mutant_fitness = round(fitness * random.uniform(0.9, 1.15), 4)
        mutation_type = random.choice(["semantic", "grpo_prune", "taguchi"])
        topology_diff = f"+{random.randint(0, 2)}/-{random.randint(0, 2)} edges"

        await sio.emit("fitness_update", {
            "generation": generation,
            "parent_fitness": parent_fitness,
            "best_fitness": mutant_fitness,
            "mutation_type": mutation_type,
            "topology_diff": topology_diff,
            "cost_per_task": round(cost, 5),
            "latency": round(latency, 3),
        })

        dag_nodes = _build_dag_nodes(generation, fitness, scenario)
        for node in dag_nodes:
            thought = node["last_actions"][-1] if node["last_actions"] else ""
            if thought:
                await sio.emit("agent_thought", {
                    "run_id": run_id,
                    "role": node["id"],
                    "content": thought,
                    "timestamp": time.time(),
                })

        node_ids = [n["id"] for n in dag_nodes]
        dag_edges = []
        for i, src in enumerate(node_ids):
            for tgt in node_ids[i + 1:i + 2]:
                dag_edges.append({
                    "source": src,
                    "target": tgt,
                    "payload_size": random.randint(64, 1024),
                    "grpo_score": round(random.uniform(-0.2, 1.0), 3),
                })
        if node_ids:
            dag_edges.append({
                "source": node_ids[1] if len(node_ids) > 1 else node_ids[0],
                "target": node_ids[0],
                "payload_size": random.randint(64, 256),
                "grpo_score": round(random.uniform(0.3, 1.0), 3),
            })

        await sio.emit("dag_update", {"nodes": dag_nodes, "edges": dag_edges})

        await sio.emit("generation_complete", {
            "gen_id": generation,
            "parent_fitness": parent_fitness,
            "child_fitness": mutant_fitness,
            "mutation_type": mutation_type,
        })

        await save_trace(TraceIn(
            run_id=run_id,
            generation=generation,
            agent_role="orchestrator",
            content=f"Generation {generation} complete. Best fitness: {mutant_fitness}",
        ))

        if mode == "hitl" and generation % 3 == 2:
            await sio.emit("hitl_request", {
                "run_id": run_id,
                "generation": generation,
                "plan": f"Mutate topology using {mutation_type} strategy",
                "confidence": round(random.uniform(0.4, 0.75), 2),
                "proposed_action": f"Prune {random.randint(1, 3)} low-scoring edges and crossover top agents",
            })
            await asyncio.sleep(5)

        parent_fitness = mutant_fitness
        generation += 1
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
