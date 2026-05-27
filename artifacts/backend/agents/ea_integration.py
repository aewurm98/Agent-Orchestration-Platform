"""
DEAP-backed evolutionary algorithm wrapper for the Arena orchestrator.

Adds a population-based EA (selection + crossover + mutation + minibatch evaluation)
that plugs into orchestrator.mutate() as a third `mutation_strategy` alongside
"MATH" and "LLM". Existing (1+1) elitism in the orchestrator still runs around
this wrapper — DEAP only proposes the next genome.

Public API:
    run_one_generation(state) -> dict
        Selects/mates/mutates a population, evaluates via minibatch, and returns
        a partial state update {genome_config, ea_population, population_stats,
        traces_to_append}. The orchestrator merges this in.

    available() -> bool
        True if deap is importable. False enables silent fallback to MATH.

Per-scenario plumbing is dispatched through a small strategy registry. Only
`manufacturing` is feature-complete in Phase 1; other scenarios raise
StrategyNotImplemented and the orchestrator must keep them on MATH/LLM until
Phase 3+.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class StrategyNotImplemented(Exception):
    """Raised when a scenario does not yet have a DEAP strategy registered."""


def available() -> bool:
    try:
        import deap  # noqa: F401
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Strategy registry: per-scenario encode/decode/mutate/evaluate
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EAStrategy:
    """Per-scenario hooks that translate a genome dict into DEAP-friendly ops."""
    name: str
    # genome_dict -> flat encoded list (DEAP individual payload)
    encode: Callable[[dict], list]
    # flat list -> genome_dict
    decode: Callable[[list], dict]
    # genome_dict -> fitness scalar (and optionally a vector for MOO)
    evaluate: Callable[[dict, dict], tuple[float, Optional[list[float]]]]
    # genome_dict -> mutated genome_dict (bounds-aware)
    mutate: Callable[[dict, random.Random], dict]
    # (parent_a, parent_b, rng) -> (child_a, child_b)
    crossover: Callable[[dict, dict, random.Random], tuple[dict, dict]]
    # genome_dict factory used to seed the initial population
    random_individual: Callable[[random.Random], dict]


_STRATEGIES: dict[str, EAStrategy] = {}


def register_strategy(strategy: EAStrategy) -> None:
    _STRATEGIES[strategy.name] = strategy


def get_strategy(name: str) -> EAStrategy:
    if name not in _STRATEGIES:
        raise StrategyNotImplemented(
            f"No DEAP strategy registered for scenario '{name}'. "
            f"Available: {sorted(_STRATEGIES.keys())}"
        )
    return _STRATEGIES[name]


# ─────────────────────────────────────────────────────────────────────────────
# Manufacturing strategy
# ─────────────────────────────────────────────────────────────────────────────

def _mfg_encode(genome: dict) -> list:
    from evolution.manufacturing_genome import ManufacturingGenome
    g = ManufacturingGenome.from_dict(genome) if "agent_counts" in genome else ManufacturingGenome.default()
    return g.encode()


def _mfg_decode(vec: list) -> dict:
    from evolution.manufacturing_genome import ManufacturingGenome
    return ManufacturingGenome.decode(vec).to_dict()


def _mfg_mutate(genome: dict, rng: random.Random) -> dict:
    from evolution.manufacturing_genome import ManufacturingGenome
    g = ManufacturingGenome.from_dict(genome)
    mutated = g.mutate(rng)
    return mutated.to_dict()


def _mfg_crossover(a: dict, b: dict, rng: random.Random) -> tuple[dict, dict]:
    # Uniform crossover on agent_counts and machine_speeds; arithmetic mean on order_rate.
    # Keeps bounds intact because parents already respected them.
    child_a = copy.deepcopy(a)
    child_b = copy.deepcopy(b)
    for role in a.get("agent_counts", {}):
        if rng.random() < 0.5:
            child_a["agent_counts"][role], child_b["agent_counts"][role] = (
                b["agent_counts"].get(role, a["agent_counts"][role]),
                a["agent_counts"][role],
            )
    for mid in a.get("machine_speeds", {}):
        if rng.random() < 0.5:
            child_a["machine_speeds"][mid], child_b["machine_speeds"][mid] = (
                b["machine_speeds"].get(mid, a["machine_speeds"][mid]),
                a["machine_speeds"][mid],
            )
    if rng.random() < 0.5:
        mean_rate = (a.get("order_arrival_rate", 12.0) + b.get("order_arrival_rate", 12.0)) / 2.0
        child_a["order_arrival_rate"] = round(mean_rate, 1)
        child_b["order_arrival_rate"] = round(mean_rate, 1)
    return child_a, child_b


def _mfg_random(rng: random.Random) -> dict:
    return {
        "agent_counts": {
            "procurement": rng.randint(1, 5),
            "operations": rng.randint(1, 8),
            "engineering": rng.randint(1, 3),
            "sales": rng.randint(1, 4),
            "management": 1,
        },
        "machine_speeds": {
            mid: rng.choice(["low", "normal", "high"])
            for mid in ["smelter_1", "circuit_fab_1", "press_1", "assembly_1", "qc_1", "packaging_1"]
        },
        "order_arrival_rate": round(rng.uniform(5.0, 30.0), 1),
    }


def _mfg_evaluate(genome: dict, state: dict) -> tuple[float, Optional[list[float]]]:
    # Reuse the existing minibatch evaluator — already spec-compliant (3 seeds × 500 ticks).
    # Contract: evaluate_genome_minibatch(genome_dict, ticks=500, seeds=DEFAULT_SEEDS)
    #          returns {"fitness", "fitness_vector", "metrics", "per_seed"}.
    from evolution.minibatch import evaluate_genome_minibatch
    seeds = tuple(state.get("ea_minibatch_seeds") or (42, 101, 777))
    ticks = int(state.get("ea_ticks_per_episode", 500))
    try:
        result = evaluate_genome_minibatch(genome, ticks=ticks, seeds=seeds)
        scalar = float(result.get("fitness", 0.0))
        vector = result.get("fitness_vector")
        return scalar, vector
    except Exception:
        # Robustness: if env eval throws, return -inf so this individual dies in selection.
        return float("-inf"), None


register_strategy(EAStrategy(
    name="manufacturing",
    encode=_mfg_encode,
    decode=_mfg_decode,
    evaluate=_mfg_evaluate,
    mutate=_mfg_mutate,
    crossover=_mfg_crossover,
    random_individual=_mfg_random,
))


# ─────────────────────────────────────────────────────────────────────────────
# Supply chain strategy
# ─────────────────────────────────────────────────────────────────────────────

_SC_BOUNDS = {
    "fleet_size":                    (1, 10),
    "supply_rate":                   (5, 80),
    "transfer_amount":               (10, 80),
    "warehouse_restock_threshold":   (0.2, 0.8),
}


def _sc_default_genome() -> dict:
    from game_envs.supply_chain import SupplyChainEnv
    return dict(SupplyChainEnv.GENOME_DEFAULTS)


def _sc_encode(genome: dict) -> list:
    d = {**_sc_default_genome(), **genome}
    return [
        int(d["fleet_size"]),
        int(d["supply_rate"]),
        int(d["transfer_amount"]),
        float(d["warehouse_restock_threshold"]),
    ]


def _sc_decode(vec: list) -> dict:
    return {
        "fleet_size": int(vec[0]),
        "supply_rate": int(vec[1]),
        "transfer_amount": int(vec[2]),
        "warehouse_restock_threshold": round(float(vec[3]), 2),
    }


def _sc_random(rng: random.Random) -> dict:
    return {
        "fleet_size": rng.randint(*_SC_BOUNDS["fleet_size"]),
        "supply_rate": rng.randint(*_SC_BOUNDS["supply_rate"]),
        "transfer_amount": rng.randint(*_SC_BOUNDS["transfer_amount"]),
        "warehouse_restock_threshold": round(rng.uniform(*_SC_BOUNDS["warehouse_restock_threshold"]), 2),
    }


def _sc_clip(genome: dict) -> dict:
    g = dict(genome)
    for k, (lo, hi) in _SC_BOUNDS.items():
        if k in g:
            v = g[k]
            v = max(lo, min(hi, v))
            g[k] = round(v, 2) if isinstance(lo, float) else int(v)
    return g


def _sc_mutate(genome: dict, rng: random.Random) -> dict:
    g = {**_sc_default_genome(), **genome}
    field = rng.choice(list(_SC_BOUNDS.keys()))
    lo, hi = _SC_BOUNDS[field]
    if isinstance(lo, float):
        delta = rng.uniform(-0.05, 0.08)
        g[field] = round(max(lo, min(hi, float(g[field]) + delta)), 2)
    else:
        delta = rng.choice([-3, -1, 1, 3, 5])
        g[field] = max(lo, min(hi, int(g[field]) + delta))
    return g


def _sc_crossover(a: dict, b: dict, rng: random.Random) -> tuple[dict, dict]:
    ca = {**_sc_default_genome(), **a}
    cb = {**_sc_default_genome(), **b}
    for key in _SC_BOUNDS:
        if rng.random() < 0.5:
            ca[key], cb[key] = cb.get(key, ca[key]), ca.get(key, cb.get(key))
    return _sc_clip(ca), _sc_clip(cb)


def _sc_evaluate(genome: dict, state: dict) -> tuple[float, Optional[list[float]]]:
    """Spin up a fresh SupplyChainEnv, apply the genome, run a 500-tick episode,
    return GLS as the fitness scalar plus a per-component vector [revenue,
    capex, opex, penalties] for future multi-objective use.
    """
    from game_envs.supply_chain import SupplyChainEnv, EPISODE_TICKS
    try:
        env = SupplyChainEnv()
        env.apply_genome(genome)
        ticks = int(state.get("ea_ticks_per_episode", EPISODE_TICKS))
        for _ in range(ticks):
            if getattr(env, "done", False):
                break
            env.step()
        gls = float(env.get_fitness())
        # Component vector — negate cost terms so larger-is-better stays consistent.
        vector = [
            float(env.revenue),
            -float(env.capex),
            -float(env.opex),
            -float(env.penalties),
        ]
        return gls, vector
    except Exception:
        return float("-inf"), None


register_strategy(EAStrategy(
    name="supply_chain",
    encode=_sc_encode,
    decode=_sc_decode,
    evaluate=_sc_evaluate,
    mutate=_sc_mutate,
    crossover=_sc_crossover,
    random_individual=_sc_random,
))


# ─────────────────────────────────────────────────────────────────────────────
# Population storage + fitness cache (persisted across calls inside state[])
# ─────────────────────────────────────────────────────────────────────────────

def _genome_hash(genome: dict) -> str:
    payload = json.dumps(genome, sort_keys=True, default=str).encode()
    return hashlib.sha1(payload).hexdigest()[:16]


def _load_population(state: dict, strategy: EAStrategy, rng: random.Random) -> list[dict]:
    """Returns [{genome, fitness, vector, hash}, ...]. Seeded on first call."""
    pop = state.get("ea_population")
    if pop:
        return pop
    pop_size = int(state.get("ea_population_size", 8))
    seeds: list[dict] = []
    # Anchor individual 0 to the current genome_config so we don't lose the warm start.
    if state.get("genome_config"):
        seeds.append(copy.deepcopy(state["genome_config"]))
    while len(seeds) < pop_size:
        seeds.append(strategy.random_individual(rng))
    return [{"genome": g, "fitness": None, "vector": None, "hash": _genome_hash(g)} for g in seeds]


def _evaluate_population(pop: list[dict], strategy: EAStrategy, state: dict, cache: dict) -> None:
    """Fills fitness/vector on any individuals missing it. Memoized by genome hash."""
    for ind in pop:
        if ind["fitness"] is not None:
            continue
        h = ind["hash"]
        if h in cache:
            ind["fitness"], ind["vector"] = cache[h]
            continue
        f, v = strategy.evaluate(ind["genome"], state)
        ind["fitness"], ind["vector"] = f, v
        cache[h] = (f, v)


def _tournament_select(pop: list[dict], k: int, rng: random.Random, tournsize: int = 3) -> list[dict]:
    selected = []
    for _ in range(k):
        contenders = rng.sample(pop, min(tournsize, len(pop)))
        winner = max(contenders, key=lambda ind: ind["fitness"] if ind["fitness"] is not None else float("-inf"))
        selected.append(copy.deepcopy(winner))
    return selected


def _population_stats(pop: list[dict]) -> dict:
    fits = [ind["fitness"] for ind in pop if ind["fitness"] is not None]
    if not fits:
        return {"size": len(pop), "best": None, "mean": None, "worst": None}
    return {
        "size": len(pop),
        "best": max(fits),
        "mean": sum(fits) / len(fits),
        "worst": min(fits),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point: run one generation
# ─────────────────────────────────────────────────────────────────────────────

def run_one_generation(state: dict) -> dict:
    """Run a single (μ+λ) generation on the population in state['ea_population'].

    Returns a partial state-update dict. Caller (orchestrator.mutate) should merge it in.

    The returned dict contains:
        genome_config: best child genome to propose this generation
        ea_population: updated population list
        ea_fitness_cache: updated cache
        population_stats: {best, mean, worst, size} for UI / logs
        traces_to_append: list[dict] of trace events
    """
    scenario = state.get("scenario", "")
    strategy = get_strategy(scenario)

    seed = state.get("ea_seed", int(os.environ.get("ARENA_EA_SEED", "0")) or random.randint(0, 1 << 30))
    rng = random.Random(seed + state.get("generation", 0))

    cache = dict(state.get("ea_fitness_cache") or {})
    population = _load_population(state, strategy, rng)

    _evaluate_population(population, strategy, state, cache)

    population.sort(key=lambda ind: ind["fitness"] if ind["fitness"] is not None else float("-inf"), reverse=True)
    elite_keep = max(1, int(state.get("ea_elite_keep", 2)))
    elites = [copy.deepcopy(ind) for ind in population[:elite_keep]]

    cx_prob = float(state.get("ea_crossover_prob", 0.6))
    mut_prob = float(state.get("ea_mutation_prob", 0.4))
    offspring_needed = len(population) - elite_keep

    parents = _tournament_select(population, offspring_needed, rng, tournsize=3)
    offspring: list[dict] = []
    i = 0
    while i < len(parents):
        a = parents[i]["genome"]
        b = parents[(i + 1) % len(parents)]["genome"]
        if rng.random() < cx_prob:
            ca, cb = strategy.crossover(a, b, rng)
        else:
            ca, cb = copy.deepcopy(a), copy.deepcopy(b)
        if rng.random() < mut_prob:
            ca = strategy.mutate(ca, rng)
        if rng.random() < mut_prob:
            cb = strategy.mutate(cb, rng)
        offspring.append({"genome": ca, "fitness": None, "vector": None, "hash": _genome_hash(ca)})
        if len(offspring) < offspring_needed:
            offspring.append({"genome": cb, "fitness": None, "vector": None, "hash": _genome_hash(cb)})
        i += 2

    _evaluate_population(offspring, strategy, state, cache)

    new_population = elites + offspring
    new_population.sort(key=lambda ind: ind["fitness"] if ind["fitness"] is not None else float("-inf"), reverse=True)
    best = new_population[0]
    stats = _population_stats(new_population)

    trace = {
        "role": "system",
        "content": (
            f"DEAP gen: best={stats['best']:.4f} mean={stats['mean']:.4f} "
            f"worst={stats['worst']:.4f} pop={stats['size']} "
            f"(cx={cx_prob} mut={mut_prob} elite={elite_keep})"
        ),
        "timestamp": time.time(),
    }

    return {
        "genome_config": best["genome"],
        "ea_population": new_population,
        "ea_fitness_cache": cache,
        "population_stats": stats,
        "traces_to_append": [trace],
        "ea_best_vector": best.get("vector"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test (does not require deap to import — strategy registry only).
# Run: python -m agents.ea_integration
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"DEAP available: {available()}")
    print(f"Registered strategies: {sorted(_STRATEGIES.keys())}")
    rng = random.Random(42)
    s = get_strategy("manufacturing")
    g = s.random_individual(rng)
    print("Random individual:", json.dumps(g, indent=2, default=str))
    g2 = s.mutate(g, rng)
    print("Mutated:", json.dumps(g2, indent=2, default=str))
    g3, g4 = s.crossover(g, g2, rng)
    print("Crossover children:", _genome_hash(g3), _genome_hash(g4))
