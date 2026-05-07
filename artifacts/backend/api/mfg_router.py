"""
Shared API contract endpoints for the Manufacturing v2 simulation.

Endpoints:
  POST /api/mfg/reset        — Reset with EnvironmentConfig, returns initial state.
  POST /api/mfg/step         — Advance one tick with submitted agent actions.
  GET  /api/mfg/metrics      — Current MetricsSnapshot.
  GET  /api/mfg/state        — Full state snapshot.
  GET  /api/mfg/action_space/{agent_id}  — Valid actions for agent.
  GET  /api/mfg/observation/{agent_id}   — Filtered observation for agent.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from game_envs.manufacturing_v2.env import ManufacturingEnvV2
from game_envs.manufacturing_v2.scenarios import FIRST_FACTORY_CONFIG
from evolution.manufacturing_genome import ConnectivityValidator

router = APIRouter(prefix="/api/mfg", tags=["manufacturing"])

_env: Optional[ManufacturingEnvV2] = None


def get_env() -> ManufacturingEnvV2:
    global _env
    if _env is None:
        _env = ManufacturingEnvV2(FIRST_FACTORY_CONFIG)
    return _env


def set_env(env: ManufacturingEnvV2) -> None:
    global _env
    _env = env


class ResetRequest(BaseModel):
    config: Optional[dict] = None
    validate_connectivity: bool = True


class StepRequest(BaseModel):
    actions: Optional[dict[str, dict]] = None


class SpeedRequest(BaseModel):
    multiplier: float = 1.0


@router.post("/reset")
async def reset(req: ResetRequest) -> dict:
    global _env
    config = req.config or FIRST_FACTORY_CONFIG
    if req.validate_connectivity:
        ok, reason = ConnectivityValidator.validate_config(config)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Invalid genome configuration: {reason}")
    _env = ManufacturingEnvV2(config)
    return _env.to_json()


@router.post("/step")
async def step(req: StepRequest) -> dict:
    env = get_env()
    if env.done:
        return {**env.to_json(), "message": "Simulation already finished"}
    state = env.step(req.actions)
    return state


@router.get("/metrics")
async def get_metrics() -> dict:
    env = get_env()
    return env.get_metrics()


@router.get("/state")
async def get_state() -> dict:
    env = get_env()
    return env.get_state()


@router.get("/action_space/{agent_id}")
async def get_action_space(agent_id: str) -> dict:
    env = get_env()
    actions = env.get_action_space(agent_id)
    if not actions:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return {"agent_id": agent_id, "actions": actions}


@router.get("/observation/{agent_id}")
async def get_observation(agent_id: str) -> dict:
    env = get_env()
    obs = env.get_observation(agent_id)
    if not obs:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return obs


@router.post("/speed")
async def set_speed(req: SpeedRequest) -> dict:
    env = get_env()
    env.set_speed(req.multiplier)
    return {"ok": True, "multiplier": req.multiplier}


@router.post("/pause")
async def pause() -> dict:
    env = get_env()
    env.pause()
    return {"ok": True, "paused": True}


@router.post("/resume")
async def resume() -> dict:
    env = get_env()
    env.resume()
    return {"ok": True, "paused": False}


@router.get("/genome/default")
async def get_default_genome() -> dict:
    from evolution.manufacturing_genome import ManufacturingGenome
    return ManufacturingGenome.default().to_dict()


@router.post("/genome/validate")
async def validate_genome(config: dict) -> dict:
    ok, reason = ConnectivityValidator.validate_config(config)
    return {"valid": ok, "reason": reason}
