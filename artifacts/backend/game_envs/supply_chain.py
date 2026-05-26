"""
Supply Chain v2 — real-time, deterministic, dual-tier LLM simulation.

A 20×20 terrain grid over which programmatic truck "edge agents" haul cargo from
Suppliers to Demand Zones.  Trucks run on A* autopilot but raise exceptions
(blocked path, full warehouse, market shock, spoiling cargo, gridlock) that are
resolved by a per-truck LLM "brain"; a global Meta-Optimizer reshapes the network
every 25 ticks.  The objective is the Global Liquidity Score (GLS) over a strict
500-tick episode:

    GLS = Total Revenue − (CapEx + OpEx + Penalties)

This module is the deterministic engine.  LLM decision-making lives in
agents.supply_chain_llm (with programmatic fallbacks), driven by the dedicated
simulation loop in main.py.  The engine is fully runnable headlessly using the
built-in programmatic fallbacks (see resolve_exception / apply_director_action).

Spec: artifacts/screenshots/jadelynn/Supply Chain v2 Spec.md
"""
from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from typing import Any, Optional

# ── module-level env reference (read by main.py socket handlers) ──────────────
_active_env: "SupplyChainEnv | None" = None

GRID = 20
EPISODE_TICKS = 500

# Terrain movement costs (spec §1.1)
TERRAIN_COST = {"highway": 1.0, "off_road": 3.0, "obstacle": float("inf")}

# Economics (spec §1.3 / §1.4)
SUPPLIER_GEN_UNITS = 10
SUPPLIER_GEN_PERIOD = 5
SUPPLIER_PRICE = 20.0            # $/unit purchase cost (OpEx when loaded)
DEMAND_RATE = 5                  # units accrued per tick per demand zone
DEMAND_BASE_PRICE = 100.0        # $/unit sale price
DEMAND_PENALTY = 50.0            # $/tick while accumulated_demand > 0
WAREHOUSE_HOLDING = 2.0          # $/tick per warehouse with cargo
TRUCK_CAPACITY = 50
TRUCK_UPKEEP = 5.0               # $/tick
SPOILAGE_PER_TICK = 1.0          # % health lost per tick in transit
SPOILAGE_PENALTY = 50.0          # $ bio-hazard cleanup on total spoilage
TRUCK_SPAWN_COST = 2000.0

# Market shock (spec §1.3)
SHOCK_LAMBDA = 0.02
SHOCK_MULT = 2.5
SHOCK_MIN_DUR, SHOCK_MAX_DUR = 10, 30

# Director infrastructure costs (spec §4.1)
INFRA = {
    "Micro_Fulfillment": {"cost": 5000.0, "capacity": 100},
    "Mega_Warehouse": {"cost": 20000.0, "capacity": 500},
    "Toll_Road": {"cost": 1000.0},
}

STARTING_CAPITAL = 50000.0

# Tripwire radius for market-shock proximity (spec §3.1)
SHOCK_RADIUS = 3
GRIDLOCK_TICKS = 3
CARGO_CRITICAL = 15.0


# ── A* pathfinding over terrain ───────────────────────────────────────────────

def astar(grid: list[list[str]], start: tuple[int, int], goal: tuple[int, int]) -> Optional[list[tuple[int, int]]]:
    """Least-cost path (list of (x,y) excluding start, including goal) or None.
    Cells are (x, y); grid is indexed grid[y][x]. Obstacles are impassable."""
    if start == goal:
        return []
    sx, sy = start
    gx, gy = goal

    def passable(x: int, y: int) -> bool:
        return 0 <= x < GRID and 0 <= y < GRID and grid[y][x] != "obstacle"

    if not passable(gx, gy):
        return None

    open_heap: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
    came: dict[tuple[int, int], tuple[int, int]] = {}
    gscore: dict[tuple[int, int], float] = {start: 0.0}
    while open_heap:
        _, cur = heapq.heappop(open_heap)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path[1:]  # drop start
        cx, cy = cur
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not passable(nx, ny):
                continue
            step_cost = TERRAIN_COST[grid[ny][nx]]
            tentative = gscore[cur] + step_cost
            if tentative < gscore.get((nx, ny), float("inf")):
                gscore[(nx, ny)] = tentative
                came[(nx, ny)] = cur
                h = abs(nx - gx) + abs(ny - gy)
                heapq.heappush(open_heap, (tentative + h, (nx, ny)))
    return None


# ── Nodes ──────────────────────────────────────────────────────────────────────

@dataclass
class Node:
    id: str
    kind: str          # "supplier" | "demand" | "warehouse"
    x: int
    y: int
    # supplier
    stock: int = 0
    gen_accum: int = 0
    # demand
    accumulated_demand: int = 0
    base_price: float = DEMAND_BASE_PRICE
    price_mod: float = 1.0          # director adjust_incentives multiplier
    shock_ticks: int = 0            # remaining shocked ticks
    served: int = 0
    # warehouse
    inventory: int = 0
    capacity: int = 0
    bribe_threshold: float = 500.0

    @property
    def current_price(self) -> float:
        mult = SHOCK_MULT if self.shock_ticks > 0 else 1.0
        return self.base_price * mult * self.price_mod

    def to_dict(self) -> dict:
        d = {"id": self.id, "kind": self.kind, "x": self.x, "y": self.y}
        if self.kind == "supplier":
            d["stock"] = self.stock
        elif self.kind == "demand":
            d.update(
                accumulated_demand=self.accumulated_demand,
                price=round(self.current_price, 1),
                shocked=self.shock_ticks > 0,
                served=self.served,
            )
        elif self.kind == "warehouse":
            d.update(inventory=self.inventory, capacity=self.capacity,
                     full=self.inventory >= self.capacity)
        return d


# ── Trucks (edge agents) ─────────────────────────────────────────────────────

@dataclass
class Truck:
    id: str
    x: int
    y: int
    state: str = "AUTOPILOT"        # AUTOPILOT | THINKING | EXECUTING_OVERRIDE
    cargo: int = 0
    cargo_health: float = 100.0
    ledger: float = 0.0
    target_id: Optional[str] = None
    path: list[tuple[int, int]] = field(default_factory=list)
    mission: str = "to_supplier"    # to_supplier | to_demand
    risk: str = "Medium"            # persona trait
    greed: str = "Medium"           # persona trait
    wait_ticks: int = 0
    stuck_counter: int = 0
    _prev_pos: tuple[int, int] = (0, 0)
    last_event: str = ""
    queued_override: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "x": self.x, "y": self.y, "state": self.state,
            "cargo": self.cargo, "capacity": TRUCK_CAPACITY,
            "cargo_health": round(self.cargo_health, 1),
            "ledger": round(self.ledger, 1), "target": self.target_id,
            "mission": self.mission, "risk": self.risk, "greed": self.greed,
            "last_event": self.last_event,
        }


# ── Edge exception types ──────────────────────────────────────────────────────

class EdgeException(Exception):
    def __init__(self, kind: str, detail: str):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


class SupplyChainEnv:
    # Genome defaults — fields the EA may evolve. Phase-3 expansion makes
    # supply_rate / transfer_amount actually wire through to env behavior (see
    # apply_genome + tick_logic). warehouse_restock_threshold is reserved for a
    # future warehouse-buying behavior; currently a vestigial knob.
    GENOME_DEFAULTS: dict = {
        "fleet_size": 3,
        "supply_rate": SUPPLIER_GEN_UNITS,
        "transfer_amount": TRUCK_CAPACITY,
        "warehouse_restock_threshold": 0.5,
    }

    def __init__(self) -> None:
        self._rng = random.Random(42)
        self._tick = 0
        self.done = False
        # Per-instance overrides for module constants the EA evolves. Default to
        # the module-level constants so behavior is unchanged when no genome is applied.
        self._supply_gen_units: int = SUPPLIER_GEN_UNITS
        self._supply_gen_period: int = SUPPLIER_GEN_PERIOD
        self._truck_capacity: int = TRUCK_CAPACITY

        # Ledger components (GLS = revenue - (capex + opex + penalties))
        self.revenue = 0.0
        self.capex = 0.0
        self.opex = 0.0
        self.penalties = 0.0
        self.capital = STARTING_CAPITAL

        self.grid = self._build_terrain()
        self.nodes: dict[str, Node] = {}
        self.trucks: list[Truck] = []
        self._truck_counter = 0
        self._build_initial_network()

        # rolling GLS window for trend reporting
        self._gls_history: list[float] = []
        self.alerts: list[str] = []
        self.director_log: list[dict] = []

    # ── world construction ────────────────────────────────────────────────────

    def _build_terrain(self) -> list[list[str]]:
        g = [["off_road"] * GRID for _ in range(GRID)]
        # Two highway corridors (one horizontal, one vertical) — cheap arteries.
        for x in range(GRID):
            g[5][x] = "highway"
            g[14][x] = "highway"
        for y in range(GRID):
            g[y][6] = "highway"
            g[y][13] = "highway"
        # Scatter obstacles, avoiding highways.
        placed = 0
        while placed < 18:
            x, y = self._rng.randrange(GRID), self._rng.randrange(GRID)
            if g[y][x] == "off_road" and not (x in (6, 13) or y in (5, 14)):
                g[y][x] = "obstacle"
                placed += 1
        return g

    def _build_initial_network(self) -> None:
        # Suppliers on the left, demand zones on the right.
        self.nodes["supplier_0"] = Node("supplier_0", "supplier", x=2, y=5, stock=30)
        self.nodes["supplier_1"] = Node("supplier_1", "supplier", x=2, y=14, stock=30)
        self.nodes["demand_0"] = Node("demand_0", "demand", x=17, y=3)
        self.nodes["demand_1"] = Node("demand_1", "demand", x=17, y=10)
        self.nodes["demand_2"] = Node("demand_2", "demand", x=17, y=16)
        # Ensure node cells are passable.
        for n in self.nodes.values():
            self.grid[n.y][n.x] = "highway" if self.grid[n.y][n.x] == "obstacle" else self.grid[n.y][n.x]
        for _ in range(3):
            self._spawn_truck("supplier_0", charge=False)

    def _spawn_truck(self, start_node_id: str, charge: bool = True) -> Truck:
        node = self.nodes.get(start_node_id) or next(iter(self.nodes.values()))
        self._truck_counter += 1
        t = Truck(id=f"truck_{self._truck_counter}", x=node.x, y=node.y)
        t._prev_pos = (t.x, t.y)
        self.trucks.append(t)
        if charge:
            self.capex += TRUCK_SPAWN_COST
            self.capital -= TRUCK_SPAWN_COST
        return t

    # ── compatibility shims (orchestrator / sockets) ──────────────────────────

    def random_action(self) -> dict:
        return {}

    def apply_genome(self, genome_config: dict) -> None:
        """Apply an evolved genome to this env instance.

        Supported fields (any missing fall back to current value):
          fleet_size:   target number of trucks (1-10 typical)
          supply_rate:  cargo units generated per supplier per generation event
          transfer_amount: max units a truck may load per pickup
          warehouse_restock_threshold: reserved for future warehouse logic; ignored today
        """
        if "fleet_size" in genome_config:
            target = int(genome_config["fleet_size"])
            while len(self.trucks) < target:
                self._spawn_truck("supplier_0")
            while len(self.trucks) > max(1, target):
                self.trucks.pop()
        if "supply_rate" in genome_config:
            self._supply_gen_units = max(1, int(genome_config["supply_rate"]))
        if "transfer_amount" in genome_config:
            self._truck_capacity = max(1, int(genome_config["transfer_amount"]))

    def set_user_knobs(self, knobs: dict) -> None:
        # Live UI override: global demand pressure (scales each zone's accrual).
        pass

    def get_fitness(self) -> float:
        return round(self.gls, 2)

    def get_objective_value(self) -> float:
        return self.get_fitness()

    @property
    def gls(self) -> float:
        return self.revenue - (self.capex + self.opex + self.penalties)

    # ── node helpers ───────────────────────────────────────────────────────────

    def _nodes_by_kind(self, kind: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind == kind]

    def _nearest_node(self, t: Truck, kind: str, predicate=None) -> Optional[Node]:
        cands = [n for n in self._nodes_by_kind(kind) if (predicate is None or predicate(n))]
        if not cands:
            return None
        return min(cands, key=lambda n: abs(n.x - t.x) + abs(n.y - t.y))

    def _assign_mission_target(self, t: Truck) -> None:
        """Pick a target node for the truck's current mission and plan an A* path."""
        if t.cargo > 0:
            t.mission = "to_demand"
            # Prefer the neediest reachable demand zone.
            demands = self._nodes_by_kind("demand")
            target = max(demands, key=lambda n: n.accumulated_demand) if demands else None
        else:
            t.mission = "to_supplier"
            target = self._nearest_node(t, "supplier", predicate=lambda n: n.stock > 0) \
                or self._nearest_node(t, "supplier")
        if target is None:
            t.target_id = None
            t.path = []
            return
        t.target_id = target.id
        t.path = astar(self.grid, (t.x, t.y), (target.x, target.y)) or []

    # ── core tick (programmatic phases A/B/D; exceptions returned for LLM) ─────

    def step(self, _action: Any = None) -> "GridState":
        """Advance one programmatic tick.  Returns a GridState; pending edge
        exceptions are exposed via self.pending_exceptions for the loop to
        resolve with the LLM brain (or fallback)."""
        self._tick += 1
        self.alerts = []
        self.pending_exceptions: list[tuple[Truck, EdgeException]] = []

        # ── B. Edge agent updates ─────────────────────────────────────────────
        for t in self.trucks:
            # 1. Mandatory upkeep & spoilage physics
            t.ledger -= TRUCK_UPKEEP
            self.opex += TRUCK_UPKEEP
            if t.cargo > 0:
                t.cargo_health -= SPOILAGE_PER_TICK
                if t.cargo_health <= 0.0:
                    t.cargo = 0
                    t.cargo_health = 0.0
                    t.ledger -= SPOILAGE_PENALTY
                    self.penalties += SPOILAGE_PENALTY
                    t.last_event = "cargo spoiled"
                    self.alerts.append(f"{t.id} cargo spoiled (-${SPOILAGE_PENALTY:.0f})")

            # 2. State machine
            if t.state == "THINKING":
                continue  # awaiting LLM decision applied later this tick
            if t.state == "EXECUTING_OVERRIDE":
                self._step_override(t)
                continue
            # AUTOPILOT
            try:
                self._step_autopilot(t)
            except EdgeException as e:
                t.state = "THINKING"
                t.last_event = f"⚠ {e.kind}"
                self.pending_exceptions.append((t, e))

        # ── D. Node updates ───────────────────────────────────────────────────
        self._update_nodes()

        # GLS bookkeeping & terminal condition
        self._gls_history.append(self.gls)
        if self._tick >= EPISODE_TICKS:
            self.done = True

        return self._state()

    def _step_autopilot(self, t: Truck) -> None:
        # (Re)plan if we have no path/target.
        if t.target_id is None or not t.path:
            if t.target_id is None:
                self._assign_mission_target(t)
            arrived = self._try_interact(t)
            if arrived:
                return
            if not t.path:
                self._assign_mission_target(t)
                if not t.path:
                    return  # nowhere to go this tick

        # Passive tripwire: market shock proximity.
        for dz in self._nodes_by_kind("demand"):
            if dz.shock_ticks > 0 and abs(dz.x - t.x) + abs(dz.y - t.y) <= SHOCK_RADIUS \
                    and dz.current_price > 1.5 * dz.base_price and t.cargo > 0 and dz.id != t.target_id:
                raise EdgeException("MarketShockException",
                                    f"Price spike at {dz.id}: ${dz.current_price:.0f}/unit within {SHOCK_RADIUS} cells")

        # Cargo critical tripwire.
        if t.cargo > 0 and t.cargo_health < CARGO_CRITICAL:
            raise EdgeException("CargoCriticalException",
                                f"Cargo health {t.cargo_health:.0f}% — spoilage imminent")

        # Step one cell along the path.
        next_cell = t.path[0]
        nx, ny = next_cell
        if self.grid[ny][nx] == "obstacle":
            t.path = astar(self.grid, (t.x, t.y), self._target_xy(t)) or []
            if not t.path:
                raise EdgeException("PathImpassableException",
                                    f"Route to {t.target_id} blocked by a new obstacle")
            next_cell = t.path[0]
            nx, ny = next_cell

        # Gridlock detection.
        if (t.x, t.y) == t._prev_pos:
            t.stuck_counter += 1
        else:
            t.stuck_counter = 0
        t._prev_pos = (t.x, t.y)
        if t.stuck_counter >= GRIDLOCK_TICKS:
            raise EdgeException("GridlockException",
                                f"{t.id} has not moved for {GRIDLOCK_TICKS} ticks")

        # Pay movement cost and advance.
        move_cost = TERRAIN_COST[self.grid[ny][nx]]
        t.ledger -= move_cost
        self.opex += move_cost
        t.x, t.y = nx, ny
        t.path.pop(0)

        # Arrived?
        if not t.path:
            refusal = self._try_interact(t)
            # _try_interact may raise NodeRefusalException internally

    def _target_xy(self, t: Truck) -> tuple[int, int]:
        n = self.nodes.get(t.target_id or "")
        return (n.x, n.y) if n else (t.x, t.y)

    def _try_interact(self, t: Truck) -> bool:
        """If the truck is at its target node, perform load/unload. Returns True
        if an interaction (or arrival handling) happened this tick."""
        node = self.nodes.get(t.target_id or "")
        if node is None or (t.x, t.y) != (node.x, node.y):
            return False

        if node.kind == "supplier" and t.cargo == 0:
            take = min(self._truck_capacity, node.stock)
            if take <= 0:
                # supplier empty — reassign elsewhere
                t.target_id = None
                return True
            node.stock -= take
            t.cargo = take
            t.cargo_health = 100.0
            cost = take * SUPPLIER_PRICE
            t.ledger -= cost
            self.opex += cost
            t.last_event = f"loaded {take}u"
            t.target_id = None  # next tick assigns a demand zone
            return True

        if node.kind == "demand" and t.cargo > 0:
            sold = min(t.cargo, max(node.accumulated_demand, t.cargo))
            sold = min(sold, t.cargo)
            rev = sold * node.current_price
            self.revenue += rev
            t.ledger += rev
            node.accumulated_demand = max(0, node.accumulated_demand - sold)
            node.served += sold
            t.cargo -= sold
            t.last_event = f"sold {sold}u (+${rev:.0f})"
            t.target_id = None
            return True

        if node.kind == "warehouse":
            if t.cargo > 0:
                if node.inventory >= node.capacity:
                    raise EdgeException("NodeRefusalException",
                                        f"{node.id} is full ({node.inventory}/{node.capacity})")
                space = node.capacity - node.inventory
                moved = min(space, t.cargo)
                node.inventory += moved
                t.cargo -= moved
                t.last_event = f"stored {moved}u @ {node.id}"
            t.target_id = None
            return True

        return False

    def _step_override(self, t: Truck) -> None:
        """Execute a one-shot LLM override action, then return to autopilot."""
        ov = t.queued_override or {"action": "ignore"}
        action = ov.get("action", "ignore")
        if action == "wait":
            t.wait_ticks = max(0, int(ov.get("ticks", 1)) - 1)
            if t.wait_ticks <= 0:
                t.state = "AUTOPILOT"
            t.last_event = "waiting"
            if t.wait_ticks <= 0:
                t.queued_override = None
            return
        if action == "reroute":
            tid = ov.get("target_node_id")
            if tid in self.nodes:
                t.target_id = tid
                t.path = astar(self.grid, (t.x, t.y), (self.nodes[tid].x, self.nodes[tid].y)) or []
            else:
                t.target_id = None
            t.last_event = f"rerouted→{tid}"
        elif action == "liquidate_cargo":
            disc = float(ov.get("discount_percent", 0.5))
            disc = max(0.0, min(1.0, disc))
            value = t.cargo * DEMAND_BASE_PRICE * disc
            self.revenue += value
            t.ledger += value
            t.last_event = f"liquidated {t.cargo}u (+${value:.0f})"
            t.cargo = 0
            t.target_id = None
        elif action == "bribe_node":
            tid = ov.get("target_node_id")
            amount = float(ov.get("amount", 0.0))
            t.ledger -= amount
            self.opex += amount
            node = self.nodes.get(tid or "")
            if node and node.kind == "warehouse" and amount > node.bribe_threshold:
                # Bribe accepted: node drops oldest inventory to take the cargo.
                node.inventory = max(0, node.inventory - t.cargo)
                t.target_id = tid
                t.path = astar(self.grid, (t.x, t.y), (node.x, node.y)) or []
            t.last_event = f"bribed {tid} (${amount:.0f})"
        else:  # ignore
            t.last_event = "ignored shock"
        t.queued_override = None
        t.state = "AUTOPILOT"

    def _update_nodes(self) -> None:
        for n in self.nodes.values():
            if n.kind == "supplier":
                n.gen_accum += 1
                if n.gen_accum >= self._supply_gen_period:
                    n.gen_accum = 0
                    n.stock += self._supply_gen_units
            elif n.kind == "demand":
                n.accumulated_demand += DEMAND_RATE
                if n.accumulated_demand > 0:
                    self.penalties += DEMAND_PENALTY
                # market shock lifecycle
                if n.shock_ticks > 0:
                    n.shock_ticks -= 1
                elif self._rng.random() < SHOCK_LAMBDA:
                    n.shock_ticks = self._rng.randint(SHOCK_MIN_DUR, SHOCK_MAX_DUR)
                    self.alerts.append(f"📈 market shock at {n.id} (price ×{SHOCK_MULT})")
            elif n.kind == "warehouse":
                if n.inventory > 0:
                    self.opex += WAREHOUSE_HOLDING

    # ── exception resolution (programmatic fallback) ──────────────────────────

    def build_exception_context(self, t: Truck, e: EdgeException) -> dict:
        local = []
        for n in self.nodes.values():
            if abs(n.x - t.x) + abs(n.y - t.y) <= 5:
                local.append(n.to_dict())
        return {
            "agent_id": t.id, "tick": self._tick, "pos": [t.x, t.y],
            "ledger": round(t.ledger, 1), "cargo": t.cargo,
            "cargo_health": round(t.cargo_health, 1),
            "target": t.target_id, "risk": t.risk, "greed": t.greed,
            "exception_type": e.kind, "exception_detail": e.detail,
            "local_entities": local,
            "nodes": [n.id for n in self.nodes.values()],
        }

    def fallback_edge_decision(self, t: Truck, e: EdgeException) -> dict:
        """Deterministic resolution when no LLM is available."""
        if e.kind == "CargoCriticalException":
            return {"action": "liquidate_cargo", "discount_percent": 0.6}
        if e.kind == "NodeRefusalException":
            dz = self._nearest_node(t, "demand")
            return {"action": "reroute", "target_node_id": dz.id} if dz else {"action": "ignore"}
        if e.kind == "PathImpassableException":
            return {"action": "wait", "ticks": 2}
        if e.kind == "GridlockException":
            return {"action": "wait", "ticks": 1}
        if e.kind == "MarketShockException":
            return {"action": "ignore"}
        return {"action": "ignore"}

    def apply_edge_decision(self, t: Truck, decision: dict) -> None:
        """Apply an LLM/fallback decision: charge the 1-tick thinking penalty
        (spec §2.C) and queue the override for next tick."""
        t.ledger -= TRUCK_UPKEEP
        self.opex += TRUCK_UPKEEP
        if t.cargo > 0:
            t.cargo_health -= SPOILAGE_PER_TICK
        t.queued_override = decision or {"action": "ignore"}
        t.state = "EXECUTING_OVERRIDE"

    # ── director (meta-optimizer) interface ───────────────────────────────────

    def director_digest(self) -> dict:
        trend = 0.0
        if len(self._gls_history) >= 26:
            prev = self._gls_history[-26]
            if prev != 0:
                trend = round((self.gls - prev) / abs(prev) * 100, 1)
        alerts = []
        for n in self._nodes_by_kind("demand"):
            if n.accumulated_demand > 50:
                alerts.append(f"{n.id} backlog {n.accumulated_demand}u (penalty stacking)")
            if n.shock_ticks > 0:
                alerts.append(f"{n.id} price shock active (×{SHOCK_MULT})")
        for n in self._nodes_by_kind("warehouse"):
            if n.inventory >= n.capacity:
                alerts.append(f"{n.id} at capacity")
        stuck = [t.id for t in self.trucks if t.stuck_counter >= 2]
        if stuck:
            alerts.append(f"gridlock risk: {', '.join(stuck)}")
        return {
            "tick": self._tick, "gls": round(self.gls, 1), "gls_trend_pct": trend,
            "fleet_count": len(self.trucks), "capital": round(self.capital, 1),
            "alerts": alerts or ["network nominal"],
            "fleet_personas": [{"id": t.id, "risk": t.risk, "greed": t.greed} for t in self.trucks],
            "nodes": [n.to_dict() for n in self.nodes.values()],
        }

    def fallback_director_actions(self) -> list[dict]:
        """Deterministic director heuristics when no LLM is available."""
        actions: list[dict] = []
        demands = self._nodes_by_kind("demand")
        worst = max(demands, key=lambda n: n.accumulated_demand) if demands else None
        # If backlog is severe and we can afford it, add a truck.
        if worst and worst.accumulated_demand > 80 and self.capital > TRUCK_SPAWN_COST:
            sup = self._nodes_by_kind("supplier")[0]
            actions.append({"action": "spawn_fleet", "count": 1, "start_node_id": sup.id})
        # Nudge incentives on the most-backlogged zone.
        if worst and worst.price_mod < 1.5:
            actions.append({"action": "adjust_incentives", "node_id": worst.id, "price_mod": 1.5})
        return actions

    def apply_director_action(self, action: dict) -> str:
        """Apply one validated director tool call. Returns a human-readable note.
        Out-of-bounds / malformed actions are penalised and ignored (spec §5.1)."""
        kind = action.get("action")
        try:
            if kind == "build_infrastructure":
                ntype = action.get("node_type") or action.get("type")
                x, y = int(action.get("x", -1)), int(action.get("y", -1))
                if ntype not in INFRA or not (0 <= x < GRID and 0 <= y < GRID):
                    raise ValueError("bad infrastructure spec")
                spec = INFRA[ntype]
                cost = spec["cost"]
                self.capex += cost
                self.capital -= cost
                if ntype == "Toll_Road":
                    self.grid[y][x] = "highway"
                    note = f"built Toll_Road @({x},{y})"
                else:
                    nid = f"warehouse_{len([n for n in self.nodes.values() if n.kind=='warehouse'])}"
                    self.nodes[nid] = Node(nid, "warehouse", x=x, y=y, capacity=spec["capacity"])
                    if self.grid[y][x] == "obstacle":
                        self.grid[y][x] = "off_road"
                    note = f"built {ntype} {nid} @({x},{y})"
            elif kind == "spawn_fleet":
                count = max(0, min(10, int(action.get("count", 1))))
                start = action.get("start_node_id")
                if start not in self.nodes:
                    start = self._nodes_by_kind("supplier")[0].id
                for _ in range(count):
                    self._spawn_truck(start)
                note = f"spawned {count} truck(s) @ {start}"
            elif kind == "mutate_persona":
                gid = action.get("group_id", "all")
                trait = action.get("trait", "").lower()
                val = action.get("new_value", "Medium")
                if val not in ("Low", "Medium", "High"):
                    raise ValueError("bad persona value")
                for t in self.trucks:
                    if gid in ("all", t.id):
                        if trait in ("risk_tolerance", "risk"):
                            t.risk = val
                        elif trait == "greed":
                            t.greed = val
                note = f"persona {gid}.{trait}={val}"
            elif kind == "adjust_incentives":
                nid = action.get("node_id")
                mod = float(action.get("price_mod", 1.0))
                node = self.nodes.get(nid or "")
                if not node:
                    raise ValueError("unknown node")
                node.price_mod = max(0.5, min(3.0, mod))
                note = f"incentive {nid} ×{node.price_mod}"
            else:
                raise ValueError(f"unknown tool {kind}")
        except Exception as exc:
            self.penalties += 500.0  # spec §5.1 validation fine
            return f"rejected {kind} ({exc}) — $500 fine"
        self.director_log.append({"tick": self._tick, "note": note})
        return note

    # ── serialisation ──────────────────────────────────────────────────────────

    def _state(self) -> "GridState":
        return GridState(env=self)

    def to_json(self) -> dict:
        return self._state().to_json()


@dataclass
class GridState:
    env: SupplyChainEnv

    def to_json(self) -> dict:
        e = self.env
        # Compact agent list reuses the generic GameAgent shape (id/role/x/y/...).
        agents = [
            {"id": t.id, "role": "truck", "x": t.x, "y": t.y,
             "state": t.state, "inventory": t.cargo}
            for t in e.trucks
        ]
        return {
            "scenario": "supply_chain",
            "tick": e._tick,
            "score": round(e.gls, 2),
            "agents": agents,
            "resources": {
                "grid_size": GRID,
                "total_delivered": int(sum(n.served for n in e._nodes_by_kind("demand"))),
                "backlog": int(sum(n.accumulated_demand for n in e._nodes_by_kind("demand"))),
            },
            # Rich v2 payload consumed by SupplyChainView.
            "sc": {
                "grid": e.grid,
                "nodes": [n.to_dict() for n in e.nodes.values()],
                "trucks": [t.to_dict() for t in e.trucks],
                "gls": round(e.gls, 1),
                "revenue": round(e.revenue, 1),
                "capex": round(e.capex, 1),
                "opex": round(e.opex, 1),
                "penalties": round(e.penalties, 1),
                "capital": round(e.capital, 1),
                "fleet": len(e.trucks),
                "episode_ticks": EPISODE_TICKS,
                "alerts": e.alerts,
                "director_log": e.director_log[-6:],
            },
        }
