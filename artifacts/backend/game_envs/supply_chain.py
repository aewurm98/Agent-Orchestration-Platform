"""
Supply Chain game environment: grid of warehouses, distribution centres, and retail nodes.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GridState:
    agents: list[dict]
    resources: dict[str, Any]
    score: float
    tick: int

    def to_json(self) -> dict:
        return {
            "scenario": "supply_chain",
            "agents": self.agents,
            "resources": self.resources,
            "score": round(self.score, 4),
            "tick": self.tick,
        }


GRID_SIZE = 8
NUM_AGENTS = 4


class SupplyChainEnv:
    def __init__(self):
        self._tick = 0
        self._score = 0.0
        self._agents = [
            {"id": f"agent_{i}", "x": random.randint(0, GRID_SIZE - 1), "y": random.randint(0, GRID_SIZE - 1), "role": r, "inventory": random.randint(10, 100)}
            for i, r in enumerate(["warehouse", "distributor", "retailer", "supplier"])
        ]
        self._resources = {
            "stock_level": random.randint(200, 1000),
            "demand_queue": random.randint(50, 300),
            "backlog": random.randint(0, 50),
            "carrying_cost": round(random.uniform(0.1, 0.5), 3),
            "grid_size": GRID_SIZE,
        }

    def random_action(self) -> dict:
        return {
            "type": random.choice(["reorder", "transfer", "hold"]),
            "agent_id": f"agent_{random.randint(0, NUM_AGENTS - 1)}",
            "quantity": random.randint(5, 50),
        }

    def step(self, action: dict) -> GridState:
        self._tick += 1

        if action.get("type") == "reorder":
            self._resources["stock_level"] = min(1000, self._resources["stock_level"] + action.get("quantity", 10))
        elif action.get("type") == "transfer":
            self._resources["demand_queue"] = max(0, self._resources["demand_queue"] - action.get("quantity", 10))

        demand_filled = max(0, min(self._resources["demand_queue"], self._resources["stock_level"]))
        self._resources["stock_level"] -= demand_filled
        self._resources["demand_queue"] = max(0, self._resources["demand_queue"] - demand_filled + random.randint(10, 40))
        self._resources["backlog"] = max(0, self._resources["demand_queue"] - 100)

        for agent in self._agents:
            agent["x"] = (agent["x"] + random.randint(-1, 1)) % GRID_SIZE
            agent["y"] = (agent["y"] + random.randint(-1, 1)) % GRID_SIZE
            agent["inventory"] = max(0, agent["inventory"] + random.randint(-5, 10))

        fill_rate = demand_filled / max(self._resources["demand_queue"] + demand_filled, 1)
        self._score = self._score * 0.9 + fill_rate * 0.1

        return GridState(
            agents=list(self._agents),
            resources=dict(self._resources),
            score=self._score,
            tick=self._tick,
        )

    def get_objective_value(self) -> float:
        return min(1.0, max(0.0, self._score + random.uniform(-0.05, 0.05)))
