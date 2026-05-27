"""
Mini-batch evaluation for the Manufacturing v2 inter-episode EA (spec §3.1).

Every generation the orchestrator runs the candidate genome across a fixed set
of stochastic seeds, then averages the resulting fitness vectors before handing
the result to the Meta-Optimizer.  Averaging guards against the LLM
over-fitting to a single lucky run (an unusually rush-order-heavy episode or a
streak with no machine failures).
"""
from __future__ import annotations

from typing import Optional

# Spec §3.1 — fixed stochastic seeds for the per-generation mini-batch.
DEFAULT_SEEDS: tuple[int, ...] = (42, 101, 777)


def evaluate_genome_minibatch(
    genome_dict: dict,
    ticks: int = 500,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
) -> dict:
    """
    Run `genome_dict` for `ticks` ticks once per seed using ScriptedGreedyPolicy
    and return the averaged fitness scalar / vector plus aggregated metrics.

    Returns:
        {
          "fitness":        float,        # mean of per-episode fitness scalars
          "fitness_vector": list[float],  # element-wise mean of fitness vectors
          "metrics":        dict,         # averaged headline metrics for the digest
          "per_seed":       list[dict],   # {seed, fitness} for traceability
        }
    """
    # Imports kept local so this module stays cheap to import.
    from evolution.manufacturing_genome import ManufacturingGenome
    from game_envs.manufacturing_v2.env import ManufacturingEnvV2
    from agents.manufacturing_policies import ScriptedGreedyPolicy

    if genome_dict and "agent_counts" in genome_dict:
        genome = ManufacturingGenome.from_dict(genome_dict)
    else:
        genome = ManufacturingGenome.default()

    policy = ScriptedGreedyPolicy()
    scalars: list[float] = []
    vectors: list[list[float]] = []
    metric_rows: list[dict] = []
    per_seed: list[dict] = []

    for seed in seeds:
        cfg = genome.to_env_config()
        cfg["random_seed"] = seed
        cfg["simulation_length"] = ticks
        env = ManufacturingEnvV2(cfg)

        for _ in range(ticks):
            if env.done:
                break
            env.step(policy.get_all_actions(env.world))

        scalars.append(env.get_fitness())
        vectors.append(env.get_fitness_vector())
        m = env.get_metrics()
        metric_rows.append(m)
        per_seed.append({"seed": seed, "fitness": round(env.get_fitness(), 4)})

    n = max(len(scalars), 1)
    mean_fitness = round(sum(scalars) / n, 4)

    vec_len = len(vectors[0]) if vectors else 0
    mean_vector = [
        round(sum(v[i] for v in vectors) / n, 4) for i in range(vec_len)
    ]

    def _avg(key: str) -> float:
        return round(sum(float(r.get(key, 0.0)) for r in metric_rows) / n, 2)

    metrics = {
        "avg_profit": _avg("current_profit"),
        "avg_revenue": _avg("total_revenue"),
        "avg_penalties": _avg("penalties") if "penalties" in (metric_rows[0] if metric_rows else {}) else round(
            sum(float(r.get("pl", {}).get("penalties", 0.0)) for r in metric_rows) / n, 2
        ),
        "avg_throughput": _avg("throughput"),
        "avg_orders_fulfilled": _avg("orders_fulfilled"),
        "avg_orders_missed": _avg("orders_missed"),
        "avg_machine_utilization": _avg("machine_utilization"),
        "avg_agent_idle_ratio": _avg("agent_idle_ratio"),
        "seeds": list(seeds),
        "ticks": ticks,
    }
    total_orders = metrics["avg_orders_fulfilled"] + metrics["avg_orders_missed"]
    metrics["miss_rate"] = round(metrics["avg_orders_missed"] / max(total_orders, 1), 3)

    # Aggregate role_active_ratios
    metrics["role_active_ratios"] = {}
    if all("role_active_ratios" in r for r in metric_rows):
        roles = metric_rows[0]["role_active_ratios"].keys()
        for role in roles:
            metrics["role_active_ratios"][role] = round(
                sum(r["role_active_ratios"].get(role, 0.0) for r in metric_rows) / n, 2
            )

    # Aggregate machine_diagnostics
    metrics["machine_diagnostics"] = {}
    if all("machine_diagnostics" in r for r in metric_rows):
        mids = metric_rows[0]["machine_diagnostics"].keys()
        for mid in mids:
            metrics["machine_diagnostics"][mid] = {
                "avg_input_queue": round(sum(r["machine_diagnostics"][mid].get("avg_input_queue", 0.0) for r in metric_rows) / n, 2),
                "avg_output_queue": round(sum(r["machine_diagnostics"][mid].get("avg_output_queue", 0.0) for r in metric_rows) / n, 2),
                "failure_count": sum(r["machine_diagnostics"][mid].get("failure_count", 0) for r in metric_rows),
            }

    return {
        "fitness": mean_fitness,
        "fitness_vector": mean_vector,
        "metrics": metrics,
        "per_seed": per_seed,
    }
