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
    policy_mode: str                 # "llm" | "scripted" | "random" — gates LLM calls in agent_step
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
    genome_config: dict              # ManufacturingGenome.to_dict() for manufacturing
    boundary_mode: str               # "INTRA" continuous | "INTER" episodic per-generation reset
    mutation_strategy: str           # "MATH" heuristic perturbation | "LLM" meta-optimizer
    inter_ticks: int                 # episode length (ticks) used in INTER mode
    inter_episode_done: bool         # True when main.py has already run the episode; agent_step skips it


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
    a FRESH env (tick=0) instantiated from the winning genome config — evaluation
    envs are discarded so generation-0 always starts from a clean initial state.
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

    # Instantiate a FRESH env from the winning genome config — the stepped evaluation
    # envs are discarded; generation-0 always starts from tick 0 with the best config.
    if best_genome is not None:
        best_env = ManufacturingEnvV2(best_genome.to_env_config())
    else:
        best_env = None

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
    """Run one tick (INTRA) or a full episode (INTER) of the active agent population.

    INTER mode: reset env with the current genome, run exactly T_max ticks using
    ScriptedGreedyPolicy, then return so evaluate() can score cumulative fitness.
    INTRA mode (default): invoke one LLM step when policy_mode == "llm"; otherwise
    the env is ticked in the outer main.py loop and this node is a lightweight hook.
    """
    scenario = state.get("scenario", "")
    boundary_mode = state.get("boundary_mode", "INTRA")

    if scenario == "manufacturing":
        from agents import manufacturing_roles
        generation = state.get("generation", 0)

        if boundary_mode == "INTER":
            if state.get("inter_episode_done", False):
                # ── Episode already run by main.py; just record a trace ──────
                _done_env = manufacturing_roles._env_v2
                _ticks_done = _done_env.world.tick if (_done_env and hasattr(_done_env, "world")) else 0
                _fit_done = _done_env.get_fitness() if _done_env else 0.0
                state["traces"] = state.get("traces", []) + [{
                    "role": "system",
                    "content": (
                        f"[Gen {generation}] INTER episode: "
                        f"{_ticks_done} ticks, "
                        f"fitness={round(_fit_done, 4)}"
                    ),
                    "timestamp": time.time(),
                }]
            else:
                # ── Fallback: run episode inline (backward compat) ────────────
                from evolution.manufacturing_genome import ManufacturingGenome
                from game_envs.manufacturing_v2.env import ManufacturingEnvV2
                from agents.manufacturing_policies import ScriptedGreedyPolicy

                genome_cfg = state.get("genome_config", {})
                if genome_cfg and "agent_counts" in genome_cfg:
                    genome = ManufacturingGenome.from_dict(genome_cfg)
                else:
                    genome = ManufacturingGenome.default()

                new_env = ManufacturingEnvV2(genome.to_env_config())
                manufacturing_roles.set_active_env_v2(new_env)

                T_max = state.get("inter_ticks", 100)
                policy = ScriptedGreedyPolicy()
                ticks_run = 0
                for _ in range(T_max):
                    if new_env.done:
                        break
                    actions = policy.get_all_actions(new_env.world)
                    new_env.world.tick_advance(actions)
                    ticks_run += 1

                state["traces"] = state.get("traces", []) + [{
                    "role": "system",
                    "content": (
                        f"[Gen {generation}] INTER episode (inline): "
                        f"{ticks_run}/{T_max} ticks, "
                        f"fitness={round(new_env.get_fitness(), 4)}"
                    ),
                    "timestamp": time.time(),
                }]

        else:
            # ── INTRA: single LLM step when policy demands it ────────────────
            env = manufacturing_roles._env_v2 or manufacturing_roles._env
            if state.get("policy_mode", "scripted") == "llm" and env is not None:
                from agents.manufacturing_roles import run_manufacturing_v2_step
                new_traces = await run_manufacturing_v2_step(generation, env)
                state["traces"] = state.get("traces", []) + new_traces

    else:
        for _cfg in state.get("agent_configs", []):
            pass

    state["traces"] = state.get("traces", []) + [{
        "role": "orchestrator",
        "content": f"[Gen {state['generation']}] Agent step complete ({boundary_mode})",
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
                kappa -= 0.3   # spec constant; combined with missed-orders drives kappa to 0.3

    fitness_history = state.get("fitness_history", [])
    if len(fitness_history) >= 3:
        last_three = fitness_history[-3:]
        if last_three[0] > last_three[1] > last_three[2]:
            kappa -= 0.3       # spec constant; combined with missed-orders drives kappa to 0.3

    return round(max(0.0, min(1.0, kappa)), 2)


def evaluate(state: ArenaState) -> ArenaState:
    """Score generation with CLEAR fitness function and metric-derived confidence."""
    latency = random.uniform(0.2, 1.5)
    cost = random.uniform(0.001, 0.05)
    success_rate = random.uniform(0.3, 0.95)

    if state.get("scenario") == "manufacturing":
        from agents import manufacturing_roles
        from agents.manufacturing_roles import sweep_edge_scores
        env = manufacturing_roles._env_v2 or manufacturing_roles._env
        if env is not None:
            if hasattr(env, "get_objective_value"):
                success_rate = env.get_objective_value()
            else:
                success_rate = env.get_fitness()

            # Sweep edge credit scores every 5 ticks — policy-agnostic so it
            # always runs regardless of scripted / random / llm mode.
            tick = env.world.tick if hasattr(env, "world") else 0
            if tick > 0 and tick % 5 == 0:
                sweep_edge_scores(tick)

        # Pull updated edge scores from the credit assignment module
        updated_edge_scores = dict(manufacturing_roles._edge_scores)
        if updated_edge_scores:
            merged = dict(state.get("edge_scores", {}))
            merged.update(updated_edge_scores)
            state["edge_scores"] = merged

    state["parent_fitness"] = state.get("current_fitness", 0.0)

    if state.get("scenario") == "manufacturing":
        # For manufacturing: use real env fitness directly — no synthetic latency/cost noise
        from agents import manufacturing_roles as _mr
        _env = _mr._env_v2 or _mr._env
        real_fitness = _env.get_fitness() if _env is not None else success_rate
        state["current_fitness"] = round(real_fitness, 4)
        state["latency"] = round(latency, 3)
        state["cost"] = round(cost, 5)
    else:
        fitness = FitnessScore(success_rate=success_rate, latency=latency, cost=cost)
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


def _apply_edge_regrowth(state: ArenaState) -> None:
    """
    With 5% probability, add a random directed edge at score 0.5 to the topology.
    Mutates state in-place. Called after each elitism decision (both accept and reject)
    so regrowth applies every generation and persists regardless of accept/reject outcome.
    """
    nodes = state.get("topology", {}).get("nodes", [])
    if not nodes or random.random() >= 0.05:
        return
    src = random.choice(nodes)
    tgt = random.choice(nodes)
    if src == tgt:
        return
    existing = state["topology"].get("edges", [])
    existing_set = {(e[0], e[1]) if isinstance(e, (list, tuple)) else e for e in existing}
    new_edge = (src, tgt)
    if new_edge in existing_set:
        return
    state["topology"] = copy.deepcopy(state["topology"])
    state["topology"]["edges"] = list(existing) + [new_edge]
    edge_key = f"{src}->{tgt}"
    if edge_key not in state.get("edge_scores", {}):
        state["edge_scores"] = dict(state.get("edge_scores", {}))
        state["edge_scores"][edge_key] = 0.5
    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": f"Edge regrowth: sprouted {edge_key} at score 0.5",
        "timestamp": time.time(),
    }]


async def mutate(state: ArenaState) -> ArenaState:
    """Apply genome mutation + Graph-GRPO edge pruning with (1+1)-EA elitism.

    Mutation strategy:
      MATH — ManufacturingGenome.mutate() heuristic perturbation (or SemanticMutation
             for non-manufacturing scenarios).
      LLM  — Meta-optimizer: build episode digest, query gpt-5-mini, apply JSON delta
             to genome_config; falls back to MATH on any LLM error.

    Boundary mode:
      INTRA — genome changes apply to the continuously running env on the next step.
      INTER — genome changes are picked up by agent_step's env reset next generation.

    Elitism:
      Child accepted when current_fitness >= immediate parent_fitness.
      Rejected child: restore parent snapshot + increment stagnation_counter.
      accepted_fitness tracks the all-time elitism best (monotone non-decreasing).

    Edge regrowth: with 5% probability a random directed edge is added at score 0.5,
    applied on both accept and reject so every generation has a chance of regrowth.
    """
    current_fitness = state.get("current_fitness", 0.0)
    parent_fitness = state.get("parent_fitness", 0.0)
    accepted_fitness = state.get("accepted_fitness", 0.0)
    stagnation_counter = state.get("stagnation_counter", 0)

    # (1+1)-EA: child accepted only when it improves upon the IMMEDIATE parent
    if current_fitness < parent_fitness:
        # Child is worse than the immediate parent — reject and RESTORE parent snapshot
        stagnation_counter += 1
        state["stagnation_counter"] = stagnation_counter

        saved_configs = state.get("saved_agent_configs")
        saved_topo = state.get("saved_topology")
        if saved_configs is not None:
            state["agent_configs"] = copy.deepcopy(saved_configs)
        if saved_topo is not None:
            state["topology"] = copy.deepcopy(saved_topo)

        # Restore fitness state so rejected child does not become next parent baseline
        state["current_fitness"] = parent_fitness

        # Edge regrowth on rejection: apply to the restored topology so the 5% chance
        # is truly per-generation and the sprouted edge persists in the restored parent.
        _apply_edge_regrowth(state)

        state["topology_diff"] = "+0/0 edges (elitism: reverted)"
        state["generation"] = state.get("generation", 0) + 1
        state["traces"] = state.get("traces", []) + [{
            "role": "system",
            "content": (
                f"Elitism: child fitness {current_fitness:.4f} < parent {parent_fitness:.4f} — "
                f"reverted to parent snapshot (stagnation={stagnation_counter})"
            ),
            "timestamp": time.time(),
        }]
        return state

    # Accept child — snapshot current configs BEFORE mutation, then update bookkeeping.
    # Also track all-time best in accepted_fitness for stagnation analytics.
    state["saved_agent_configs"] = copy.deepcopy(state.get("agent_configs", []))
    state["saved_topology"] = copy.deepcopy(state.get("topology", {}))

    # Edge regrowth on acceptance: applied after snapshot so the restored snapshot is
    # clean, but the live topology may grow a new edge before pruning.
    _apply_edge_regrowth(state)
    state["accepted_fitness"] = max(current_fitness, accepted_fitness)
    state["stagnation_counter"] = 0
    before_edge_count = len(state.get("topology", {}).get("edges", []))

    # ── Genome / agent-config mutation ────────────────────────────────────────
    scenario = state.get("scenario", "")
    mutation_strategy = state.get("mutation_strategy", "MATH")

    mutation_label = mutation_strategy

    if mutation_strategy == "LLM":
        # ── LLM meta-optimizer path ───────────────────────────────────────────
        print(
            f"[LLM] Calling meta-optimizer — gen={state.get('generation', 0)}, "
            f"scenario={scenario}, boundary={state.get('boundary_mode', 'INTRA')}"
        )
        try:
            from agents.meta_optimizer import query_meta_optimizer, apply_genome_delta
            from agents import manufacturing_roles as _mr
            _meta_env = _mr._env_v2 if scenario == "manufacturing" else None
            delta = await query_meta_optimizer(state, _meta_env)
            state["genome_config"] = apply_genome_delta(
                state.get("genome_config", {}), delta, scenario
            )
            reasoning = state.get("genome_config", {}).get("_llm_reasoning", "")
            print(f"[LLM] Meta-optimizer succeeded — reasoning: {reasoning[:120] if reasoning else '(none)'}")
            if reasoning:
                state["traces"] = state.get("traces", []) + [{
                    "role": "system",
                    "content": f"LLM meta-optimizer: {reasoning}",
                    "timestamp": time.time(),
                }]
        except Exception as _llm_exc:
            print(f"[LLM] Meta-optimizer FAILED ({_llm_exc!r}) — falling back to MATH")
            mutation_strategy = "MATH"
            mutation_label = "LLM→MATH(fallback)"

    if mutation_strategy == "MATH":
        # ── Heuristic perturbation path ───────────────────────────────────────
        if scenario == "manufacturing":
            from evolution.manufacturing_genome import ManufacturingGenome
            genome_cfg = state.get("genome_config", {})
            if genome_cfg and "agent_counts" in genome_cfg:
                genome = ManufacturingGenome.from_dict(genome_cfg)
            else:
                genome = ManufacturingGenome.default()
            mutated = genome.mutate()
            state["genome_config"] = mutated.to_dict()
            state["traces"] = state.get("traces", []) + [{
                "role": "system",
                "content": (
                    f"MATH mutation: genome → "
                    f"agents={mutated.agent_counts}, "
                    f"order_rate={mutated.order_arrival_rate}"
                ),
                "timestamp": time.time(),
            }]
        else:
            for i, cfg in enumerate(state.get("agent_configs", [])):
                state["agent_configs"][i] = SemanticMutation(cfg)

    # ── Graph-GRPO pruning ────────────────────────────────────────────────────
    pruned = GraphGRPOPrune(state["topology"], state["edge_scores"])
    state["topology"] = pruned
    after_edge_count = len(pruned.get("edges", []))
    diff = after_edge_count - before_edge_count
    state["topology_diff"] = f"+0/{abs(diff)} edges" if diff <= 0 else f"+{diff}/0 edges"
    state["generation"] = state.get("generation", 0) + 1
    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": (
            f"Mutation complete [{mutation_label}]. "
            f"Now at generation {state['generation']}"
        ),
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
    # hitl_gate always proceeds to mutate — elitism and generation increment must
    # always execute.  HITL pause is handled in main.py by checking hitl_pending
    # after run_one_generation returns; the graph itself never skips mutate.
    graph.add_edge("hitl_gate", "mutate")
    graph.add_edge("mutate", "checkpoint")
    graph.add_conditional_edges("checkpoint", _continue_route, {
        "done": END,
        "next": "agent_step",
    })

    return graph.compile()


def _build_step_graph() -> StateGraph:
    """Single-generation graph: agent_step → evaluate → hitl_gate → mutate → checkpoint → END.

    hitl_gate only sets the hitl_pending flag; it never bypasses mutate.
    Elitism and generation increment run every cycle without exception.
    """
    graph = StateGraph(ArenaState)

    graph.add_node("agent_step", agent_step)
    graph.add_node("evaluate", evaluate)
    graph.add_node("hitl_gate", hitl_gate)
    graph.add_node("mutate", mutate)
    graph.add_node("checkpoint", checkpoint)

    graph.set_entry_point("agent_step")
    graph.add_edge("agent_step", "evaluate")
    graph.add_edge("evaluate", "hitl_gate")
    graph.add_edge("hitl_gate", "mutate")
    graph.add_edge("mutate", "checkpoint")
    graph.add_edge("checkpoint", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _make_initial_state(
    scenario: str,
    run_id: str,
    max_generations: int,
    boundary_mode: str = "INTRA",
    mutation_strategy: str = "MATH",
    inter_ticks: int = 100,
) -> ArenaState:
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
        policy_mode="scripted",
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
        boundary_mode=boundary_mode,
        mutation_strategy=mutation_strategy,
        inter_ticks=inter_ticks,
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
    existing_state.setdefault("policy_mode", "scripted")
    existing_state.setdefault("boundary_mode", "INTRA")
    existing_state.setdefault("mutation_strategy", "MATH")
    existing_state.setdefault("inter_ticks", 100)
    existing_state.setdefault("inter_episode_done", False)

    graph = _build_step_graph()
    result = await graph.ainvoke(
        existing_state,
        config={"recursion_limit": 20},
    )
    return dict(result)
