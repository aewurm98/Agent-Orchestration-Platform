"""
Baseline agent policies for the Manufacturing v2 simulation.

Three tiers:
  - RandomPolicy:        Uniform random valid action each tick.
  - ScriptedGreedyPolicy: Priority-rule heuristic (functional but not optimal).
  - LLMPolicy:           Wrapper around manufacturing_roles LLM agents.

Policy overrides allow Management LLM agents to mutate scripted rules at runtime
via the `update_policy` skill.  Call apply_policy_override(rule, value) to write
a new rule; ScriptedGreedyPolicy reads from _policy_overrides at decision time.
"""
from __future__ import annotations

import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game_envs.manufacturing_v2.world import WorldModel

from game_envs.manufacturing_v2.entities import (
    Agent, AgentRole, AgentState, CellType, Item, ItemType,
    Machine, MachineState, MachineType,
)
from game_envs.manufacturing_v2.recipes import RECIPES


# ---------------------------------------------------------------------------
# Runtime policy overrides — Management LLM agents write here via update_policy
# ---------------------------------------------------------------------------

_policy_overrides: dict[str, object] = {}

OVERRIDABLE_RULES = {
    "replenishment_urgency_threshold": 3,
    "operations_pickup_radius": None,
    "engineering_idle_repair_trigger": 0,
    "management_hire_engineer_threshold": 1,
    "management_hire_ops_budget_floor": 300,
}


def apply_policy_override(rule: str, value: object) -> tuple[bool, str]:
    """Write a policy override with type coercion and range validation.

    Returns (ok, message). LLM output may arrive as strings or wrong numeric types,
    so the value is coerced to match the default type before storing.
    """
    if rule not in OVERRIDABLE_RULES:
        return False, f"Unknown rule '{rule}'. Valid rules: {list(OVERRIDABLE_RULES)}"
    default = OVERRIDABLE_RULES[rule]
    try:
        coerced: object
        if isinstance(default, float):
            coerced = float(value)  # type: ignore[arg-type]
        elif isinstance(default, int):
            coerced = int(float(value))  # type: ignore[arg-type]
        elif default is None:
            # No type hint from default — try numeric coercion; fall back to raw value
            try:
                as_float = float(value)  # type: ignore[arg-type]
                coerced = int(as_float) if as_float == int(as_float) else as_float
            except (TypeError, ValueError):
                coerced = value
        else:
            coerced = value
        # Basic sanity: numeric values must be positive
        if isinstance(coerced, (int, float)) and coerced < 0:
            return False, f"Invalid value for '{rule}': must be >= 0, got {coerced}"
    except (TypeError, ValueError) as exc:
        return False, f"Invalid value for '{rule}': cannot coerce {value!r} — {exc}"
    _policy_overrides[rule] = coerced
    return True, f"Policy override applied: {rule} = {coerced!r}"


def get_rule(rule: str) -> object:
    """Fetch the effective value of a rule, checking overrides first."""
    if rule in _policy_overrides:
        return _policy_overrides[rule]
    return OVERRIDABLE_RULES[rule]


class BasePolicy:
    def get_action(self, agent_id: str, observation: dict, world: "WorldModel") -> dict:
        raise NotImplementedError

    def get_all_actions(self, world: "WorldModel") -> dict[str, dict]:
        actions: dict[str, dict] = {}
        for agent_id, agent in world.agents.items():
            if agent.is_standby:
                continue
            obs = world.get_observation(agent_id)
            actions[agent_id] = self.get_action(agent_id, obs, world)
        return actions


class RandomPolicy(BasePolicy):
    """Each tick: select a uniformly random valid action from the action space."""

    def __init__(self, rng: Optional[random.Random] = None):
        self._rng = rng or random.Random()

    def get_action(self, agent_id: str, observation: dict, world: "WorldModel") -> dict:
        valid = world.get_action_space(agent_id)
        valid = [a for a in valid if a not in ("go_to", "pickup_nearest", "deliver_to", "deliver_to_machine")]
        if not valid:
            return {"type": "wait", "params": {}}
        action_type = self._rng.choice(valid)
        params: dict = {}
        if action_type == "move":
            params["direction"] = self._rng.choice(["north", "south", "east", "west"])
        elif action_type == "purchase":
            params["item_type"] = self._rng.choice(["raw_ore", "raw_silicon"])
            params["qty"] = 1
        elif action_type == "load_machine":
            if world.machines:
                params["machine_id"] = self._rng.choice(list(world.machines.keys()))
        elif action_type == "unload_machine":
            if world.machines:
                params["machine_id"] = self._rng.choice(list(world.machines.keys()))
        elif action_type == "repair":
            params["machine_id"] = self._rng.choice(list(world.machines.keys())) if world.machines else ""
        elif action_type == "set_speed":
            params["machine_id"] = self._rng.choice(list(world.machines.keys())) if world.machines else ""
            params["mode"] = self._rng.choice(["low", "normal", "high"])
        return {"type": action_type, "params": params}


class ScriptedGreedyPolicy(BasePolicy):
    """
    Priority heuristic — all threshold rules are read from _policy_overrides so
    Management LLM agents can tune behaviour at runtime via update_policy.

    Decision order:
    1. If carrying item → deliver to nearest appropriate machine / dock.
    2. If not carrying → pickup nearest available item.
    3. If no items visible → move toward machine with output_ready.
    4. Else → wander (random move).
    """

    def get_action(self, agent_id: str, observation: dict, world: "WorldModel") -> dict:
        agent = world.agents.get(agent_id)
        if not agent:
            return {"type": "wait", "params": {}}

        role = agent.role

        if role == AgentRole.PROCUREMENT:
            return self._procurement_action(agent, observation, world)
        elif role == AgentRole.OPERATIONS:
            return self._operations_action(agent, observation, world)
        elif role == AgentRole.ENGINEERING:
            return self._engineering_action(agent, observation, world)
        elif role == AgentRole.SALES:
            return self._sales_action(agent, observation, world)
        elif role == AgentRole.MANAGEMENT:
            return self._management_action(agent, observation, world)

        return {"type": "wait", "params": {}}

    def _procurement_action(self, agent: Agent, obs: dict, world: "WorldModel") -> dict:
        cell = world.grid[agent.row][agent.col]
        from game_envs.manufacturing_v2.actions import is_adjacent

        # Carrying raw material → deliver to the machine that consumes it.
        if agent.inventory:
            target = self._dag_target_machine(agent, world)
            if target is not None:
                if is_adjacent(agent.row, agent.col, target.row, target.col):
                    return {"type": "load_machine", "params": {"machine_id": target.id}}
                return self._step_toward(agent, target.row, target.col, world)
            # No machine needs it right now — hold position near a smelter/fab.
            return {"type": "wait", "params": {}}

        # Not carrying → buy at a loading dock, else walk to the nearest one.
        if cell == CellType.LOADING_DOCK and agent.purchase_cooldown == 0:
            needed = self._most_needed_raw(world)
            return {"type": "purchase", "params": {"item_type": needed.value, "qty": 1}}
        dock_pos = self._nearest_cell_of_type(agent, world, CellType.LOADING_DOCK) or world._find_loading_dock()
        return self._step_toward(agent, dock_pos[0], dock_pos[1], world)

    def _operations_action(self, agent: Agent, obs: dict, world: "WorldModel") -> dict:
        from game_envs.manufacturing_v2.actions import is_adjacent

        if agent.inventory:
            carried = agent.inventory[0].item_type
            # Scrap exception (spec §2.1): reject items go to the shipping dock.
            if carried == ItemType.REJECT:
                dock = world._find_shipping_dock()
                if (agent.row, agent.col) == dock or is_adjacent(agent.row, agent.col, dock[0], dock[1]):
                    return {"type": "drop", "params": {}}
                return self._step_toward(agent, dock[0], dock[1], world)
            target = self._dag_target_machine(agent, world)
            if target is not None:
                if is_adjacent(agent.row, agent.col, target.row, target.col):
                    return {"type": "load_machine", "params": {"machine_id": target.id}}
                return self._step_toward(agent, target.row, target.col, world)
            # Deadlock Resolution: drop the intermediate item on the floor if there is no target machine needing it.
            return {"type": "drop", "params": {}}

        # Empty-handed → pull output from the nearest machine with goods ready (excluding PACKAGING which sales handles).
        output_ready = [
            m for m in world.machines.values()
            if m.state == MachineState.OUTPUT_READY and m.output_queue and m.machine_type != MachineType.PACKAGING
        ]
        if output_ready:
            nearest = min(output_ready, key=lambda m: abs(m.row - agent.row) + abs(m.col - agent.col))
            if is_adjacent(agent.row, agent.col, nearest.row, nearest.col):
                return {"type": "unload_machine", "params": {"machine_id": nearest.id}}
            return self._step_toward(agent, nearest.row, nearest.col, world)

        # Pick up any loose item on the floor (e.g. a dropped intermediate) that a machine actually has room/need for right now.
        floor_items = []
        for i in world.items.values():
            if i.carrier_id is None and i.row is not None and i.item_type != ItemType.REJECT:
                # Check if there is any active machine that has room for this item in its input queue
                has_need = False
                for m in world.machines.values():
                    if m.state in (MachineState.BROKEN, MachineState.OFFLINE):
                        continue
                    recipe = RECIPES.get(m.machine_type, {})
                    req_qty = next((q for t, q in recipe.get("inputs", []) if t == i.item_type), 0)
                    if req_qty > 0:
                        current_count = sum(1 for item in m.input_queue if item.item_type == i.item_type)
                        if current_count < req_qty * 2:
                            has_need = True
                            break
                if has_need:
                    floor_items.append(i)

        if floor_items:
            nearest = min(floor_items, key=lambda i: abs(i.row - agent.row) + abs(i.col - agent.col))
            if (agent.row, agent.col) == (nearest.row, nearest.col):
                return {"type": "pickup", "params": {"item_id": nearest.id}}
            return self._step_toward(agent, nearest.row, nearest.col, world)

        return {"type": "wait", "params": {}}

    def _engineering_action(self, agent: Agent, obs: dict, world: "WorldModel") -> dict:
        from game_envs.manufacturing_v2.actions import is_adjacent
        idle_repair_trigger = int(get_rule("engineering_idle_repair_trigger"))

        broken = [m for m in world.machines.values() if m.state == MachineState.BROKEN]
        if len(broken) > idle_repair_trigger:
            nearest = min(broken, key=lambda m: abs(m.row - agent.row) + abs(m.col - agent.col))
            if is_adjacent(agent.row, agent.col, nearest.row, nearest.col):
                return {"type": "repair", "params": {"machine_id": nearest.id}}
            return self._step_toward(agent, nearest.row, nearest.col, world)

        return {"type": "wait", "params": {}}

    def _sales_action(self, agent: Agent, obs: dict, world: "WorldModel") -> dict:
        cell = world.grid[agent.row][agent.col]
        from game_envs.manufacturing_v2.actions import is_adjacent

        if agent.inventory:
            if cell == CellType.SHIPPING_DOCK:
                return {"type": "sell", "params": {}}
            dock_pos = self._nearest_cell_of_type(agent, world, CellType.SHIPPING_DOCK) or world._find_shipping_dock()
            return self._step_toward(agent, dock_pos[0], dock_pos[1], world)

        # Pick up finished goods or reject scrap items from the shipping dock floor.
        sellables = [
            i for i in world.items.values()
            if i.carrier_id is None and i.row is not None
            and i.item_type in (ItemType.FINISHED_PRODUCT, ItemType.REJECT)
        ]
        if sellables:
            nearest = min(sellables, key=lambda i: abs(i.row - agent.row) + abs(i.col - agent.col))
            if (agent.row, agent.col) == (nearest.row, nearest.col):
                return {"type": "pickup", "params": {"item_id": nearest.id}}
            return self._step_toward(agent, nearest.row, nearest.col, world)

        output_packaging = [
            m for m in world.machines.values()
            if m.machine_type == MachineType.PACKAGING and m.state == MachineState.OUTPUT_READY and m.output_queue
        ]
        if output_packaging:
            nearest = min(output_packaging, key=lambda m: abs(m.row - agent.row) + abs(m.col - agent.col))
            if is_adjacent(agent.row, agent.col, nearest.row, nearest.col):
                return {"type": "unload_machine", "params": {"machine_id": nearest.id}}
            return self._step_toward(agent, nearest.row, nearest.col, world)

        return {"type": "wait", "params": {}}

    def _management_action(self, agent: Agent, obs: dict, world: "WorldModel") -> dict:
        hire_eng_threshold = int(get_rule("management_hire_engineer_threshold"))
        hire_ops_budget_floor = int(get_rule("management_hire_ops_budget_floor"))

        broken_cnt = sum(1 for m in world.machines.values() if m.state == MachineState.BROKEN)
        engineers = [a for a in world.agents.values() if a.role == AgentRole.ENGINEERING]
        if broken_cnt >= hire_eng_threshold and broken_cnt > len(engineers) and world.economy.budget > 500:
            return {"type": "hire", "params": {"agent_type": "engineering"}}

        idle_ops = sum(
            1 for a in world.agents.values()
            if a.role == AgentRole.OPERATIONS and a.state == AgentState.IDLE
        )
        if idle_ops == 0 and world.economy.budget > hire_ops_budget_floor:
            bottleneck = self._find_bottleneck_machine(world)
            if bottleneck:
                return {"type": "hire", "params": {"agent_type": "operations"}}

        return {"type": "view_financials", "params": {}}

    def _most_needed_raw(self, world: "WorldModel") -> ItemType:
        # Smelter consumes 2 ore per ingot, so ore demand is double silicon's.
        # Count machine queues, floor stock AND in-transit material carried by
        # every agent — otherwise multiple procurement agents all pick the same
        # raw at once and starve the other line.
        smelter_queue = sum(
            len(m.input_queue) for m in world.machines.values() if m.machine_type == MachineType.SMELTER
        )
        circuit_queue = sum(
            len(m.input_queue) for m in world.machines.values() if m.machine_type == MachineType.CIRCUIT_FAB
        )
        ore_in_transit = silicon_in_transit = 0
        for a in world.agents.values():
            for i in a.inventory:
                if i.item_type == ItemType.RAW_ORE:
                    ore_in_transit += 1
                elif i.item_type == ItemType.RAW_SILICON:
                    silicon_in_transit += 1
        ore_stock = sum(
            1 for i in world.items.values() if i.item_type == ItemType.RAW_ORE and i.carrier_id is None
        )
        silicon_stock = sum(
            1 for i in world.items.values() if i.item_type == ItemType.RAW_SILICON and i.carrier_id is None
        )
        # Ore "supply" is halved because each ingot needs two ore units.
        ore_supply = (ore_stock + smelter_queue + ore_in_transit) / 2.0
        silicon_supply = silicon_stock + circuit_queue + silicon_in_transit
        return ItemType.RAW_ORE if ore_supply <= silicon_supply else ItemType.RAW_SILICON

    def _nearest_cell_of_type(self, agent: Agent, world: "WorldModel", cell_type: CellType) -> Optional[tuple[int, int]]:
        """Nearest grid cell of a given type — used to spread agents across the
        multiple loading/shipping dock cells instead of all targeting the first."""
        best = None
        best_d = 1e9
        for r in range(world.rows):
            for c in range(world.cols):
                if world.grid[r][c] == cell_type:
                    d = abs(r - agent.row) + abs(c - agent.col)
                    if d < best_d:
                        best_d = d
                        best = (r, c)
        return best

    def _nearest_machine_needing_input(
        self,
        agent: Agent,
        world: "WorldModel",
        input_threshold: int = 5,
    ) -> Optional[Machine]:
        if not agent.inventory:
            return None
        carried_item = agent.inventory[0].item_type
        candidates = []
        for m in world.machines.values():
            if m.state in (MachineState.BROKEN, MachineState.OFFLINE):
                continue
            recipe = RECIPES.get(m.machine_type, {})
            req_qty = next((q for t, q in recipe.get("inputs", []) if t == carried_item), 0)
            if req_qty > 0:
                current_count = sum(1 for i in m.input_queue if i.item_type == carried_item)
                if current_count < req_qty * 2:
                    dist = abs(m.row - agent.row) + abs(m.col - agent.col)
                    candidates.append((dist, m))
        if not candidates:
            return None
        return min(candidates, key=lambda x: x[0])[1]

    # Alias used by the deterministic role logic — routes a carried item to the
    # next machine in the production DAG that consumes its type.
    def _dag_target_machine(self, agent: Agent, world: "WorldModel") -> Optional[Machine]:
        return self._nearest_machine_needing_input(agent, world, input_threshold=5)

    def _step_toward(self, agent: Agent, tr: int, tc: int, world: "WorldModel") -> dict:
        """
        Dynamic single-step navigation: pick the walkable neighbour that most
        reduces Manhattan distance to (tr, tc), preferring cells not currently
        occupied by another agent.  Re-evaluated every tick, so it never relies
        on a stale precomputed path and degrades gracefully under congestion
        (the world's MAPF resolver handles any residual right-of-way ties).
        """
        WALKABLE = {
            CellType.FLOOR, CellType.CONVEYOR, CellType.LOADING_DOCK,
            CellType.SHIPPING_DOCK, CellType.STORAGE_ZONE,
        }
        occupied = {(a.row, a.col) for a in world.agents.values() if a.id != agent.id}
        DIRS = {"north": (-1, 0), "south": (1, 0), "east": (0, 1), "west": (0, -1)}
        best_dir = None
        best_key = None
        for dname, (dr, dc) in DIRS.items():
            nr, nc = agent.row + dr, agent.col + dc
            if not (0 <= nr < world.rows and 0 <= nc < world.cols):
                continue
            if world.grid[nr][nc] not in WALKABLE:
                continue
            dist = abs(nr - tr) + abs(nc - tc)
            # Sort cost: heavy penalty (10 steps) for occupied cells to encourage detours
            cost = dist + (10 if (nr, nc) in occupied else 0)
            if best_key is None or cost < best_key:
                best_key = cost
                best_dir = dname
        if best_dir is None:
            return {"type": "wait", "params": {}}
        return {"type": "move", "params": {"direction": best_dir}}

    def _find_adjacent_floor(self, machine: Machine, world: "WorldModel") -> Optional[tuple[int, int]]:
        WALKABLE = {
            CellType.FLOOR, CellType.CONVEYOR, CellType.LOADING_DOCK,
            CellType.SHIPPING_DOCK, CellType.STORAGE_ZONE,
        }
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = machine.row + dr, machine.col + dc
            if 0 <= nr < world.rows and 0 <= nc < world.cols:
                if world.grid[nr][nc] in WALKABLE:
                    occupied = {(a.row, a.col) for a in world.agents.values()}
                    if (nr, nc) not in occupied:
                        return (nr, nc)
        return None

    def _find_bottleneck_machine(self, world: "WorldModel") -> Optional[Machine]:
        candidates = [
            m for m in world.machines.values()
            if len(m.input_queue) >= 2 and m.state != MachineState.BROKEN
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: len(m.input_queue))

    def _wander(self, agent: Agent) -> dict:
        direction = random.choice(["north", "south", "east", "west"])
        return {"type": "move", "params": {"direction": direction}}


class LLMPolicy(BasePolicy):
    """
    LLM-augmented policy for Manufacturing v2.

    Architecture:
    - The simulation_loop calls run_manufacturing_v2_step() asynchronously every
      LANGGRAPH_TICK_INTERVAL ticks.  That coroutine uses _call_llm_v2 to get
      actions for management_1 and procurement_1, then injects them into each
      agent's action_buffer.
    - On every tick, get_all_actions() drains the action_buffer for agents that
      have queued LLM actions; for all other agents it falls back to
      ScriptedGreedyPolicy so the factory keeps running between LLM calls.
    """

    def __init__(self):
        self._fallback = ScriptedGreedyPolicy()

    def get_action(self, agent_id: str, observation: dict, world: "WorldModel") -> dict:
        agent = world.agents.get(agent_id)
        if agent and agent.action_buffer:
            return agent.action_buffer.pop(0)
        return self._fallback.get_action(agent_id, observation, world)

    def get_all_actions(self, world: "WorldModel") -> dict[str, dict]:
        actions: dict[str, dict] = {}
        for agent_id, agent in world.agents.items():
            if agent.is_standby:
                continue
            if agent.action_buffer:
                actions[agent_id] = agent.action_buffer.pop(0)
            else:
                obs = world.get_observation(agent_id)
                actions[agent_id] = self._fallback.get_action(agent_id, obs, world)
        return actions


POLICY_REGISTRY: dict[str, type] = {
    "random": RandomPolicy,
    "scripted": ScriptedGreedyPolicy,
    "llm": LLMPolicy,
}


def get_policy(name: str, **kwargs) -> BasePolicy:
    cls = POLICY_REGISTRY.get(name, ScriptedGreedyPolicy)
    return cls(**kwargs)
