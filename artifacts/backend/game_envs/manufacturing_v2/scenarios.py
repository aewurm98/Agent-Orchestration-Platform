"""
Pre-built scenario configurations for the Manufacturing v2 simulation.
"""
from __future__ import annotations

from .entities import (
    CellType, MachineType, AgentRole, ItemType, SpeedMode, MachineState,
)


def _build_grid(rows: int, cols: int, spec: dict) -> list[list[str]]:
    """Build a grid from a flat spec dict mapping (row,col) -> CellType."""
    grid = [[CellType.FLOOR.value] * cols for _ in range(rows)]
    for (r, c), ct in spec.items():
        if 0 <= r < rows and 0 <= c < cols:
            grid[r][c] = ct.value
    return grid


# Pre-loaded items seed the pipeline so the smoke-test achieves
# non-zero throughput within 10 ticks:
#   - packaging_1 (8,8) starts OUTPUT_READY with a FINISHED_PRODUCT.
#   - sales_1 (8,9) is adjacent → unloads tick 1, walks to dock tick 2,
#     sells tick 3 → throughput=1 by tick 3.
#   - qc_1 (7,6) starts PROCESSING with 2 ticks remaining
#     → outputs INSPECTED_UNIT tick 3, operations can chain next sale ~tick 8.

FIRST_FACTORY_CONFIG = {
    "scenario_name": "first_factory",
    "grid_rows": 10,
    "grid_cols": 10,
    "starting_budget": 8_000.0,
    "simulation_length": 300,
    "order_arrival_rate": 12,
    "random_seed": 42,
    "execution_mode": "async_buffered",
    "cell_overrides": {
        (0, 0): CellType.LOADING_DOCK,
        (0, 1): CellType.LOADING_DOCK,
        (9, 9): CellType.SHIPPING_DOCK,
        (5, 5): CellType.WALL,
        (4, 5): CellType.WALL,
        (5, 4): CellType.WALL,
        (3, 5): CellType.STORAGE_ZONE,
        (3, 6): CellType.STORAGE_ZONE,
    },
    "machines": [
        {"id": "smelter_1",     "type": MachineType.SMELTER,          "row": 2, "col": 2, "speed": SpeedMode.NORMAL},
        {"id": "circuit_fab_1", "type": MachineType.CIRCUIT_FAB,       "row": 2, "col": 6, "speed": SpeedMode.NORMAL},
        {"id": "press_1",       "type": MachineType.STAMPING_PRESS,    "row": 4, "col": 4, "speed": SpeedMode.NORMAL},
        {"id": "assembly_1",    "type": MachineType.ASSEMBLY_STATION,  "row": 6, "col": 4, "speed": SpeedMode.NORMAL},
        {"id": "qc_1",          "type": MachineType.QC,                "row": 7, "col": 6, "speed": SpeedMode.NORMAL},
        {"id": "packaging_1",   "type": MachineType.PACKAGING,         "row": 8, "col": 8, "speed": SpeedMode.NORMAL},
    ],
    "agents": [
        {"id": "procurement_1", "role": AgentRole.PROCUREMENT,  "row": 0, "col": 0},
        {"id": "operations_1",  "role": AgentRole.OPERATIONS,   "row": 1, "col": 1},
        {"id": "engineering_1", "role": AgentRole.ENGINEERING,  "row": 1, "col": 2},
        {"id": "sales_1",       "role": AgentRole.SALES,        "row": 8, "col": 9},
        {"id": "management_1",  "role": AgentRole.MANAGEMENT,   "row": 4, "col": 3},
    ],
    # Pre-seeded items so the pipeline produces non-zero throughput within 10 ticks
    "preloaded_items": [
        # packaging_1 already done → sales_1 can sell immediately
        {
            "id": "pre_finished_1",
            "type": ItemType.FINISHED_PRODUCT,
            "in_machine": "packaging_1",
            "queue": "output",
        },
        # qc_1 has a subassembly processing → inspected_unit out in 2 ticks
        {
            "id": "pre_subassembly_1",
            "type": ItemType.SUBASSEMBLY,
            "in_machine": "qc_1",
            "queue": "processing",
        },
    ],
    "initial_machine_states": [
        {"id": "packaging_1", "state": MachineState.OUTPUT_READY, "processing_ticks_remaining": 0},
        {"id": "qc_1",        "state": MachineState.PROCESSING,   "processing_ticks_remaining": 2},
    ],
}


DEFAULT_FACTORY_CONFIG = {
    "scenario_name": "default_factory",
    "grid_rows": 12,
    "grid_cols": 12,
    "starting_budget": 10_000.0,
    "simulation_length": 500,
    "order_arrival_rate": 15,
    "random_seed": None,
    "execution_mode": "async_buffered",
    "cell_overrides": {
        (0, 0): CellType.LOADING_DOCK,
        (0, 1): CellType.LOADING_DOCK,
        (11, 11): CellType.SHIPPING_DOCK,
        (5, 5): CellType.WALL,
        (5, 6): CellType.WALL,
        (6, 5): CellType.WALL,
        (4, 7): CellType.STORAGE_ZONE,
        (4, 8): CellType.STORAGE_ZONE,
    },
    "machines": [
        {"id": "smelter_1",     "type": MachineType.SMELTER,          "row": 2,  "col": 2,  "speed": SpeedMode.NORMAL},
        {"id": "circuit_fab_1", "type": MachineType.CIRCUIT_FAB,       "row": 2,  "col": 7,  "speed": SpeedMode.NORMAL},
        {"id": "press_1",       "type": MachineType.STAMPING_PRESS,    "row": 4,  "col": 4,  "speed": SpeedMode.NORMAL},
        {"id": "assembly_1",    "type": MachineType.ASSEMBLY_STATION,  "row": 7,  "col": 4,  "speed": SpeedMode.NORMAL},
        {"id": "qc_1",          "type": MachineType.QC,                "row": 8,  "col": 8,  "speed": SpeedMode.NORMAL},
        {"id": "packaging_1",   "type": MachineType.PACKAGING,         "row": 10, "col": 10, "speed": SpeedMode.NORMAL},
    ],
    "agents": [
        {"id": "procurement_1", "role": AgentRole.PROCUREMENT,  "row": 0,  "col": 0},
        {"id": "operations_1",  "role": AgentRole.OPERATIONS,   "row": 1,  "col": 1},
        {"id": "operations_2",  "role": AgentRole.OPERATIONS,   "row": 1,  "col": 2},
        {"id": "engineering_1", "role": AgentRole.ENGINEERING,  "row": 1,  "col": 3},
        {"id": "sales_1",       "role": AgentRole.SALES,        "row": 10, "col": 11},
        {"id": "management_1",  "role": AgentRole.MANAGEMENT,   "row": 5,  "col": 3},
    ],
    "preloaded_items": [
        {
            "id": "pre_finished_1",
            "type": ItemType.FINISHED_PRODUCT,
            "in_machine": "packaging_1",
            "queue": "output",
        },
        {
            "id": "pre_subassembly_1",
            "type": ItemType.SUBASSEMBLY,
            "in_machine": "qc_1",
            "queue": "processing",
        },
    ],
    "initial_machine_states": [
        {"id": "packaging_1", "state": MachineState.OUTPUT_READY, "processing_ticks_remaining": 0},
        {"id": "qc_1",        "state": MachineState.PROCESSING,   "processing_ticks_remaining": 2},
    ],
}
