"""
Entity definitions for the Manufacturing v2 grid-based simulation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CellType(str, Enum):
    FLOOR = "floor"
    WALL = "wall"
    CONVEYOR = "conveyor"
    MACHINE_SLOT = "machine_slot"
    LOADING_DOCK = "loading_dock"
    SHIPPING_DOCK = "shipping_dock"
    STORAGE_ZONE = "storage_zone"


class MachineType(str, Enum):
    SMELTER = "smelter"
    STAMPING_PRESS = "stamping_press"
    ASSEMBLY_STATION = "assembly_station"
    QC = "qc"
    PACKAGING = "packaging"
    CIRCUIT_FAB = "circuit_fab"


class MachineState(str, Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    LOADING = "loading"
    PROCESSING = "processing"
    OUTPUT_READY = "output_ready"
    BROKEN = "broken"


class SpeedMode(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class AgentRole(str, Enum):
    PROCUREMENT = "procurement"
    OPERATIONS = "operations"
    ENGINEERING = "engineering"
    SALES = "sales"
    MANAGEMENT = "management"


class AgentState(str, Enum):
    IDLE = "idle"
    MOVING = "moving"
    WORKING = "working"
    COMMUNICATING = "communicating"
    STANDBY = "standby"


class ItemType(str, Enum):
    RAW_ORE = "raw_ore"
    RAW_SILICON = "raw_silicon"
    METAL_INGOT = "metal_ingot"
    STAMPED_PART = "stamped_part"
    CIRCUIT = "circuit"
    SUBASSEMBLY = "subassembly"
    INSPECTED_UNIT = "inspected_unit"
    FINISHED_PRODUCT = "finished_product"
    REJECT = "reject"


ITEM_WEIGHT: dict[ItemType, float] = {
    ItemType.RAW_ORE: 2.0,
    ItemType.RAW_SILICON: 2.0,
    ItemType.METAL_INGOT: 1.5,
    ItemType.STAMPED_PART: 1.25,
    ItemType.CIRCUIT: 1.0,
    ItemType.SUBASSEMBLY: 1.25,
    ItemType.INSPECTED_UNIT: 1.0,
    ItemType.FINISHED_PRODUCT: 1.1,
    ItemType.REJECT: 1.0,
}

ITEM_PURCHASE_COST: dict[ItemType, float] = {
    ItemType.RAW_ORE: 10.0,
    ItemType.RAW_SILICON: 15.0,
}

ITEM_SALE_PRICE: dict[ItemType, float] = {
    ItemType.FINISHED_PRODUCT: 200.0,
    ItemType.REJECT: 5.0,
}

# Throughput multipliers (legacy: time = base_ticks / mult). Kept for backward
# compatibility with any external importers. Speed→processing-time is now driven
# by SPEED_TIME_MULT below (see Machine.base_ticks).
SPEED_MULTIPLIERS: dict[SpeedMode, float] = {
    SpeedMode.LOW: 0.5,
    SpeedMode.NORMAL: 1.0,
    SpeedMode.HIGH: 1.5,
}

# Spec §1.3 — processing time multiplier applied to a machine's base tick count:
#   low  → 1.5× time (slow, cheap, reliable)
#   high → 0.6× time (fast, 2× power, 2.5× fail rate)
SPEED_TIME_MULT: dict[SpeedMode, float] = {
    SpeedMode.LOW: 1.5,
    SpeedMode.NORMAL: 1.0,
    SpeedMode.HIGH: 0.6,
}

SPEED_POWER_MULT: dict[SpeedMode, float] = {
    SpeedMode.LOW: 0.5,
    SpeedMode.NORMAL: 1.0,
    SpeedMode.HIGH: 2.0,
}

SPEED_FAILURE_MULT: dict[SpeedMode, float] = {
    SpeedMode.LOW: 0.5,
    SpeedMode.NORMAL: 1.0,
    SpeedMode.HIGH: 2.5,
}

MACHINE_BASE_TICKS: dict[MachineType, int] = {
    MachineType.SMELTER: 4,
    MachineType.STAMPING_PRESS: 3,
    MachineType.ASSEMBLY_STATION: 6,
    MachineType.QC: 2,
    MachineType.PACKAGING: 2,
    MachineType.CIRCUIT_FAB: 5,
}

MACHINE_BASE_COST: dict[MachineType, float] = {
    MachineType.SMELTER: 500.0,
    MachineType.STAMPING_PRESS: 400.0,
    MachineType.ASSEMBLY_STATION: 800.0,
    MachineType.QC: 300.0,
    MachineType.PACKAGING: 200.0,
    MachineType.CIRCUIT_FAB: 600.0,
}

MACHINE_POWER_COST: dict[MachineType, float] = {
    MachineType.SMELTER: 2.0,
    MachineType.STAMPING_PRESS: 3.0,
    MachineType.ASSEMBLY_STATION: 4.0,
    MachineType.QC: 1.0,
    MachineType.PACKAGING: 1.0,
    MachineType.CIRCUIT_FAB: 3.0,
}

MACHINE_BASE_FAILURE_RATE: dict[MachineType, float] = {
    MachineType.SMELTER: 0.03,
    MachineType.STAMPING_PRESS: 0.02,
    MachineType.ASSEMBLY_STATION: 0.02,
    MachineType.QC: 0.01,
    MachineType.PACKAGING: 0.01,
    MachineType.CIRCUIT_FAB: 0.03,
}

REPAIR_TICKS: dict[MachineType, int] = {
    MachineType.SMELTER: 5,
    MachineType.STAMPING_PRESS: 4,
    MachineType.ASSEMBLY_STATION: 5,
    MachineType.QC: 3,
    MachineType.PACKAGING: 3,
    MachineType.CIRCUIT_FAB: 5,
}

AGENT_HIRE_COST: dict[AgentRole, float] = {
    AgentRole.PROCUREMENT: 200.0,
    AgentRole.OPERATIONS: 150.0,
    AgentRole.ENGINEERING: 350.0,
    AgentRole.SALES: 250.0,
    AgentRole.MANAGEMENT: 500.0,
}

AGENT_WAGE: dict[AgentRole, float] = {
    AgentRole.PROCUREMENT: 3.0,
    AgentRole.OPERATIONS: 2.0,
    AgentRole.ENGINEERING: 5.0,
    AgentRole.SALES: 4.0,
    AgentRole.MANAGEMENT: 8.0,
}

AGENT_CARRY_CAPACITY: dict[AgentRole, int] = {
    AgentRole.PROCUREMENT: 2,
    AgentRole.OPERATIONS: 1,
    AgentRole.ENGINEERING: 0,
    AgentRole.SALES: 2,
    AgentRole.MANAGEMENT: 0,
}

AGENT_VISIBILITY: dict[AgentRole, int] = {
    AgentRole.PROCUREMENT: 3,
    AgentRole.OPERATIONS: 3,
    AgentRole.ENGINEERING: 3,
    AgentRole.SALES: 3,
    AgentRole.MANAGEMENT: 999,
}


@dataclass
class Item:
    id: str
    item_type: ItemType
    row: Optional[int] = None
    col: Optional[int] = None
    carrier_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.item_type.value,
            "row": self.row,
            "col": self.col,
            "carrier_id": self.carrier_id,
        }


@dataclass
class Machine:
    id: str
    machine_type: MachineType
    row: int
    col: int
    state: MachineState = MachineState.IDLE
    speed_mode: SpeedMode = SpeedMode.NORMAL
    input_queue: list = field(default_factory=list)
    output_queue: list = field(default_factory=list)
    processing_ticks_remaining: int = 0
    health: float = 1.0
    total_produced: int = 0

    def power_cost_per_tick(self) -> float:
        if self.state == MachineState.OFFLINE:
            return 0.0
        return MACHINE_POWER_COST[self.machine_type] * SPEED_POWER_MULT[self.speed_mode]

    def base_ticks(self) -> int:
        # Spec §1.3: processing time = base ticks × speed time-multiplier.
        # low → 1.5× (slower), high → 0.6× (faster).
        raw = MACHINE_BASE_TICKS[self.machine_type]
        time_mult = SPEED_TIME_MULT[self.speed_mode]
        return max(1, round(raw * time_mult))

    def failure_rate(self) -> float:
        return MACHINE_BASE_FAILURE_RATE[self.machine_type] * SPEED_FAILURE_MULT[self.speed_mode]

    def utilization_signal(self) -> float:
        if self.state in (MachineState.PROCESSING, MachineState.LOADING):
            return 1.0
        if self.state == MachineState.OUTPUT_READY:
            return 0.8
        return 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.machine_type.value,
            "row": self.row,
            "col": self.col,
            "state": self.state.value,
            "speed": self.speed_mode.value,
            "input_queue_len": len(self.input_queue),
            "output_queue_len": len(self.output_queue),
            "input_queue": [i.to_dict() for i in self.input_queue],
            "output_queue": [i.to_dict() for i in self.output_queue],
            "processing_ticks_remaining": self.processing_ticks_remaining,
            "health": round(self.health, 2),
            "total_produced": self.total_produced,
            "power_cost_per_tick": round(self.power_cost_per_tick(), 2),
        }


@dataclass
class Agent:
    id: str
    role: AgentRole
    row: int
    col: int
    state: AgentState = AgentState.IDLE
    inventory: list = field(default_factory=list)
    is_standby: bool = False
    comm_cooldown: int = 0
    purchase_cooldown: int = 0
    action_buffer: list = field(default_factory=list)
    active_macro: Optional[str] = None
    ticks_on_action: int = 0
    forecast_cooldown: int = 0
    messages: list = field(default_factory=list)
    # Planned path: list of (row, col) waypoints from A* pathfinding (for UI rendering)
    planned_path: list = field(default_factory=list)

    def carry_capacity(self) -> int:
        return AGENT_CARRY_CAPACITY[self.role]

    def wage_per_tick(self) -> float:
        base = AGENT_WAGE[self.role]
        return base * 0.5 if self.is_standby else base

    def visibility(self) -> int:
        return AGENT_VISIBILITY[self.role]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role.value,
            "row": self.row,
            "col": self.col,
            "state": self.state.value,
            "inventory": [i.to_dict() for i in self.inventory],
            "inventory_count": len(self.inventory),
            "is_standby": self.is_standby,
            "active_macro": self.active_macro,
            "wage_per_tick": round(self.wage_per_tick(), 2),
            "messages": self.messages[-3:],
            # Planned path for UI: list of [row, col] waypoints
            "path": [[r, c] for r, c in self.planned_path],
        }


@dataclass
class Order:
    id: str
    product_type: ItemType
    quantity: int
    deadline_tick: int
    base_price: float
    arrival_tick: int
    fulfilled: int = 0
    is_rush: bool = False

    def is_expired(self, current_tick: int) -> bool:
        return current_tick > self.deadline_tick and self.fulfilled < self.quantity

    def effective_price(self) -> float:
        return self.base_price * (1.5 if self.is_rush else 1.0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "product_type": self.product_type.value,
            "quantity": self.quantity,
            "deadline_tick": self.deadline_tick,
            "base_price": self.base_price,
            "effective_price": round(self.effective_price(), 2),
            "arrival_tick": self.arrival_tick,
            "fulfilled": self.fulfilled,
            "is_rush": self.is_rush,
            "remaining": self.quantity - self.fulfilled,
        }
