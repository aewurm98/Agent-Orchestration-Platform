"""
LangGraph StateGraph orchestrator for the Agentic Engineering Arena.
All 7 nodes wired: goal_intake, topology_init, agent_step, evaluate,
hitl_gate (proper node), mutate, checkpoint.

run_orchestrator()  — full episode (init + N cycles until max_generations)
run_one_generation() — single LangGraph cycle from agent_step onwards
"""
from __future__ import annotations

import copy
import random
import time
from typing import TypedDict

from langgraph.graph import StateGraph, END

from agents.evolutionary_engine import (
    FitnessScore,
    SemanticMutation,
    GraphGRPOPrune,
    TaguchiL9Sample,
    GenerationLog,
)


class ArenaState(TypedDict):
    scenario: str
    objective: str
    agent_configs: list[dict]
    topology: dict
    current_fitness: float
    parent_fitness: float
    accepted_fitness: float          # highest fitness ever accepted by elitism
    saved_agent_configs: list[dict]  # snapshot of agent_configs at last accepted generation
    saved_topology: dict             # snapshot of topology at last accepted generation
    topology_diff: str
    latency: float
    cost: float
    generation: int
    max_generations: int
    hitl_pending: bool
    confidence: float
    edge_scores: dict[str, float]
    checkpoint_key: str
    run_id: str
    traces: list[dict]
    stagnation_counter: int
    fitness_history: list[float]
    prev_penalty_cost: float
    taguchi_baseline_log: list[dict]
    genome_config: dict              # winning Taguchi L9 genome params for manufacturing


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def goal_intake(state: ArenaState) -> ArenaState:
    """Parse scenario and set high-level objective."""
    objective_map = {
        "supply_chain":    "Minimise stockout rate while reducing carrying cost",
        "disaster_relief": "Maximise survivor rescue rate within 24 simulated hours",
        "peer_agents":     "Achieve Nash equilibrium in multi-agent resource allocation",
        "manufacturing":   "Maximise pipeline throughput across three manufacturing stages",
    }
    state["objective"] = objective_map.get(state["scenario"], "Optimise agent performance")
    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": f"Goal intake complete: {state['objective']}",
        "timestamp": time.time(),
    }]
    return state


def _run_taguchi_evaluation(configs: list[dict], ticks: int = 50):
    """
    Evaluate each Taguchi L9 config by running `ticks` ticks of the manufacturing
    environment with ScriptedGreedyPolicy.

    Returns (best_config, best_genome, best_env, baseline_log) where best_env is
    already stepped to tick `ticks` from the winning configuration — the caller
    can hand it directly to set_active_env_v2 as the generation-0 parent env.
    """
    from evolution.manufacturing_genome import ManufacturingGenome
    from game_envs.manufacturing_v2.env import ManufacturingEnvV2
    from agents.manufacturing_policies import ScriptedGreedyPolicy

    policy = ScriptedGreedyPolicy()
    best_fitness = float("-inf")
    best_config = configs[0]
    best_genome: ManufacturingGenome | None = None
    best_env: ManufacturingEnvV2 | None = None
    baseline_log: list[dict] = []

    for idx, cfg in enumerate(configs):
        genome = ManufacturingGenome(
            agent_counts={
                "procurement": int(cfg.get("procurement_count", 1)),
                "operations":  int(cfg.get("operations_count", 2)),
                "engineering": 1,
                "sales": 1,
                "management": 1,
            },
            order_arrival_rate=float(cfg.get("order_arrival_rate", 12.0)),
        )
        env_config = genome.to_env_config()
        env = ManufacturingEnvV2(env_config)

        for _ in range(ticks):
            if env.done:
                break
            actions = policy.get_all_actions(env.world)
            env.step(actions)

        fitness = env.get_fitness()
        baseline_log.append({"config_idx": idx, "config": cfg, "fitness": round(fitness, 4)})

        if fitness > best_fitness:
            best_fitness = fitness
            best_config = cfg
            best_genome = genome
            best_env = env

    return best_config, best_genome, best_env, baseline_log


def topology_init(state: ArenaState) -> ArenaState:
    """Initialise the agent graph topology.

    For the manufacturing scenario: evaluate all 9 Taguchi L9 configurations
    for 50 ticks each using ScriptedGreedyPolicy; the best-scoring configuration
    becomes the generation-0 parent.  For other scenarios: sample Taguchi L9
    configs directly.
    """
    if state.get("scenario") == "manufacturing":
        from agents.manufacturing_roles import ALL_MANUFACTURING_AGENT_CONFIGS, set_active_env_v2, init_edge_scores

        param_grid = {
            "procurement_count":  [1, 2, 3],
            "operations_count":   [1, 3, 5],
            "order_arrival_rate": [8.0, 12.0, 18.0],
        }
        taguchi_configs = TaguchiL9Sample(param_grid)
        best_cfg, best_genome, best_env, baseline_log = _run_taguchi_evaluation(taguchi_configs, ticks=50)

        # Apply the winning Taguchi genome as generation-0 parent:
        # - Register the best-scoring env as the active simulation environment
        # - Store genome params in state for downstream mutation
        if best_env is not None:
            set_active_env_v2(best_env)
        state["genome_config"] = best_cfg
        state["taguchi_baseline_log"] = baseline_log

        # Seed agent_configs with the genome metadata so the loop has a record
        # of generation-0 parameters alongside the role definitions
        state["agent_configs"] = list(ALL_MANUFACTURING_AGENT_CONFIGS) + [
            {"role": "_genome", "params": best_cfg}
        ]

        # Derive initial topology node names from the best genome's agent counts
        state["topology"] = {
            "nodes": ["planner_1", "worker_raw_materials", "worker_intermediates", "worker_finished_product"],
            "edges": [
                ("planner_1", "worker_raw_materials"),
                ("planner_1", "worker_intermediates"),
                ("planner_1", "worker_finished_product"),
                ("worker_raw_materials", "planner_1"),
                ("worker_intermediates", "planner_1"),
                ("worker_finished_product", "planner_1"),
            ],
        }
        state["edge_scores"] = {
            "planner_1->worker_raw_materials": 0.8,
            "planner_1->worker_intermediates": 0.8,
            "planner_1->worker_finished_product": 0.8,
            "worker_raw_materials->planner_1": 0.7,
            "worker_intermediates->planner_1": 0.7,
            "worker_finished_product->planner_1": 0.7,
        }
        init_edge_scores(state["edge_scores"])

        best_fitness_val = next(
            (e["fitness"] for e in baseline_log if e["config"] == best_cfg), 0.0
        )
        state["accepted_fitness"] = best_fitness_val
        state["current_fitness"] = best_fitness_val

        # Snapshot generation-0 state so elitism can restore on first rejection
        state["saved_agent_configs"] = copy.deepcopy(state["agent_configs"])
        state["saved_topology"] = copy.deepcopy(state["topology"])

        best_summary = (
            f"procurement={best_cfg.get('procurement_count')}, "
            f"ops={best_cfg.get('operations_count')}, "
            f"order_rate={best_cfg.get('order_arrival_rate')}, "
            f"fitness={best_fitness_val:.4f}"
        )
        state["traces"] = state.get("traces", []) + [{
            "role": "system",
            "content": f"Taguchi L9 init complete — winner: {best_summary}",
            "timestamp": time.time(),
        }]
    else:
        sample_configs = TaguchiL9Sample({
            "model": ["claude-3-haiku", "claude-3-sonnet", "claude-3-5-sonnet"],
            "temperature": [0.3, 0.7, 1.0],
            "max_tokens": [512, 1024, 2048],
        })
        state["agent_configs"] = sample_configs[:3]
        state["topology"] = {
            "nodes": ["orchestrator", "evaluator", "worker_1", "worker_2"],
            "edges": [
                ("orchestrator", "evaluator"),
                ("orchestrator", "worker_1"),
                ("orchestrator", "worker_2"),
                ("evaluator", "orchestrator"),
            ],
        }
        state["edge_scores"] = {
            "orchestrator->evaluator": 0.8,
            "orchestrator->worker_1": 0.6,
            "orchestrator->worker_2": 0.5,
            "evaluator->orchestrator": 0.9,
        }

    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": f"Topology initialised with {len(state['topology']['nodes'])} agents",
        "timestamp": time.time(),
    }]
    return state


async def agent_step(state: ArenaState) -> ArenaState:
    """Run one tick of the active agent population."""
    if state.get("scenario") == "manufacturing":
        from agents.manufacturing_roles import run_manufacturing_step
        generation = state.get("generation", 0)
        new_traces = await run_manufacturing_step(generation)
        state["traces"] = state.get("traces", []) + new_traces
    else:
        # Stub for other scenarios — future LLM integration
        for _cfg in state.get("agent_configs", []):
            pass

    state["traces"] = state.get("traces", []) + [{
        "role": "orchestrator",
        "content": f"[Gen {state['generation']}] Agent step complete",
        "timestamp": time.time(),
    }]
    return state


def _compute_confidence(state: ArenaState) -> float:
    """
    Compute confidence kappa from real environment metrics.

    Starts at 1.0 and applies reductions:
      - subtract 0.4 if missed-order ratio > 0.20
      - subtract 0.3 if penalty cost increased by more than 50% since last tick
      - subtract 0.3 if fitness has declined for 3 consecutive generations

    Result is clamped to [0.0, 1.0].
    """
    kappa = 1.0

    if state.get("scenario") == "manufacturing":
        from agents import manufacturing_roles
        env = manufacturing_roles._env_v2 or manufacturing_roles._env
        if env is not None and hasattr(env, "world"):
            econ = env.world.economy
            fulfilled = econ._orders_fulfilled
            missed = econ._orders_missed
            total_orders = fulfilled + missed
            missed_ratio = missed / max(total_orders, 1)
            if missed_ratio > 0.20:
                kappa -= 0.4   # drives kappa to 0.6; gate uses <= 0.6

            current_penalties = econ.pl.penalties
            prev_penalties = state.get("prev_penalty_cost", 0.0)
            if prev_penalties > 0 and current_penalties > prev_penalties * 1.5:
                kappa -= 0.4   # individually drives kappa to 0.6, triggering HITL

    fitness_history = state.get("fitness_history", [])
    if len(fitness_history) >= 3:
        last_three = fitness_history[-3:]
        if last_three[0] > last_three[1] > last_three[2]:
            kappa -= 0.4       # individually drives kappa to 0.6, triggering HITL

    return round(max(0.0, min(1.0, kappa)), 2)


def evaluate(state: ArenaState) -> ArenaState:
    """Score generation with CLEAR fitness function and metric-derived confidence."""
    latency = random.uniform(0.2, 1.5)
    cost = random.uniform(0.001, 0.05)
    success_rate = random.uniform(0.3, 0.95)

    if state.get("scenario") == "manufacturing":
        from agents import manufacturing_roles
        env = manufacturing_roles._env_v2 or manufacturing_roles._env
        if env is not None:
            if hasattr(env, "get_objective_value"):
                success_rate = env.get_objective_value()
            else:
                success_rate = env.get_fitness()

        # Pull updated edge scores from the credit assignment module
        updated_edge_scores = dict(manufacturing_roles._edge_scores)
        if updated_edge_scores:
            merged = dict(state.get("edge_scores", {}))
            merged.update(updated_edge_scores)
            state["edge_scores"] = merged

    fitness = FitnessScore(success_rate=success_rate, latency=latency, cost=cost)
    state["parent_fitness"] = state.get("current_fitness", 0.0)
    state["current_fitness"] = round(fitness, 4)
    state["latency"] = round(latency, 3)
    state["cost"] = round(cost, 5)

    fitness_history = list(state.get("fitness_history", []))
    fitness_history.append(state["current_fitness"])
    if len(fitness_history) > 10:
        fitness_history = fitness_history[-10:]
    state["fitness_history"] = fitness_history

    # Compute kappa using prev_penalty_cost from the PREVIOUS tick before updating it
    state["confidence"] = _compute_confidence(state)

    # NOW update prev_penalty_cost for next generation's comparison
    if state.get("scenario") == "manufacturing":
        from agents import manufacturing_roles
        env_inner = manufacturing_roles._env_v2 or manufacturing_roles._env
        if env_inner is not None and hasattr(env_inner, "world"):
            state["prev_penalty_cost"] = env_inner.world.economy.pl.penalties

    state["traces"] = state.get("traces", []) + [{
        "role": "evaluator",
        "content": f"Fitness={state['current_fitness']}, confidence={state['confidence']}",
        "timestamp": time.time(),
    }]
    return state


def hitl_gate(state: ArenaState) -> ArenaState:
    """Node 5: mark state for HITL pause when confidence <= 0.6."""
    state["hitl_pending"] = state.get("confidence", 1.0) <= 0.6
    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": (
            "HITL gate: pausing for human review"
            if state["hitl_pending"]
            else "HITL gate: confidence OK, continuing"
        ),
        "timestamp": time.time(),
    }]
    return state


def mutate(state: ArenaState) -> ArenaState:
    """Apply semantic mutation + Graph-GRPO edge pruning with elitism and edge regrowth.

    Elitism: compare current_fitness against accepted_fitness (the highest fitness
    ever accepted by elitism, initialized at generation-0 Taguchi winner score).
    If the child is strictly worse, mutation is skipped and stagnation_counter
    increments.  Only when child >= accepted_fitness do we accept and mutate.
    This ensures the fitness curve can only plateau or rise between accepted
    generations — it never regresses.

    Edge regrowth: before pruning, with 5% probability a random directed edge is
    added at score 0.5, giving pruned topologies a path back to connectivity.
    """
    current_fitness = state.get("current_fitness", 0.0)
    accepted_fitness = state.get("accepted_fitness", 0.0)
    stagnation_counter = state.get("stagnation_counter", 0)

    # --- Elitism check against the best accepted fitness, not last generation ---
    # --- Edge regrowth (5% chance per generation, regardless of accept/reject) ---
    _rg_nodes = state.get("topology", {}).get("nodes", [])
    if _rg_nodes and random.random() < 0.05:
        _rg_src = random.choice(_rg_nodes)
        _rg_tgt = random.choice(_rg_nodes)
        if _rg_src != _rg_tgt:
            _rg_existing = state["topology"].get("edges", [])
            _rg_set = {(e[0], e[1]) if isinstance(e, (list, tuple)) else e for e in _rg_existing}
            _rg_new = (_rg_src, _rg_tgt)
            if _rg_new not in _rg_set:
                state["topology"] = copy.deepcopy(state["topology"])
                state["topology"]["edges"] = list(_rg_existing) + [_rg_new]
                _rg_key = f"{_rg_src}->{_rg_tgt}"
                if _rg_key not in state["edge_scores"]:
                    state["edge_scores"] = dict(state["edge_scores"])
                    state["edge_scores"][_rg_key] = 0.5
                state["traces"] = state.get("traces", []) + [{
                    "role": "system",
                    "content": f"Edge regrowth: sprouted {_rg_key} at score 0.5",
                    "timestamp": time.time(),
                }]

    if current_fitness < accepted_fitness:
        # Child is strictly worse than the accepted parent — reject and RESTORE
        # parent snapshots so the next agent_step runs with the accepted configs.
        stagnation_counter += 1
        state["stagnation_counter"] = stagnation_counter

        saved_configs = state.get("saved_agent_configs")
        saved_topo = state.get("saved_topology")
        if saved_configs is not None:
            state["agent_configs"] = copy.deepcopy(saved_configs)
        if saved_topo is not None:
            state["topology"] = copy.deepcopy(saved_topo)

        state["topology_diff"] = "+0/0 edges (elitism: reverted)"
        state["generation"] = state.get("generation", 0) + 1
        state["traces"] = state.get("traces", []) + [{
            "role": "system",
            "content": (
                f"Elitism: child fitness {current_fitness:.4f} < accepted {accepted_fitness:.4f} — "
                f"reverted to parent snapshot (stagnation={stagnation_counter})"
            ),
            "timestamp": time.time(),
        }]
        return state

    # Accept child — snapshot current configs BEFORE mutation, then update bookkeeping
    state["saved_agent_configs"] = copy.deepcopy(state.get("agent_configs", []))
    state["saved_topology"] = copy.deepcopy(state.get("topology", {}))
    state["accepted_fitness"] = current_fitness
    state["stagnation_counter"] = 0
    before_edge_count = len(state.get("topology", {}).get("edges", []))

    # --- Semantic mutation (non-manufacturing configs) ---
    if state.get("scenario") == "manufacturing":
        pass
    else:
        for i, cfg in enumerate(state.get("agent_configs", [])):
            state["agent_configs"][i] = SemanticMutation(cfg)

    # --- Graph-GRPO pruning ---
    pruned = GraphGRPOPrune(state["topology"], state["edge_scores"])
    state["topology"] = pruned
    after_edge_count = len(pruned.get("edges", []))
    diff = after_edge_count - before_edge_count
    state["topology_diff"] = f"+0/{abs(diff)} edges" if diff <= 0 else f"+{diff}/0 edges"
    state["generation"] = state.get("generation", 0) + 1
    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": f"Mutation complete. Now at generation {state['generation']}",
        "timestamp": time.time(),
    }]
    return state


def checkpoint(state: ArenaState) -> ArenaState:
    """Serialize state snapshot; wire Redis here when ready."""
    key = f"arena:{state.get('run_id', 'default')}:gen:{state.get('generation', 0)}"
    state["checkpoint_key"] = key
    GenerationLog(
        gen_id=state.get("generation", 0),
        parent_fitness=state.get("parent_fitness", 0.0),
        child_fitness=state.get("current_fitness", 0.0),
        mutation_type=state.get("agent_configs", [{}])[0].get("mutation_type", "semantic")
        if state.get("agent_configs") and state["scenario"] != "manufacturing" else "semantic",
        topology_diff=state.get("topology_diff", "+0/0 edges"),
    )
    return state


# ---------------------------------------------------------------------------
# Routing helpers (not graph nodes)
# ---------------------------------------------------------------------------

def _hitl_route(state: ArenaState) -> str:
    return "hitl" if state.get("hitl_pending") else "continue"


def _continue_route(state: ArenaState) -> str:
    if state.get("generation", 0) >= state.get("max_generations", 10):
        return "done"
    return "next"


# ---------------------------------------------------------------------------
# Graph factories
# ---------------------------------------------------------------------------

def _build_full_graph() -> StateGraph:
    """Full episode graph: init → repeated agent_step cycles → END."""
    graph = StateGraph(ArenaState)

    graph.add_node("goal_intake", goal_intake)
    graph.add_node("topology_init", topology_init)
    graph.add_node("agent_step", agent_step)
    graph.add_node("evaluate", evaluate)
    graph.add_node("hitl_gate", hitl_gate)
    graph.add_node("mutate", mutate)
    graph.add_node("checkpoint", checkpoint)

    graph.set_entry_point("goal_intake")
    graph.add_edge("goal_intake", "topology_init")
    graph.add_edge("topology_init", "agent_step")
    graph.add_edge("agent_step", "evaluate")
    graph.add_edge("evaluate", "hitl_gate")
    graph.add_conditional_edges("hitl_gate", _hitl_route, {
        "hitl": "checkpoint",
        "continue": "mutate",
    })
    graph.add_edge("mutate", "checkpoint")
    graph.add_conditional_edges("checkpoint", _continue_route, {
        "done": END,
        "next": "agent_step",
    })

    return graph.compile()


def _build_step_graph() -> StateGraph:
    """Single-generation graph: agent_step → evaluate → hitl_gate → mutate/checkpoint → END."""
    graph = StateGraph(ArenaState)

    graph.add_node("agent_step", agent_step)
    graph.add_node("evaluate", evaluate)
    graph.add_node("hitl_gate", hitl_gate)
    graph.add_node("mutate", mutate)
    graph.add_node("checkpoint", checkpoint)

    graph.set_entry_point("agent_step")
    graph.add_edge("agent_step", "evaluate")
    graph.add_edge("evaluate", "hitl_gate")
    graph.add_conditional_edges("hitl_gate", _hitl_route, {
        "hitl": "checkpoint",
        "continue": "mutate",
    })
    graph.add_edge("mutate", "checkpoint")
    graph.add_edge("checkpoint", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _make_initial_state(scenario: str, run_id: str, max_generations: int) -> ArenaState:
    return ArenaState(
        scenario=scenario,
        objective="",
        agent_configs=[],
        topology={},
        current_fitness=0.0,
        parent_fitness=0.0,
        accepted_fitness=0.0,
        saved_agent_configs=[],
        saved_topology={},
        topology_diff="+0/0 edges",
        latency=0.0,
        cost=0.0,
        generation=0,
        max_generations=max_generations,
        hitl_pending=False,
        confidence=1.0,
        edge_scores={},
        checkpoint_key="",
        run_id=run_id,
        traces=[],
        stagnation_counter=0,
        fitness_history=[],
        prev_penalty_cost=0.0,
        taguchi_baseline_log=[],
        genome_config={},
    )


async def run_orchestrator(
    scenario: str,
    run_id: str,
    max_generations: int = 5,
) -> dict:
    """Run the full orchestrator graph (init + N generation cycles) and return final state."""
    graph = _build_full_graph()
    initial = _make_initial_state(scenario, run_id, max_generations)
    result = await graph.ainvoke(
        initial,
        config={"recursion_limit": max_generations * 10 + 20},
    )
    return dict(result)


async def run_one_generation(existing_state: dict) -> dict:
    """Run a single LangGraph generation cycle from agent_step onwards."""
    # Ensure new fields are present for backward compatibility with older states
    existing_state.setdefault("stagnation_counter", 0)
    existing_state.setdefault("fitness_history", [])
    existing_state.setdefault("prev_penalty_cost", 0.0)
    existing_state.setdefault("taguchi_baseline_log", [])
    existing_state.setdefault("accepted_fitness", existing_state.get("current_fitness", 0.0))
    existing_state.setdefault("genome_config", {})
    existing_state.setdefault("saved_agent_configs", existing_state.get("agent_configs", []))
    existing_state.setdefault("saved_topology", existing_state.get("topology", {}))

    graph = _build_step_graph()
    result = await graph.ainvoke(
        existing_state,
        config={"recursion_limit": 20},
    )
    return dict(result)
