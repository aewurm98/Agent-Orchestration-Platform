"""
Action definitions and A* pathfinding for the Manufacturing v2 simulation.
"""
from __future__ import annotations

import heapq
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .entities import (
    Agent, AgentRole, AgentState, CellType, Item, ItemType,
    Machine, MachineState, ITEM_WEIGHT,
)


@dataclass
class ActionResult:
    ok: bool
    message: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "message": self.message, **self.data}


def astar(
    grid: list[list[CellType]],
    start: tuple[int, int],
    goal: tuple[int, int],
    occupied_cells: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    """
    A* pathfinding over walkable grid cells.
    Returns list of (row, col) steps NOT including start, or empty if no path.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows else 0

    WALKABLE = {
        CellType.FLOOR,
        CellType.CONVEYOR,
        CellType.LOADING_DOCK,
        CellType.SHIPPING_DOCK,
        CellType.STORAGE_ZONE,
    }

    def neighbors(r: int, c: int):
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                cell = grid[nr][nc]
                if cell in WALKABLE or (nr, nc) == goal:
                    if (nr, nc) not in occupied_cells or (nr, nc) == goal:
                        yield (nr, nc)

    def h(a: tuple, b: tuple) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    open_heap: list[tuple[int, tuple[int, int]]] = []
    heapq.heappush(open_heap, (0, start))
    came_from: dict[tuple, Optional[tuple]] = {start: None}
    g_score: dict[tuple, int] = {start: 0}

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current == goal:
            path = []
            while current != start:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path
        for nxt in neighbors(*current):
            tentative_g = g_score[current] + 1
            if tentative_g < g_score.get(nxt, 999999):
                came_from[nxt] = current
                g_score[nxt] = tentative_g
                f = tentative_g + h(nxt, goal)
                heapq.heappush(open_heap, (f, nxt))

    return []


def adjacent_cells(row: int, col: int) -> list[tuple[int, int]]:
    return [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]


def is_adjacent(row1: int, col1: int, row2: int, col2: int) -> bool:
    return (abs(row1 - row2) + abs(col1 - col2)) == 1


def apply_micro_action(
    agent: Agent,
    action_type: str,
    params: dict,
    grid: list[list[CellType]],
    machines: dict[str, Machine],
    items: dict[str, Item],
    agents: dict[str, Agent],
    alerts: list,
) -> ActionResult:
    """
    Execute a single micro-action for an agent.
    Returns ActionResult. On failure, the tick is still consumed.
    """
    ROWS = len(grid)
    COLS = len(grid[0]) if ROWS else 0

    WALKABLE = {
        CellType.FLOOR,
        CellType.CONVEYOR,
        CellType.LOADING_DOCK,
        CellType.SHIPPING_DOCK,
        CellType.STORAGE_ZONE,
    }

    occupied = {
        (a.row, a.col) for a in agents.values() if a.id != agent.id
    }

    if action_type == "move":
        direction = params.get("direction", "wait")
        DIRS = {"north": (-1, 0), "south": (1, 0), "east": (0, 1), "west": (0, -1)}
        if direction not in DIRS:
            return ActionResult(False, f"Unknown direction: {direction}")
        dr, dc = DIRS[direction]
        nr, nc = agent.row + dr, agent.col + dc
        if not (0 <= nr < ROWS and 0 <= nc < COLS):
            return ActionResult(False, "Out of bounds")
        cell = grid[nr][nc]
        if cell not in WALKABLE:
            return ActionResult(False, f"Cell ({nr},{nc}) is not walkable: {cell.value}")
        if (nr, nc) in occupied:
            return ActionResult(False, f"Cell ({nr},{nc}) occupied by another agent")
        agent.row, agent.col = nr, nc
        agent.state = AgentState.MOVING
        return ActionResult(True, f"Moved {direction} to ({nr},{nc})")

    elif action_type == "wait":
        agent.state = AgentState.IDLE
        return ActionResult(True, "Waited")

    elif action_type == "pickup":
        item_id = params.get("item_id")
        if agent.role in (AgentRole.ENGINEERING, AgentRole.MANAGEMENT):
            return ActionResult(False, f"{agent.role.value} cannot carry items")
        if len(agent.inventory) >= agent.carry_capacity():
            return ActionResult(False, "Inventory full")
        target_item: Optional[Item] = None
        if item_id:
            target_item = items.get(item_id)
        else:
            for item in items.values():
                if item.carrier_id is None and item.row == agent.row and item.col == agent.col:
                    target_item = item
                    break
                if item.carrier_id is None and is_adjacent(agent.row, agent.col, item.row or -1, item.col or -1):
                    target_item = item
                    break
        if target_item is None:
            return ActionResult(False, "No item found to pick up")
        if target_item.carrier_id is not None:
            return ActionResult(False, f"Item {target_item.id} already carried")
        target_item.carrier_id = agent.id
        target_item.row = None
        target_item.col = None
        agent.inventory.append(target_item)
        agent.state = AgentState.WORKING
        return ActionResult(True, f"Picked up {target_item.item_type.value}", {"item_id": target_item.id})

    elif action_type == "drop":
        item_id = params.get("item_id")
        if not agent.inventory:
            return ActionResult(False, "Nothing to drop")
        target_item = agent.inventory[0] if not item_id else next(
            (i for i in agent.inventory if i.id == item_id), None
        )
        if target_item is None:
            return ActionResult(False, "Item not in inventory")
        agent.inventory.remove(target_item)
        target_item.carrier_id = None
        target_item.row = agent.row
        target_item.col = agent.col
        items[target_item.id] = target_item
        agent.state = AgentState.IDLE
        return ActionResult(True, f"Dropped {target_item.item_type.value}", {"item_id": target_item.id})

    elif action_type == "load_machine":
        machine_id = params.get("machine_id")
        machine = machines.get(machine_id)
        if machine is None:
            return ActionResult(False, f"Machine {machine_id} not found")
        if not is_adjacent(agent.row, agent.col, machine.row, machine.col):
            return ActionResult(False, "Not adjacent to machine")
        if machine.state == MachineState.BROKEN:
            return ActionResult(False, "Machine is broken")
        if len(machine.input_queue) >= 3:
            return ActionResult(False, "Machine input queue full (max 3)")
        if not agent.inventory:
            return ActionResult(False, "Nothing to load")
        item = agent.inventory.pop(0)
        item.carrier_id = None
        item.row = None
        item.col = None
        machine.input_queue.append(item)
        if machine.state == MachineState.IDLE:
            machine.state = MachineState.LOADING
        agent.state = AgentState.WORKING
        return ActionResult(True, f"Loaded {item.item_type.value} into {machine_id}", {"item_id": item.id})

    elif action_type == "unload_machine":
        machine_id = params.get("machine_id")
        machine = machines.get(machine_id)
        if machine is None:
            return ActionResult(False, f"Machine {machine_id} not found")
        if not is_adjacent(agent.row, agent.col, machine.row, machine.col):
            return ActionResult(False, "Not adjacent to machine")
        if machine.state != MachineState.OUTPUT_READY:
            return ActionResult(False, "Machine has no output ready")
        if len(agent.inventory) >= agent.carry_capacity():
            return ActionResult(False, "Inventory full")
        if not machine.output_queue:
            return ActionResult(False, "Output queue empty")
        item = machine.output_queue.pop(0)
        item.carrier_id = agent.id
        agent.inventory.append(item)
        if not machine.output_queue:
            machine.state = MachineState.IDLE
        agent.state = AgentState.WORKING
        return ActionResult(True, f"Unloaded {item.item_type.value} from {machine_id}", {"item_id": item.id})

    elif action_type == "start_machine":
        machine_id = params.get("machine_id")
        machine = machines.get(machine_id)
        if machine is None:
            return ActionResult(False, f"Machine {machine_id} not found")
        if not is_adjacent(agent.row, agent.col, machine.row, machine.col):
            return ActionResult(False, "Not adjacent to machine")
        if machine.state not in (MachineState.IDLE, MachineState.LOADING):
            return ActionResult(False, f"Machine in state {machine.state.value}, cannot start")
        from .recipes import RecipeEngine, RECIPES
        recipe = RECIPES.get(machine.machine_type)
        if recipe is None:
            return ActionResult(False, "No recipe for this machine type")
        input_counts: dict = {}
        for item in machine.input_queue:
            input_counts[item.item_type] = input_counts.get(item.item_type, 0) + 1
        for itype, qty in recipe["inputs"]:
            if input_counts.get(itype, 0) < qty:
                return ActionResult(False, f"Missing input: {itype.value} (need {qty})")
        machine.state = MachineState.PROCESSING
        machine.processing_ticks_remaining = machine.base_ticks()
        for itype, qty in recipe["inputs"]:
            removed = 0
            new_q = []
            for item in machine.input_queue:
                if item.item_type == itype and removed < qty:
                    removed += 1
                else:
                    new_q.append(item)
            machine.input_queue = new_q
        agent.state = AgentState.WORKING
        return ActionResult(True, f"Started {machine.machine_type.value}")

    elif action_type == "repair":
        machine_id = params.get("machine_id")
        machine = machines.get(machine_id)
        if machine is None:
            return ActionResult(False, f"Machine {machine_id} not found")
        if agent.role != AgentRole.ENGINEERING:
            return ActionResult(False, "Only Engineering agents can repair")
        if not is_adjacent(agent.row, agent.col, machine.row, machine.col):
            return ActionResult(False, "Not adjacent to machine")
        if machine.state != MachineState.BROKEN:
            return ActionResult(False, "Machine is not broken")
        machine.state = MachineState.IDLE
        machine.health = min(1.0, machine.health + 0.3)
        agent.state = AgentState.WORKING
        return ActionResult(True, f"Repaired {machine_id}")

    elif action_type == "set_speed":
        machine_id = params.get("machine_id")
        mode_str = params.get("mode", "normal")
        machine = machines.get(machine_id)
        if machine is None:
            return ActionResult(False, f"Machine {machine_id} not found")
        if agent.role not in (AgentRole.ENGINEERING, AgentRole.MANAGEMENT):
            return ActionResult(False, "Only Engineering or Management can set speed")
        if not is_adjacent(agent.row, agent.col, machine.row, machine.col):
            return ActionResult(False, "Not adjacent to machine")
        from .entities import SpeedMode
        try:
            new_mode = SpeedMode(mode_str)
        except ValueError:
            return ActionResult(False, f"Invalid speed mode: {mode_str}")
        machine.speed_mode = new_mode
        agent.state = AgentState.WORKING
        return ActionResult(True, f"Set {machine_id} speed to {mode_str}")

    elif action_type == "sell":
        item_id = params.get("item_id")
        cell = grid[agent.row][agent.col]
        if cell != CellType.SHIPPING_DOCK:
            return ActionResult(False, "Must be on a Shipping Dock to sell")
        if not agent.inventory:
            return ActionResult(False, "Nothing to sell")
        item = next(
            (i for i in agent.inventory if (not item_id or i.id == item_id)),
            None
        )
        if item is None:
            return ActionResult(False, "Item not found in inventory")
        if item.item_type not in (ItemType.FINISHED_PRODUCT, ItemType.REJECT):
            return ActionResult(False, f"Cannot sell {item.item_type.value}")
        agent.inventory.remove(item)
        if item.id in items:
            del items[item.id]
        agent.state = AgentState.WORKING
        return ActionResult(True, f"Sold {item.item_type.value}", {"item_type": item.item_type.value, "item_id": item.id})

    elif action_type == "purchase":
        item_type_str = params.get("item_type", "raw_ore")
        qty = max(1, min(int(params.get("qty", 1)), 4))
        cell = grid[agent.row][agent.col]
        if cell != CellType.LOADING_DOCK:
            return ActionResult(False, "Must be on a Loading Dock to purchase")
        if agent.role != AgentRole.PROCUREMENT:
            return ActionResult(False, "Only Procurement agents can purchase")
        if agent.purchase_cooldown > 0:
            return ActionResult(False, f"Purchase cooldown: {agent.purchase_cooldown} ticks remaining")
        available_slots = agent.carry_capacity() - len(agent.inventory)
        qty = min(qty, available_slots)
        if qty <= 0:
            return ActionResult(False, "Inventory full")
        try:
            itype = ItemType(item_type_str)
        except ValueError:
            return ActionResult(False, f"Unknown item type: {item_type_str}")
        from .entities import ITEM_PURCHASE_COST
        if itype not in ITEM_PURCHASE_COST:
            return ActionResult(False, f"{itype.value} cannot be purchased")
        agent.purchase_cooldown = 5
        agent.state = AgentState.WORKING
        new_items = []
        for _ in range(qty):
            new_item = Item(
                id=f"{itype.value}_{uuid.uuid4().hex[:6]}",
                item_type=itype,
                carrier_id=agent.id,
            )
            agent.inventory.append(new_item)
            items[new_item.id] = new_item
            new_items.append(new_item.id)
        return ActionResult(True, f"Purchased {qty}x {itype.value}", {"purchased": new_items, "qty": qty, "item_type": itype.value})

    elif action_type == "broadcast":
        if agent.comm_cooldown > 0:
            return ActionResult(False, f"Comm cooldown: {agent.comm_cooldown} ticks")
        message = params.get("message", "")
        agent.comm_cooldown = 3
        alerts.append({
            "type": "broadcast",
            "from": agent.id,
            "message": message,
            "row": agent.row,
            "col": agent.col,
        })
        return ActionResult(True, "Broadcast sent")

    elif action_type == "diagnose":
        machine_id = params.get("machine_id")
        machine = machines.get(machine_id)
        if machine is None:
            return ActionResult(False, f"Machine {machine_id} not found")
        if not is_adjacent(agent.row, agent.col, machine.row, machine.col):
            return ActionResult(False, "Not adjacent to machine")
        return ActionResult(True, "Diagnosis complete", {
            "health": machine.health,
            "failure_rate": machine.failure_rate(),
            "state": machine.state.value,
        })

    elif action_type == "check_orders":
        return ActionResult(True, "Orders checked", {})

    elif action_type == "check_prices":
        from .entities import ITEM_PURCHASE_COST
        return ActionResult(True, "Prices checked", {"prices": {k.value: v for k, v in ITEM_PURCHASE_COST.items()}})

    elif action_type == "view_financials":
        return ActionResult(True, "Financials viewed", {})

    elif action_type == "hire":
        if agent.role != AgentRole.MANAGEMENT:
            return ActionResult(False, "Only Management can hire")
        return ActionResult(True, "Hire request recorded", {"agent_type": params.get("agent_type", "operations")})

    elif action_type == "fire":
        if agent.role != AgentRole.MANAGEMENT:
            return ActionResult(False, "Only Management can fire")
        target_id = params.get("agent_id")
        if target_id and target_id in agents:
            return ActionResult(True, f"Agent {target_id} fired", {"agent_id": target_id})
        return ActionResult(False, "Agent not found")

    elif action_type == "assign_task":
        if agent.role != AgentRole.MANAGEMENT:
            return ActionResult(False, "Only Management can assign tasks")
        target_id = params.get("agent_id")
        task = params.get("task", "")
        if target_id and target_id in agents:
            agents[target_id].messages.append({"from": agent.id, "task": task})
            return ActionResult(True, f"Task assigned to {target_id}")
        return ActionResult(False, "Target agent not found")

    elif action_type == "idle":
        agent.state = AgentState.IDLE
        return ActionResult(True, "Idle")

    return ActionResult(False, f"Unknown action: {action_type}")


def decompose_macro_action(
    agent: Agent,
    macro_type: str,
    params: dict,
    grid: list[list[CellType]],
    machines: dict[str, Machine],
    items: dict[str, Item],
    agents: dict[str, Agent],
) -> list[dict]:
    """
    Decompose a macro-action into a list of micro-action dicts.
    Returns list of {type, params} micro-actions to queue on the agent.
    """
    ROWS = len(grid)
    COLS = len(grid[0]) if ROWS else 0
    occupied = {(a.row, a.col) for a in agents.values() if a.id != agent.id}

    if macro_type == "go_to":
        target_row = params.get("row", agent.row)
        target_col = params.get("col", agent.col)
        path = astar(grid, (agent.row, agent.col), (target_row, target_col), occupied)
        steps = []
        for (pr, pc) in path:
            dr = pr - agent.row
            dc = pc - agent.col
            if dr == -1: steps.append({"type": "move", "params": {"direction": "north"}})
            elif dr == 1: steps.append({"type": "move", "params": {"direction": "south"}})
            elif dc == -1: steps.append({"type": "move", "params": {"direction": "west"}})
            elif dc == 1: steps.append({"type": "move", "params": {"direction": "east"}})
        return steps

    elif macro_type == "pickup_nearest":
        item_type_str = params.get("item_type")
        best: Optional[Item] = None
        best_dist = 999999
        for item in items.values():
            if item.carrier_id is not None:
                continue
            if item.row is None:
                continue
            if item_type_str and item.item_type.value != item_type_str:
                continue
            dist = abs(item.row - agent.row) + abs(item.col - agent.col)
            if dist < best_dist:
                best_dist = dist
                best = item
        if best is None:
            return [{"type": "wait", "params": {}}]
        path = astar(grid, (agent.row, agent.col), (best.row, best.col), occupied)
        steps = []
        cur_r, cur_c = agent.row, agent.col
        for (pr, pc) in path:
            dr = pr - cur_r
            dc = pc - cur_c
            if dr == -1: steps.append({"type": "move", "params": {"direction": "north"}})
            elif dr == 1: steps.append({"type": "move", "params": {"direction": "south"}})
            elif dc == -1: steps.append({"type": "move", "params": {"direction": "west"}})
            elif dc == 1: steps.append({"type": "move", "params": {"direction": "east"}})
            cur_r, cur_c = pr, pc
        steps.append({"type": "pickup", "params": {"item_id": best.id}})
        return steps

    elif macro_type == "deliver_to":
        target_row = params.get("row", agent.row)
        target_col = params.get("col", agent.col)
        path = astar(grid, (agent.row, agent.col), (target_row, target_col), occupied)
        steps = []
        for (pr, pc) in path:
            dr = pr - agent.row
            dc = pc - agent.col
            if dr == -1: steps.append({"type": "move", "params": {"direction": "north"}})
            elif dr == 1: steps.append({"type": "move", "params": {"direction": "south"}})
            elif dc == -1: steps.append({"type": "move", "params": {"direction": "west"}})
            elif dc == 1: steps.append({"type": "move", "params": {"direction": "east"}})
        steps.append({"type": "drop", "params": {}})
        return steps

    elif macro_type == "deliver_to_machine":
        machine_id = params.get("machine_id")
        machine = machines.get(machine_id)
        if machine is None:
            return [{"type": "wait", "params": {}}]
        adj = [(machine.row - 1, machine.col), (machine.row + 1, machine.col),
               (machine.row, machine.col - 1), (machine.row, machine.col + 1)]
        WALKABLE = {CellType.FLOOR, CellType.CONVEYOR, CellType.LOADING_DOCK,
                    CellType.SHIPPING_DOCK, CellType.STORAGE_ZONE}
        adj = [(r, c) for r, c in adj
               if 0 <= r < ROWS and 0 <= c < COLS and grid[r][c] in WALKABLE]
        if not adj:
            return [{"type": "wait", "params": {}}]
        best_adj = min(adj, key=lambda rc: abs(rc[0]-agent.row)+abs(rc[1]-agent.col))
        path = astar(grid, (agent.row, agent.col), best_adj, occupied)
        steps = []
        for (pr, pc) in path:
            dr = pr - agent.row
            dc = pc - agent.col
            if dr == -1: steps.append({"type": "move", "params": {"direction": "north"}})
            elif dr == 1: steps.append({"type": "move", "params": {"direction": "south"}})
            elif dc == -1: steps.append({"type": "move", "params": {"direction": "west"}})
            elif dc == 1: steps.append({"type": "move", "params": {"direction": "east"}})
        steps.append({"type": "load_machine", "params": {"machine_id": machine_id}})
        return steps

    return [{"type": "wait", "params": {}}]
