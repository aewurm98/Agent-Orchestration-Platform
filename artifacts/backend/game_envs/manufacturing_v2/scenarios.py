"""
Pre-built scenario configurations for the Manufacturing v2 simulation.

FIRST_FACTORY_CONFIG  — Canonical "spec §12 First Factory" default used by
                        /api/mfg/reset, the simulation loop, and EA evaluation.
                        Layout: 10×14 · Loading docks (left edge, col 0) ·
                        Shipping docks (right edge, col 13) · Left-to-right
                        production flow: raw processing (col 3) → mid processing
                        (col 7) → finishing (col 11) → output · 10 machines ·
                        8 agents · $8,000 · 300 ticks · random seed 42.

FIRST_FACTORY_SEEDED_CONFIG — Alias of FIRST_FACTORY_CONFIG retained for
                        backward-compatible imports in unit tests.

DEFAULT_FACTORY_CONFIG — Alias of FIRST_FACTORY_CONFIG for legacy imports.
"""
from __future__ import annotations

from .entities import (
    CellType, MachineType, AgentRole, ItemType, SpeedMode, MachineState,
)


# ── Spec §12 First Factory ────────────────────────────────────────────────────
#
# Grid: 10 rows × 14 cols.  Flow direction: LEFT (input) → RIGHT (output).
#
# Machine columns:
#   Col  3 — Raw processing:  smelter×2, circuit_fab×1
#   Col  7 — Mid processing:  press×2, assembly×1
#   Col 11 — Finishing:       qc×2, packaging×2
#
# Conveyor rows connect adjacent machine columns so items can be routed.
# Storage zones between columns provide drop-off buffers.
# Wall pairs at (4-5, 1) and (2-3, 12) create routing interest.
#
# Pipeline bootstrap items:
#   pre_finished_1    — FINISHED_PRODUCT in packaging_1 output queue;
#                       sales_1 sells at tick 3 → throughput = 1.
#   pre_subassembly_1 — SUBASSEMBLY in qc_1 processing, 2 ticks remaining.
FIRST_FACTORY_CONFIG: dict = {
    "scenario_name": "first_factory",
    # ── Grid ──────────────────────────────────────────────────────────────────
    "grid_rows": 10,
    "grid_cols": 14,
    # ── Economy ───────────────────────────────────────────────────────────────
    "starting_budget": 8_000.0,
    "simulation_length": 300,
    "order_arrival_rate": 12,
    "random_seed": 42,
    "execution_mode": "async_buffered",
    # ── Cell layout ───────────────────────────────────────────────────────────
    "cell_overrides": {
        # Loading docks — LEFT edge (input)
        (0, 0): CellType.LOADING_DOCK,
        (1, 0): CellType.LOADING_DOCK,
        (2, 0): CellType.LOADING_DOCK,
        # Shipping docks — RIGHT edge (output)
        (7, 13): CellType.SHIPPING_DOCK,
        (8, 13): CellType.SHIPPING_DOCK,
        (9, 13): CellType.SHIPPING_DOCK,
        # Conveyors — flow lanes between machine columns
        (1, 4): CellType.CONVEYOR, (1, 5): CellType.CONVEYOR, (1, 6): CellType.CONVEYOR,
        (2, 8): CellType.CONVEYOR, (2, 9): CellType.CONVEYOR, (2, 10): CellType.CONVEYOR,
        (5, 4): CellType.CONVEYOR, (5, 5): CellType.CONVEYOR, (5, 6): CellType.CONVEYOR,
        (6, 8): CellType.CONVEYOR, (6, 9): CellType.CONVEYOR, (6, 10): CellType.CONVEYOR,
        (7, 12): CellType.CONVEYOR,
        (8, 12): CellType.CONVEYOR,
        # Storage zones — inter-column buffers
        (3, 5): CellType.STORAGE_ZONE,
        (4, 5): CellType.STORAGE_ZONE,
        (3, 9): CellType.STORAGE_ZONE,
        (4, 9): CellType.STORAGE_ZONE,
        (6, 9): CellType.STORAGE_ZONE,
        # Walls — routing challenge
        (4, 1): CellType.WALL,
        (5, 1): CellType.WALL,
        (2, 12): CellType.WALL,
        (3, 12): CellType.WALL,
    },
    # ── Machines ──────────────────────────────────────────────────────────────
    "machines": [
        # Column 1 — Raw processing (col 3)
        {"id": "smelter_1",     "type": MachineType.SMELTER,          "row": 1, "col": 3, "speed": SpeedMode.NORMAL},
        {"id": "smelter_2",     "type": MachineType.SMELTER,          "row": 5, "col": 3, "speed": SpeedMode.NORMAL},
        {"id": "circuit_fab_1", "type": MachineType.CIRCUIT_FAB,      "row": 7, "col": 3, "speed": SpeedMode.NORMAL},
        # Column 2 — Mid processing (col 7)
        {"id": "press_1",       "type": MachineType.STAMPING_PRESS,   "row": 2, "col": 7, "speed": SpeedMode.NORMAL},
        {"id": "press_2",       "type": MachineType.STAMPING_PRESS,   "row": 5, "col": 7, "speed": SpeedMode.NORMAL},
        {"id": "assembly_1",    "type": MachineType.ASSEMBLY_STATION, "row": 8, "col": 7, "speed": SpeedMode.NORMAL},
        # Column 3 — Finishing (col 11)
        {"id": "qc_1",          "type": MachineType.QC,               "row": 2, "col": 11, "speed": SpeedMode.NORMAL},
        {"id": "qc_2",          "type": MachineType.QC,               "row": 6, "col": 11, "speed": SpeedMode.NORMAL},
        {"id": "packaging_1",   "type": MachineType.PACKAGING,        "row": 7, "col": 11, "speed": SpeedMode.NORMAL},
        {"id": "packaging_2",   "type": MachineType.PACKAGING,        "row": 8, "col": 11, "speed": SpeedMode.NORMAL},
    ],
    # ── Agents ────────────────────────────────────────────────────────────────
    "agents": [
        # Procurement — starts at loading docks (input side)
        {"id": "procurement_1", "role": AgentRole.PROCUREMENT, "row": 0, "col": 0},
        {"id": "procurement_2", "role": AgentRole.PROCUREMENT, "row": 2, "col": 0},
        # Operations — move items between machine columns
        {"id": "operations_1",  "role": AgentRole.OPERATIONS,  "row": 1, "col": 5},
        {"id": "operations_2",  "role": AgentRole.OPERATIONS,  "row": 5, "col": 5},
        {"id": "operations_3",  "role": AgentRole.OPERATIONS,  "row": 7, "col": 9},
        # Engineering — repair machines (stationed near raw column)
        {"id": "engineering_1", "role": AgentRole.ENGINEERING, "row": 4, "col": 3},
        # Sales — near shipping docks (output side)
        {"id": "sales_1",       "role": AgentRole.SALES,       "row": 9, "col": 12},
        # Management — center of factory floor
        {"id": "management_1",  "role": AgentRole.MANAGEMENT,  "row": 4, "col": 7},
    ],
    # ── Pipeline bootstrap ────────────────────────────────────────────────────
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

# Aliases for backward-compatible imports
FIRST_FACTORY_SEEDED_CONFIG: dict = FIRST_FACTORY_CONFIG
DEFAULT_FACTORY_CONFIG: dict = FIRST_FACTORY_CONFIG
