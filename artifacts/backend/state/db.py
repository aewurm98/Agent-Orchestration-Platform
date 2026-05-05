"""
SQLite persistence layer using SQLAlchemy + aiosqlite.
Models: workflows, generations, traces.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import Column, Float, Integer, JSON, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import select

DATABASE_URL = "sqlite+aiosqlite:///./arena.db"

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
