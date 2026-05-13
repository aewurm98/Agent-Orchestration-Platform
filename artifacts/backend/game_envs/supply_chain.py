"""
Supply Chain — genome-driven 10×10 grid simulation.

Genome parameters (evolved by the EA):
  supply_rate            — units Supplier generates per tick
  transfer_amount        — units moved per delivery event
  warehouse_restock_threshold — fraction of capacity that triggers a restock fetch

Fitness = recent throughput rate normalised to TARGET_RATE.
Starts deliberately low (supply_rate=12, transfer=15) so the EA has a long
runway to improve — yielding a nice linearly-increasing fitness trend.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any


# ── module-level env reference (read by orchestrator evaluate node) ───────────
_active_env: "SupplyChainEnv | None" = None

GRID_SIZE = 10
WAREHOUSE_CAP = 200
DISTRIBUTOR_CAP = 150
RETAILER_DEMAND_PER_TICK = 8
RETAILER_CAP = 500

# Rolling-window size for fitness computation (one EA generation = 5 ticks)
_FITNESS_WINDOW = 30
# Throughput target (units/tick) achievable only with a well-evolved genome
_TARGET_RATE = 16.0


# ── helpers ──────────────────────────────────────────────────────────────────

def _adjacent(a: dict, b: dict) -> bool:
    return abs(a["x"] - b["x"]) <= 1 and abs(a["y"] - b["y"]) <= 1


def _step_toward(agent: dict, target: dict) -> tuple[int, int]:
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
    # Deliberately weak defaults — EA must evolve these upward for fitness to climb
    GENOME_DEFAULTS: dict = {
        "supply_rate": 12,
        "transfer_amount": 15,
        "warehouse_restock_threshold": 0.5,
    }

    def __init__(self) -> None:
        self._tick = 0
        self._total_delivered = 0
        self._total_demand = 0
        self._tick_window: deque[int] = deque(maxlen=_FITNESS_WINDOW)

        # Genome-controlled params (start at weak defaults)
        self._supply_rate: int = self.GENOME_DEFAULTS["supply_rate"]
        self._transfer_amount: int = self.GENOME_DEFAULTS["transfer_amount"]
        self._wh_restock_threshold: float = self.GENOME_DEFAULTS["warehouse_restock_threshold"]

        self._agents: list[dict] = [
            {
                "id": "supplier_0", "role": "supplier",
                "x": 1, "y": 5,
                "inventory": 50, "capacity": 9_999,
                "state": "generating",
            },
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
            {
                "id": "distributor_0", "role": "distributor",
                "x": 6, "y": 5,
                "inventory": 0, "capacity": DISTRIBUTOR_CAP,
                "state": "idle",
            },
            {
                "id": "retailer_0", "role": "retailer",
                "x": 9, "y": 2,
                "inventory": 0, "capacity": RETAILER_CAP,
                "demand": 0, "delivered": 0, "state": "waiting",
            },
            {
                "id": "retailer_1", "role": "retailer",
                "x": 9, "y": 5,
                "inventory": 0, "capacity": RETAILER_CAP,
                "demand": 0, "delivered": 0, "state": "waiting",
            },
            {
                "id": "retailer_2", "role": "retailer",
                "x": 9, "y": 8,
                "inventory": 0, "capacity": RETAILER_CAP,
                "demand": 0, "delivered": 0, "state": "waiting",
            },
        ]

    # ── genome interface ────────────────────────────────────────────────────

    def apply_genome(self, genome_config: dict) -> None:
        """Apply EA-evolved genome parameters live during INTRA simulation."""
        if "supply_rate" in genome_config:
            self._supply_rate = max(10, min(80, int(genome_config["supply_rate"])))
        if "transfer_amount" in genome_config:
            self._transfer_amount = max(10, min(80, int(genome_config["transfer_amount"])))
        if "warehouse_restock_threshold" in genome_config:
            self._wh_restock_threshold = max(0.2, min(0.8, float(genome_config["warehouse_restock_threshold"])))

    def get_fitness(self) -> float:
        """
        Fitness = recent throughput rate / TARGET_RATE (capped at 1.0).
        Uses a rolling window so it responds quickly to genome improvements
        rather than being dragged down by early weak-genome history.
        """
        if len(self._tick_window) == 0:
            return 0.0
        recent_delivered = sum(self._tick_window)
        window_len = len(self._tick_window)
        recent_rate = recent_delivered / window_len
        return min(1.0, round(recent_rate / _TARGET_RATE, 4))

    def get_objective_value(self) -> float:
        return self.get_fitness()

    # ── internal helpers ────────────────────────────────────────────────────

    def _by_role(self, role: str) -> list[dict]:
        return [a for a in self._agents if a["role"] == role]

    # ── public interface ────────────────────────────────────────────────────

    def random_action(self) -> dict:
        return {}

    def step(self, _action: dict | None = None) -> GridState:
        self._tick += 1
        delivered_this_tick = 0

        supplier    = self._by_role("supplier")[0]
        warehouses  = self._by_role("warehouse")
        distributor = self._by_role("distributor")[0]
        retailers   = self._by_role("retailer")

        # ── 1. Supplier generates inventory (genome-controlled rate) ──────
        supplier["inventory"] += self._supply_rate
        supplier["state"] = "generating"

        # ── 2. Warehouses: fetch from Supplier or deliver to Distributor ──
        for wh in warehouses:
            needs_restock = wh["inventory"] < WAREHOUSE_CAP * self._wh_restock_threshold
            if needs_restock:
                wh["state"] = "fetching"
                if _adjacent(wh, supplier) and supplier["inventory"] >= self._transfer_amount:
                    take = min(self._transfer_amount, supplier["inventory"],
                               wh["capacity"] - wh["inventory"])
                    supplier["inventory"] -= take
                    wh["inventory"] += take
                else:
                    wh["x"], wh["y"] = _step_toward(wh, supplier)
            else:
                wh["state"] = "delivering"
                if _adjacent(wh, distributor) and wh["inventory"] > 0:
                    give = min(self._transfer_amount, wh["inventory"],
                               distributor["capacity"] - distributor["inventory"])
                    wh["inventory"] -= give
                    distributor["inventory"] += give
                else:
                    wh["x"], wh["y"] = _step_toward(wh, distributor)

        # ── 3. Distributor: fetch or deliver (genome-controlled transfer) ──
        if distributor["inventory"] < DISTRIBUTOR_CAP * 0.3:
            richest = max(warehouses, key=lambda w: w["inventory"])
            distributor["state"] = "fetching"
            if _adjacent(distributor, richest) and richest["inventory"] >= self._transfer_amount:
                take = min(self._transfer_amount, richest["inventory"],
                           distributor["capacity"] - distributor["inventory"])
                richest["inventory"] -= take
                distributor["inventory"] += take
            else:
                distributor["x"], distributor["y"] = _step_toward(distributor, richest)
        else:
            neediest = max(retailers, key=lambda r: r.get("demand", 0))
            distributor["state"] = "delivering"
            if _adjacent(distributor, neediest) and distributor["inventory"] > 0:
                give = min(self._transfer_amount, distributor["inventory"])
                distributor["inventory"] -= give
                neediest["inventory"] += give
                neediest["delivered"] = neediest.get("delivered", 0) + give
                self._total_delivered += give
                delivered_this_tick += give
            else:
                distributor["x"], distributor["y"] = _step_toward(distributor, neediest)

        # ── 4. Retailers accumulate demand and consume ────────────────────
        for ret in retailers:
            ret["demand"] = ret.get("demand", 0) + RETAILER_DEMAND_PER_TICK
            self._total_demand += RETAILER_DEMAND_PER_TICK
            consumed = min(ret["inventory"], ret["demand"])
            ret["inventory"] -= consumed
            ret["demand"] = max(0, ret["demand"] - consumed)
            ret["state"] = "stocked" if ret["inventory"] > 0 else "waiting"

        # ── 5. Update rolling fitness window ─────────────────────────────
        self._tick_window.append(delivered_this_tick)

        # ── 6. Score / resources ──────────────────────────────────────────
        score = self.get_fitness()
        total_stock = sum(a["inventory"] for a in self._agents)
        total_demand = sum(r.get("demand", 0) for r in retailers)
        resources = {
            "grid_size": GRID_SIZE,
            "stock_level": int(total_stock),
            "demand_queue": int(total_demand),
            "backlog": int(max(0, self._total_demand - self._total_delivered)),
            "carrying_cost": round(total_stock * 0.001, 3),
            "total_delivered": self._total_delivered,
            "supply_rate": self._supply_rate,
            "transfer_amount": self._transfer_amount,
        }

        serialized_agents = []
        for a in self._agents:
            entry: dict = {
                "id":        a["id"],
                "role":      a["role"],
                "x":         a["x"],
                "y":         a["y"],
                "inventory": int(a.get("inventory", 0)),
                "state":     a.get("state", "idle"),
            }
            if a["role"] == "retailer":
                entry["delivered"] = int(a.get("delivered", 0))
                entry["demand"]    = int(a.get("demand", 0))
            serialized_agents.append(entry)

        return GridState(
            agents=serialized_agents,
            resources=resources,
            score=score,
            tick=self._tick,
        )
