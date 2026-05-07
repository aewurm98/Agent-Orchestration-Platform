"""
Pre-built scenario configurations for the Manufacturing v2 simulation.

FIRST_FACTORY_CONFIG  — Canonical "spec §12 First Factory" default used by
                        /api/mfg/reset, the simulation loop, and EA evaluation.
                        Layout: 10×10 · Loading dock (0,0)/(0,1) · Shipping (9,9)
                        · Wall cluster at (5,5)/(4,5)/(5,4) · $8,000 · 300 ticks
                        · order every 12 ticks · random seed 42.
                        Includes two pre-seeded pipeline items (clearly documented
                        below) so scripted smoke-tests achieve non-zero throughput
                        within 10 ticks without requiring a full production cycle.

FIRST_FACTORY_SEEDED_CONFIG — Alias of FIRST_FACTORY_CONFIG retained for
                        backward-compatible imports in unit tests.

DEFAULT_FACTORY_CONFIG — Alias of FIRST_FACTORY_CONFIG for legacy imports.
"""
from __future__ import annotations

from .entities import (
    CellType, MachineType, AgentRole, ItemType, SpeedMode, MachineState,
)


# ── Spec §12 First Factory (canonical default) ────────────────────────────────
#
# Pipeline bootstrap items (documented):
#   pre_finished_1 — FINISHED_PRODUCT in packaging_1 output queue.
#                    packaging_1 starts OUTPUT_READY → sales_1 (adjacent at 8,9)
#                    unloads tick 1, walks to shipping dock tick 2, sells tick 3
#                    → throughput = 1 by tick 3.  Satisfies smoke-test criterion.
#   pre_subassembly_1 — SUBASSEMBLY in qc_1, PROCESSING with 2 ticks remaining
#                    → inspected_unit released tick 3 to keep pipeline flowing.
#
# These items are deterministic (seed 42) bootstrap state, not "live" production
# output.  EA runs therefore start from an identical baseline every evaluation.
FIRST_FACTORY_CONFIG: dict = {
    "scenario_name": "first_factory",
    # ── Grid ──────────────────────────────────────────────────────────────────
    "grid_rows": 10,
    "grid_cols": 10,
    # ── Economy ───────────────────────────────────────────────────────────────
    "starting_budget": 8_000.0,
    "simulation_length": 300,
    "order_arrival_rate": 12,
    "random_seed": 42,
    "execution_mode": "async_buffered",
    # ── Cell layout ───────────────────────────────────────────────────────────
    "cell_overrides": {
        # Loading dock (top-left corner)
        (0, 0): CellType.LOADING_DOCK,
        (0, 1): CellType.LOADING_DOCK,
        # Shipping dock (bottom-right corner)
        (9, 9): CellType.SHIPPING_DOCK,
        # Wall cluster (creates routing challenge without trapping agents)
        (5, 5): CellType.WALL,
        (4, 5): CellType.WALL,
        (5, 4): CellType.WALL,
        # Storage zones (buffer area between circuit fab and press)
        (3, 5): CellType.STORAGE_ZONE,
        (3, 6): CellType.STORAGE_ZONE,
    },
    # ── Machines (6 types) ────────────────────────────────────────────────────
    "machines": [
        {"id": "smelter_1",     "type": MachineType.SMELTER,          "row": 2, "col": 2, "speed": SpeedMode.NORMAL},
        {"id": "circuit_fab_1", "type": MachineType.CIRCUIT_FAB,       "row": 2, "col": 6, "speed": SpeedMode.NORMAL},
        {"id": "press_1",       "type": MachineType.STAMPING_PRESS,    "row": 4, "col": 4, "speed": SpeedMode.NORMAL},
        {"id": "assembly_1",    "type": MachineType.ASSEMBLY_STATION,  "row": 6, "col": 4, "speed": SpeedMode.NORMAL},
        {"id": "qc_1",          "type": MachineType.QC,                "row": 7, "col": 6, "speed": SpeedMode.NORMAL},
        {"id": "packaging_1",   "type": MachineType.PACKAGING,         "row": 8, "col": 8, "speed": SpeedMode.NORMAL},
    ],
    # ── Agents (5 roles) ──────────────────────────────────────────────────────
    "agents": [
        {"id": "procurement_1", "role": AgentRole.PROCUREMENT,  "row": 0, "col": 0},
        {"id": "operations_1",  "role": AgentRole.OPERATIONS,   "row": 1, "col": 1},
        {"id": "engineering_1", "role": AgentRole.ENGINEERING,  "row": 1, "col": 2},
        {"id": "sales_1",       "role": AgentRole.SALES,        "row": 8, "col": 9},
        {"id": "management_1",  "role": AgentRole.MANAGEMENT,   "row": 4, "col": 3},
    ],
    # ── Pipeline bootstrap (deterministic seed for smoke-tests) ───────────────
    "preloaded_items": [
        # packaging_1 already has a finished product → sales_1 sells at tick 3
        {
            "id": "pre_finished_1",
            "type": ItemType.FINISHED_PRODUCT,
            "in_machine": "packaging_1",
            "queue": "output",
        },
        # qc_1 is mid-process → releases inspected_unit at tick 3
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
