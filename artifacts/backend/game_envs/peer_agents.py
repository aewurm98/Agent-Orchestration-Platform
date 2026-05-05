"""
Peer Agents game environment: multi-agent resource auction.
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
            "scenario": "peer_agents",
            "agents": self.agents,
            "resources": self.resources,
            "score": round(self.score, 4),
            "tick": self.tick,
        }


GRID_SIZE = 6
RESOURCE_POOL = 1000


class PeerAgentsEnv:
    def __init__(self):
        self._tick = 0
        self._score = 0.0
        self._total_resources = RESOURCE_POOL
        self._agents = [
            {"id": f"agent_{i}", "x": random.randint(0, GRID_SIZE - 1), "y": random.randint(0, GRID_SIZE - 1),
             "role": f"bidder_{chr(65+i)}", "allocation": 0, "bid": random.randint(10, 100),
             "utility": 0.0, "tasks_completed": 0}
            for i in range(4)
        ]
        self._resources = {
            "total_pool": RESOURCE_POOL,
            "remaining": RESOURCE_POOL,
            "round": 0,
            "nash_distance": 1.0,
            "fairness_index": 0.5,
            "grid_size": GRID_SIZE,
        }

    def random_action(self) -> dict:
        return {
            "type": random.choice(["bid", "negotiate", "yield"]),
            "agent_id": f"agent_{random.randint(0, 3)}",
            "amount": random.randint(5, 150),
        }

    def step(self, action: dict) -> GridState:
        self._tick += 1
        self._resources["round"] += 1

        bids = [a["bid"] for a in self._agents]
        total_bids = sum(bids) or 1
        allocations = [int(b / total_bids * self._total_resources) for b in bids]

        for i, agent in enumerate(self._agents):
            agent["allocation"] = allocations[i]
            agent["bid"] = max(1, agent["bid"] + random.randint(-10, 15))
            agent["utility"] = round(allocations[i] / max(agent["bid"], 1), 3)
            agent["tasks_completed"] += random.randint(0, 3)
            agent["x"] = (agent["x"] + random.randint(-1, 1)) % GRID_SIZE
            agent["y"] = (agent["y"] + random.randint(-1, 1)) % GRID_SIZE

        self._resources["remaining"] = max(0, self._resources["remaining"] - random.randint(10, 50))
        self._resources["nash_distance"] = round(random.uniform(0.05, 0.4), 3)
        self._resources["fairness_index"] = round(1 - self._resources["nash_distance"], 3)

        self._score = self._score * 0.85 + (1 - self._resources["nash_distance"]) * 0.15

        return GridState(
            agents=list(self._agents),
            resources=dict(self._resources),
            score=self._score,
            tick=self._tick,
        )

    def get_objective_value(self) -> float:
        return min(1.0, max(0.0, self._resources["fairness_index"]))
