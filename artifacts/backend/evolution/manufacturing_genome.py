"""
Tier 1 genome encoder/decoder and ConnectivityValidator for the Manufacturing v2 EA.

Tier 1 genome fields (12 dimensions):
  - agent_counts: dict[role -> int]  (5 integers)
  - machine_speeds: dict[machine_id -> SpeedMode]  (6 categorical)
  - order_arrival_rate: float  (1 float)
"""
from __future__ import annotations

import copy
import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game_envs.manufacturing_v2.env import ManufacturingEnvV2

from game_envs.manufacturing_v2.entities import AgentRole, SpeedMode
from game_envs.manufacturing_v2.scenarios import FIRST_FACTORY_CONFIG


SPEED_CYCLE = [SpeedMode.LOW, SpeedMode.NORMAL, SpeedMode.HIGH]
# Spec §4.1 — genome agent-count boundaries. Management is fixed (not part of
# the LLM action space) and pinned to a single coordinator agent.
MIN_AGENT_COUNTS: dict[str, int] = {
    "procurement": 1,
    "operations": 1,
    "engineering": 1,
    "sales": 1,
    "management": 1,
}
MAX_AGENT_COUNTS: dict[str, int] = {
    "procurement": 5,
    "operations": 8,
    "engineering": 3,
    "sales": 4,
    "management": 1,
}


class ManufacturingGenome:
    def __init__(
        self,
        agent_counts: Optional[dict[str, int]] = None,
        machine_speeds: Optional[dict[str, str]] = None,
        order_arrival_rate: float = 12.0,
        base_config: Optional[dict] = None,
    ):
        self.agent_counts: dict[str, int] = agent_counts or {
            "procurement": 1,
            "operations": 1,
            "engineering": 1,
            "sales": 1,
            "management": 1,
        }
        self.machine_speeds: dict[str, str] = machine_speeds or {
            "smelter_1": "normal",
            "circuit_fab_1": "normal",
            "press_1": "normal",
            "assembly_1": "normal",
            "qc_1": "normal",
            "packaging_1": "normal",
        }
        self.order_arrival_rate: float = order_arrival_rate
        self._base_config = base_config or copy.deepcopy(FIRST_FACTORY_CONFIG)

    def encode(self) -> list:
        """Encode genome as a flat list for logging / comparison."""
        vec = []
        for role in ["procurement", "operations", "engineering", "sales", "management"]:
            vec.append(self.agent_counts.get(role, 1))
        for mid in sorted(self.machine_speeds.keys()):
            speed_idx = {"low": 0, "normal": 1, "high": 2}.get(self.machine_speeds[mid], 1)
            vec.append(speed_idx)
        vec.append(self.order_arrival_rate)
        return vec

    @classmethod
    def decode(cls, vec: list, machine_ids: Optional[list[str]] = None) -> "ManufacturingGenome":
        roles = ["procurement", "operations", "engineering", "sales", "management"]
        agent_counts = {roles[i]: int(vec[i]) for i in range(5)}
        mids = machine_ids or ["smelter_1", "circuit_fab_1", "press_1", "assembly_1", "qc_1", "packaging_1"]
        machine_speeds = {}
        for j, mid in enumerate(sorted(mids)):
            speed_names = ["low", "normal", "high"]
            idx = min(int(vec[5 + j]), 2)
            machine_speeds[mid] = speed_names[idx]
        order_arrival_rate = float(vec[5 + len(mids)])
        return cls(
            agent_counts=agent_counts,
            machine_speeds=machine_speeds,
            order_arrival_rate=order_arrival_rate,
        )

    def mutate(self, rng: Optional[random.Random] = None) -> "ManufacturingGenome":
        rng = rng or random.Random()
        new_counts = dict(self.agent_counts)
        new_speeds = dict(self.machine_speeds)
        new_rate = self.order_arrival_rate

        mutation = rng.choice(["agent_count", "machine_speed", "order_rate"])

        if mutation == "agent_count":
            role = rng.choice(list(new_counts.keys()))
            delta = rng.choice([-1, 1])
            new_val = new_counts[role] + delta
            new_val = max(MIN_AGENT_COUNTS.get(role, 0), min(MAX_AGENT_COUNTS.get(role, 5), new_val))
            new_counts[role] = new_val

        elif mutation == "machine_speed":
            mid = rng.choice(list(new_speeds.keys()))
            current_mode = SpeedMode(new_speeds[mid])
            idx = SPEED_CYCLE.index(current_mode)
            next_idx = (idx + rng.choice([-1, 1])) % len(SPEED_CYCLE)
            new_speeds[mid] = SPEED_CYCLE[next_idx].value

        elif mutation == "order_rate":
            delta_pct = rng.uniform(-0.15, 0.15)
            new_rate = max(5.0, min(30.0, self.order_arrival_rate * (1 + delta_pct)))

        return ManufacturingGenome(
            agent_counts=new_counts,
            machine_speeds=new_speeds,
            order_arrival_rate=round(new_rate, 1),
            base_config=copy.deepcopy(self._base_config),
        )

    def to_env_config(self) -> dict:
        """Produce an EnvironmentConfig dict for ManufacturingEnvV2.reset()."""
        config = copy.deepcopy(self._base_config)
        config["order_arrival_rate"] = int(round(self.order_arrival_rate))

        for m_cfg in config.get("machines", []):
            mid = m_cfg["id"]
            if mid in self.machine_speeds:
                m_cfg["speed"] = SpeedMode(self.machine_speeds[mid])

        base_agents_by_role = _count_roles(config.get("agents", []))
        target_agents_by_role = dict(self.agent_counts)
        new_agents = []
        for agent_cfg in config.get("agents", []):
            role_str = agent_cfg["role"].value if hasattr(agent_cfg["role"], "value") else str(agent_cfg["role"])
            role_key = role_str
            if target_agents_by_role.get(role_key, 0) > 0:
                new_agents.append(agent_cfg)
                target_agents_by_role[role_key] = target_agents_by_role.get(role_key, 0) - 1

        from game_envs.manufacturing_v2.entities import AgentRole, AGENT_HIRE_COST
        spawn_row, spawn_col = 0, 0
        import uuid
        for role_key, remaining in target_agents_by_role.items():
            for _ in range(max(0, remaining)):
                try:
                    role = AgentRole(role_key)
                except ValueError:
                    continue
                new_agents.append({
                    "id": f"{role_key}_{uuid.uuid4().hex[:4]}",
                    "role": role,
                    "row": spawn_row,
                    "col": spawn_col + len(new_agents) % 2,
                })
        config["agents"] = new_agents
        return config

    def to_dict(self) -> dict:
        return {
            "agent_counts": self.agent_counts,
            "machine_speeds": self.machine_speeds,
            "order_arrival_rate": self.order_arrival_rate,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ManufacturingGenome":
        return cls(
            agent_counts=d.get("agent_counts", {}),
            machine_speeds=d.get("machine_speeds", {}),
            order_arrival_rate=float(d.get("order_arrival_rate", 12.0)),
        )

    @classmethod
    def default(cls) -> "ManufacturingGenome":
        return cls()


def _count_roles(agents: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for a in agents:
        role = a["role"]
        role_str = role.value if hasattr(role, "value") else str(role)
        counts[role_str] = counts.get(role_str, 0) + 1
    return counts


class ConnectivityValidator:
    """
    BFS-based validator: ensures all machines are reachable from a Loading Dock
    and that Shipping Dock is reachable.
    """

    @staticmethod
    def validate(env: "ManufacturingEnvV2") -> tuple[bool, str]:
        return env.world.connectivity_valid()

    @staticmethod
    def validate_config(config: dict) -> tuple[bool, str]:
        from game_envs.manufacturing_v2.env import ManufacturingEnvV2
        env = ManufacturingEnvV2(config)
        return env.world.connectivity_valid()
