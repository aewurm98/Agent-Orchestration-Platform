"""
ManufacturingEnvV2: high-level wrapper around WorldModel.

Exposes reset(config), step(actions), tick(), to_json(), and fitness extraction.
Compatible with the main simulation loop in main.py.
"""
from __future__ import annotations

from typing import Any, Optional

from .world import WorldModel
from .entities import CellType, MachineType, AgentRole, SpeedMode, MachineState, Item, ItemType
from .scenarios import FIRST_FACTORY_CONFIG
from .economics import MetricsSnapshot


class ManufacturingEnvV2:
    def __init__(self, config: Optional[dict] = None):
        self._config = config or FIRST_FACTORY_CONFIG
        self.world: WorldModel = self._build_world(self._config)

    def _build_world(self, config: dict) -> WorldModel:
        world = WorldModel(
            grid_rows=config.get("grid_rows", 10),
            grid_cols=config.get("grid_cols", 10),
            starting_budget=config.get("starting_budget", 8_000.0),
            simulation_length=config.get("simulation_length", 300),
            order_arrival_rate=config.get("order_arrival_rate", 12),
            random_seed=config.get("random_seed"),
            execution_mode=config.get("execution_mode", "async_buffered"),
        )

        for key, ct in config.get("cell_overrides", {}).items():
            # key may be a tuple (r,c) from in-process configs, or a string
            # "(r,c)" when deserialized from JSON (JSON only supports string keys).
            if isinstance(key, (tuple, list)):
                r, c = int(key[0]), int(key[1])
            else:
                # parse "(r,c)" or "r,c"
                clean = str(key).strip("() ")
                r, c = (int(x) for x in clean.split(","))
            # ct may be a CellType enum or a plain string value
            if isinstance(ct, str):
                ct = CellType(ct)
            world.set_cell(r, c, ct)

        for m_cfg in config.get("machines", []):
            mtype = m_cfg["type"]
            if isinstance(mtype, str):
                mtype = MachineType(mtype)
            mspeed = m_cfg.get("speed", SpeedMode.NORMAL)
            if isinstance(mspeed, str):
                mspeed = SpeedMode(mspeed)
            world.add_machine(
                machine_id=m_cfg["id"],
                machine_type=mtype,
                row=m_cfg["row"],
                col=m_cfg["col"],
                speed=mspeed,
            )

        for a_cfg in config.get("agents", []):
            role = a_cfg["role"]
            if isinstance(role, str):
                role = AgentRole(role)
            world.add_agent(
                agent_id=a_cfg["id"],
                role=role,
                row=a_cfg["row"],
                col=a_cfg["col"],
            )

        # Pre-load items into machines / floor to seed the pipeline
        for item_cfg in config.get("preloaded_items", []):
            itype = item_cfg["type"]
            if isinstance(itype, str):
                itype = ItemType(itype)
            item = Item(
                id=item_cfg["id"],
                item_type=itype,
                row=item_cfg.get("row"),
                col=item_cfg.get("col"),
                carrier_id=item_cfg.get("carrier_id"),
            )
            world.items[item.id] = item
            machine_id = item_cfg.get("in_machine")
            if machine_id:
                m = world.machines.get(machine_id)
                if m:
                    queue = item_cfg.get("queue", "input")
                    if queue == "output":
                        m.output_queue.append(item)
                    else:
                        m.input_queue.append(item)

        # Apply initial machine state overrides
        for m_init in config.get("initial_machine_states", []):
            m = world.machines.get(m_init["id"])
            if m:
                state_val = m_init.get("state", MachineState.IDLE)
                if isinstance(state_val, str):
                    state_val = MachineState(state_val)
                m.state = state_val
                if "processing_ticks_remaining" in m_init:
                    m.processing_ticks_remaining = int(m_init["processing_ticks_remaining"])

        return world

    def reset(self, config: Optional[dict] = None) -> dict:
        if config:
            self._config = config
        self.world = self._build_world(self._config)
        return self.world.to_json()

    def step(self, actions: Optional[Any] = None) -> dict:
        """
        Advance one tick. Accepts:
          - dict[str, dict]  — {agent_id: {type, params}}
          - list of dicts    — [{agent_id, type, params}]
          - None             — policy-free tick

        Returns a *state delta* containing only the dynamic fields that change
        each tick (agents, machines, items, budget, metrics, events, orders).
        Static fields (full grid layout, simulation_length, scenario) are omitted
        to keep headless EA/API consumers efficient.  Full state is always
        available via GET /api/mfg/state.
        """
        actions_dict: Optional[dict] = None
        if isinstance(actions, dict):
            actions_dict = actions
        elif isinstance(actions, list):
            actions_dict = {
                a["agent_id"]: {"type": a.get("type", "wait"), "params": a.get("params", {})}
                for a in actions
                if "agent_id" in a
            }
        tick_result = self.world.tick_advance(actions_dict)
        metrics = self.world.economy.snapshot(
            self.world.tick, self.world.agents, self.world.machines
        )
        orders_list = [o.to_dict() for o in self.world._active_orders]
        return {
            # Identification
            "tick": self.world.tick,
            "done": self.world.done,
            # Dynamic entity state (positions, states, inventories)
            "agents":   {aid: a.to_dict() for aid, a in self.world.agents.items()},
            "machines": {mid: m.to_dict() for mid, m in self.world.machines.items()},
            "items":    [i.to_dict() for i in self.world.items.values()],
            # Economy
            "budget":   round(self.world.economy.budget, 2),
            "orders":   orders_list,
            "active_orders": orders_list,  # compat alias
            # Metrics & fitness
            "metrics":  metrics.to_dict(),
            "fitness":  metrics.fitness_scalar(),
            "fitness_vector": metrics.fitness_vector(),
            # Events from this tick
            "events":   tick_result.get("alerts", []) + self.world._pending_alerts,
            # Grid dimensions (lightweight ref, not full grid)
            "grid_rows": self.world.rows,
            "grid_cols": self.world.cols,
        }

    def tick(self) -> None:
        self.world.tick_advance()

    def to_json(self) -> dict:
        return self.world.to_json()

    def get_metrics(self) -> dict:
        metrics = self.world.economy.snapshot(
            self.world.tick, self.world.agents, self.world.machines
        )
        res = metrics.to_dict()
        
        # Calculate active ratios
        res["role_active_ratios"] = {}
        total_ticks = max(1, self.world.tick)
        for role, ticks in self.world.role_active_ticks.items():
            count = sum(1 for a in self.world.agents.values() if a.role.value == role)
            if count > 0:
                res["role_active_ratios"][role] = round(ticks / (total_ticks * count), 2)
            else:
                res["role_active_ratios"][role] = 0.0

        # Calculate average queue lengths
        res["machine_diagnostics"] = {}
        for mid, diag in self.world.machine_diagnostics.items():
            res["machine_diagnostics"][mid] = {
                "avg_input_queue": round(diag["input_queue_sum"] / total_ticks, 2),
                "avg_output_queue": round(diag["output_queue_sum"] / total_ticks, 2),
                "failure_count": diag["failure_count"],
            }
            
        return res

    def get_state(self) -> dict:
        return self.world.to_json()

    def get_action_space(self, agent_id: str) -> list[str]:
        return self.world.get_action_space(agent_id)

    def get_observation(self, agent_id: str) -> dict:
        return self.world.get_observation(agent_id)

    def get_fitness(self) -> float:
        metrics = self.world.economy.snapshot(
            self.world.tick, self.world.agents, self.world.machines
        )
        return metrics.fitness_scalar()

    def get_fitness_vector(self) -> list[float]:
        metrics = self.world.economy.snapshot(
            self.world.tick, self.world.agents, self.world.machines
        )
        return metrics.fitness_vector()

    @property
    def done(self) -> bool:
        return self.world.done

    @property
    def tick_count(self) -> int:
        return self.world.tick

    def connectivity_valid(self) -> tuple[bool, str]:
        return self.world.connectivity_valid()

    def set_speed(self, multiplier: float) -> None:
        self.world._speed_multiplier = multiplier

    def pause(self) -> None:
        self.world._paused = True

    def resume(self) -> None:
        self.world._paused = False
