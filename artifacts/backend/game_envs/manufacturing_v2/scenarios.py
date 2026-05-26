"""
Pre-built scenario configurations for the Manufacturing v2 simulation.

FIRST_FACTORY_CONFIG  — Canonical spec v2 §1.2 "Fixed Factory Floorplan".
                        12×12 discrete grid with a walled border.  Loading docks
                        on the left edge (col 0, rows 1–3), shipping docks on the
                        right edge (col 11, rows 4–6).  Six machines, one of each
                        type, at the spec's fixed coordinates.  1000-tick episodes.

FIRST_FACTORY_SEEDED_CONFIG — Alias of FIRST_FACTORY_CONFIG retained for
                        backward-compatible imports in unit tests.

DEFAULT_FACTORY_CONFIG — Alias of FIRST_FACTORY_CONFIG for legacy imports.
"""
from __future__ import annotations

from .entities import (
    CellType, MachineType, AgentRole, ItemType, SpeedMode, MachineState,
)


# ── Spec v2 §1.2 Fixed Factory Floorplan ──────────────────────────────────────
#
#    0 1 2 3 4 5 6 7 8 9 0 1   (columns 0-11)
#  0 W W W W W W W W W W W W
#  1 L . . . . . . . . . . W
#  2 L . S . . . P . . . . W      S = Smelter (2,2)   P = Stamping Press (2,6)
#  3 L . . . . . . . . . . W
#  4 W . . . . . . . . . . S
#  5 W . F . . . A . . . . S      F = Circuit Fab (5,2)  A = Assembly (5,6)
#  6 W . . . . . . . . . . S
#  7 W . . . . . Q . . . . W      Q = QC Station (7,6)
#  8 W . . . . . . . . . . W
#  9 W . . . . . K . . . . W      K = Packaging (9,6)
# 10 W . . . . . . . . . . W
# 11 W W W W W W W W W W W W
#
# Machine coordinates are (row, col).  Interaction happens from adjacent floor.
def _build_cell_overrides() -> dict:
    overrides: dict[tuple[int, int], CellType] = {}
    # Top & bottom border walls (full rows)
    for c in range(12):
        overrides[(0, c)] = CellType.WALL
        overrides[(11, c)] = CellType.WALL
    # Left edge: loading docks rows 1-3, walls rows 4-10
    overrides[(1, 0)] = CellType.LOADING_DOCK
    overrides[(2, 0)] = CellType.LOADING_DOCK
    overrides[(3, 0)] = CellType.LOADING_DOCK
    for r in range(4, 11):
        overrides[(r, 0)] = CellType.WALL
    # Right edge: shipping docks rows 4-6, walls rows 1-3 and 7-10
    for r in (1, 2, 3, 7, 8, 9, 10):
        overrides[(r, 11)] = CellType.WALL
    overrides[(4, 11)] = CellType.SHIPPING_DOCK
    overrides[(5, 11)] = CellType.SHIPPING_DOCK
    overrides[(6, 11)] = CellType.SHIPPING_DOCK
    return overrides


FIRST_FACTORY_CONFIG: dict = {
    "scenario_name": "first_factory",
    # ── Grid ──────────────────────────────────────────────────────────────────
    "grid_rows": 12,
    "grid_cols": 12,
    # ── Economy / episode ──────────────────────────────────────────────────────
    "starting_budget": 10_000.0,
    "simulation_length": 1000,          # spec §0 — 1000-tick episodes
    "order_arrival_rate": 12,
    "random_seed": 42,
    "execution_mode": "async_buffered",
    # ── Cell layout ─────────────────────────────────────────────────────────────
    "cell_overrides": _build_cell_overrides(),
    # ── Machines (one of each type, spec coordinates) ───────────────────────────
    "machines": [
        {"id": "smelter_1",     "type": MachineType.SMELTER,          "row": 2, "col": 2, "speed": SpeedMode.NORMAL},
        {"id": "press_1",       "type": MachineType.STAMPING_PRESS,   "row": 2, "col": 6, "speed": SpeedMode.NORMAL},
        {"id": "circuit_fab_1", "type": MachineType.CIRCUIT_FAB,      "row": 5, "col": 2, "speed": SpeedMode.NORMAL},
        {"id": "assembly_1",    "type": MachineType.ASSEMBLY_STATION, "row": 5, "col": 6, "speed": SpeedMode.NORMAL},
        {"id": "qc_1",          "type": MachineType.QC,               "row": 7, "col": 6, "speed": SpeedMode.NORMAL},
        {"id": "packaging_1",   "type": MachineType.PACKAGING,        "row": 9, "col": 6, "speed": SpeedMode.NORMAL},
    ],
    # ── Agents (default fleet; genome.to_env_config rebuilds counts per genome) ─
    "agents": [
        {"id": "procurement_1", "role": AgentRole.PROCUREMENT, "row": 1, "col": 0},
        {"id": "procurement_2", "role": AgentRole.PROCUREMENT, "row": 2, "col": 0},
        {"id": "operations_1",  "role": AgentRole.OPERATIONS,  "row": 3, "col": 3},
        {"id": "operations_2",  "role": AgentRole.OPERATIONS,  "row": 4, "col": 5},
        {"id": "operations_3",  "role": AgentRole.OPERATIONS,  "row": 6, "col": 6},
        {"id": "engineering_1", "role": AgentRole.ENGINEERING, "row": 4, "col": 4},
        {"id": "sales_1",       "role": AgentRole.SALES,       "row": 6, "col": 9},
        {"id": "management_1",  "role": AgentRole.MANAGEMENT,  "row": 5, "col": 5},
    ],
    # ── Pipeline bootstrap — seed one finished product so sales has early work ──
    "preloaded_items": [
        {
            "id": "pre_finished_1",
            "type": ItemType.FINISHED_PRODUCT,
            "in_machine": "packaging_1",
            "queue": "output",
        },
    ],
    "initial_machine_states": [
        {"id": "packaging_1", "state": MachineState.OUTPUT_READY, "processing_ticks_remaining": 0},
    ],
}

# Aliases for backward-compatible imports
FIRST_FACTORY_SEEDED_CONFIG: dict = FIRST_FACTORY_CONFIG
DEFAULT_FACTORY_CONFIG: dict = FIRST_FACTORY_CONFIG
