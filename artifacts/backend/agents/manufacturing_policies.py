"""
Baseline agent policies for the Manufacturing v2 simulation.

Three tiers:
  - RandomPolicy:        Uniform random valid action each tick.
  - ScriptedGreedyPolicy: Priority-rule heuristic (functional but not optimal).
  - LLMPolicy:           Wrapper around manufacturing_roles LLM agents.
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
    Priority heuristic:
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

        if len(agent.inventory) < agent.carry_capacity():
            if cell == CellType.LOADING_DOCK and agent.purchase_cooldown == 0:
                needed = self._most_needed_raw(world)
                return {"type": "purchase", "params": {"item_type": needed.value, "qty": 1}}

        if agent.inventory:
            target = self._nearest_machine_needing_input(agent, world)
            if target:
                return {"type": "deliver_to_machine", "params": {"machine_id": target.id}}

        dock_pos = world._find_loading_dock()
        if (agent.row, agent.col) != dock_pos:
            return {"type": "go_to", "params": {"row": dock_pos[0], "col": dock_pos[1]}}

        return {"type": "wait", "params": {}}

    def _operations_action(self, agent: Agent, obs: dict, world: "WorldModel") -> dict:
        if agent.inventory:
            target = self._nearest_machine_needing_input(agent, world)
            if target:
                return {"type": "deliver_to_machine", "params": {"machine_id": target.id}}
            return {"type": "go_to", "params": {"row": agent.row, "col": agent.col}}

        output_ready = [m for m in world.machines.values() if m.state == MachineState.OUTPUT_READY]
        if output_ready:
            nearest = min(output_ready, key=lambda m: abs(m.row - agent.row) + abs(m.col - agent.col))
            adj = self._find_adjacent_floor(nearest, world)
            if adj and (agent.row, agent.col) in [adj]:
                return {"type": "unload_machine", "params": {"machine_id": nearest.id}}
            if adj:
                return {"type": "go_to", "params": {"row": adj[0], "col": adj[1]}}

        floor_items = [i for i in world.items.values() if i.carrier_id is None and i.row is not None]
        if floor_items:
            nearest = min(floor_items, key=lambda i: abs(i.row - agent.row) + abs(i.col - agent.col))
            return {"type": "pickup_nearest", "params": {"item_type": nearest.item_type.value}}

        return self._wander(agent)

    def _engineering_action(self, agent: Agent, obs: dict, world: "WorldModel") -> dict:
        broken = [m for m in world.machines.values() if m.state == MachineState.BROKEN]
        if broken:
            nearest = min(broken, key=lambda m: abs(m.row - agent.row) + abs(m.col - agent.col))
            adj = self._find_adjacent_floor(nearest, world)
            from game_envs.manufacturing_v2.actions import is_adjacent
            if is_adjacent(agent.row, agent.col, nearest.row, nearest.col):
                return {"type": "repair", "params": {"machine_id": nearest.id}}
            if adj:
                return {"type": "go_to", "params": {"row": adj[0], "col": adj[1]}}

        return {"type": "wait", "params": {}}

    def _sales_action(self, agent: Agent, obs: dict, world: "WorldModel") -> dict:
        cell = world.grid[agent.row][agent.col]

        if agent.inventory and cell == CellType.SHIPPING_DOCK:
            return {"type": "sell", "params": {}}

        if agent.inventory:
            dock_pos = world._find_shipping_dock()
            return {"type": "go_to", "params": {"row": dock_pos[0], "col": dock_pos[1]}}

        finished = [
            i for i in world.items.values()
            if i.carrier_id is None and i.row is not None
            and i.item_type == ItemType.FINISHED_PRODUCT
        ]
        if finished:
            nearest = min(finished, key=lambda i: abs(i.row - agent.row) + abs(i.col - agent.col))
            return {"type": "pickup_nearest", "params": {"item_type": ItemType.FINISHED_PRODUCT.value}}

        output_packaging = [
            m for m in world.machines.values()
            if m.machine_type == MachineType.PACKAGING and m.state == MachineState.OUTPUT_READY
        ]
        if output_packaging:
            nearest = min(output_packaging, key=lambda m: abs(m.row - agent.row) + abs(m.col - agent.col))
            adj = self._find_adjacent_floor(nearest, world)
            from game_envs.manufacturing_v2.actions import is_adjacent
            if is_adjacent(agent.row, agent.col, nearest.row, nearest.col):
                return {"type": "unload_machine", "params": {"machine_id": nearest.id}}
            if adj:
                return {"type": "go_to", "params": {"row": adj[0], "col": adj[1]}}

        return self._wander(agent)

    def _management_action(self, agent: Agent, obs: dict, world: "WorldModel") -> dict:
        broken_cnt = sum(1 for m in world.machines.values() if m.state == MachineState.BROKEN)
        engineers = [a for a in world.agents.values() if a.role == AgentRole.ENGINEERING]
        if broken_cnt > len(engineers) and world.economy.budget > 500:
            return {"type": "hire", "params": {"agent_type": "engineering"}}

        idle_ops = sum(
            1 for a in world.agents.values()
            if a.role == AgentRole.OPERATIONS and a.state == AgentState.IDLE
        )
        if idle_ops == 0 and world.economy.budget > 300:
            bottleneck = self._find_bottleneck_machine(world)
            if bottleneck:
                return {"type": "hire", "params": {"agent_type": "operations"}}

        return {"type": "view_financials", "params": {}}

    def _most_needed_raw(self, world: "WorldModel") -> ItemType:
        smelter_queue = sum(
            len(m.input_queue) for m in world.machines.values() if m.machine_type == MachineType.SMELTER
        )
        circuit_queue = sum(
            len(m.input_queue) for m in world.machines.values() if m.machine_type == MachineType.CIRCUIT_FAB
        )
        ore_stock = sum(
            1 for i in world.items.values() if i.item_type == ItemType.RAW_ORE and i.carrier_id is None
        )
        silicon_stock = sum(
            1 for i in world.items.values() if i.item_type == ItemType.RAW_SILICON and i.carrier_id is None
        )
        if silicon_stock + circuit_queue < ore_stock + smelter_queue:
            return ItemType.RAW_SILICON
        return ItemType.RAW_ORE

    def _nearest_machine_needing_input(self, agent: Agent, world: "WorldModel") -> Optional[Machine]:
        if not agent.inventory:
            return None
        carrying_types = {i.item_type for i in agent.inventory}
        candidates = []
        for m in world.machines.values():
            if m.state in (MachineState.BROKEN, MachineState.OFFLINE):
                continue
            if len(m.input_queue) >= 3:
                continue
            recipe = RECIPES.get(m.machine_type, {})
            needed_types = {itype for itype, _ in recipe.get("inputs", [])}
            if carrying_types & needed_types:
                dist = abs(m.row - agent.row) + abs(m.col - agent.col)
                candidates.append((dist, m))
        if not candidates:
            return None
        return min(candidates, key=lambda x: x[0])[1]

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
