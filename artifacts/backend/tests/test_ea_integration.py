"""
Unit tests for agents.ea_integration — the DEAP wrapper.

Covers encode/decode roundtrip, bounds preservation under mutation and crossover,
genome-hash determinism, and strategy registry behaviour. No env spin-up.
"""
from __future__ import annotations

import random

import pytest

from agents import ea_integration
from agents.ea_integration import (
    StrategyNotImplemented,
    _genome_hash,
    _SC_BOUNDS,
    get_strategy,
)

SCENARIOS = ["manufacturing", "supply_chain"]


@pytest.fixture
def rng() -> random.Random:
    return random.Random(12345)


def test_available_predicate_returns_bool():
    # deap is installed in this project, but the predicate must remain a bool
    # either way so the orchestrator can use it as a feature flag.
    assert isinstance(ea_integration.available(), bool)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_strategy_registered(scenario):
    s = get_strategy(scenario)
    assert s.name == scenario
    assert callable(s.random_individual)
    assert callable(s.mutate)
    assert callable(s.crossover)
    assert callable(s.evaluate)


def test_unknown_scenario_raises():
    with pytest.raises(StrategyNotImplemented):
        get_strategy("nonexistent_scenario")


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_encode_decode_roundtrip(scenario, rng):
    s = get_strategy(scenario)
    genome = s.random_individual(rng)
    encoded = s.encode(genome)
    assert isinstance(encoded, list)
    decoded = s.decode(encoded)
    # The decoded genome must contain at least every key in the encoded keyset.
    re_encoded = s.encode(decoded)
    assert encoded == re_encoded, (
        f"encode/decode/encode is not idempotent for {scenario}: "
        f"first={encoded} second={re_encoded}"
    )


def test_genome_hash_stable():
    g1 = {"a": 1, "b": [1, 2, 3], "c": {"x": 1, "y": 2}}
    g2 = {"c": {"y": 2, "x": 1}, "b": [1, 2, 3], "a": 1}  # same data, different order
    assert _genome_hash(g1) == _genome_hash(g2)
    assert _genome_hash(g1) != _genome_hash({"a": 1, "b": [1, 2, 4], "c": {"x": 1, "y": 2}})
    # Hash is short and deterministic.
    assert len(_genome_hash(g1)) == 16


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_random_individual_in_bounds(scenario, rng):
    s = get_strategy(scenario)
    for _ in range(50):
        g = s.random_individual(rng)
        _assert_genome_in_bounds(scenario, g)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_mutate_in_bounds(scenario, rng):
    s = get_strategy(scenario)
    g = s.random_individual(rng)
    for _ in range(100):
        g = s.mutate(g, rng)
        _assert_genome_in_bounds(scenario, g)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_crossover_preserves_bounds(scenario, rng):
    s = get_strategy(scenario)
    for _ in range(50):
        a = s.random_individual(rng)
        b = s.random_individual(rng)
        ca, cb = s.crossover(a, b, rng)
        _assert_genome_in_bounds(scenario, ca)
        _assert_genome_in_bounds(scenario, cb)


def _assert_genome_in_bounds(scenario: str, g: dict) -> None:
    if scenario == "supply_chain":
        for field, (lo, hi) in _SC_BOUNDS.items():
            assert field in g, f"missing field {field} in supply_chain genome: {g}"
            v = g[field]
            assert lo <= v <= hi, f"{field}={v} out of [{lo},{hi}]"
    elif scenario == "manufacturing":
        from evolution.manufacturing_genome import MIN_AGENT_COUNTS, MAX_AGENT_COUNTS

        for role, count in g["agent_counts"].items():
            lo = MIN_AGENT_COUNTS.get(role, 0)
            hi = MAX_AGENT_COUNTS.get(role, 99)
            assert lo <= count <= hi, f"{role}={count} out of [{lo},{hi}]"
        for mid, speed in g["machine_speeds"].items():
            assert speed in ("low", "normal", "high"), f"{mid}={speed!r} invalid speed"
        assert 5.0 <= g["order_arrival_rate"] <= 30.0
    else:
        raise AssertionError(f"unknown scenario {scenario}")
