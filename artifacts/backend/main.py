import asyncio
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

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

SCENARIOS = {
    "supply_chain": SupplyChainEnv,
    "disaster_relief": DisasterReliefEnv,
    "peer_agents": PeerAgentsEnv,
}

active_run: dict[str, Any] = {}
simulation_task: Optional[asyncio.Task] = None


async def simulation_loop(scenario: str, mode: str, run_id: str):
    env_cls = SCENARIOS.get(scenario, SupplyChainEnv)
    env = env_cls()
    generation = 0
    parent_fitness = 0.5

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
        topology_diff = f"+{random.randint(0,2)}/-{random.randint(0,2)} edges"

        await sio.emit("fitness_update", {
            "generation": generation,
            "parent_fitness": parent_fitness,
            "best_fitness": mutant_fitness,
            "mutation_type": mutation_type,
            "topology_diff": topology_diff,
            "cost_per_task": round(cost, 5),
            "latency": round(latency, 3),
        })

        for agent_role in ["orchestrator", "evaluator", "supply_agent", "demand_agent"]:
            thought = f"[Gen {generation}] {agent_role}: tick={tick}, fitness={fitness:.3f}"  # noqa
            await sio.emit("agent_thought", {
                "run_id": run_id,
                "role": agent_role,
                "content": thought,
                "timestamp": time.time(),
            })

        await sio.emit("dag_update", {
            "nodes": [
                {"id": "orchestrator", "label": "Orchestrator", "status": "active", "ctx_util": 0.6},
                {"id": "evaluator", "label": "Evaluator", "status": "idle", "ctx_util": 0.3},
                {"id": "supply_agent", "label": "Supply Agent", "status": "active" if generation % 2 == 0 else "idle", "ctx_util": 0.45},
                {"id": "demand_agent", "label": "Demand Agent", "status": "evolved" if mutant_fitness > fitness else "idle", "ctx_util": 0.55},
            ],
            "edges": [
                {"source": "orchestrator", "target": "evaluator", "payload_size": 512, "grpo_score": random.uniform(-0.2, 0.8)},
                {"source": "orchestrator", "target": "supply_agent", "payload_size": 256, "grpo_score": random.uniform(0.1, 0.9)},
                {"source": "orchestrator", "target": "demand_agent", "payload_size": 384, "grpo_score": random.uniform(-0.1, 0.7)},
                {"source": "evaluator", "target": "orchestrator", "payload_size": 128, "grpo_score": random.uniform(0.3, 1.0)},
            ],
        })

        await sio.emit("generation_complete", {
            "gen_id": generation,
            "parent_fitness": parent_fitness,
            "child_fitness": mutant_fitness,
            "mutation_type": mutation_type,
        })

        await save_trace(TraceIn(run_id=run_id, generation=generation, agent_role="orchestrator", content=f"Generation {generation} complete. Best fitness: {mutant_fitness}"))

        if mode == "hitl" and generation % 3 == 2:
            await sio.emit("hitl_request", {
                "run_id": run_id,
                "generation": generation,
                "plan": f"Mutate topology using {mutation_type} strategy",
                "confidence": round(random.uniform(0.4, 0.75), 2),
                "proposed_action": f"Prune {random.randint(1,3)} low-scoring edges and crossover top agents",
            })
            await asyncio.sleep(5)

        parent_fitness = mutant_fitness
        generation += 1
        await asyncio.sleep(0.5)


@app.post("/api/scenario/start")
async def start_scenario(payload: dict):
    global simulation_task
    scenario = payload.get("scenario", "supply_chain")
    mode = payload.get("mode", "autonomous")
    run_id = f"run_{int(time.time())}"

    if simulation_task and not simulation_task.done():
        simulation_task.cancel()

    active_run.clear()
    active_run["running"] = True
    active_run["run_id"] = run_id
    active_run["scenario"] = scenario
    simulation_task = asyncio.create_task(simulation_loop(scenario, mode, run_id))
    return {"status": "started", "run_id": run_id}


@app.post("/api/scenario/stop")
async def stop_scenario():
    global simulation_task
    active_run["running"] = False
    if simulation_task and not simulation_task.done():
        simulation_task.cancel()
    return {"status": "stopped"}


@app.get("/api/workflows")
async def list_workflows():
    workflows = await get_workflows()
    return {"workflows": workflows}


@app.post("/api/workflows/save")
async def save_current_workflow(payload: dict):
    wf = WorkflowIn(
        name=payload.get("name", "Untitled"),
        scenario=payload.get("scenario", active_run.get("scenario", "supply_chain")),
        best_fitness=payload.get("best_fitness", 0.0),
        topology=payload.get("topology", {}),
    )
    saved = await save_workflow(wf)
    return {"workflow": saved}


@app.get("/api/traces/{run_id}")
async def get_run_traces(run_id: str):
    traces = await get_traces(run_id)
    return {"traces": traces}


@app.get("/api/healthz")
async def health():
    return {"status": "ok"}


@sio.event
async def connect(sid, environ, auth=None):
    print(f"Client connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")


@sio.event
async def hitl_response(sid, data):
    print(f"HITL response from {sid}: {data}")
    if data.get("action") == "stop":
        active_run["running"] = False
    elif data.get("action") == "override":
        print(f"Human override constraint: {data.get('constraint')}")


@sio.event
async def scenario_select(sid, data):
    print(f"Scenario selected: {data}")


@sio.event
async def start_evolution(sid, data):
    print(f"Start evolution requested: {data}")


app_with_socket = socketio.ASGIApp(sio, app)
