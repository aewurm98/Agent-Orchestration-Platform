"""
Disaster Relief game environment: rescue teams navigate a disaster grid.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass
class GridState:
    agents: list[dict]
    resources: dict[str, Any]
    score: float
    tick: int

    def to_json(self) -> dict:
        return {
            "scenario": "disaster_relief",
            "agents": self.agents,
            "resources": self.resources,
            "score": round(self.score, 4),
            "tick": self.tick,
        }


GRID_SIZE = 10
ZONES = ["north", "south", "east", "west", "central"]


class DisasterReliefEnv:
    def __init__(self):
        self._tick = 0
        self._score = 0.0
        self._agents = [
            {"id": f"team_{i}", "x": random.randint(0, GRID_SIZE - 1), "y": random.randint(0, GRID_SIZE - 1),
             "role": role, "survivors_rescued": 0, "supplies": random.randint(50, 200)}
            for i, role in enumerate(["rescue", "medical", "logistics", "command"])
        ]
        self._resources = {
            "total_survivors": 500,
            "rescued": 0,
            "supplies_deployed": 0,
            "zones_cleared": 0,
            "active_zones": random.randint(3, 5),
            "grid_size": GRID_SIZE,
        }

    def random_action(self) -> dict:
        return {
            "type": random.choice(["deploy_team", "rescue", "resupply", "evacuate"]),
            "zone": random.choice(ZONES),
            "team_id": f"team_{random.randint(0, 3)}",
        }

    def step(self, action: dict) -> GridState:
        self._tick += 1

        rescued_this_tick = random.randint(0, 20)
        self._resources["rescued"] = min(self._resources["total_survivors"], self._resources["rescued"] + rescued_this_tick)
        self._resources["supplies_deployed"] += random.randint(5, 30)
        self._resources["zones_cleared"] = min(5, self._resources["zones_cleared"] + (1 if random.random() > 0.85 else 0))

        for agent in self._agents:
            agent["x"] = (agent["x"] + random.randint(-2, 2)) % GRID_SIZE
            agent["y"] = (agent["y"] + random.randint(-2, 2)) % GRID_SIZE
            agent["survivors_rescued"] += random.randint(0, 5)
            agent["supplies"] = max(0, agent["supplies"] - random.randint(1, 10))

        rescue_rate = self._resources["rescued"] / max(self._resources["total_survivors"], 1)
        self._score = rescue_rate

        return GridState(
            agents=list(self._agents),
            resources=dict(self._resources),
            score=self._score,
            tick=self._tick,
        )

    def get_objective_value(self) -> float:
        return min(1.0, max(0.0, self._resources["rescued"] / max(self._resources["total_survivors"], 1)))
