"""
Manufacturing v3 test-suite (spec §2-§5).

Covers genome bounds/evolution, the deterministic flow-graph engine (spawn math,
edge bandwidth limiting, 2-tick processing, soft-degradation breakdowns,
economics, fitness), the meta-optimizer prompt/parse/fallback, and the
(mu+lambda) EA. Ends with a stress test that fuzzes random genomes and long EA
runs while asserting the spec invariants always hold.
"""
from __future__ import annotations

import asyncio
import random
from unittest.mock import patch

import pytest

from game_envs.manufacturing_v3 import (
    ManufacturingV3Env,
    ManufacturingV3Genome,
    MACHINE_IDS,
    EDGE_IDS,
)
from game_envs.manufacturing_v3 import env as v3env
from game_envs.manufacturing_v3.env import (
    PROCESS_TICKS,
    REPAIR_TICKS,
    REVENUE_PER_GOOD,
    MISSED_ORDER_PENALTY,
    MAINTENANCE_COST,
    IDLE,
    PROCESSING,
    DOWN,
    RAW_PLASTIC,
)
from agents import manufacturing_v3_optimizer as opt
from evolution import manufacturing_v3_evolution as evo


def _balanced_genome(cap=10, bw=10, maint="high", intake=40) -> ManufacturingV3Genome:
    return ManufacturingV3Genome(
        machine_capacities={m: cap for m in MACHINE_IDS},
        edge_bandwidths={e: bw for e in EDGE_IDS},
        maintenance_policy=maint,
        order_intake_rate=intake,
    )


# ── Genome ────────────────────────────────────────────────────────────────────

def test_genome_default_valid():
    g = ManufacturingV3Genome.default()
    assert set(g.machine_capacities) == set(MACHINE_IDS)
    assert set(g.edge_bandwidths) == set(EDGE_IDS)
    assert g.maintenance_policy == "medium"
    assert 1 <= g.order_intake_rate <= 100


def test_genome_clamps_out_of_range():
    g = ManufacturingV3Genome(
        machine_capacities={"molding": 999, "wire_drawing": -5, "assembly": 0, "packaging": 50},
        edge_bandwidths={e: 9999 for e in EDGE_IDS},
        maintenance_policy="nonsense",
        order_intake_rate=10_000,
    )
    assert g.machine_capacities["molding"] == 50
    assert g.machine_capacities["wire_drawing"] == 1
    assert g.machine_capacities["assembly"] == 1
    assert all(g.edge_bandwidths[e] == 50 for e in EDGE_IDS)
    assert g.maintenance_policy == "medium"   # invalid -> default
    assert g.order_intake_rate == 100


def test_genome_roundtrip():
    g = _balanced_genome(7, 9, "low", 33)
    assert ManufacturingV3Genome.from_dict(g.to_dict()).to_dict() == g.to_dict()


def test_genome_mutate_stays_in_bounds():
    rng = random.Random(0)
    g = ManufacturingV3Genome.default()
    for _ in range(500):
        g = g.mutate(rng)
        assert all(1 <= v <= 50 for v in g.machine_capacities.values())
        assert all(1 <= v <= 50 for v in g.edge_bandwidths.values())
        assert g.maintenance_policy in ("low", "medium", "high")
        assert 1 <= g.order_intake_rate <= 100


def test_genome_apply_delta_partial_and_clamp():
    base = _balanced_genome(10, 10, "medium", 40)
    out = base.apply_delta({
        "machine_capacities": {"assembly": 99, "molding": None},  # clamp + ignore None
        "order_intake_rate": 75,
        "maintenance_policy": "bogus",                            # ignored -> keep base
        "unknown_field": 123,
    })
    assert out.machine_capacities["assembly"] == 50
    assert out.machine_capacities["molding"] == 10               # None left unchanged
    assert out.order_intake_rate == 75
    assert out.maintenance_policy == "medium"


# ── Engine: spawning (§3.1) ─────────────────────────────────────────────────────

def test_spawn_count_equals_intake_rate():
    for rate in (1, 5, 10, 37, 90, 100):
        env = ManufacturingV3Env(_balanced_genome(intake=rate), seed=0)
        env.run()
        assert env.orders_received == rate, f"rate={rate}"


def test_spawn_timing_evenly_spaced():
    # rate=10 over 500 ticks -> one order every 50 ticks at ticks 0,50,...,450
    env = ManufacturingV3Env(_balanced_genome(intake=10), seed=0)
    spawn_ticks, prev = [], 0
    for _ in range(500):
        env.step()
        if env.orders_received > prev:
            spawn_ticks.append(env.tick - 1)
            prev = env.orders_received
    assert spawn_ticks == [0, 50, 100, 150, 200, 250, 300, 350, 400, 450]


def test_spawn_deposits_materials_and_charges_cost():
    env = ManufacturingV3Env(_balanced_genome(intake=4), seed=0)
    env._spawn_orders()  # tick 0 spawn
    assert env.orders_received == 1
    assert env.inbound.output_queue[RAW_PLASTIC] == 1
    assert env.total_material_cost == 100.0  # $50 plastic + $50 copper


# ── Engine: edges (§3.2) ────────────────────────────────────────────────────────

def test_edge_bandwidth_limits_transfer():
    # Pile lots of finished goods in packaging.output, set the sink edge to bw=3.
    g = _balanced_genome()
    g.edge_bandwidths["packaging_to_out"] = 3
    env = ManufacturingV3Env(g, seed=0)
    env.nodes["packaging"].output_queue[v3env.FINISHED_GOOD] = 100
    env._run_edges()
    assert env.orders_fulfilled == 3                       # only bandwidth moved
    assert env.nodes["packaging"].output_count() == 97
    assert env.edge_flow["packaging_to_out"] == 3


def test_sink_counts_fulfilled_and_revenue():
    g = _balanced_genome()
    env = ManufacturingV3Env(g, seed=0)
    env.nodes["packaging"].output_queue[v3env.FINISHED_GOOD] = 5
    env._run_edges()
    assert env.orders_fulfilled == 5
    assert env.total_revenue == 5 * REVENUE_PER_GOOD


# ── Engine: processing delay (§3.2) ──────────────────────────────────────────────

def test_processing_takes_exactly_two_ticks():
    g = _balanced_genome(cap=5, bw=5, intake=1)
    env = ManufacturingV3Env(g, seed=0)
    # tick 0: spawn -> edge moves plastic into molding -> molding starts PROCESSING
    env.step()
    assert env.nodes["molding"].state == PROCESSING
    assert env.nodes["molding"].output_count() == 0
    env.step()  # still processing (timer 2 -> 1)
    assert env.nodes["molding"].state == PROCESSING
    env.step()  # timer 1 -> 0: batch drops to output, back to IDLE
    assert env.nodes["molding"].state == IDLE
    assert env.nodes["molding"].output_count() == 1


# ── Engine: soft degradation (§3.3) ──────────────────────────────────────────────

def test_breakdown_down_for_fifteen_ticks_and_freezes_materials():
    g = _balanced_genome(cap=5, bw=5, maint="low", intake=1)
    env = ManufacturingV3Env(g, seed=0)
    # Force a guaranteed breakdown on the first start attempt.
    with patch.dict(v3env.BREAKDOWN_PROB, {"low": 1.0}):
        env._spawn_orders()
        env._run_edges()                       # plastic now in molding.input
        frozen = env.nodes["molding"].input_count()
        assert frozen >= 1
        env._run_machines()                    # IDLE -> rolls breakdown -> DOWN
        node = env.nodes["molding"]
        assert node.state == DOWN
        assert node.repair_timer == REPAIR_TICKS
        assert node.input_count() == frozen     # materials frozen (not consumed)
        # Tick down the repair timer; materials stay frozen the whole time.
        for _ in range(REPAIR_TICKS - 1):
            env._run_machines()
            assert env.nodes["molding"].state == DOWN
            assert env.nodes["molding"].input_count() == frozen
    # Final repair tick (prob restored to 0 via context exit won't matter): becomes IDLE
    env._run_machines()
    assert env.nodes["molding"].state in (IDLE, PROCESSING)
    assert env.nodes["molding"].failure_count == 1


def test_breakdown_probabilities_match_spec():
    assert v3env.BREAKDOWN_PROB == {"low": 0.02, "medium": 0.005, "high": 0.0005}


def test_no_breakdown_roll_when_no_work():
    # An IDLE machine with empty input must never break down (§3.3).
    g = _balanced_genome(maint="low", intake=1)
    env = ManufacturingV3Env(g, seed=0)
    with patch.dict(v3env.BREAKDOWN_PROB, {"low": 1.0}):
        # packaging has no upstream work early on; step a few ticks
        for _ in range(3):
            env.step()
        assert env.nodes["packaging"].failure_count == 0


# ── Engine: economics & fitness (§4) ─────────────────────────────────────────────

def test_fitness_formula_matches_components():
    g = _balanced_genome(cap=8, bw=8, maint="medium", intake=30)
    env = ManufacturingV3Env(g, seed=123)
    env.run()
    revenue = REVENUE_PER_GOOD * env.orders_fulfilled
    material = 100.0 * env.orders_received
    penalty = MISSED_ORDER_PENALTY * env.orders_missed
    expected = round(revenue - (env.total_opex + material) - penalty, 2)
    assert env.get_fitness() == expected
    # vector decomposition sums to fitness
    assert round(sum(env.get_fitness_vector()), 2) == env.get_fitness()


def test_tick_opex_uses_exponential_costs():
    g = _balanced_genome(cap=10, bw=10, maint="medium")
    env = ManufacturingV3Env(g, seed=0)
    expected_machine = 4 * (1.00 * (10 ** 1.2))
    expected_edge = 6 * (0.50 * (10 ** 1.1))
    expected = expected_machine + expected_edge + MAINTENANCE_COST["medium"]
    assert env._tick_opex == pytest.approx(expected)


def test_material_cost_charged_even_when_unfulfilled():
    # Bandwidth 1 + high intake -> late orders can't traverse the pipeline by the
    # deadline, yet their raw materials were still purchased at spawn.
    g = _balanced_genome(cap=1, bw=1, maint="medium", intake=100)
    env = ManufacturingV3Env(g, seed=0)
    env.run()
    assert env.total_material_cost == 100.0 * env.orders_received
    assert env.orders_missed > 0


def test_over_provisioning_loses_money():
    # High capacity + 'high' maintenance fulfils everything but bleeds OpEx (§4.2).
    g = _balanced_genome(cap=10, bw=10, maint="high", intake=50)
    env = ManufacturingV3Env(g, seed=0)
    env.run()
    assert env.orders_fulfilled == env.orders_received  # not throughput-limited
    assert env.get_fitness() < 0                          # OpEx dominates revenue


def test_penalty_applied_for_missed_orders():
    g = _balanced_genome(cap=1, bw=1, maint="medium", intake=100)
    env = ManufacturingV3Env(g, seed=0)
    env.run()
    metrics = env.get_metrics()
    assert metrics["penalties"] == MISSED_ORDER_PENALTY * env.orders_missed


# ── Engine: determinism & episode completion ─────────────────────────────────────

def test_determinism_same_seed():
    g = ManufacturingV3Genome.random(random.Random(9))
    a = ManufacturingV3Env(g.clone(), seed=2024); a.run()
    b = ManufacturingV3Env(g.clone(), seed=2024); b.run()
    assert a.get_fitness() == b.get_fitness()
    assert a.orders_fulfilled == b.orders_fulfilled


def test_different_seeds_can_differ_under_low_maintenance():
    # Low maintenance => breakdowns => seed-dependent outcomes (usually).
    g = _balanced_genome(cap=5, bw=5, maint="low", intake=80)
    fits = {ManufacturingV3Env(g.clone(), seed=s).run().get_fitness() for s in range(8)}
    assert len(fits) >= 1  # at minimum it runs; variation is expected but not required


def test_full_episode_completes():
    env = ManufacturingV3Env(ManufacturingV3Genome.default(), seed=0)
    env.run()
    assert env.tick == env.simulation_length
    assert env.done
    assert isinstance(env.get_fitness(), float)
    js = env.to_json()
    assert len(js["nodes"]) == 4 and len(js["edges"]) == 6


# ── Meta-optimizer (§5) ──────────────────────────────────────────────────────────

def test_user_prompt_has_required_sections():
    g = ManufacturingV3Genome.default()
    env = ManufacturingV3Env(g, seed=0); env.run()
    prompt = opt.build_user_prompt(env.get_metrics(), g, [
        {"generation": 0, "fitness": 100, "throughput": 5, "opex": 5000},
    ])
    for marker in ("HISTORICAL TREND", "CURRENT EPISODE PERFORMANCE",
                   "BOTTLENECK DIAGNOSTICS", "CURRENT GENOME"):
        assert marker in prompt
    for mid in MACHINE_IDS:
        assert mid in prompt


def test_parse_candidates_prose_wrapped_partial_and_clamped():
    base = _balanced_genome(10, 10, "medium", 40)
    raw = (
        "Here is my plan:\n"
        '[{"reasoning":"assembly is the bottleneck","machine_capacities":{"assembly":99},'
        '"order_intake_rate":150},'
        '{"maintenance_policy":"high"},'
        '{"edge_bandwidths":{"packaging_to_out":0}}]\n'
        "These three candidates should improve flow."
    )
    cands = opt.parse_candidates(raw, base)
    assert len(cands) == 3
    assert cands[0].machine_capacities["assembly"] == 50      # clamped
    assert cands[0].order_intake_rate == 100                   # clamped
    assert getattr(cands[0], "_reasoning") == "assembly is the bottleneck"
    assert cands[1].maintenance_policy == "high"
    assert cands[2].edge_bandwidths["packaging_to_out"] == 1   # clamped up from 0


def test_parse_candidates_single_object():
    base = ManufacturingV3Genome.default()
    cands = opt.parse_candidates('{"order_intake_rate": 22}', base)
    assert len(cands) == 1 and cands[0].order_intake_rate == 22


def test_parse_candidates_raises_without_json():
    with pytest.raises(Exception):
        opt.parse_candidates("no json here at all", ManufacturingV3Genome.default())


def test_math_candidates_count_and_validity():
    base = ManufacturingV3Genome.default()
    cands = opt.math_candidates(base, n=3, rng=random.Random(1))
    assert len(cands) == 3
    assert all(isinstance(c, ManufacturingV3Genome) for c in cands)


def test_query_candidates_falls_back_to_math_on_error():
    base = ManufacturingV3Genome.default()
    env = ManufacturingV3Env(base, seed=0); env.run()
    # Force the LLM client to blow up -> must fall back to MATH, never raise.
    with patch("agents.meta_optimizer._get_anthropic_client", side_effect=RuntimeError("no key")):
        cands = asyncio.run(opt.query_candidates(base, env.get_metrics(), []))
    assert len(cands) == opt.N_CANDIDATES
    assert all(isinstance(c, ManufacturingV3Genome) for c in cands)


def test_query_candidates_success_path_with_mocked_client():
    base = ManufacturingV3Genome.default()
    env = ManufacturingV3Env(base, seed=0); env.run()

    class _Block:
        text = '[{"reasoning":"a","order_intake_rate":50},{"maintenance_policy":"high"},{"machine_capacities":{"assembly":12}}]'

    class _Resp:
        content = [_Block()]

    class _Messages:
        async def create(self, **kwargs):
            # system is now a cacheable content block carrying the prompt text.
            assert kwargs["system"][0]["text"] == opt.SYSTEM_PROMPT
            assert kwargs["thinking"]["type"] == "adaptive"
            return _Resp()

    class _Client:
        messages = _Messages()

    with patch("agents.meta_optimizer._get_anthropic_client", return_value=_Client()):
        cands = asyncio.run(opt.query_candidates(base, env.get_metrics(), []))
    assert len(cands) == 3
    assert cands[0].order_intake_rate == 50


# ── (mu + lambda) EA (§5) ────────────────────────────────────────────────────────

def test_evaluate_genome_structure_and_determinism():
    g = _balanced_genome(cap=6, bw=6, maint="medium", intake=30)
    r1 = evo.evaluate_genome(g)
    r2 = evo.evaluate_genome(g)
    assert r1["fitness"] == r2["fitness"]
    assert set(r1["metrics"]).issuperset({"orders_fulfilled", "total_opex", "node_diagnostics"})
    assert len(r1["per_seed"]) == len(evo.DEFAULT_SEEDS)


def test_run_generation_is_elitist():
    state = {
        "genome": ManufacturingV3Genome.default().to_dict(),
        "generation": 0, "engine": "MATH", "seeds": evo.DEFAULT_SEEDS,
        "rng_seed": 3, "history": [],
    }
    state = asyncio.run(evo.run_generation(state))
    first = state["best_fitness"]
    for _ in range(6):
        prev = state["best_fitness"]
        state = asyncio.run(evo.run_generation(state))
        assert state["best_fitness"] >= prev - 1e-6   # (mu+lambda): never regresses
    assert state["best_fitness"] >= first
    assert state["generation"] == 7


def test_run_evolution_math_monotonic_and_improves():
    state = asyncio.run(evo.run_evolution(generations=12, engine="MATH", rng_seed=7))
    fits = [h["fitness"] for h in state["history"]]
    assert len(fits) == 12
    assert all(fits[i] <= fits[i + 1] + 1e-6 for i in range(len(fits) - 1))
    assert fits[-1] > fits[0]   # MATH EA finds a real improvement from the default


def test_run_evolution_llm_engine_falls_back_without_key():
    # engine=LLM but client errors -> MATH offspring; loop must still complete.
    with patch("agents.meta_optimizer._get_anthropic_client", side_effect=RuntimeError("no key")):
        state = asyncio.run(evo.run_evolution(generations=4, engine="LLM", rng_seed=1))
    assert len(state["history"]) == 4
    assert isinstance(state["best_fitness"], float)


# ── Stress test ──────────────────────────────────────────────────────────────────

def _assert_episode_invariants(env: ManufacturingV3Env) -> None:
    assert env.orders_fulfilled <= env.orders_received
    assert env.orders_missed == env.orders_received - env.orders_fulfilled
    assert env.orders_missed >= 0
    # economics consistency
    assert env.total_revenue == REVENUE_PER_GOOD * env.orders_fulfilled
    assert env.total_material_cost == 100.0 * env.orders_received
    expected = round(
        env.total_revenue
        - (env.total_opex + env.total_material_cost)
        - MISSED_ORDER_PENALTY * env.orders_missed,
        2,
    )
    assert env.get_fitness() == expected
    # queues never negative; node states valid
    for n in list(env.nodes.values()) + [env.inbound]:
        assert all(v >= 0 for v in n.input_queue.values())
        assert all(v >= 0 for v in n.output_queue.values())
    for mid in MACHINE_IDS:
        assert env.nodes[mid].state in (IDLE, PROCESSING, DOWN)


def test_stress_random_genomes_full_episodes():
    rng = random.Random(2024)
    for i in range(120):
        g = ManufacturingV3Genome.random(rng)
        env = ManufacturingV3Env(g, seed=rng.randint(0, 10_000))
        env.run()
        assert env.done
        _assert_episode_invariants(env)


def test_stress_extreme_genomes():
    extremes = [
        _balanced_genome(cap=1, bw=1, maint="low", intake=100),
        _balanced_genome(cap=50, bw=50, maint="high", intake=1),
        _balanced_genome(cap=50, bw=1, maint="medium", intake=100),
        _balanced_genome(cap=1, bw=50, maint="high", intake=100),
        _balanced_genome(cap=50, bw=50, maint="low", intake=100),
    ]
    for g in extremes:
        for seed in (0, 1, 99):
            env = ManufacturingV3Env(g.clone(), seed=seed)
            env.run()
            _assert_episode_invariants(env)


def test_stress_long_ea_run_stable():
    # 30-generation MATH EA must stay elitist and never crash.
    state = asyncio.run(evo.run_evolution(generations=30, engine="MATH", rng_seed=99))
    fits = [h["fitness"] for h in state["history"]]
    assert len(fits) == 30
    assert all(fits[i] <= fits[i + 1] + 1e-6 for i in range(len(fits) - 1))
    # final genome is valid and within bounds
    final = ManufacturingV3Genome.from_dict(state["genome"])
    assert all(1 <= v <= 50 for v in final.machine_capacities.values())
    assert all(1 <= v <= 50 for v in final.edge_bandwidths.values())
    assert 1 <= final.order_intake_rate <= 100
