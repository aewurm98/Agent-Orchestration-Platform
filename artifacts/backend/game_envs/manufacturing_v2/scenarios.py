"""
Pre-built scenario configurations for the Manufacturing v2 simulation.

FIRST_FACTORY_CONFIG  — spec §12 compliant: 12×12 grid, 6 machines, 5 agents,
                        no preloaded pipeline state.  Used as the canonical
                        default for the /api/mfg/reset endpoint and any
                        externally-visible baseline.

FIRST_FACTORY_SEEDED_CONFIG — extends the same layout with pre-seeded pipeline
                        items so the automated smoke-test achieves non-zero
                        throughput within 10 ticks without running a full
                        production cycle.  Used only by internal unit tests.
"""
from __future__ import annotations

from .entities import (
    CellType, MachineType, AgentRole, ItemType, SpeedMode, MachineState,
)


# ── Spec §12 default scenario ─────────────────────────────────────────────────
# 12×12 grid · 6 machine types · 5 agent roles · $10k budget · 500 ticks
# No preloaded items or forced machine states.
FIRST_FACTORY_CONFIG: dict = {
    "scenario_name": "first_factory",
    "grid_rows": 12,
    "grid_cols": 12,
    "starting_budget": 10_000.0,
    "simulation_length": 500,
    "order_arrival_rate": 15,
    "random_seed": 42,
    "execution_mode": "async_buffered",
    "cell_overrides": {
        # Loading dock (top-left)
        (0, 0): CellType.LOADING_DOCK,
        (0, 1): CellType.LOADING_DOCK,
        # Shipping dock (bottom-right)
        (11, 11): CellType.SHIPPING_DOCK,
        # Internal walls (create routing challenge without trapping agents)
        (5, 5): CellType.WALL,
        (5, 6): CellType.WALL,
        (6, 5): CellType.WALL,
        # Storage zones
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
        {"id": "engineering_1", "role": AgentRole.ENGINEERING,  "row": 1,  "col": 3},
        {"id": "sales_1",       "role": AgentRole.SALES,        "row": 10, "col": 11},
        {"id": "management_1",  "role": AgentRole.MANAGEMENT,   "row": 5,  "col": 3},
    ],
}

# ── Smoke-test seeded variant ─────────────────────────────────────────────────
# Identical layout but with pre-seeded pipeline items so automated tests can
# verify non-zero throughput within 10 ticks.  Not used in production.
#   - packaging_1 starts OUTPUT_READY with a FINISHED_PRODUCT → sales_1 sells
#     at tick 3 → throughput=1.
#   - qc_1 starts PROCESSING (2 ticks remaining) → chains next unit.
FIRST_FACTORY_SEEDED_CONFIG: dict = {
    **FIRST_FACTORY_CONFIG,
    "scenario_name": "first_factory_seeded",
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

# Kept for backward-compat imports
DEFAULT_FACTORY_CONFIG = FIRST_FACTORY_CONFIG
