"""
WorldModel: core simulation engine for Manufacturing v2.

Manages the grid, entities, tick processing, and serialization.
"""
from __future__ import annotations

import math
import random
import uuid
from typing import Any, Optional

from .entities import (
    Agent, AgentRole, AgentState, CellType, Item, ItemType,
    Machine, MachineState, MachineType, Order, SpeedMode,
    ITEM_PURCHASE_COST, ITEM_SALE_PRICE,
)
from .recipes import RecipeEngine
from .economics import EconomicModel, MetricsSnapshot
from .actions import apply_micro_action, decompose_macro_action


class WorldModel:
    def __init__(
        self,
        grid_rows: int = 12,
        grid_cols: int = 12,
        starting_budget: float = 10_000.0,
        simulation_length: int = 500,
        order_arrival_rate: int = 15,
        random_seed: Optional[int] = None,
        execution_mode: str = "async_buffered",
    ):
        self.rows = grid_rows
        self.cols = grid_cols
        self.simulation_length = simulation_length
        self.order_arrival_rate = order_arrival_rate
        # "sync"           — deterministic serial order (alphabetical agent id)
        # "async_buffered" — agents execute in random order each tick
        self.execution_mode = execution_mode

        self.rng = random.Random(random_seed)
        self.tick: int = 0
        self.done: bool = False

        self.grid: list[list[CellType]] = [
            [CellType.FLOOR] * grid_cols for _ in range(grid_rows)
        ]
        self.machines: dict[str, Machine] = {}
        self.agents: dict[str, Agent] = {}
        self.items: dict[str, Item] = {}
        self.orders: list[Order] = []
        self._active_orders: list[Order] = []
        self._fulfilled_orders: list[Order] = []
        self._missed_orders: list[Order] = []

        self.economy = EconomicModel(starting_budget)
        self.recipe_engine = RecipeEngine(self.rng)

        self._pending_alerts: list[dict] = []
        self._action_results: list[dict] = []
        self._speed_multiplier: float = 1.0
        self._paused: bool = False

        self._order_counter = 0
        self._price_fluctuation: float = 0.0

        # Poisson inter-arrival: draw first arrival tick at construction
        self._next_order_tick: float = float(self.rng.expovariate(1.0 / max(order_arrival_rate, 1)))

    # ── Grid / entity setup ───────────────────────────────────────────────────

    def set_cell(self, row: int, col: int, cell_type: CellType) -> None:
        self.grid[row][col] = cell_type

    def add_machine(
        self,
        machine_id: str,
        machine_type: MachineType,
        row: int,
        col: int,
        speed: SpeedMode = SpeedMode.NORMAL,
    ) -> Machine:
        m = Machine(
            id=machine_id,
            machine_type=machine_type,
            row=row,
            col=col,
            speed_mode=speed,
        )
        self.machines[machine_id] = m
        self.grid[row][col] = CellType.MACHINE_SLOT
        return m

    def add_agent(
        self,
        agent_id: str,
        role: AgentRole,
        row: int,
        col: int,
    ) -> Agent:
        a = Agent(id=agent_id, role=role, row=row, col=col)
        self.agents[agent_id] = a
        return a

    # ── Core tick loop ────────────────────────────────────────────────────────

    def tick_advance(self, submitted_actions: Optional[dict[str, dict]] = None) -> dict:
        """
        Advance world by one tick.

        submitted_actions: {agent_id: {type, params}}

        execution_mode:
          "sync"           — agents act in deterministic alphabetical order
          "async_buffered" — agents act in random shuffled order (default)

        Returns: dict with alerts, action_results for this tick.
        """
        if self.done or self._paused:
            return {"alerts": [], "action_results": []}

        self.tick += 1
        alerts: list[dict] = []
        action_results: list[dict] = []

        # ── 1. Decrement agent cooldowns ──────────────────────────────────────
        for agent in self.agents.values():
            if agent.comm_cooldown > 0:
                agent.comm_cooldown -= 1
            if agent.purchase_cooldown > 0:
                agent.purchase_cooldown -= 1
            if agent.forecast_cooldown > 0:
                agent.forecast_cooldown -= 1

        # ── 2. Process machine ticks ──────────────────────────────────────────
        for machine in self.machines.values():
            if machine.state == MachineState.LOADING:
                if self.recipe_engine.can_start(machine):
                    self.recipe_engine.start_processing(machine)
                else:
                    machine.state = MachineState.IDLE
            produced = self.recipe_engine.advance_tick(machine, alerts)
            for item in produced:
                self.items[item.id] = item

        # ── 3. Determine action order based on execution_mode ─────────────────
        if self.execution_mode == "sync":
            action_order = sorted(self.agents.keys())
        else:
            action_order = list(self.agents.keys())
            self.rng.shuffle(action_order)

        # ── 4. Apply agent actions ────────────────────────────────────────────
        for agent_id in action_order:
            agent = self.agents[agent_id]
            if agent.is_standby:
                agent.state = AgentState.STANDBY
                continue

            # Expire completed planned_path each step
            if agent.planned_path and not agent.action_buffer:
                agent.planned_path = []

            action: Optional[dict] = None

            if agent.action_buffer:
                action = agent.action_buffer.pop(0)
            elif submitted_actions and agent_id in submitted_actions:
                raw = submitted_actions[agent_id]
                if raw.get("type") in (
                    "go_to", "pickup_nearest", "deliver_to",
                    "deliver_to_machine", "unload_machine", "work_machine"
                ):
                    steps = decompose_macro_action(
                        agent, raw["type"],
                        raw.get("params", {}),
                        self.grid, self.machines, self.items, self.agents,
                    )
                    agent.action_buffer.extend(steps[1:])
                    if steps:
                        action = steps[0]
                    agent.active_macro = raw["type"]
                else:
                    action = {"type": raw.get("type", "wait"), "params": raw.get("params", {})}

            if action is None:
                action = {"type": "wait", "params": {}}

            result = apply_micro_action(
                agent=agent,
                action_type=action["type"],
                params=action.get("params", {}),
                grid=self.grid,
                machines=self.machines,
                items=self.items,
                agents=self.agents,
                alerts=alerts,
            )

            if not result.ok and action["type"] not in ("wait", "idle"):
                agent.state = AgentState.IDLE

            if action["type"] == "sell" and result.ok:
                item_type_str = result.data.get("item_type", ItemType.FINISHED_PRODUCT.value)
                try:
                    itype = ItemType(item_type_str)
                except Exception:
                    itype = ItemType.FINISHED_PRODUCT
                matched_order = self._find_open_order()
                revenue = self.economy.record_sale(itype, matched_order, self.tick)
                if matched_order:
                    matched_order.fulfilled += 1
                    if matched_order.fulfilled >= matched_order.quantity:
                        self.economy.record_order_fulfilled()
                        self._active_orders.remove(matched_order)
                        self._fulfilled_orders.append(matched_order)
                alerts.append({
                    "type": "sale",
                    "agent_id": agent_id,
                    "item_type": item_type_str,
                    "revenue": round(revenue, 2),
                })

            if action["type"] == "purchase" and result.ok:
                itype_str = result.data.get("item_type", "raw_ore")
                qty = result.data.get("qty", 1)
                try:
                    itype = ItemType(itype_str)
                except Exception:
                    itype = ItemType.RAW_ORE
                ok, msg = self.economy.purchase_materials(itype, qty)
                if not ok:
                    for item_id in result.data.get("purchased", []):
                        if item_id in self.items:
                            item = self.items.pop(item_id)
                            if item in agent.inventory:
                                agent.inventory.remove(item)

            if action["type"] == "hire" and result.ok:
                self._handle_hire(result.data.get("agent_type", "operations"), alerts)

            if action["type"] == "fire" and result.ok:
                target_id = result.data.get("agent_id")
                if target_id and target_id in self.agents:
                    del self.agents[target_id]

            action_results.append({
                "agent_id": agent_id,
                "role": agent.role.value,
                "action": action["type"],
                "params": action.get("params", {}),
                "ok": result.ok,
                "message": result.message,
            })

        # ── 5. Deduct running costs ────────────────────────────────────────────
        self.economy.deduct_wages(self.agents)
        self.economy.deduct_power(self.machines)

        # ── 6. Poisson order arrivals ─────────────────────────────────────────
        # Use exponential inter-arrival times to model a Poisson process.
        # Spawn all orders whose inter-arrival time falls within this tick.
        while self.tick >= self._next_order_tick:
            self._spawn_order()
            inter = self.rng.expovariate(1.0 / max(self.order_arrival_rate, 1))
            self._next_order_tick += inter

        # ── 7. Check expired orders ────────────────────────────────────────────
        newly_missed = [o for o in self._active_orders if o.is_expired(self.tick)]
        for o in newly_missed:
            self.economy.record_order_missed()
            self._active_orders.remove(o)
            self._missed_orders.append(o)
            alerts.append({
                "type": "alert",
                "event": "order_missed",
                "order_id": o.id,
                "deadline": o.deadline_tick,
            })

        # ── 8. Budget warning ──────────────────────────────────────────────────
        warn = self.economy.check_budget_warning()
        if warn:
            alerts.append(warn)

        # ── 9. Check terminal conditions ───────────────────────────────────────
        if self.tick >= self.simulation_length or self.economy.budget <= 0:
            self.done = True

        # ── 10. Price fluctuation ──────────────────────────────────────────────
        self._price_fluctuation = math.sin(self.tick / 30.0) * 10.0

        self._pending_alerts = alerts
        self._action_results = action_results
        return {"alerts": alerts, "action_results": action_results}

    # ── Order / economy helpers ────────────────────────────────────────────────

    def _find_open_order(self) -> Optional[Order]:
        for o in self._active_orders:
            if o.fulfilled < o.quantity:
                return o
        return None

    def _spawn_order(self) -> None:
        self._order_counter += 1
        is_rush = self.rng.random() < 0.2
        deadline = self.tick + self.rng.randint(20, 80)
        base_price = 200.0 + self._price_fluctuation
        order = Order(
            id=f"order_{self._order_counter}",
            product_type=ItemType.FINISHED_PRODUCT,
            quantity=1,
            deadline_tick=deadline,
            base_price=base_price,
            arrival_tick=self.tick,
            is_rush=is_rush,
        )
        self._active_orders.append(order)
        self.orders.append(order)

    def _handle_hire(self, agent_type_str: str, alerts: list) -> None:
        try:
            role = AgentRole(agent_type_str)
        except ValueError:
            role = AgentRole.OPERATIONS
        from .entities import AGENT_HIRE_COST
        cost = AGENT_HIRE_COST[role]
        if self.economy.budget < cost:
            return
        self.economy.budget -= cost
        self.economy.pl.equipment_costs += cost
        agent_id = f"{role.value}_{uuid.uuid4().hex[:4]}"
        spawn_row, spawn_col = self._find_loading_dock()
        self.add_agent(agent_id, role, spawn_row, spawn_col)
        alerts.append({
            "type": "alert",
            "event": "agent_hired",
            "agent_id": agent_id,
            "role": role.value,
        })

    def _find_loading_dock(self) -> tuple[int, int]:
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == CellType.LOADING_DOCK:
                    return (r, c)
        return (0, 0)

    def _find_shipping_dock(self) -> tuple[int, int]:
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == CellType.SHIPPING_DOCK:
                    return (r, c)
        return (self.rows - 1, self.cols - 1)

    # ── Observation / serialisation ───────────────────────────────────────────

    def get_observation(self, agent_id: str) -> dict:
        agent = self.agents.get(agent_id)
        if not agent:
            return {}
        vis = agent.visibility()
        visible_machines: dict[str, dict] = {}
        visible_items: list[dict] = []
        for mid, m in self.machines.items():
            if vis >= 999 or (abs(m.row - agent.row) + abs(m.col - agent.col)) <= vis:
                visible_machines[mid] = m.to_dict()
        for iid, item in self.items.items():
            if item.row is None:
                continue
            if vis >= 999 or (abs(item.row - agent.row) + abs(item.col - agent.col)) <= vis:
                visible_items.append(item.to_dict())
        return {
            "agent": agent.to_dict(),
            "tick": self.tick,
            "budget": round(self.economy.budget, 2),
            "visible_machines": visible_machines,
            "visible_items": visible_items,
            "inventory": [i.to_dict() for i in agent.inventory],
            "messages": agent.messages,
            "active_orders": [o.to_dict() for o in self._active_orders[:5]],
            "grid_cell": self.grid[agent.row][agent.col].value,
        }

    def get_action_space(self, agent_id: str) -> list[str]:
        """Return only actions that are fully implemented in apply_micro_action."""
        agent = self.agents.get(agent_id)
        if not agent:
            return []
        role = agent.role
        # "broadcast", "idle" are valid no-ops but not useful for planning; include them.
        # Removed from every role: any action whose elif branch doesn't exist or returns
        # "Unknown action" (stockpile, request_help, install_machine, remove_machine,
        # negotiate_price, forecast_demand, set_budget_allocation, approve_purchase).
        common = ["wait", "move", "broadcast", "idle"]
        role_actions: dict[AgentRole, list[str]] = {
            AgentRole.PROCUREMENT:  ["purchase", "pickup", "drop", "check_prices"],
            AgentRole.OPERATIONS:   ["pickup", "drop", "load_machine", "unload_machine", "start_machine"],
            AgentRole.ENGINEERING:  ["repair", "set_speed", "diagnose"],
            AgentRole.SALES:        ["sell", "pickup", "drop", "check_orders"],
            AgentRole.MANAGEMENT:   ["hire", "fire", "assign_task", "view_financials"],
        }
        macro = ["go_to", "pickup_nearest", "deliver_to", "deliver_to_machine", "work_machine"]
        return common + role_actions.get(role, []) + macro

    def get_state_json(self) -> dict:
        return self.to_json()

    def to_json(self) -> dict:
        metrics = self.economy.snapshot(self.tick, self.agents, self.machines)
        orders_list = [o.to_dict() for o in self._active_orders]
        return {
            "scenario": "manufacturing",
            "tick": self.tick,
            "done": self.done,
            "grid": [[cell.value for cell in row] for row in self.grid],
            "grid_rows": self.rows,
            "grid_cols": self.cols,
            "agents": {aid: a.to_dict() for aid, a in self.agents.items()},
            "machines": {mid: m.to_dict() for mid, m in self.machines.items()},
            # Include ALL items: floor items (carrier_id=None) AND carried items
            "items": [i.to_dict() for i in self.items.values()],
            "budget": round(self.economy.budget, 2),
            "starting_budget": round(self.economy.starting_budget, 2),
            # Spec-compliant field name
            "orders": orders_list,
            # Backward-compat alias
            "active_orders": orders_list,
            "metrics": metrics.to_dict(),
            "fitness": metrics.fitness_scalar(),
            "score": metrics.fitness_scalar(),
            "alerts": self._pending_alerts,
            "simulation_length": self.simulation_length,
            "resources": {
                "grid_size": max(self.rows, self.cols),
                "budget": round(self.economy.budget, 2),
                "throughput": metrics.throughput,
                "orders_fulfilled": metrics.orders_fulfilled,
                "orders_missed": metrics.orders_missed,
                "profit": round(metrics.current_profit, 2),
            },
        }

    def connectivity_valid(self) -> tuple[bool, str]:
        """
        BFS from all Loading Dock cells.
        Checks:
          1. All machines have at least one reachable adjacent walkable cell.
          2. At least one Shipping Dock is reachable.
          3. All agent spawn positions are reachable (agents cannot be trapped).
        """
        from collections import deque

        WALKABLE = {
            CellType.FLOOR, CellType.CONVEYOR,
            CellType.LOADING_DOCK, CellType.SHIPPING_DOCK, CellType.STORAGE_ZONE,
        }

        starts: list[tuple[int, int]] = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == CellType.LOADING_DOCK:
                    starts.append((r, c))

        if not starts:
            return False, "No Loading Dock found"

        visited: set[tuple[int, int]] = set()
        queue: deque[tuple[int, int]] = deque(starts)
        for s in starts:
            visited.add(s)

        while queue:
            r, c = queue.popleft()
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if (nr, nc) in visited:
                    continue
                if not (0 <= nr < self.rows and 0 <= nc < self.cols):
                    continue
                cell = self.grid[nr][nc]
                if cell in WALKABLE:
                    visited.add((nr, nc))
                    queue.append((nr, nc))
                elif cell == CellType.MACHINE_SLOT:
                    visited.add((nr, nc))

        # 1. Machine reachability
        machine_unreachable = []
        for m in self.machines.values():
            adj_reachable = any(
                (m.row + dr, m.col + dc) in visited
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]
            )
            if not adj_reachable:
                machine_unreachable.append(m.id)

        if machine_unreachable:
            return False, f"Machines unreachable: {machine_unreachable}"

        # 2. Shipping dock reachability
        shipping_reachable = any(
            self.grid[r][c] == CellType.SHIPPING_DOCK
            for (r, c) in visited
        )
        if not shipping_reachable:
            return False, "Shipping Dock unreachable from Loading Dock"

        # 3. Agent spawn positions not trapped
        trapped_agents = []
        for agent in self.agents.values():
            if (agent.row, agent.col) not in visited:
                trapped_agents.append(agent.id)

        if trapped_agents:
            return False, f"Agents trapped (not reachable from Loading Dock): {trapped_agents}"

        return True, "OK"
