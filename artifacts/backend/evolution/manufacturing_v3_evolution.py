"""
Manufacturing v3 evolutionary driver (spec §5 — (mu + lambda) EA).

Each generation:
  1. The incumbent (mu = 1) is the best genome found so far.
  2. lambda = 3 offspring are proposed by the LLM meta-optimizer (or MATH fallback).
  3. Every genome is scored by a stochastic-seed mini-batch so the EA never
     over-fits a single lucky breakdown sequence (mirrors the v2 design).
  4. (mu + lambda) selection keeps the single best of {incumbent} U {offspring}.

The driver is engine-agnostic: pass engine="LLM" to call Anthropic, or "MATH"
for a fully-offline heuristic run (used by the test-suite and stress test).
"""
from __future__ import annotations

import logging
import random
from typing import Optional

from game_envs.manufacturing_v3.env import ManufacturingV3Env
from game_envs.manufacturing_v3.genome import ManufacturingV3Genome

log = logging.getLogger(__name__)

DEFAULT_SEEDS: tuple[int, ...] = (42, 101, 777)
EPISODE_TICKS = 500


def evaluate_genome(
    genome: ManufacturingV3Genome | dict,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    ticks: int = EPISODE_TICKS,
) -> dict:
    """Run a genome once per seed, returning mean fitness and averaged metrics.

    Returns:
        {
          "fitness":  float,          # mean over seeds
          "per_seed": list[dict],     # {seed, fitness}
          "metrics":  dict,           # averaged headline metrics + node diagnostics
        }
    """
    if isinstance(genome, dict):
        genome = ManufacturingV3Genome.from_dict(genome)

    scalars: list[float] = []
    metric_rows: list[dict] = []
    per_seed: list[dict] = []
    for seed in seeds:
        env = ManufacturingV3Env(genome.clone(), simulation_length=ticks, seed=seed)
        env.run()
        f = env.get_fitness()
        scalars.append(f)
        metric_rows.append(env.get_metrics())
        per_seed.append({"seed": seed, "fitness": f})

    n = max(1, len(scalars))
    mean_fitness = round(sum(scalars) / n, 2)

    def avg(key: str) -> float:
        return round(sum(float(r.get(key, 0.0)) for r in metric_rows) / n, 2)

    metrics = {
        "fitness": mean_fitness,
        "orders_received": round(avg("orders_received")),
        "orders_fulfilled": round(avg("orders_fulfilled")),
        "orders_missed": round(avg("orders_missed")),
        "throughput": round(avg("orders_fulfilled")),
        "total_revenue": avg("total_revenue"),
        "total_opex": avg("total_opex"),
        "total_material_cost": avg("total_material_cost"),
        "penalties": avg("penalties"),
        "seeds": list(seeds),
        "ticks": ticks,
    }
    # Average node diagnostics across seeds (queues / utilization are stable).
    from game_envs.manufacturing_v3.genome import MACHINE_IDS

    node_diag: dict[str, dict] = {}
    for mid in MACHINE_IDS:
        rows = [r["node_diagnostics"][mid] for r in metric_rows if mid in r.get("node_diagnostics", {})]
        if not rows:
            continue
        node_diag[mid] = {
            "utilization": round(sum(x["utilization"] for x in rows) / len(rows), 3),
            "avg_input_queue": round(sum(x["avg_input_queue"] for x in rows) / len(rows), 2),
            "avg_output_queue": round(sum(x["avg_output_queue"] for x in rows) / len(rows), 2),
            "failure_count": sum(x["failure_count"] for x in rows),
            "capacity": rows[0]["capacity"],
        }
    metrics["node_diagnostics"] = node_diag

    return {"fitness": mean_fitness, "per_seed": per_seed, "metrics": metrics}


async def run_generation(state: dict) -> dict:
    """Advance the (mu + lambda) EA by one generation. Mutates and returns `state`.

    Expected/maintained state keys:
      genome (dict), generation (int), engine ("LLM"|"MATH"), seeds (tuple),
      best_fitness (float), history (list[dict]), parent_metrics (dict),
      rng_seed (int), reasoning (str), candidate_log (list[dict]).
    """
    engine = str(state.get("engine", "MATH")).upper()
    seeds = tuple(state.get("seeds", DEFAULT_SEEDS))
    generation = int(state.get("generation", 0))
    rng = random.Random(int(state.get("rng_seed", 12345)) + generation)

    parent = ManufacturingV3Genome.from_dict(state.get("genome") or {})

    # Incumbent score: reuse last generation's evaluation when available, else evaluate.
    if "best_fitness" in state and state.get("parent_metrics"):
        parent_fitness = float(state["best_fitness"])
        parent_metrics = state["parent_metrics"]
    else:
        ev = evaluate_genome(parent, seeds)
        parent_fitness, parent_metrics = ev["fitness"], ev["metrics"]

    # ── Propose lambda offspring ──────────────────────────────────────────────
    if engine == "LLM":
        from agents.manufacturing_v3_optimizer import query_candidates

        history = state.get("history", [])
        offspring = await query_candidates(parent, parent_metrics, history, rng=rng)
    else:
        from agents.manufacturing_v3_optimizer import math_candidates

        offspring = math_candidates(parent, rng=rng)

    # ── Evaluate offspring; (mu + lambda) selection ───────────────────────────
    pool = [{
        "genome": parent,
        "fitness": parent_fitness,
        "metrics": parent_metrics,
        "reasoning": "(incumbent)",
        "is_parent": True,
    }]
    candidate_log: list[dict] = []
    for cand in offspring:
        ev = evaluate_genome(cand, seeds)
        reasoning = getattr(cand, "_reasoning", "")
        pool.append({
            "genome": cand,
            "fitness": ev["fitness"],
            "metrics": ev["metrics"],
            "reasoning": reasoning,
            "is_parent": False,
        })
        candidate_log.append({
            "fitness": ev["fitness"],
            "reasoning": reasoning,
            "genome": cand.to_dict(),
        })

    best = max(pool, key=lambda p: p["fitness"])
    improved = (not best["is_parent"]) and best["fitness"] > parent_fitness

    # ── Commit selection ──────────────────────────────────────────────────────
    state["genome"] = best["genome"].to_dict()
    state["best_fitness"] = best["fitness"]
    state["parent_metrics"] = best["metrics"]
    state["reasoning"] = best["reasoning"]
    state["improved"] = improved
    state["candidate_log"] = candidate_log
    state["engine_used"] = engine
    state["generation"] = generation + 1

    history = list(state.get("history", []))
    bm = best["metrics"]
    history.append({
        "generation": generation,
        "fitness": best["fitness"],
        "throughput": bm.get("orders_fulfilled", 0),
        "opex": round(bm.get("total_opex", 0.0)),
        "genome": state["genome"],
    })
    state["history"] = history

    log.info(
        "v3 gen %d [%s]: best_fitness=%.1f improved=%s",
        generation, engine, best["fitness"], improved,
    )
    return state


async def run_evolution(
    generations: int = 10,
    engine: str = "MATH",
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    base_genome: Optional[ManufacturingV3Genome] = None,
    rng_seed: int = 12345,
) -> dict:
    """Drive `generations` generations and return the final state (with history)."""
    base = base_genome or ManufacturingV3Genome.default()
    state: dict = {
        "genome": base.to_dict(),
        "generation": 0,
        "engine": engine,
        "seeds": seeds,
        "rng_seed": rng_seed,
        "history": [],
    }
    for _ in range(generations):
        state = await run_generation(state)
    return state
