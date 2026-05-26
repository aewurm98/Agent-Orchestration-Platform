"""
SQLite persistence layer using SQLAlchemy + aiosqlite.
Models: workflows, generations, traces.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import Column, Float, Integer, JSON, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import select

DATABASE_URL = os.environ.get("ARENA_DB_URL", "sqlite+aiosqlite:///./arena.db")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


class WorkflowModel(Base):
    __tablename__ = "workflows"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    scenario = Column(String(100), nullable=False)
    best_fitness = Column(Float, default=0.0)
    topology = Column(JSON, default={})
    created_at = Column(Float, default=time.time)


class GenerationModel(Base):
    __tablename__ = "generations"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), nullable=False, index=True)
    gen_id = Column(Integer, nullable=False)
    parent_fitness = Column(Float)
    child_fitness = Column(Float)
    mutation_type = Column(String(100))
    topology_diff = Column(String(255))
    timestamp = Column(Float, default=time.time)


class TraceModel(Base):
    __tablename__ = "traces"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), nullable=False, index=True)
    generation = Column(Integer, default=0)
    agent_role = Column(String(100))
    content = Column(Text)
    timestamp = Column(Float, default=time.time)


class EAGenerationModel(Base):
    """Per-generation EA checkpoint for resume + analytics.

    Separate from GenerationModel (legacy, kept for backwards compatibility) so
    existing arena.db files do not need a schema migration to pick this up.
    """
    __tablename__ = "ea_generations"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(100), nullable=False, index=True)
    scenario = Column(String(64), nullable=False, index=True)
    gen_id = Column(Integer, nullable=False)
    boundary_mode = Column(String(16), default="INTRA")
    mutation_strategy = Column(String(16), default="MATH")
    parent_fitness = Column(Float)
    child_fitness = Column(Float)
    accepted_fitness = Column(Float)
    stagnation = Column(Integer, default=0)
    genome_json = Column(JSON, default={})
    fitness_vector_json = Column(JSON, default=[])
    population_stats_json = Column(JSON, default={})
    topology_diff = Column(String(255))
    timestamp = Column(Float, default=time.time)


@dataclass
class WorkflowIn:
    name: str
    scenario: str
    best_fitness: float = 0.0
    topology: Any = None

    def __post_init__(self):
        if self.topology is None:
            self.topology = {}


@dataclass
class TraceIn:
    run_id: str
    generation: int
    agent_role: str
    content: str


@dataclass
class EAGenerationIn:
    run_id: str
    scenario: str
    gen_id: int
    parent_fitness: float = 0.0
    child_fitness: float = 0.0
    accepted_fitness: float = 0.0
    stagnation: int = 0
    boundary_mode: str = "INTRA"
    mutation_strategy: str = "MATH"
    genome_json: Any = None
    fitness_vector_json: Any = None
    population_stats_json: Any = None
    topology_diff: str = ""

    def __post_init__(self):
        if self.genome_json is None:
            self.genome_json = {}
        if self.fitness_vector_json is None:
            self.fitness_vector_json = []
        if self.population_stats_json is None:
            self.population_stats_json = {}


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_workflow(wf: WorkflowIn) -> dict:
    async with AsyncSessionLocal() as session:
        row = WorkflowModel(
            name=wf.name,
            scenario=wf.scenario,
            best_fitness=wf.best_fitness,
            topology=wf.topology,
            created_at=time.time(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return {
            "id": row.id,
            "name": row.name,
            "scenario": row.scenario,
            "best_fitness": row.best_fitness,
            "topology": row.topology,
            "created_at": row.created_at,
        }


async def get_workflows() -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkflowModel).order_by(WorkflowModel.created_at.desc()).limit(50)
        )
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "scenario": r.scenario,
                "best_fitness": r.best_fitness,
                "topology": r.topology,
                "created_at": r.created_at,
            }
            for r in rows
        ]


async def save_trace(trace: TraceIn) -> dict:
    async with AsyncSessionLocal() as session:
        row = TraceModel(
            run_id=trace.run_id,
            generation=trace.generation,
            agent_role=trace.agent_role,
            content=trace.content,
            timestamp=time.time(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return {
            "id": row.id,
            "run_id": row.run_id,
            "generation": row.generation,
            "agent_role": row.agent_role,
            "content": row.content,
            "timestamp": row.timestamp,
        }


async def get_workflow_by_id(workflow_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkflowModel).where(WorkflowModel.id == int(workflow_id))
        )
        row = result.scalars().first()
        if row is None:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "scenario": row.scenario,
            "best_fitness": row.best_fitness,
            "topology": row.topology,
            "created_at": row.created_at,
        }


async def save_ea_generation(row_in: EAGenerationIn) -> dict:
    async with AsyncSessionLocal() as session:
        row = EAGenerationModel(
            run_id=row_in.run_id,
            scenario=row_in.scenario,
            gen_id=row_in.gen_id,
            boundary_mode=row_in.boundary_mode,
            mutation_strategy=row_in.mutation_strategy,
            parent_fitness=row_in.parent_fitness,
            child_fitness=row_in.child_fitness,
            accepted_fitness=row_in.accepted_fitness,
            stagnation=row_in.stagnation,
            genome_json=row_in.genome_json,
            fitness_vector_json=row_in.fitness_vector_json,
            population_stats_json=row_in.population_stats_json,
            topology_diff=row_in.topology_diff,
            timestamp=time.time(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _ea_generation_to_dict(row)


async def get_latest_ea_generation(run_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EAGenerationModel)
            .where(EAGenerationModel.run_id == run_id)
            .order_by(EAGenerationModel.gen_id.desc())
            .limit(1)
        )
        row = result.scalars().first()
        return _ea_generation_to_dict(row) if row else None


async def get_ea_generations(run_id: str, limit: int = 500) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EAGenerationModel)
            .where(EAGenerationModel.run_id == run_id)
            .order_by(EAGenerationModel.gen_id.asc())
            .limit(limit)
        )
        return [_ea_generation_to_dict(r) for r in result.scalars().all()]


def _ea_generation_to_dict(row: EAGenerationModel) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "scenario": row.scenario,
        "gen_id": row.gen_id,
        "boundary_mode": row.boundary_mode,
        "mutation_strategy": row.mutation_strategy,
        "parent_fitness": row.parent_fitness,
        "child_fitness": row.child_fitness,
        "accepted_fitness": row.accepted_fitness,
        "stagnation": row.stagnation,
        "genome_json": row.genome_json,
        "fitness_vector_json": row.fitness_vector_json,
        "population_stats_json": row.population_stats_json,
        "topology_diff": row.topology_diff,
        "timestamp": row.timestamp,
    }


async def get_traces(run_id: str) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TraceModel)
            .where(TraceModel.run_id == run_id)
            .order_by(TraceModel.timestamp.asc())
            .limit(500)
        )
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "run_id": r.run_id,
                "generation": r.generation,
                "agent_role": r.agent_role,
                "content": r.content,
                "timestamp": r.timestamp,
            }
            for r in rows
        ]
