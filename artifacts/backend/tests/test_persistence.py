"""
End-to-end roundtrip: write an EA generation to a fresh temp DB, read it back
via get_latest_ea_generation, assert the fields survive intact.
"""
from __future__ import annotations

import asyncio
import os

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point state.db at a temporary SQLite file for the duration of one test."""
    db_path = tmp_path / "test_arena.db"
    monkeypatch.setenv("ARENA_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    # state.db reads ARENA_DB_URL at import time on first import. We may need
    # to reload the module so the fixture takes effect.
    import importlib
    import state.db as db_module
    importlib.reload(db_module)
    return db_module


def test_save_and_read_ea_generation(tmp_db):
    db = tmp_db

    async def _go():
        await db.init_db()
        row_in = db.EAGenerationIn(
            run_id="test_run_42",
            scenario="manufacturing",
            gen_id=5,
            parent_fitness=100.0,
            child_fitness=125.5,
            accepted_fitness=125.5,
            stagnation=0,
            boundary_mode="INTER",
            mutation_strategy="DEAP",
            genome_json={"agent_counts": {"procurement": 3}, "order_arrival_rate": 11.5},
            fitness_vector_json=[125.5, 200.0, -50.0, -25.0],
            population_stats_json={"size": 8, "best": 125.5, "mean": 100.0, "worst": 80.0},
            topology_diff="genome:procurement+1",
        )
        await db.save_ea_generation(row_in)

        latest = await db.get_latest_ea_generation("test_run_42")
        return latest

    latest = asyncio.run(_go())

    assert latest is not None
    assert latest["run_id"] == "test_run_42"
    assert latest["gen_id"] == 5
    assert latest["scenario"] == "manufacturing"
    assert latest["mutation_strategy"] == "DEAP"
    assert latest["accepted_fitness"] == 125.5
    assert latest["genome_json"]["agent_counts"]["procurement"] == 3
    assert latest["genome_json"]["order_arrival_rate"] == 11.5
    assert latest["fitness_vector_json"] == [125.5, 200.0, -50.0, -25.0]
    assert latest["population_stats_json"]["size"] == 8
    assert latest["topology_diff"] == "genome:procurement+1"


def test_get_latest_returns_highest_gen_id(tmp_db):
    db = tmp_db

    async def _go():
        await db.init_db()
        for gen_id in [1, 2, 3, 7, 4]:
            await db.save_ea_generation(db.EAGenerationIn(
                run_id="multi_gen_run",
                scenario="manufacturing",
                gen_id=gen_id,
                accepted_fitness=float(gen_id),
            ))
        return await db.get_latest_ea_generation("multi_gen_run")

    latest = asyncio.run(_go())
    assert latest is not None
    assert latest["gen_id"] == 7  # highest gen_id wins, not insertion order
    assert latest["accepted_fitness"] == 7.0


def test_get_latest_unknown_run_returns_none(tmp_db):
    db = tmp_db

    async def _go():
        await db.init_db()
        return await db.get_latest_ea_generation("never_ran")

    assert asyncio.run(_go()) is None


def test_get_ea_generations_in_ascending_order(tmp_db):
    db = tmp_db

    async def _go():
        await db.init_db()
        for gen_id in [3, 1, 2, 5, 4]:
            await db.save_ea_generation(db.EAGenerationIn(
                run_id="order_run",
                scenario="manufacturing",
                gen_id=gen_id,
                accepted_fitness=float(gen_id * 10),
            ))
        return await db.get_ea_generations("order_run")

    rows = asyncio.run(_go())
    assert len(rows) == 5
    gen_ids = [r["gen_id"] for r in rows]
    assert gen_ids == sorted(gen_ids), f"rows not in ascending gen_id order: {gen_ids}"
