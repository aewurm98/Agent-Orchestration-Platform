"""
Tests for `run_one_generation` — the public DEAP entry point that the
orchestrator's mutate node calls. We stub strategy.evaluate so the test
does not require a full env spin-up; the orchestration logic is what we
care about here.
"""
from __future__ import annotations

import random
from unittest.mock import patch

from agents import ea_integration


def _build_mfg_state(extra: dict | None = None) -> dict:
    state = {
        "scenario": "manufacturing",
        "generation": 0,
        "genome_config": {
            "agent_counts": {
                "procurement": 2, "operations": 4, "engineering": 1,
                "sales": 2, "management": 1,
            },
            "machine_speeds": {
                mid: "normal" for mid in
                ["smelter_1", "circuit_fab_1", "press_1", "assembly_1", "qc_1", "packaging_1"]
            },
            "order_arrival_rate": 12.0,
        },
        "ea_population_size": 4,
        "ea_elite_keep": 1,
        "ea_seed": 42,
        # Stub-friendly small numbers — evaluate is mocked anyway.
        "ea_minibatch_seeds": (1, 2, 3),
        "ea_ticks_per_episode": 10,
    }
    if extra:
        state.update(extra)
    return state


def test_run_one_generation_returns_expected_keys():
    state = _build_mfg_state()
    fake_eval = lambda genome, st: (random.Random(_genome_str(genome)).uniform(0, 1000), [1.0, 2.0])
    with patch.object(ea_integration, "_mfg_evaluate", side_effect=fake_eval):
        # Re-register the manufacturing strategy with the patched evaluator so the
        # registry hands the mock back. The simplest path: patch the strategy's
        # evaluate attribute directly.
        strat = ea_integration.get_strategy("manufacturing")
        original_eval = strat.evaluate
        strat.evaluate = fake_eval
        try:
            out = ea_integration.run_one_generation(state)
        finally:
            strat.evaluate = original_eval

    for key in (
        "genome_config", "ea_population", "ea_fitness_cache",
        "population_stats", "traces_to_append",
    ):
        assert key in out, f"missing key {key} in run_one_generation output"
    assert len(out["ea_population"]) == state["ea_population_size"]
    assert out["population_stats"]["size"] == state["ea_population_size"]
    assert out["population_stats"]["best"] >= out["population_stats"]["mean"]
    assert out["population_stats"]["mean"] >= out["population_stats"]["worst"]
    assert len(out["traces_to_append"]) >= 1
    assert "DEAP gen" in out["traces_to_append"][0]["content"]


def test_run_one_generation_elitism_keeps_best():
    """The best individual's fitness should never decrease across two generations
    when evaluator is deterministic — elitism guarantees the elite carries over."""
    state = _build_mfg_state({"ea_population_size": 6, "ea_elite_keep": 2})

    # Deterministic evaluator: hash-based so the same genome always scores the same.
    def deterministic_eval(genome, st):
        h = hash(_genome_str(genome)) % 10_000
        return float(h), [float(h)]

    strat = ea_integration.get_strategy("manufacturing")
    original_eval = strat.evaluate
    strat.evaluate = deterministic_eval
    try:
        gen1 = ea_integration.run_one_generation(state)
        # Feed gen1 results forward (population + cache) so gen2 builds on them.
        state2 = dict(state)
        state2["ea_population"] = gen1["ea_population"]
        state2["ea_fitness_cache"] = gen1["ea_fitness_cache"]
        state2["generation"] = 1
        gen2 = ea_integration.run_one_generation(state2)
    finally:
        strat.evaluate = original_eval

    assert gen2["population_stats"]["best"] >= gen1["population_stats"]["best"], (
        f"Elitism violated: gen1.best={gen1['population_stats']['best']}, "
        f"gen2.best={gen2['population_stats']['best']}"
    )


def test_run_one_generation_unknown_scenario_raises():
    state = _build_mfg_state({"scenario": "no_such_scenario"})
    try:
        ea_integration.run_one_generation(state)
    except ea_integration.StrategyNotImplemented:
        return
    raise AssertionError("expected StrategyNotImplemented for unknown scenario")


def _genome_str(genome: dict) -> str:
    import json
    return json.dumps(genome, sort_keys=True, default=str)
