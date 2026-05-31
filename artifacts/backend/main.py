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
import game_envs.supply_chain as _sc_module
from game_envs.disaster_relief import DisasterReliefEnv
from game_envs.peer_agents import PeerAgentsEnv
from game_envs.manufacturing import ManufacturingEnvLegacy
from game_envs.manufacturing_v2 import ManufacturingEnvV2
from game_envs.manufacturing_v2.scenarios import FIRST_FACTORY_CONFIG
from game_envs.manufacturing_v3 import ManufacturingV3Env
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
    "supply_chain":     SupplyChainEnv,
    "disaster_relief":  DisasterReliefEnv,
    "peer_agents":      PeerAgentsEnv,
    "manufacturing":    ManufacturingEnvV2,
    "manufacturing_v3": ManufacturingV3Env,
}

SCENARIO_LABEL_MAP: dict[str, str] = {
    "Supply Chain":      "supply_chain",
    "Disaster Relief":   "disaster_relief",
    "Peer Agents":       "peer_agents",
    # The user-facing "Manufacturing" scenario now runs the v3 Topological Flow
    # Graph (the legacy grid env at key "manufacturing" is retired from the UI).
    "Manufacturing":     "manufacturing_v3",
    "Manufacturing V3":  "manufacturing_v3",
    "supply_chain":      "supply_chain",
    "disaster_relief":   "disaster_relief",
    "peer_agents":       "peer_agents",
    "manufacturing":     "manufacturing_v3",
    "manufacturing_v3":  "manufacturing_v3",
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


def _apply_resume_payload(orch_state: dict, run_id: str) -> dict:
    """
    If `active_run["resume_payload"]` is set (populated by /api/scenario/start when
    `resume_payload` is in the POST body), copy the saved generation state into
    `orch_state` so the simulation picks up where it left off.

    Returns the same dict (mutated in place) for chaining. No-op if no payload.
    Wrapped in try/except so a malformed payload never crashes the loop.
    """
    rp = active_run.get("resume_payload")
    if not rp:
        return orch_state
    try:
        gen_id = int(rp.get("gen_id", 0) or 0)
        accepted = float(rp.get("accepted_fitness") or 0.0)
        child = float(rp.get("child_fitness") or 0.0)
        stagnation = int(rp.get("stagnation") or 0)
        mut_strat = str(rp.get("mutation_strategy") or orch_state.get("mutation_strategy") or "MATH")
        genome_json = rp.get("genome_json") or {}

        if isinstance(genome_json, dict) and genome_json:
            orch_state["genome_config"] = genome_json
        orch_state["generation"] = gen_id
        orch_state["accepted_fitness"] = accepted
        orch_state["parent_fitness"] = child  # last child becomes next parent
        orch_state["current_fitness"] = child
        orch_state["stagnation_counter"] = stagnation
        orch_state["mutation_strategy"] = mut_strat

        # System trace so the UI can show a "resumed" banner.
        traces = orch_state.setdefault("traces", [])
        traces.append({
            "role": "system",
            "content": (
                f"Resumed run {run_id} from generation {gen_id} "
                f"(accepted_fitness={accepted:.4f}, strategy={mut_strat})"
            ),
            "timestamp": time.time(),
        })
        print(
            f"[resume] run_id={run_id} gen={gen_id} accepted={accepted:.4f} "
            f"child={child:.4f} strategy={mut_strat} "
            f"genome_keys={list(genome_json.keys()) if isinstance(genome_json, dict) else 'n/a'}"
        )
    except Exception as exc:
        # Never let a malformed payload crash the sim — log and continue cold.
        print(f"[resume] WARNING: failed to apply resume_payload: {exc}")
    return orch_state


async def simulation_loop(scenario: str, mode: str, run_id: str) -> None:
    """
    Main simulation loop.
    Manufacturing: ticks every 500ms; every 25 ticks runs one EA generation
    (evaluate → elitism → mutate genome → apply live mutations → emit fitness_update).
    Other scenarios: LangGraph orchestrator steps every 5 ticks.
    """
    LANGGRAPH_TICK_INTERVAL = 5

    # ── Manufacturing v2 loop (Generational EA) ───────────────────────────────
    if scenario == "manufacturing":
        from agents.manufacturing_policies import get_policy
        from agents import manufacturing_roles
        from agents.manufacturing_roles import run_manufacturing_v2_step
        from evolution.manufacturing_genome import ManufacturingGenome
        from game_envs.manufacturing_v2.entities import SpeedMode as _SpeedMode

        # --- Taguchi L9 init: evaluate 9 env configs, start from the best winner ---
        from agents.evolutionary_engine import TaguchiL9Sample
        from agents.orchestrator import _run_taguchi_evaluation
        from agents.manufacturing_roles import init_edge_scores

        _taguchi_param_grid = {
            "procurement_count": [1, 2, 3],
            "operations_count":  [1, 3, 5],
            "order_arrival_rate": [8.0, 12.0, 18.0],
        }
        _taguchi_configs = TaguchiL9Sample(_taguchi_param_grid)
        _best_cfg, _best_genome, _best_env, _baseline_log = _run_taguchi_evaluation(
            _taguchi_configs, ticks=50
        )

        env = _best_env if _best_env is not None else ManufacturingEnvV2(FIRST_FACTORY_CONFIG)
        mfg_set_env(env)
        manufacturing_roles.set_active_env_v2(env)

        # Seed edge scores from the winning topology
        _initial_edges = {
            f"{src}->{tgt}": 0.5
            for src, tgt in (
                [("management_1", aid) for aid in env.world.agents if aid != "management_1"]
                + [(aid, "management_1") for aid in env.world.agents if aid != "management_1"]
            )
        }
        init_edge_scores(_initial_edges)

        _best_fitness_at_init = next(
            (e["fitness"] for e in _baseline_log if e["config"] == _best_cfg), 0.0
        )

        # Policy selection: read from run config (random / scripted / llm)
        policy_name = active_run.get("policy", "scripted")
        policy = get_policy(str(policy_name))

        # ── EA state ──────────────────────────────────────────────────────────
        GENERATION_TICKS = 25   # ticks per EA generation (fast enough to see multiple gens in demo)
        METRICS_INTERVAL = 5    # emit metrics_update every N ticks for MetricsBar

        genome = ManufacturingGenome.default()
        parent_genome_dict = genome.to_dict()
        parent_fitness: float = 0.0
        consecutive_drops: int = 0
        game_tick_counter: int = 0
        trace_cursor: int = 0

        orch_state: dict = {
            "scenario": scenario,
            "objective": "Maximise manufacturing profit by evolving machine speeds and order rates across generations",
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
            "accepted_fitness": _best_fitness_at_init,
            "policy_mode": str(active_run.get("policy", "scripted")),
            "saved_agent_configs": [
                {"agent_id": aid, "role": a.role.value}
                for aid, a in env.world.agents.items()
            ],
            "saved_topology": {
                "nodes": list(env.world.agents.keys()),
                "edges": [
                    ("management_1", aid)
                    for aid in env.world.agents.keys() if aid != "management_1"
                ] + [
                    (aid, "management_1")
                    for aid in env.world.agents.keys() if aid != "management_1"
                ],
            },
            "genome_config": _best_genome.to_dict() if _best_genome is not None else {},
            "taguchi_baseline_log": _baseline_log,
            "stagnation_counter": 0,
            "fitness_history": [],
            "prev_penalty_cost": 0.0,
            "topology_diff": "+0/0 edges",
            "latency": 0.0,
            "cost": 0.0,
            "generation": 0,
            "max_generations": 999,
            "hitl_pending": False,
            "confidence": 1.0,
            "edge_scores": _initial_edges,
            "checkpoint_key": "",
            "run_id": run_id,
            "traces": [],
            "boundary_mode": active_run.get("boundary_mode", "INTRA"),
            "mutation_strategy": active_run.get("mutation_strategy", "MATH"),
            "inter_ticks": active_run.get("inter_ticks", 100),
            "inter_episode_done": False,
        }

        # Warm-start: if /api/scenario/start was called with a resume_payload,
        # overlay the saved generation state on top of the cold-start orch_state.
        orch_state = _apply_resume_payload(orch_state, run_id)

        boundary_mode_mfg = active_run.get("boundary_mode", "INTRA")

        if boundary_mode_mfg == "INTER":
            # ── INTER mode: episodic simulation ──────────────────────────────
            # Episode is ticked HERE in main.py (with per-tick UI emissions and
            # event-loop yields).  agent_step is signalled via inter_episode_done
            # to skip the episode and just record a trace.
            from evolution.manufacturing_genome import ManufacturingGenome as _MG
            from game_envs.manufacturing_v2.env import ManufacturingEnvV2 as _MEV2
            from agents.manufacturing_policies import ScriptedGreedyPolicy as _SGP
            print(
                f"[INTER] loop start — "
                f"mutation_strategy={active_run.get('mutation_strategy', 'MATH')}, "
                f"inter_ticks={active_run.get('inter_ticks', 100)}"
            )

            while active_run.get("running"):
                if active_run.get("paused"):
                    await asyncio.sleep(0.1)
                    continue

                speed_mult = float(active_run.get("speed_multiplier", 1.0))
                T_max = int(active_run.get("inter_ticks", 100))

                # 1. Build env from current genome ────────────────────────────
                _genome_cfg = orch_state.get("genome_config", {})
                if _genome_cfg and "agent_counts" in _genome_cfg:
                    _genome = _MG.from_dict(_genome_cfg)
                else:
                    _genome = _MG.default()

                _env_cfg = _genome.to_env_config()
                _env_cfg["simulation_length"] = T_max
                _inter_env = _MEV2(_env_cfg)
                mfg_set_env(_inter_env)
                manufacturing_roles.set_active_env_v2(_inter_env)
                _sgp = _SGP()

                # Emit the fresh initial state of the new generation/episode immediately to reset the frontend
                await sio.emit("game_state_update", _inter_env.to_json())
                await sio.emit("tick_update", _inter_env.to_json())
                await sio.emit("metrics_update", _inter_env.get_metrics())

                # 2. Tick episode with per-tick emissions (yields event loop) ─
                _tick_delay = max(0.01, 0.5 / max(speed_mult, 0.1)) / 10
                for _ti in range(T_max):
                    if not active_run.get("running") or _inter_env.done:
                        break
                    _sgp_actions = _sgp.get_all_actions(_inter_env.world)
                    _inter_env.world.tick_advance(_sgp_actions)
                    if _ti % 5 == 0:
                        await sio.emit("tick_update", _inter_env.to_json())
                        await sio.emit("metrics_update", _inter_env.get_metrics())
                        await asyncio.sleep(_tick_delay)

                if not active_run.get("running"):
                    break

                # 2b. Mini-batch evaluation (spec §3.1): run the candidate genome
                #     across fixed stochastic seeds and average the fitness vectors
                #     so the EA / meta-optimizer never over-fits a single lucky run.
                #     Runs off the event loop to avoid blocking per-tick emissions.
                from evolution.minibatch import evaluate_genome_minibatch
                _mb = await asyncio.to_thread(
                    evaluate_genome_minibatch, orch_state.get("genome_config", {}), T_max
                )
                orch_state["minibatch_fitness"] = _mb["fitness"]
                orch_state["minibatch_vector"] = _mb["fitness_vector"]
                orch_state["minibatch_metrics"] = _mb["metrics"]
                print(
                    f"[INTER minibatch] seeds={_mb['metrics'].get('seeds')} "
                    f"mean_fitness={_mb['fitness']} per_seed={_mb['per_seed']}"
                )

                # 3. Run evolutionary step: evaluate → hitl_gate → mutate ─────
                orch_state["inter_episode_done"] = True
                orch_state = await run_one_generation(orch_state)
                orch_state["inter_episode_done"] = False

                # 4. Emit final episode state ──────────────────────────────────
                await sio.emit("game_state_update", _inter_env.to_json())
                await sio.emit("tick_update", _inter_env.to_json())
                await sio.emit("metrics_update", _inter_env.get_metrics())

                generation = orch_state.get("generation", 0)
                current_fitness = orch_state.get("current_fitness", 0.0)
                parent_fitness = orch_state.get("parent_fitness", 0.0)
                accepted_fitness = orch_state.get("accepted_fitness", current_fitness)

                await sio.emit("fitness_update", {
                    "generation": generation,
                    "parent_fitness": round(parent_fitness, 4),
                    "best_fitness": round(accepted_fitness, 4),
                    "mutation_type": active_run.get("mutation_strategy", "MATH").lower(),
                    "topology_diff": orch_state.get("topology_diff", "+0/0 edges"),
                    "cost_per_task": round(orch_state.get("cost", 0.0), 5),
                    "latency": round(orch_state.get("latency", 0.0), 3),
                })

                dag_payload = _build_dag_update(orch_state, scenario)
                await sio.emit("dag_update", dag_payload)

                new_traces = orch_state.get("traces", [])[trace_cursor:]
                trace_cursor = len(orch_state.get("traces", []))
                for trace in new_traces:
                    t_payload = {
                        "run_id": run_id,
                        "role": trace.get("role", "system"),
                        "content": trace.get("content", ""),
                        "timestamp": trace.get("timestamp", time.time()),
                    }
                    await sio.emit("agent_thought", t_payload)

                if mode == "hitl" and orch_state.get("hitl_pending"):
                    await sio.emit("hitl_request", {
                        "run_id": run_id,
                        "generation": generation,
                        "plan": (
                            f"INTER episode {generation} complete — "
                            f"fitness={round(current_fitness, 4)}"
                        ),
                        "confidence": round(orch_state.get("confidence", 0.5), 2),
                        "proposed_action": "Apply genome mutation and start new episode",
                    })

                await asyncio.sleep(0.1)
            return

        # ── INTRA mode: continuous tick-by-tick simulation ────────────────────
        while active_run.get("running"):
            if active_run.get("paused"):
                await asyncio.sleep(0.1)
                continue

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

            # ── Periodic metrics update ────────────────────────────────────────
            if game_tick_counter % METRICS_INTERVAL == 0:
                await sio.emit("metrics_update", env.get_metrics())

            # ── Generation boundary: orchestrator evaluate → elitism → mutate ──
            if game_tick_counter > 0 and game_tick_counter % GENERATION_TICKS == 0:
                orch_state = await run_one_generation(orch_state)
                gen: int = orch_state.get("generation", 0)
                current_fitness = orch_state.get("current_fitness", 0.0)
                parent_fitness = orch_state.get("parent_fitness", 0.0)
                # accepted_fitness is the all-time elitism best — never decreases.
                accepted_fitness = orch_state.get("accepted_fitness", current_fitness)
                confidence = orch_state.get("confidence", 1.0)
                stagnation = orch_state.get("stagnation_counter", 0)
                gdict = orch_state.get("genome_config", {})
                mutation_label = orch_state.get("topology_diff", "genome:evolve")
                metrics_snap: dict = env.get_metrics()
                cost_per_task = round(
                    metrics_snap.get("total_costs", 0.0)
                    / max(metrics_snap.get("orders_fulfilled", 1), 1),
                    3,
                )

                await sio.emit("fitness_update", {
                    "generation": gen,
                    "parent_fitness": round(parent_fitness, 4),
                    "best_fitness": round(accepted_fitness, 4),
                    "mutation_type": mutation_label,
                    "topology_diff": mutation_label,
                    "cost_per_task": cost_per_task,
                    "latency": round(metrics_snap.get("avg_latency", 0.5), 3),
                    # Extended fields consumed by EvoDashboard genome panel
                    "genome": gdict,
                    "improved": current_fitness >= parent_fitness,
                    # Consecutive generations without improvement — triggers stagnation UI
                    "stagnation": stagnation,
                })

                dag_payload = _build_dag_update(orch_state, scenario)
                await sio.emit("dag_update", dag_payload)

                # LLM reasoning is handled by orchestrator agent_step (via run_one_generation)
                # when policy_mode == "llm". Emit any agent_thought traces it produced.
                new_traces = orch_state.get("traces", [])[trace_cursor:]
                trace_cursor = len(orch_state.get("traces", []))
                for trace in new_traces:
                    if trace.get("role") in ("management", "procurement", "operations",
                                              "engineering", "sales"):
                        payload = {
                            "run_id": run_id,
                            "role": trace.get("role", "system"),
                            "content": trace.get("content", ""),
                            "timestamp": trace.get("timestamp", time.time()),
                        }
                        for field_name in ("agent_name", "agent_role", "action",
                                           "parameters", "reasoning"):
                            if field_name in trace:
                                payload[field_name] = trace[field_name]
                        await sio.emit("agent_thought", payload)
                        await asyncio.sleep(0.05)

                if mode == "hitl" and orch_state.get("hitl_pending"):
                    await sio.emit("hitl_request", {
                        "run_id": run_id,
                        "generation": gen,
                        "plan": f"Mutation: {mutation_label}",
                        "confidence": confidence,
                        "proposed_action": (
                            f"speeds:{list(gdict.get('machine_speeds', {}).values())[:3]}, "
                            f"order_rate:{gdict.get('order_arrival_rate', 'n/a')}"
                        ),
                    })

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

    # ── Manufacturing v3 loop (Topological Flow Graph + (mu+lambda) EA) ───────
    if scenario == "manufacturing_v3":
        from evolution.manufacturing_v3_evolution import run_generation, DEFAULT_SEEDS
        from game_envs.manufacturing_v3 import ManufacturingV3Env, ManufacturingV3Genome

        # Default to the LLM meta-optimizer (MATH is only the offline/no-key fallback).
        engine = active_run.get("mutation_strategy", "LLM")
        ea_state: dict = {
            "genome": ManufacturingV3Genome.default().to_dict(),
            "generation": 0,
            "engine": engine,
            "seeds": tuple(DEFAULT_SEEDS),
            "rng_seed": 12345,
            "history": [],
        }
        print(f"[manufacturing_v3] loop start — engine={engine}")

        while active_run.get("running"):
            if active_run.get("paused"):
                await asyncio.sleep(0.1)
                continue

            speed_mult = float(active_run.get("speed_multiplier", 1.0))
            prev_best = float(ea_state.get("best_fitness", 0.0))

            # 1. Stream a representative episode of the current genome for the UI.
            live_genome = ManufacturingV3Genome.from_dict(ea_state["genome"])
            live = ManufacturingV3Env(live_genome, seed=DEFAULT_SEEDS[0])
            await sio.emit("game_state_update", live.to_json())
            await sio.emit("tick_update", live.to_json())
            await sio.emit("metrics_update", live.get_metrics())

            # Stream the episode at a watchable pace: ~20s per 500-tick episode
            # at 1×, ~10s at 2×. Without this the episode races to completion in
            # ~2.5s and the UI just sees 0/500 → 500/500.
            tick_delay = max(0.04, 0.2 / max(speed_mult, 0.1))
            for _ti in range(live.simulation_length):
                if not active_run.get("running") or live.done:
                    break
                live.step()
                if _ti % 5 == 0:
                    snapshot = live.to_json()
                    await sio.emit("tick_update", snapshot)
                    await sio.emit("metrics_update", live.get_metrics())
                    # Live DAG: stream node state + edge flow during the episode
                    # so the agent graph actually animates, not just at end-of-gen.
                    await sio.emit("dag_update", {
                        "nodes": [
                            {"id": n["id"], "label": n["label"], "status": (
                                "active" if n["state"] == "PROCESSING"
                                else "down" if n["state"] == "DOWN" else "idle"
                            ), "ctx_util": n["utilization"]}
                            for n in snapshot["nodes"]
                        ],
                        "edges": [
                            {"source": e["source"], "target": e["target"],
                             "payload_size": e["flow"],
                             "grpo_score": round(e["bandwidth"] / 50.0, 3)}
                            for e in snapshot["edges"]
                        ],
                    })
                    await asyncio.sleep(tick_delay)

            if not active_run.get("running"):
                break

            await sio.emit("game_state_update", live.to_json())
            await sio.emit("metrics_update", live.get_metrics())

            # 2. Evolve one generation ((mu+lambda) over LLM/MATH offspring).
            ea_state = await run_generation(ea_state)
            generation = ea_state["generation"]
            best_fitness = ea_state["best_fitness"]

            await sio.emit("fitness_update", {
                "generation": generation,
                "parent_fitness": round(prev_best, 2),
                "best_fitness": round(best_fitness, 2),
                "mutation_type": ea_state.get("engine_used", engine).lower(),
                "topology_diff": f"flow graph (intake={ea_state['genome']['order_intake_rate']})",
                "cost_per_task": round(
                    ea_state.get("parent_metrics", {}).get("total_opex", 0.0)
                    / max(1, ea_state.get("parent_metrics", {}).get("orders_fulfilled", 1)),
                    3,
                ),
                "latency": 0.0,
                "genome": ea_state["genome"],
                "improved": ea_state.get("improved", False),
            })

            # v3-native DAG payload (nodes + conveyor edges with last-tick flow).
            await sio.emit("dag_update", {
                "nodes": [
                    {"id": n["id"], "label": n["label"], "status": (
                        "active" if n["state"] == "PROCESSING"
                        else "down" if n["state"] == "DOWN" else "idle"
                    ), "ctx_util": n["utilization"]}
                    for n in live.to_json()["nodes"]
                ],
                "edges": [
                    {"source": e["source"], "target": e["target"],
                     "payload_size": e["flow"], "grpo_score": round(
                         e["bandwidth"] / 50.0, 3)}
                    for e in live.to_json()["edges"]
                ],
            })

            reasoning = ea_state.get("reasoning", "")
            if reasoning:
                await sio.emit("agent_thought", {
                    "run_id": run_id,
                    # The Factory Executive is this scenario's orchestrator — tag it so
                    # the Traces tab's "Orchestrator" filter and colour pick it up.
                    "role": "orchestrator",
                    "agent_role": "Factory Executive",
                    "content": f"[Gen {generation}] {reasoning}",
                    "timestamp": time.time(),
                })
            for cand in ea_state.get("candidate_log", []):
                await sio.emit("agent_thought", {
                    "run_id": run_id,
                    "role": "orchestrator",
                    "agent_role": "Factory Executive",
                    "content": (
                        f"  candidate fitness=${cand['fitness']:,.0f}: "
                        f"{cand.get('reasoning', '')}"
                    ),
                    "timestamp": time.time(),
                })

            await asyncio.sleep(0.1)
        return

    # ── Supply Chain v2 loop (real-time truck edge-agents + director) ─────────
    if scenario == "supply_chain":
        from game_envs.supply_chain import SupplyChainEnv as _SCEnv2
        from agents import supply_chain_llm as _sc_llm

        env = _SCEnv2()
        _sc_module._active_env = env
        # LLM brains active only in "LLM" mutation mode; otherwise deterministic
        # fallbacks run the whole show (no API calls / cost).
        use_llm = active_run.get("mutation_strategy", "MATH") == "LLM"
        print(f"[supply_chain v2] loop start — use_llm={use_llm}")

        while active_run.get("running"):
            if active_run.get("paused"):
                await asyncio.sleep(0.1)
                continue
            speed_mult = float(active_run.get("speed_multiplier", 1.0))

            # ── A. Meta-Optimizer / Director intervention every 25 ticks ──────
            if env._tick > 0 and env._tick % 25 == 0:
                digest = env.director_digest()
                try:
                    actions = await _sc_llm.run_director(digest) if use_llm else None
                    if actions is None:
                        actions = env.fallback_director_actions()
                    notes = [env.apply_director_action(a) for a in actions]
                except Exception as exc:
                    env.penalties += 500.0  # validation fine
                    note = f"rejected director actions ({exc}) — $500 fine"
                    notes = [note]
                
                generation = env._tick // 25
                await sio.emit("fitness_update", {
                    "generation": generation,
                    "parent_fitness": round(env.gls, 2),
                    "best_fitness": round(env.gls, 2),
                    "mutation_type": "LLM" if use_llm else "math",
                    "topology_diff": f"{len(env.trucks)} trucks",
                    "cost_per_task": round((env.opex + env.capex) / max(1, sum(
                        n.served for n in env._nodes_by_kind("demand"))), 4),
                    "latency": 0.0,
                })
                for note in notes:
                    await sio.emit("agent_thought", {
                        "run_id": run_id,
                        "role": "director",
                        "content": f"[Director t{env._tick}] {note}",
                        "timestamp": time.time(),
                    })

            # ── B. Programmatic Edge Agent Updates ────────────────────────────
            env.step_agents()

            # ── C. Local Exception Resolution (Concurrent LLM Batching) ───────
            exceptions = getattr(env, "pending_exceptions", [])
            if exceptions:
                if use_llm:
                    ctxs = [env.build_exception_context(t, e) for t, e in exceptions]
                    
                    async def safe_resolve_edge(truck, exception, ctx_data):
                        try:
                            res = await _sc_llm.resolve_edge_exception(ctx_data)
                            return res or env.fallback_edge_decision(truck, exception)
                        except Exception as val_exc:
                            env.alerts.append(f"{truck.id} validation error: {val_exc} (defaulting to ignore)")
                            return {"action": "ignore"}
                    
                    results = await asyncio.gather(
                        *[safe_resolve_edge(t, e, c) for (t, e), c in zip(exceptions, ctxs)]
                    )
                else:
                    results = [env.fallback_edge_decision(t, e) for t, e in exceptions]
                
                for (t, e), decision in zip(exceptions, results):
                    env.apply_edge_decision(t, decision)
                    await sio.emit("agent_thought", {
                        "run_id": run_id,
                        "role": "truck",
                        "agent_name": t.id,
                        "content": (
                            f"{t.id}: {e.kind} → {decision.get('action')} "
                            f"{ {k: v for k, v in decision.items() if k != 'action'} }"
                        ),
                        "timestamp": time.time(),
                    })

            # ── D. Node Updates & GLS Bookkeeping ─────────────────────────────
            env.step_nodes()

            # ── Emit state & alerts ───────────────────────────────────────────
            gs = env.to_json()
            await sio.emit("game_state_update", gs)
            await sio.emit("tick_update", gs)
            for al in env.alerts:
                await sio.emit("alert", {"type": "alert", "message": al, "run_id": run_id})

            if env.done:
                await sio.emit("game_over", {
                    "run_id": run_id,
                    "fitness": env.get_fitness(),
                    "gls": env.gls,
                    "ticks": env._tick,
                })
                active_run["running"] = False
                break

            await asyncio.sleep(max(0.03, 0.25 / max(speed_mult, 0.1)))
        return

    # ── All other scenarios ───────────────────────────────────────────────────
    env_cls = SCENARIOS.get(scenario, SupplyChainEnv)
    env = env_cls()

    # Register supply chain env so the orchestrator evaluate node can read real fitness
    if scenario == "supply_chain":
        _sc_module._active_env = env

    orch_state: dict = await run_orchestrator(
        scenario=scenario,
        run_id=run_id,
        max_generations=1,
    )
    # Inject live run config so boundary_mode / mutation_strategy / inter_ticks
    # are honoured for non-manufacturing scenarios exactly as for manufacturing.
    orch_state["boundary_mode"] = active_run.get("boundary_mode", "INTRA")
    orch_state["mutation_strategy"] = active_run.get("mutation_strategy", "MATH")
    orch_state["inter_ticks"] = active_run.get("inter_ticks", 100)
    orch_state["inter_episode_done"] = False
    orch_state["scenario"] = scenario

    # Initialise supply chain genome so the first mutation has a baseline to perturb
    if scenario == "supply_chain" and not orch_state.get("genome_config"):
        orch_state["genome_config"] = dict(SupplyChainEnv.GENOME_DEFAULTS)

    # Warm-start for non-manufacturing scenarios: overlay saved generation state
    # if /api/scenario/start was called with a resume_payload. Also re-apply the
    # saved genome to the env, since the env was just freshly constructed.
    orch_state = _apply_resume_payload(orch_state, run_id)
    if (
        active_run.get("resume_payload")
        and hasattr(env, "apply_genome")
        and isinstance(orch_state.get("genome_config"), dict)
        and orch_state["genome_config"]
    ):
        try:
            env.apply_genome(orch_state["genome_config"])
        except Exception as exc:
            print(f"[resume] WARNING: env.apply_genome failed: {exc}")

    game_tick_counter = 0
    trace_cursor = 0

    sc_boundary_mode = active_run.get("boundary_mode", "INTRA")
    print(
        f"[sim_loop/{scenario}] boundary_mode={sc_boundary_mode}, "
        f"mutation_strategy={orch_state['mutation_strategy']}, "
        f"inter_ticks={orch_state['inter_ticks']}"
    )

    if sc_boundary_mode == "INTER":
        # ── INTER: episodic simulation for non-manufacturing scenarios ────────
        while active_run.get("running"):
            if active_run.get("paused"):
                await asyncio.sleep(0.1)
                continue

            speed_mult = float(active_run.get("speed_multiplier", 1.0))
            T_max = int(active_run.get("inter_ticks", 100))
            _tick_delay = max(0.01, 0.5 / max(speed_mult, 0.1)) / 10

            # Tick one complete episode with per-tick emissions
            for _ti in range(T_max):
                if not active_run.get("running"):
                    break
                _gs = env.step(env.random_action())
                if _ti % 5 == 0:
                    await sio.emit("game_state_update", _gs.to_json())
                    await sio.emit("tick_update", _gs.to_json())
                    await asyncio.sleep(_tick_delay)

            if not active_run.get("running"):
                break

            # Run evolutionary step: evaluate → hitl_gate → mutate
            orch_state["inter_episode_done"] = True
            orch_state = await run_one_generation(orch_state)
            orch_state["inter_episode_done"] = False

            # Reset env for next episode, then apply evolved genome
            env = env_cls()
            if hasattr(env, "apply_genome") and orch_state.get("genome_config"):
                env.apply_genome(orch_state["genome_config"])
            if scenario == "supply_chain":
                _sc_module._active_env = env

            generation = orch_state.get("generation", 0)
            current_fitness = orch_state.get("current_fitness", 0.0)
            parent_fitness = orch_state.get("parent_fitness", 0.0)
            accepted_fitness_sc = orch_state.get("accepted_fitness", current_fitness)

            await sio.emit("fitness_update", {
                "generation": generation,
                "parent_fitness": round(parent_fitness, 4),
                "best_fitness": round(accepted_fitness_sc, 4),
                "mutation_type": active_run.get("mutation_strategy", "MATH").lower(),
                "topology_diff": orch_state.get("topology_diff", "+0/0 edges"),
                "cost_per_task": round(orch_state.get("cost", 0.0), 5),
                "latency": round(orch_state.get("latency", 0.0), 3),
            })

            dag_payload = _build_dag_update(orch_state, scenario)
            await sio.emit("dag_update", dag_payload)

            new_traces = orch_state.get("traces", [])[trace_cursor:]
            trace_cursor = len(orch_state.get("traces", []))
            for trace in new_traces:
                t_payload = {
                    "run_id": run_id,
                    "role": trace.get("role", "system"),
                    "content": trace.get("content", ""),
                    "timestamp": trace.get("timestamp", time.time()),
                }
                await sio.emit("agent_thought", t_payload)

            if mode == "hitl" and orch_state.get("hitl_pending"):
                await sio.emit("hitl_request", {
                    "run_id": run_id,
                    "generation": generation,
                    "plan": (
                        f"INTER episode {generation} complete — "
                        f"fitness={round(current_fitness, 4)}"
                    ),
                    "confidence": round(orch_state.get("confidence", 0.5), 2),
                    "proposed_action": "Apply genome mutation and start new episode",
                })

            await asyncio.sleep(0.1)
        return

    # ── INTRA mode: continuous ticking ───────────────────────────────────────
    while active_run.get("running"):
        game_state = env.step(env.random_action())
        await sio.emit("game_state_update", game_state.to_json())
        game_tick_counter += 1

        if not active_run.get("running"):
            break

        if game_tick_counter % LANGGRAPH_TICK_INTERVAL == 0:
            orch_state = await run_one_generation(orch_state)

            # Apply evolved genome parameters to the running env
            if hasattr(env, "apply_genome") and orch_state.get("genome_config"):
                env.apply_genome(orch_state["genome_config"])

            generation: int = orch_state.get("generation", 0)
            current_fitness: float = orch_state.get("current_fitness", 0.0)
            parent_fitness: float = orch_state.get("parent_fitness", 0.0)
            # accepted_fitness is the monotone all-time elitism best (never decreases).
            accepted_fitness_sc: float = orch_state.get("accepted_fitness", current_fitness)
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
                "best_fitness": round(accepted_fitness_sc, 4),
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


ALLOWED_ENGINES = {"MATH", "DEAP", "LLM"}


def _resolve_engine(payload: dict) -> str:
    """Pick the EA engine. Precedence: payload.engine > payload.mutation_strategy > env var > 'MATH'.

    `engine` is the user-facing alias; `mutation_strategy` is the legacy key kept for backwards
    compatibility. Unknown values silently fall back to the env-var default so a typo cannot
    crash a run.
    """
    candidate = payload.get("engine") or payload.get("mutation_strategy") \
        or os.environ.get("ARENA_DEFAULT_ENGINE", "MATH")
    candidate = str(candidate).upper()
    return candidate if candidate in ALLOWED_ENGINES else "MATH"


@app.post("/api/scenario/start")
async def start_scenario(payload: dict) -> dict:
    global simulation_task
    scenario = _normalise_scenario(payload.get("scenario", "supply_chain"))
    mode = payload.get("mode", "autonomous")
    run_id = payload.get("resume_run_id") or f"run_{int(time.time())}"

    if simulation_task and not simulation_task.done():
        simulation_task.cancel()

    _node_action_history.clear()
    active_run.clear()
    active_run["running"] = True
    active_run["paused"] = False
    active_run["run_id"] = run_id
    active_run["scenario"] = scenario
    active_run["policy"] = payload.get("policy", "scripted")
    active_run["boundary_mode"] = payload.get("boundary_mode", "INTRA")
    active_run["mutation_strategy"] = _resolve_engine(payload)
    active_run["inter_ticks"] = int(payload.get("inter_ticks", 100))

    if payload.get("resume_payload"):
        # Caller is restoring state from /api/scenario/resume. The simulation_loop /
        # orchestrator init will check active_run["resume_payload"] before seeding.
        active_run["resume_payload"] = payload["resume_payload"]

    print(
        f"[start_scenario] scenario={scenario}, mode={mode}, "
        f"boundary_mode={active_run['boundary_mode']}, "
        f"engine={active_run['mutation_strategy']}, "
        f"inter_ticks={active_run['inter_ticks']}, "
        f"resume={bool(payload.get('resume_payload'))}"
    )
    simulation_task = asyncio.create_task(simulation_loop(scenario, mode, run_id))
    return {
        "status": "started",
        "run_id": run_id,
        "scenario": scenario,
        "engine": active_run["mutation_strategy"],
    }


@app.get("/api/scenario/resume/{run_id}")
async def resume_lookup(run_id: str) -> dict:
    """Returns the latest EAGeneration checkpoint for run_id, so the client can
    re-POST it to /api/scenario/start with `resume_payload=<row>` and
    `resume_run_id=<run_id>` to warm-start the simulation.

    Two-step design (lookup + restart) keeps the simulation_loop free of resume
    coupling and lets the frontend mediate any UI confirmation.
    """
    from state.db import get_latest_ea_generation
    row = await get_latest_ea_generation(run_id)
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No checkpoint found for run_id={run_id}")
    return {
        "run_id": run_id,
        "scenario": row["scenario"],
        "boundary_mode": row["boundary_mode"],
        "engine": row["mutation_strategy"],
        "from_generation": row["gen_id"],
        "accepted_fitness": row["accepted_fitness"],
        "genome_config": row["genome_json"],
        "resume_payload": row,
    }


@app.get("/api/ea/generations/{run_id}")
async def ea_generations_list(run_id: str, limit: int = 500) -> dict:
    """Full generation history for a run — useful for charts and analytics."""
    from state.db import get_ea_generations
    rows = await get_ea_generations(run_id, limit=limit)
    return {"run_id": run_id, "count": len(rows), "generations": rows}


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
    # Set paused flag WITHOUT stopping the loop — world state is preserved
    active_run["paused"] = True
    print(f"Manufacturing paused by {sid}")


async def _handle_resume(sid: str, data: dict) -> None:
    # Clear paused flag — the running loop wakes up on next iteration
    active_run["paused"] = False
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
async def set_supply_chain_knobs(sid: str, data: dict) -> None:
    """User overrides for the supply chain INTRA-mode sliders.

    Payload: { supply_rate?: number|null, retail_demand_base?: number|null }
    `null` clears that override and falls back to genome / default.
    """
    env = _sc_module._active_env
    if env is None:
        print(f"[supply_chain] no active env; ignoring knob update from {sid}")
        return
    try:
        env.set_user_knobs(data or {})
        print(f"[supply_chain] knobs set by {sid}: {data}")
    except Exception as e:
        print(f"[supply_chain] set_user_knobs failed: {e}")


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
