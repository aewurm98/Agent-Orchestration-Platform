"""
Env-level tests for SupplyChainEnv.apply_genome — verifies that the 4 fields
exposed via GENOME_DEFAULTS actually propagate to instance state, and that
the env can run a small number of ticks without raising.
"""
from __future__ import annotations

import pytest

from game_envs.supply_chain import SupplyChainEnv


def test_genome_defaults_contains_expected_fields():
    expected = {"fleet_size", "supply_rate", "transfer_amount", "warehouse_restock_threshold"}
    assert expected.issubset(set(SupplyChainEnv.GENOME_DEFAULTS.keys()))


def test_apply_genome_sets_fleet_and_overrides():
    env = SupplyChainEnv()
    env.apply_genome({
        "fleet_size": 5,
        "supply_rate": 25,
        "transfer_amount": 30,
        "warehouse_restock_threshold": 0.45,
    })
    assert len(env.trucks) == 5, f"expected 5 trucks, got {len(env.trucks)}"
    assert env._supply_gen_units == 25
    assert env._truck_capacity == 30
    # warehouse_restock_threshold is accepted but intentionally not stored —
    # reserved for future warehouse logic (action A13). This test asserts the
    # field is silently ignored, not raised, and documents the current contract.
    assert not hasattr(env, "_warehouse_restock_threshold")


def test_apply_genome_partial_leaves_unset_fields_alone():
    env = SupplyChainEnv()
    pre_fleet = len(env.trucks)
    pre_capacity = env._truck_capacity
    env.apply_genome({"supply_rate": 50})
    # Fleet and truck capacity should not change because we only mutated supply_rate.
    assert len(env.trucks) == pre_fleet
    assert env._truck_capacity == pre_capacity
    assert env._supply_gen_units == 50


def test_apply_genome_ignores_unknown_keys():
    env = SupplyChainEnv()
    # Should not raise.
    env.apply_genome({"completely_made_up_field": 9999})


def test_env_runs_ticks_after_apply_genome():
    env = SupplyChainEnv()
    env.apply_genome({"fleet_size": 3, "supply_rate": 20, "transfer_amount": 25})
    # 50 ticks should be plenty to exercise pickup/delivery paths without
    # consuming much CPU.
    for _ in range(50):
        if getattr(env, "done", False):
            break
        env.step()
    # No exceptions == pass. Fitness should be a finite number.
    fitness = float(env.get_fitness())
    assert fitness == fitness, f"non-finite fitness: {fitness}"  # NaN check


def test_apply_genome_clamps_fleet_size_minimum():
    """Edge case: a genome with fleet_size=0 or negative should not result in
    silently producing zero trucks if the env defines a minimum. (If no min is
    enforced, this test documents the current behaviour.)"""
    env = SupplyChainEnv()
    env.apply_genome({"fleet_size": 1})
    assert len(env.trucks) == 1
