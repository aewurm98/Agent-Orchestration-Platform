"""
ManufacturingEnvV2: high-level wrapper around WorldModel.

Exposes reset(config), step(actions), tick(), to_json(), and fitness extraction.
Compatible with the main simulation loop in main.py.
"""
from __future__ import annotations

from typing import Any, Optional

from .world import WorldModel
from .entities import CellType, MachineType, AgentRole, SpeedMode
from .scenarios import FIRST_FACTORY_CONFIG
from .economics import MetricsSnapshot


class ManufacturingEnvV2:
    def __init__(self, config: Optional[dict] = None):
        self._config = config or FIRST_FACTORY_CONFIG
        self.world: WorldModel = self._build_world(self._config)

    def _build_world(self, config: dict) -> WorldModel:
        world = WorldModel(
            grid_rows=config.get("grid_rows", 10),
            grid_cols=config.get("grid_cols", 10),
            starting_budget=config.get("starting_budget", 8_000.0),
            simulation_length=config.get("simulation_length", 300),
            order_arrival_rate=config.get("order_arrival_rate", 12),
            random_seed=config.get("random_seed"),
            execution_mode=config.get("execution_mode", "async_buffered"),
        )

        for (r, c), ct in config.get("cell_overrides", {}).items():
            world.set_cell(r, c, ct)

        for m_cfg in config.get("machines", []):
            world.add_machine(
                machine_id=m_cfg["id"],
                machine_type=m_cfg["type"],
                row=m_cfg["row"],
                col=m_cfg["col"],
                speed=m_cfg.get("speed", SpeedMode.NORMAL),
            )

        for a_cfg in config.get("agents", []):
            world.add_agent(
                agent_id=a_cfg["id"],
                role=a_cfg["role"],
                row=a_cfg["row"],
                col=a_cfg["col"],
            )

        return world

    def reset(self, config: Optional[dict] = None) -> dict:
        if config:
            self._config = config
        self.world = self._build_world(self._config)
        return self.world.to_json()

    def step(self, actions: Optional[dict[str, dict]] = None) -> dict:
        result = self.world.tick_advance(actions)
        state = self.world.to_json()
        state["_tick_result"] = result
        return state

    def tick(self) -> None:
        self.world.tick_advance()

    def to_json(self) -> dict:
        return self.world.to_json()

    def get_metrics(self) -> dict:
        metrics = self.world.economy.snapshot(
            self.world.tick, self.world.agents, self.world.machines
        )
        return metrics.to_dict()

    def get_state(self) -> dict:
        return self.world.to_json()

    def get_action_space(self, agent_id: str) -> list[str]:
        return self.world.get_action_space(agent_id)

    def get_observation(self, agent_id: str) -> dict:
        return self.world.get_observation(agent_id)

    def get_fitness(self) -> float:
        metrics = self.world.economy.snapshot(
            self.world.tick, self.world.agents, self.world.machines
        )
        return metrics.fitness_scalar()

    def get_fitness_vector(self) -> list[float]:
        metrics = self.world.economy.snapshot(
            self.world.tick, self.world.agents, self.world.machines
        )
        return metrics.fitness_vector()

    @property
    def done(self) -> bool:
        return self.world.done

    @property
    def tick_count(self) -> int:
        return self.world.tick

    def connectivity_valid(self) -> tuple[bool, str]:
        return self.world.connectivity_valid()

    def set_speed(self, multiplier: float) -> None:
        self.world._speed_multiplier = multiplier

    def pause(self) -> None:
        self.world._paused = True

    def resume(self) -> None:
        self.world._paused = False
