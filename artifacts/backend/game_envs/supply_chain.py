"""
Supply Chain — genome-driven 10×10 grid simulation.

Genome parameters (evolved by the EA):
  supply_rate            — units Supplier generates per tick
  transfer_amount        — units moved per delivery event
  warehouse_restock_threshold — fraction of capacity that triggers a restock fetch

Demand model (NEW):
  Retailer demand each tick = base_demand + noise + rare_spike, where:
    - noise ~ Normal(0, 1.5) clipped to ±3
    - rare_spike: 2% chance per tick to multiply that tick's demand by 3×
  Seeded deterministically so runs are comparable across simulations
  (small entropy via tick-derived sub-seed).

User overrides (NEW):
  supply_rate_override        — manual production rate, takes precedence over genome
  retail_demand_base_override — manual base demand, takes precedence over default
  Set via the `set_supply_chain_knobs` socket event for INTRA-mode sliders.

Fitness = recent throughput rate normalised to TARGET_RATE.
"""
from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass
from typing import Any


# ── module-level env reference (read by orchestrator evaluate node) ───────────
_active_env: "SupplyChainEnv | None" = None

GRID_SIZE = 10
WAREHOUSE_CAP = 200
DISTRIBUTOR_CAP = 150
RETAILER_DEMAND_BASE = 8         # nominal mean demand per retailer per tick
RETAILER_DEMAND_NOISE_STD = 1.5  # gaussian noise stdev
RETAILER_DEMAND_SPIKE_P = 0.02   # P(rare 3× spike) per retailer per tick
RETAILER_DEMAND_SPIKE_MULT = 3.0
RETAILER_CAP = 500

# Rolling-window size for fitness computation (one EA generation = 5 ticks)
_FITNESS_WINDOW = 30
# Number of retailers — also used to compute the fitness target so EA is
# rewarded for actually meeting demand, not an arbitrary throughput number.
_NUM_RETAILERS = 3
# Throughput target = aggregate expected demand. fitness=1.0 ⇔ full service.
_TARGET_RATE = float(_NUM_RETAILERS * RETAILER_DEMAND_BASE)  # 24.0


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
        self._stockouts = 0           # ticks where a retailer had unfilled demand
        self._customers_served = 0    # cumulative units delivered to end customers

        # Genome-controlled params (start at weak defaults)
        self._supply_rate: int = self.GENOME_DEFAULTS["supply_rate"]
        self._transfer_amount: int = self.GENOME_DEFAULTS["transfer_amount"]
        self._wh_restock_threshold: float = self.GENOME_DEFAULTS["warehouse_restock_threshold"]

        # User-controlled overrides (None = use genome / default)
        self._supply_rate_override: int | None = None
        self._retail_demand_base_override: float | None = None

        # Deterministic RNG so runs are comparable; seeded by a stable seed,
        # entropy enters only through tick number.
        self._demand_rng = random.Random(42)

        # All agents start mutually adjacent (8-way) — removes the walking
        # bottleneck so throughput is gated by genome (transfer_amount,
        # supply_rate) rather than how far apart the agents happen to spawn.
        self._agents: list[dict] = [
            {
                "id": "supplier_0", "role": "supplier",
                "x": 1, "y": 5,
                "inventory": 50, "capacity": 9_999,
                "state": "generating",
            },
            {
                "id": "warehouse_0", "role": "warehouse",
                "x": 2, "y": 4,
                "inventory": 0, "capacity": WAREHOUSE_CAP,
                "state": "idle",
            },
            {
                "id": "warehouse_1", "role": "warehouse",
                "x": 2, "y": 6,
                "inventory": 0, "capacity": WAREHOUSE_CAP,
                "state": "idle",
            },
            {
                "id": "distributor_0", "role": "distributor",
                "x": 3, "y": 5,
                "inventory": 0, "capacity": DISTRIBUTOR_CAP,
                "state": "idle",
            },
            {
                "id": "retailer_0", "role": "retailer",
                "x": 4, "y": 4,
                "inventory": 0, "capacity": RETAILER_CAP,
                "demand": 0, "delivered": 0, "state": "waiting",
            },
            {
                "id": "retailer_1", "role": "retailer",
                "x": 4, "y": 5,
                "inventory": 0, "capacity": RETAILER_CAP,
                "demand": 0, "delivered": 0, "state": "waiting",
            },
            {
                "id": "retailer_2", "role": "retailer",
                "x": 4, "y": 6,
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

    def set_user_knobs(self, knobs: dict) -> None:
        """Apply user-controlled overrides from the UI sliders.

        Either knob can be set to None to clear the override and fall back to
        the genome / default value.
        """
        if "supply_rate" in knobs:
            v = knobs["supply_rate"]
            self._supply_rate_override = None if v is None else max(0, min(120, int(v)))
        if "retail_demand_base" in knobs:
            v = knobs["retail_demand_base"]
            self._retail_demand_base_override = None if v is None else max(0.0, min(40.0, float(v)))

    def _effective_supply_rate(self) -> int:
        return self._supply_rate_override if self._supply_rate_override is not None else self._supply_rate

    def _effective_demand_base(self) -> float:
        if self._retail_demand_base_override is not None:
            return self._retail_demand_base_override
        return float(RETAILER_DEMAND_BASE)

    def _sample_retailer_demand(self) -> int:
        """Stochastic demand per tick: base ± noise + rare spike."""
        base = self._effective_demand_base()
        noise = self._demand_rng.gauss(0.0, RETAILER_DEMAND_NOISE_STD)
        noise = max(-3.0, min(3.0, noise))
        d = base + noise
        if self._demand_rng.random() < RETAILER_DEMAND_SPIKE_P:
            d *= RETAILER_DEMAND_SPIKE_MULT
        return max(0, int(round(d)))

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

        # ── 1. Supplier generates inventory (genome- or user-controlled rate) ──
        supplier["inventory"] += self._effective_supply_rate()
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
            # Deliver to ALL needy retailers this tick, allocating the
            # transfer budget proportionally to each retailer's open demand.
            # Total deliverable this tick is capped at transfer_amount so
            # throughput scales with the evolved genome.
            distributor["state"] = "delivering"
            needy = [r for r in retailers if r.get("demand", 0) > 0]
            adjacent_needy = [r for r in needy if _adjacent(distributor, r)]
            if adjacent_needy and distributor["inventory"] > 0:
                tick_budget = min(self._transfer_amount, distributor["inventory"])
                total_demand = sum(r["demand"] for r in adjacent_needy)
                # Proportional allocation, then floor; redistribute remainder
                # to the neediest retailer so we don't drop fractional units.
                allocations: list[tuple[dict, int]] = []
                allocated = 0
                for r in adjacent_needy:
                    share = int(tick_budget * (r["demand"] / total_demand))
                    allocations.append((r, share))
                    allocated += share
                remainder = tick_budget - allocated
                if remainder > 0 and adjacent_needy:
                    # Give leftover to the neediest
                    adjacent_needy_sorted = sorted(adjacent_needy, key=lambda r: -r["demand"])
                    allocations = [
                        (r, give + (remainder if r is adjacent_needy_sorted[0] else 0))
                        for (r, give) in allocations
                    ]
                for ret, give in allocations:
                    if give <= 0:
                        continue
                    give = min(give, distributor["inventory"], ret["demand"])
                    distributor["inventory"] -= give
                    ret["inventory"] += give
                    ret["delivered"] = ret.get("delivered", 0) + give
                    self._total_delivered += give
                    delivered_this_tick += give
            elif needy and not adjacent_needy:
                # No retailer adjacent — walk toward the neediest one
                neediest = max(needy, key=lambda r: r["demand"])
                distributor["x"], distributor["y"] = _step_toward(distributor, neediest)

        # ── 4. Retailers accumulate stochastic demand and try to fill it ───
        for ret in retailers:
            tick_demand = self._sample_retailer_demand()
            ret["demand"] = ret.get("demand", 0) + tick_demand
            ret["last_demand"] = tick_demand
            self._total_demand += tick_demand

            consumed = min(ret["inventory"], ret["demand"])
            ret["inventory"] -= consumed
            ret["demand"] = max(0, ret["demand"] - consumed)
            ret["last_sold"] = consumed
            self._customers_served += consumed

            # Stockout flag — non-zero unmet demand this tick
            ret["stockout"] = ret["demand"] > 0
            if ret["stockout"]:
                self._stockouts += 1
            ret["state"] = "stocked" if ret["inventory"] > 0 else "waiting"

        # ── 5. Update rolling fitness window ─────────────────────────────
        self._tick_window.append(delivered_this_tick)

        # ── 6. Score / resources ──────────────────────────────────────────
        score = self.get_fitness()
        total_stock = sum(a["inventory"] for a in self._agents)
        total_demand = sum(r.get("demand", 0) for r in retailers)
        # Service level: fraction of cumulative demand that's been served.
        service_level = (self._customers_served / max(1, self._total_demand))

        resources = {
            "grid_size": GRID_SIZE,
            "stock_level": int(total_stock),
            "demand_queue": int(total_demand),
            "backlog": int(max(0, self._total_demand - self._total_delivered)),
            "carrying_cost": round(total_stock * 0.001, 3),
            "total_delivered": self._total_delivered,
            "supply_rate": self._effective_supply_rate(),
            "demand_base": self._effective_demand_base(),
            "transfer_amount": self._transfer_amount,
            "customers_served": self._customers_served,
            "service_level": round(service_level, 4),
            "stockout_ticks": self._stockouts,
            "supply_override": self._supply_rate_override is not None,
            "demand_override": self._retail_demand_base_override is not None,
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
                entry["delivered"]   = int(a.get("delivered", 0))
                entry["demand"]      = int(a.get("demand", 0))
                entry["last_demand"] = int(a.get("last_demand", 0))
                entry["last_sold"]   = int(a.get("last_sold", 0))
                entry["stockout"]    = bool(a.get("stockout", False))
                entry["capacity"]    = int(a.get("capacity", RETAILER_CAP))
            serialized_agents.append(entry)

        return GridState(
            agents=serialized_agents,
            resources=resources,
            score=score,
            tick=self._tick,
        )
