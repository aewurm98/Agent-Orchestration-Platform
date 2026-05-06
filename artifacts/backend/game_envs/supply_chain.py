"""
Supply Chain — fully rule-based 10×10 grid simulation.

Agents
------
  Supplier   ×1   fixed at (1, 5)   — generates SUPPLY_RATE units/tick
  Warehouse  ×2   mobile            — shuttles stock Supplier → Distributor
  Distributor×1   mobile            — routes stock Warehouses → Retailers
  Retailer   ×3   fixed             — consumes stock, accumulates demand

Score = total units delivered to Retailers / max(1, tick)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


GRID_SIZE = 10
SUPPLY_RATE = 25           # units Supplier generates each tick
WAREHOUSE_CAP = 200
DISTRIBUTOR_CAP = 150
RETAILER_DEMAND_PER_TICK = 8   # demand added to each Retailer per tick
TRANSFER_AMT = 30              # units moved on each transfer event


# ── helpers ──────────────────────────────────────────────────────────────────

def _adjacent(a: dict, b: dict) -> bool:
    return abs(a["x"] - b["x"]) <= 1 and abs(a["y"] - b["y"]) <= 1


def _step_toward(agent: dict, target: dict) -> tuple[int, int]:
    """Return new (x, y) one step closer to target, clamped to grid."""
    dx = target["x"] - agent["x"]
    dy = target["y"] - agent["y"]
    nx = agent["x"] + (1 if dx > 0 else -1 if dx < 0 else 0)
    ny = agent["y"] + (1 if dy > 0 else -1 if dy < 0 else 0)
    return max(0, min(GRID_SIZE - 1, nx)), max(0, min(GRID_SIZE - 1, ny))


# ── state container ───────────────────────────────────────────────────────────

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


# ── environment ───────────────────────────────────────────────────────────────

class SupplyChainEnv:
    def __init__(self) -> None:
        self._tick = 0
        self._total_delivered = 0
        self._total_demand = 0

        self._agents: list[dict] = [
            # Supplier — stationary left-centre
            {
                "id": "supplier_0", "role": "supplier",
                "x": 1, "y": 5,
                "inventory": 100, "capacity": 9_999,
                "state": "generating",
            },
            # Warehouses — start mid-left
            {
                "id": "warehouse_0", "role": "warehouse",
                "x": 3, "y": 2,
                "inventory": 0, "capacity": WAREHOUSE_CAP,
                "state": "idle",
            },
            {
                "id": "warehouse_1", "role": "warehouse",
                "x": 3, "y": 7,
                "inventory": 0, "capacity": WAREHOUSE_CAP,
                "state": "idle",
            },
            # Distributor — starts at centre
            {
                "id": "distributor_0", "role": "distributor",
                "x": 6, "y": 5,
                "inventory": 0, "capacity": DISTRIBUTOR_CAP,
                "state": "idle",
            },
            # Retailers — right column, stationary
            {
                "id": "retailer_0", "role": "retailer",
                "x": 9, "y": 2,
                "inventory": 0, "capacity": 500,
                "demand": 0, "delivered": 0, "state": "waiting",
            },
            {
                "id": "retailer_1", "role": "retailer",
                "x": 9, "y": 5,
                "inventory": 0, "capacity": 500,
                "demand": 0, "delivered": 0, "state": "waiting",
            },
            {
                "id": "retailer_2", "role": "retailer",
                "x": 9, "y": 8,
                "inventory": 0, "capacity": 500,
                "demand": 0, "delivered": 0, "state": "waiting",
            },
        ]

    # ── internal helpers ───────────────────────────────────────────────────

    def _by_role(self, role: str) -> list[dict]:
        return [a for a in self._agents if a["role"] == role]

    # ── public interface ───────────────────────────────────────────────────

    def random_action(self) -> dict:
        """Compatibility shim — env is fully self-driven."""
        return {}

    def step(self, _action: dict | None = None) -> GridState:
        self._tick += 1

        supplier    = self._by_role("supplier")[0]
        warehouses  = self._by_role("warehouse")
        distributor = self._by_role("distributor")[0]
        retailers   = self._by_role("retailer")

        # ── 1. Supplier generates inventory ──────────────────────────────
        supplier["inventory"] += SUPPLY_RATE
        supplier["state"] = "generating"

        # ── 2. Warehouses: fetch from Supplier or deliver to Distributor ──
        for wh in warehouses:
            needs_restock = wh["inventory"] < WAREHOUSE_CAP * 0.4
            if needs_restock:
                wh["state"] = "fetching"
                if _adjacent(wh, supplier) and supplier["inventory"] >= TRANSFER_AMT:
                    take = min(TRANSFER_AMT, supplier["inventory"],
                               wh["capacity"] - wh["inventory"])
                    supplier["inventory"] -= take
                    wh["inventory"] += take
                else:
                    wh["x"], wh["y"] = _step_toward(wh, supplier)
            else:
                wh["state"] = "delivering"
                if _adjacent(wh, distributor) and wh["inventory"] > 0:
                    give = min(TRANSFER_AMT, wh["inventory"],
                               distributor["capacity"] - distributor["inventory"])
                    wh["inventory"] -= give
                    distributor["inventory"] += give
                else:
                    wh["x"], wh["y"] = _step_toward(wh, distributor)

        # ── 3. Distributor: fetch from richest Warehouse or deliver to neediest Retailer ──
        if distributor["inventory"] < DISTRIBUTOR_CAP * 0.3:
            richest = max(warehouses, key=lambda w: w["inventory"])
            distributor["state"] = "fetching"
            if _adjacent(distributor, richest) and richest["inventory"] >= TRANSFER_AMT:
                take = min(TRANSFER_AMT, richest["inventory"],
                           distributor["capacity"] - distributor["inventory"])
                richest["inventory"] -= take
                distributor["inventory"] += take
            else:
                distributor["x"], distributor["y"] = _step_toward(distributor, richest)
        else:
            neediest = max(retailers, key=lambda r: r.get("demand", 0))
            distributor["state"] = "delivering"
            if _adjacent(distributor, neediest) and distributor["inventory"] > 0:
                give = min(TRANSFER_AMT, distributor["inventory"])
                distributor["inventory"] -= give
                neediest["inventory"] += give
                neediest["delivered"] = neediest.get("delivered", 0) + give
                self._total_delivered += give
            else:
                distributor["x"], distributor["y"] = _step_toward(distributor, neediest)

        # ── 4. Retailers accumulate demand and consume from local inventory ──
        for ret in retailers:
            ret["demand"] = ret.get("demand", 0) + RETAILER_DEMAND_PER_TICK
            self._total_demand += RETAILER_DEMAND_PER_TICK
            consumed = min(ret["inventory"], ret["demand"])
            ret["inventory"] -= consumed
            ret["demand"] = max(0, ret["demand"] - consumed)
            ret["state"] = "stocked" if ret["inventory"] > 0 else "waiting"

        # ── 5. Score = total_delivered / tick ─────────────────────────────
        score = self._total_delivered / self._tick

        # ── 6. Aggregate resources ─────────────────────────────────────────
        total_stock = sum(a["inventory"] for a in self._agents)
        total_demand = sum(r.get("demand", 0) for r in retailers)
        resources = {
            "grid_size": GRID_SIZE,
            "stock_level": int(total_stock),
            "demand_queue": int(total_demand),
            "backlog": int(max(0, self._total_demand - self._total_delivered)),
            "carrying_cost": round(total_stock * 0.001, 3),
            "total_delivered": self._total_delivered,
        }

        # Serialize — only expose fields the frontend needs
        serialized_agents = [
            {
                "id":        a["id"],
                "role":      a["role"],
                "x":         a["x"],
                "y":         a["y"],
                "inventory": int(a.get("inventory", 0)),
                "state":     a.get("state", "idle"),
            }
            for a in self._agents
        ]

        return GridState(
            agents=serialized_agents,
            resources=resources,
            score=score,
            tick=self._tick,
        )

    def get_objective_value(self) -> float:
        if self._total_demand == 0:
            return 0.0
        return min(1.0, self._total_delivered / self._total_demand)
