"""
Economic model for the Manufacturing v2 simulation.

Tracks P&L, wages, power costs, material purchases, and revenue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .entities import (
    Agent, AgentRole, AgentState, Item, ItemType, Machine, MachineState,
    ITEM_PURCHASE_COST, ITEM_SALE_PRICE, Order,
)


@dataclass
class PLSnapshot:
    total_revenue: float = 0.0
    material_costs: float = 0.0
    equipment_costs: float = 0.0
    labor_costs: float = 0.0
    modification_costs: float = 0.0
    penalties: float = 0.0

    @property
    def total_costs(self) -> float:
        return (
            self.material_costs
            + self.equipment_costs
            + self.labor_costs
            + self.modification_costs
            + self.penalties
        )

    @property
    def profit(self) -> float:
        return self.total_revenue - self.total_costs

    def to_dict(self) -> dict:
        return {
            "total_revenue": round(self.total_revenue, 2),
            "material_costs": round(self.material_costs, 2),
            "equipment_costs": round(self.equipment_costs, 2),
            "labor_costs": round(self.labor_costs, 2),
            "modification_costs": round(self.modification_costs, 2),
            "penalties": round(self.penalties, 2),
            "total_costs": round(self.total_costs, 2),
            "profit": round(self.profit, 2),
        }


@dataclass
class MetricsSnapshot:
    tick: int = 0
    throughput: int = 0
    avg_latency: float = 0.0
    total_revenue: float = 0.0
    total_costs: float = 0.0
    current_profit: float = 0.0
    agent_idle_ratio: float = 0.0
    machine_utilization: float = 0.0
    queue_lengths: dict = field(default_factory=dict)
    orders_fulfilled: int = 0
    orders_missed: int = 0
    budget: float = 0.0
    pl: dict = field(default_factory=dict)

    @property
    def missed_rate(self) -> float:
        """Fraction of all orders (fulfilled + missed) that expired unfulfilled."""
        return self.orders_missed / max(self.orders_fulfilled + self.orders_missed, 1)

    def fitness_vector(self) -> list[float]:
        """
        Spec §3.2 — 5 components in specified order, all raw (not negated):
          [0] Profit         cumulative profit (higher is better)
          [1] Throughput     cumulative finished items shipped
          [2] Missed Rate    missed / (fulfilled + missed)  (lower is better)
          [3] Idle Ratio     0-1 fraction of agents idle    (lower is better)
          [4] Machine Util   0-1 (higher is better)
        Sign handling for Missed Rate / Idle Ratio is via negative fitness weights.
        """
        return [
            self.current_profit,
            float(self.throughput),
            self.missed_rate,
            self.agent_idle_ratio,
            self.machine_utilization,
        ]

    def fitness_scalar(
        self,
        weights: Optional[list[float]] = None,
    ) -> float:
        # Spec §3.2 weights aligned to fitness_vector() order:
        # [Profit, Throughput, Missed Rate, Idle Ratio, Machine Util]
        # Missed Rate and Idle Ratio carry negative weights (lower = better).
        if weights is None:
            weights = [0.50, 0.30, -0.15, -0.05, 0.05]
        vec = self.fitness_vector()
        score = 0.0
        for w, v in zip(weights, vec):
            score += w * v
        return round(score, 4)

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "throughput": self.throughput,
            "avg_latency": round(self.avg_latency, 2),
            "total_revenue": round(self.total_revenue, 2),
            "total_costs": round(self.total_costs, 2),
            "current_profit": round(self.current_profit, 2),
            "agent_idle_ratio": round(self.agent_idle_ratio, 3),
            "machine_utilization": round(self.machine_utilization, 3),
            "queue_lengths": self.queue_lengths,
            "orders_fulfilled": self.orders_fulfilled,
            "orders_missed": self.orders_missed,
            "budget": round(self.budget, 2),
            "pl": self.pl,
        }


class EconomicModel:
    def __init__(self, starting_budget: float = 10_000.0):
        self.starting_budget = starting_budget
        self.budget = starting_budget
        self.pl = PLSnapshot()
        self._latency_samples: list[float] = []
        self._finished_items_shipped: int = 0
        self._orders_fulfilled: int = 0
        self._orders_missed: int = 0
        self._pending_alerts: list[dict] = []

    def deduct_wages(self, agents: dict[str, Agent]) -> None:
        for agent in agents.values():
            cost = agent.wage_per_tick()
            self.budget -= cost
            self.pl.labor_costs += cost

    def deduct_power(self, machines: dict[str, Machine]) -> None:
        for machine in machines.values():
            cost = machine.power_cost_per_tick()
            self.budget -= cost
            self.pl.equipment_costs += cost

    def purchase_materials(self, item_type: ItemType, qty: int) -> tuple[bool, str]:
        unit_cost = ITEM_PURCHASE_COST.get(item_type)
        if unit_cost is None:
            return False, f"{item_type.value} cannot be purchased"
        total = unit_cost * qty
        if self.budget < total:
            return False, f"Insufficient budget: need ${total:.0f}, have ${self.budget:.0f}"
        self.budget -= total
        self.pl.material_costs += total
        return True, f"Purchased {qty}x {item_type.value} for ${total:.0f}"

    def record_sale(self, item_type: ItemType, order: Optional[Order], current_tick: int) -> float:
        base = ITEM_SALE_PRICE.get(item_type, 0.0)
        price = base
        if order:
            price = order.effective_price()
            ticks_late = max(0, current_tick - order.deadline_tick)
            if ticks_late > 0:
                penalty = ticks_late * 20.0
                self.budget -= penalty
                self.pl.penalties += penalty
        self.budget += price
        self.pl.total_revenue += price
        self._finished_items_shipped += 1
        return price

    def record_order_fulfilled(self) -> None:
        self._orders_fulfilled += 1

    def record_order_missed(self, penalty: float = 10.0) -> None:
        self._orders_missed += 1
        self.budget -= penalty
        self.pl.penalties += penalty

    def record_latency(self, ticks: float) -> None:
        self._latency_samples.append(ticks)
        if len(self._latency_samples) > 200:
            self._latency_samples = self._latency_samples[-200:]

    def check_budget_warning(self, threshold: float = 0.2) -> Optional[dict]:
        if self.budget < self.starting_budget * threshold:
            return {
                "type": "alert",
                "event": "budget_warning",
                "budget": round(self.budget, 2),
                "message": f"Budget critical: ${self.budget:.0f} remaining",
            }
        return None

    def snapshot(
        self,
        tick: int,
        agents: dict[str, Agent],
        machines: dict[str, Machine],
    ) -> MetricsSnapshot:
        total_agents = len(agents)
        idle_agents = sum(
            1 for a in agents.values()
            if a.state == AgentState.IDLE or a.state == AgentState.STANDBY
        )
        agent_idle_ratio = idle_agents / max(total_agents, 1)

        active_machines = [
            m for m in machines.values()
            if m.state not in (MachineState.OFFLINE,)
        ]
        if active_machines:
            machine_util = sum(m.utilization_signal() for m in active_machines) / len(active_machines)
        else:
            machine_util = 0.0

        queue_lengths = {m.id: len(m.input_queue) for m in machines.values()}
        avg_lat = (
            sum(self._latency_samples) / len(self._latency_samples)
            if self._latency_samples else 0.0
        )

        return MetricsSnapshot(
            tick=tick,
            throughput=self._finished_items_shipped,
            avg_latency=avg_lat,
            total_revenue=self.pl.total_revenue,
            total_costs=self.pl.total_costs,
            current_profit=self.pl.profit,
            agent_idle_ratio=agent_idle_ratio,
            machine_utilization=machine_util,
            queue_lengths=queue_lengths,
            orders_fulfilled=self._orders_fulfilled,
            orders_missed=self._orders_missed,
            budget=self.budget,
            pl=self.pl.to_dict(),
        )

    @property
    def orders_fulfilled(self) -> int:
        return self._orders_fulfilled

    @property
    def orders_missed(self) -> int:
        return self._orders_missed
