"""
Manufacturing v3 — Topological Flow Graph environment (spec §2-§4).

The factory is a directed acyclic graph of processing Nodes (machines) connected
by logistics Edges (conveyors). There are no spatial coordinates and no agent
pathfinding: the deterministic tick() loop in §3.4 advances queues, processing
timers, and soft-degradation breakdowns, while the economics in §4 accumulate
revenue, OpEx, material cost, and end-of-episode penalties.

Determinism: the only stochastic element is the per-batch breakdown roll, driven
by a seeded random.Random, so a given (genome, seed, length) yields identical
fitness — which the minibatch evaluator and the test-suite rely on.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .genome import ManufacturingV3Genome, MACHINE_IDS, EDGE_IDS

# ── Spec constants ───────────────────────────────────────────────────────────
EPISODE_TICKS = 500
PROCESS_TICKS = 2          # §3.2 — a batch takes exactly 2 ticks
REPAIR_TICKS = 15          # §3.3 — a DOWN machine stays down 15 ticks

# §3.3 breakdown probability per the batch-start roll, keyed by maintenance policy
BREAKDOWN_PROB: dict[str, float] = {"low": 0.02, "medium": 0.005, "high": 0.0005}

# §4.1 financial constants
REVENUE_PER_GOOD = 1000.0
MATERIAL_COST_PLASTIC = 50.0
MATERIAL_COST_COPPER = 50.0
MISSED_ORDER_PENALTY = 200.0

# §4.2 maintenance OpEx per tick
MAINTENANCE_COST: dict[str, float] = {"low": 10.0, "medium": 30.0, "high": 80.0}

# Item types flowing through the graph
RAW_PLASTIC = "raw_plastic"
RAW_COPPER = "raw_copper"
MOLDED_CASING = "molded_casing"
SPOOL = "spool"
UNVERIFIED_UNIT = "unverified_unit"
FINISHED_GOOD = "finished_good"

# Node recipes: inputs Counter -> outputs Counter (one "set" per application)
RECIPES: dict[str, tuple[dict[str, int], dict[str, int]]] = {
    "molding": ({RAW_PLASTIC: 1}, {MOLDED_CASING: 1}),
    "wire_drawing": ({RAW_COPPER: 1}, {SPOOL: 1}),
    "assembly": ({MOLDED_CASING: 1, SPOOL: 1}, {UNVERIFIED_UNIT: 1}),
    "packaging": ({UNVERIFIED_UNIT: 1}, {FINISHED_GOOD: 1}),
}

SINK = "__sink__"

# Edge wiring: (edge_id, src_node, dst_node, item_type). §2.2.
EDGES: tuple[tuple[str, str, str, str], ...] = (
    ("in_to_molding", "inbound", "molding", RAW_PLASTIC),
    ("in_to_wire", "inbound", "wire_drawing", RAW_COPPER),
    ("molding_to_assembly", "molding", "assembly", MOLDED_CASING),
    ("wire_to_assembly", "wire_drawing", "assembly", SPOOL),
    ("assembly_to_packaging", "assembly", "packaging", UNVERIFIED_UNIT),
    ("packaging_to_out", "packaging", SINK, FINISHED_GOOD),
)

# Node states
IDLE, PROCESSING, DOWN = "IDLE", "PROCESSING", "DOWN"


@dataclass
class Node:
    node_id: str
    capacity: int
    state: str = IDLE
    input_queue: Counter = field(default_factory=Counter)
    output_queue: Counter = field(default_factory=Counter)
    process_timer: int = 0
    repair_timer: int = 0
    # batch currently in the processing core; dropped to output_queue when timer hits 0
    processing_batch: Counter = field(default_factory=Counter)
    # telemetry accumulators
    processing_ticks: int = 0
    down_ticks: int = 0
    failure_count: int = 0
    _input_q_sum: int = 0
    _output_q_sum: int = 0

    def input_count(self) -> int:
        return sum(self.input_queue.values())

    def output_count(self) -> int:
        return sum(self.output_queue.values())


class ManufacturingV3Env:
    def __init__(
        self,
        genome: ManufacturingV3Genome | dict | None = None,
        simulation_length: int = EPISODE_TICKS,
        seed: Optional[int] = None,
    ):
        if isinstance(genome, dict):
            genome = ManufacturingV3Genome.from_dict(genome)
        self.genome: ManufacturingV3Genome = genome or ManufacturingV3Genome.default()
        self.simulation_length = int(simulation_length)
        self._rng = random.Random(seed)
        self.seed = seed

        self.tick = 0

        # Inbound docks: a pure source node holding raw materials deposited at spawn.
        self.inbound = Node(node_id="inbound", capacity=0)

        # Processing nodes
        caps = self.genome.machine_capacities
        self.nodes: dict[str, Node] = {
            mid: Node(node_id=mid, capacity=int(caps[mid])) for mid in MACHINE_IDS
        }

        # §3.1 order spawning math
        self.order_intake_rate = int(self.genome.order_intake_rate)
        self.ticks_per_order = self.simulation_length / max(1, self.order_intake_rate)

        # Order / economics bookkeeping
        self.orders_received = 0
        self.orders_fulfilled = 0
        self.total_revenue = 0.0
        self.total_material_cost = 0.0
        self.total_opex = 0.0       # machine + edge + maintenance, accrued per tick
        self._tick_opex = self._compute_tick_opex()

        # per-tick flow telemetry (last tick's edge throughput)
        self.edge_flow: dict[str, int] = {eid: 0 for eid in EDGE_IDS}

    # ── Economics helpers (§4.2) ─────────────────────────────────────────────
    def _compute_tick_opex(self) -> float:
        machine_cost = sum(
            1.00 * (self.nodes[mid].capacity ** 1.2) for mid in MACHINE_IDS
        )
        edge_cost = sum(
            0.50 * (self.genome.edge_bandwidths[eid] ** 1.1) for eid in EDGE_IDS
        )
        maint_cost = MAINTENANCE_COST[self.genome.maintenance_policy]
        return machine_cost + edge_cost + maint_cost

    @property
    def done(self) -> bool:
        return self.tick >= self.simulation_length

    @property
    def orders_missed(self) -> int:
        return max(0, self.orders_received - self.orders_fulfilled)

    # ── Tick loop (§3.4) ──────────────────────────────────────────────────────
    def step(self) -> None:
        """Advance the simulation by exactly one tick following §3.4 in order."""
        if self.done:
            return

        # 1. Spawn orders ------------------------------------------------------
        self._spawn_orders()

        # 2. Edge transfers ----------------------------------------------------
        self._run_edges()

        # 3. Machine processing ------------------------------------------------
        self._run_machines()

        # 4. Metrics collection + per-tick OpEx accrual ------------------------
        self.total_opex += self._tick_opex
        for node in self.nodes.values():
            node._input_q_sum += node.input_count()
            node._output_q_sum += node.output_count()
            if node.state == PROCESSING:
                node.processing_ticks += 1
            elif node.state == DOWN:
                node.down_ticks += 1

        self.tick += 1

    def run(self, ticks: Optional[int] = None) -> "ManufacturingV3Env":
        """Run to completion (or `ticks` more ticks). Returns self for chaining."""
        limit = self.simulation_length if ticks is None else min(self.tick + ticks, self.simulation_length)
        while self.tick < limit and not self.done:
            self.step()
        return self

    # --- step 1 ---
    def _spawn_orders(self) -> None:
        # Spawn order i at the first tick >= i * ticks_per_order (§3.1). This emits
        # exactly `order_intake_rate` orders over the episode, evenly spaced, and is
        # robust to a non-integer ticks_per_order (e.g. rate=90 -> 5.55 ticks/order).
        while (
            self.orders_received < self.order_intake_rate
            and self.tick + 1e-9 >= self.orders_received * self.ticks_per_order
        ):
            self.orders_received += 1
            self.inbound.output_queue[RAW_PLASTIC] += 1
            self.inbound.output_queue[RAW_COPPER] += 1
            self.total_material_cost += MATERIAL_COST_PLASTIC + MATERIAL_COST_COPPER

    # --- step 2 ---
    def _run_edges(self) -> None:
        for eid, src, dst, item in EDGES:
            bandwidth = self.genome.edge_bandwidths[eid]
            src_node = self.inbound if src == "inbound" else self.nodes[src]
            available = src_node.output_queue[item]
            moved = min(bandwidth, available)
            self.edge_flow[eid] = moved
            if moved <= 0:
                continue
            src_node.output_queue[item] -= moved
            if dst == SINK:
                # §3.4 step 2: items leaving Outbound Docks count as Orders Fulfilled
                self.orders_fulfilled += moved
                self.total_revenue += REVENUE_PER_GOOD * moved
            else:
                self.nodes[dst].input_queue[item] += moved

    # --- step 3 ---
    def _run_machines(self) -> None:
        for mid in MACHINE_IDS:
            node = self.nodes[mid]
            if node.state == DOWN:
                node.repair_timer -= 1
                if node.repair_timer <= 0:
                    node.state = IDLE
            elif node.state == PROCESSING:
                node.process_timer -= 1
                if node.process_timer <= 0:
                    node.output_queue.update(node.processing_batch)
                    node.processing_batch = Counter()
                    node.state = IDLE
            elif node.state == IDLE:
                self._try_start(node, mid)

    def _try_start(self, node: Node, mid: str) -> None:
        inputs, outputs = RECIPES[mid]
        # how many complete ingredient sets the queue can supply
        available_sets = min(
            node.input_queue[item] // qty for item, qty in inputs.items()
        )
        if available_sets <= 0:
            return  # genuinely idle (no work) — §3.3: no breakdown roll when not processing

        # §3.4 step 3: at the moment it would begin processing, roll for breakdown.
        if self._rng.random() < BREAKDOWN_PROB[self.genome.maintenance_policy]:
            node.state = DOWN
            node.repair_timer = REPAIR_TICKS
            node.failure_count += 1
            return  # materials remain frozen in the input_queue (§3.3)

        sets = min(node.capacity, available_sets)
        for item, qty in inputs.items():
            node.input_queue[item] -= qty * sets
        batch = Counter()
        for item, qty in outputs.items():
            batch[item] += qty * sets
        node.processing_batch = batch
        node.state = PROCESSING
        node.process_timer = PROCESS_TICKS

    # ── Economics / fitness (§4.3) ────────────────────────────────────────────
    def get_fitness(self) -> float:
        """Fitness = Revenue - (OpEx + Material) - Penalties (§4.3).

        Penalty uses orders_missed (received but not fulfilled). At mid-episode
        this counts in-flight orders as missed; at the 500-tick deadline it is the
        true unfulfilled count, which is what the EA evaluates.
        """
        penalties = MISSED_ORDER_PENALTY * self.orders_missed
        return round(
            self.total_revenue
            - (self.total_opex + self.total_material_cost)
            - penalties,
            2,
        )

    def get_fitness_vector(self) -> list[float]:
        """Decomposed objective for the EA / digest: [revenue, -opex, -material, -penalty]."""
        return [
            round(self.total_revenue, 2),
            round(-self.total_opex, 2),
            round(-self.total_material_cost, 2),
            round(-MISSED_ORDER_PENALTY * self.orders_missed, 2),
        ]

    # ── Telemetry (§5.2 diagnostics) ──────────────────────────────────────────
    def _node_diagnostics(self) -> dict[str, dict]:
        elapsed = max(1, self.tick)
        diag: dict[str, dict] = {}
        for mid in MACHINE_IDS:
            n = self.nodes[mid]
            diag[mid] = {
                "utilization": round(n.processing_ticks / elapsed, 3),
                "avg_input_queue": round(n._input_q_sum / elapsed, 2),
                "avg_output_queue": round(n._output_q_sum / elapsed, 2),
                "input_queue": n.input_count(),
                "output_queue": n.output_count(),
                "state": n.state,
                "failure_count": n.failure_count,
                "capacity": n.capacity,
            }
        return diag

    def get_metrics(self) -> dict:
        return {
            "tick": self.tick,
            "orders_received": self.orders_received,
            "orders_fulfilled": self.orders_fulfilled,
            "orders_missed": self.orders_missed,
            "throughput": self.orders_fulfilled,
            "total_revenue": round(self.total_revenue, 2),
            "total_opex": round(self.total_opex, 2),
            "total_material_cost": round(self.total_material_cost, 2),
            "penalties": round(MISSED_ORDER_PENALTY * self.orders_missed, 2),
            "fitness": self.get_fitness(),
            "tick_opex": round(self._tick_opex, 2),
            "node_diagnostics": self._node_diagnostics(),
            "edge_bandwidths": dict(self.genome.edge_bandwidths),
            "edge_flow": dict(self.edge_flow),
            "maintenance_policy": self.genome.maintenance_policy,
            "order_intake_rate": self.order_intake_rate,
        }

    def to_json(self) -> dict:
        """Frontend-friendly snapshot of the flow graph."""
        diag = self._node_diagnostics()
        return {
            "scenario": "manufacturing_v3",
            "tick": self.tick,
            "simulation_length": self.simulation_length,
            "done": self.done,
            "nodes": [
                {
                    "id": mid,
                    "label": mid.replace("_", " ").title(),
                    "state": self.nodes[mid].state,
                    "capacity": self.nodes[mid].capacity,
                    "input_queue": self.nodes[mid].input_count(),
                    "output_queue": self.nodes[mid].output_count(),
                    "utilization": diag[mid]["utilization"],
                }
                for mid in MACHINE_IDS
            ],
            "edges": [
                {
                    "id": eid,
                    "source": src,
                    "target": dst,
                    "bandwidth": self.genome.edge_bandwidths[eid],
                    "flow": self.edge_flow[eid],
                    "item": item,
                }
                for eid, src, dst, item in EDGES
            ],
            "economics": {
                "revenue": round(self.total_revenue, 2),
                "opex": round(self.total_opex, 2),
                "material_cost": round(self.total_material_cost, 2),
                "penalties": round(MISSED_ORDER_PENALTY * self.orders_missed, 2),
                "fitness": self.get_fitness(),
            },
            "orders": {
                "received": self.orders_received,
                "fulfilled": self.orders_fulfilled,
                "missed": self.orders_missed,
            },
        }
