"""
Manufacturing game environment: three-stage pipeline simulation (Legacy).

This module is kept for backward compatibility.
The new implementation is in game_envs/manufacturing_v2/.

ManufacturingEnvLegacy = original 3-stage pipeline abstraction
ManufacturingEnv       = alias for ManufacturingEnvV2 (the grid-based engine)
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

DEFECT_RATE = 0.08


STAGE_NAMES = ["raw_materials", "intermediates", "finished_product"]
STAGE_LABELS = ["Raw Materials", "Intermediates", "Finished Product"]
MATERIAL_TYPES = ["ore", "components", "products"]

INITIAL_INPUT = [120, 0, 0]
THROUGHPUT_CAPS = [35, 28, 22]
DEFAULT_TARGETS = [20, 15, 10]
NATURAL_REPLENISHMENT = 12


@dataclass
class Stage:
    name: str
    label: str
    material_type: str
    input_buffer: int
    output_buffer: int
    throughput_capacity: int
    target_units: int
    worker_state: str = "idle"
    total_processed: int = 0
    defective_units: int = 0
    idle_ticks: int = 0


class ManufacturingEnvLegacy:
    def __init__(self) -> None:
        self._tick: int = 0
        self._approved_finished: int = 0
        self._stages: list[Stage] = [
            Stage(
                name=STAGE_NAMES[i],
                label=STAGE_LABELS[i],
                material_type=MATERIAL_TYPES[i],
                input_buffer=INITIAL_INPUT[i],
                output_buffer=0,
                throughput_capacity=THROUGHPUT_CAPS[i],
                target_units=DEFAULT_TARGETS[i],
            )
            for i in range(3)
        ]

    def process_batch(self, stage_name: str, quantity: int) -> dict:
        stage = self._get_stage(stage_name)
        if stage is None:
            return {"ok": False, "error": "unknown stage"}
        qty = max(0, min(quantity, stage.input_buffer, stage.throughput_capacity))
        if qty == 0:
            stage.worker_state = "blocked"
            stage.idle_ticks += 1
            return {"ok": False, "processed": 0, "reason": "input buffer empty or capacity exceeded"}
        stage.input_buffer -= qty
        defective = int(qty * DEFECT_RATE * (0.5 + random.random()))
        good = qty - defective
        stage.output_buffer += qty
        stage.defective_units += defective
        stage.total_processed += good
        stage.worker_state = "processing"
        stage.idle_ticks = 0
        return {"ok": True, "processed": qty, "good": good, "defective": defective}

    def inspect_input(self, stage_name: str) -> dict:
        stage = self._get_stage(stage_name)
        if stage is None:
            return {"ok": False, "error": "unknown stage"}
        defect_pct = round(stage.defective_units / max(stage.input_buffer, 1) * 100, 1)
        return {
            "ok": True,
            "stage": stage_name,
            "input_buffer": stage.input_buffer,
            "material_type": stage.material_type,
            "defect_pct": defect_pct,
            "quality": "poor" if defect_pct > 15 else "ok" if defect_pct > 5 else "good",
        }

    def rework_output(self, stage_name: str, quantity: int) -> dict:
        stage = self._get_stage(stage_name)
        if stage is None:
            return {"ok": False, "error": "unknown stage"}
        qty = max(0, min(quantity, stage.output_buffer, stage.defective_units))
        stage.defective_units = max(0, stage.defective_units - qty)
        stage.output_buffer -= qty
        stage.input_buffer += qty
        return {"ok": True, "reworked": qty}

    def reallocate_materials(self, from_stage: str, to_stage: str, quantity: int) -> dict:
        src = self._get_stage(from_stage)
        dst = self._get_stage(to_stage)
        if src is None or dst is None:
            return {"ok": False, "error": "unknown stage"}
        qty = max(0, min(quantity, src.input_buffer))
        src.input_buffer -= qty
        dst.input_buffer += qty
        return {"ok": True, "moved": qty, "from": from_stage, "to": to_stage}

    def set_production_target(self, stage_name: str, target_units: int) -> dict:
        stage = self._get_stage(stage_name)
        if stage is None:
            return {"ok": False, "error": "unknown stage"}
        stage.target_units = max(0, target_units)
        return {"ok": True, "stage": stage_name, "new_target": stage.target_units}

    def approve_release(self, quantity: int) -> dict:
        fp = self._get_stage("finished_product")
        qty = max(0, min(quantity, fp.output_buffer))
        fp.output_buffer -= qty
        self._approved_finished += qty
        return {"ok": True, "released": qty, "total_approved": self._approved_finished}

    def get_stage_snapshot(self, stage_name: str) -> dict:
        stage = self._get_stage(stage_name)
        if stage is None:
            return {}
        return {
            "name": stage.name,
            "label": stage.label,
            "material_type": stage.material_type,
            "input_buffer": stage.input_buffer,
            "output_buffer": stage.output_buffer,
            "throughput_capacity": stage.throughput_capacity,
            "target_units": stage.target_units,
            "worker_state": stage.worker_state,
            "total_processed": stage.total_processed,
            "defective_units": stage.defective_units,
        }

    def query_pipeline_status(self) -> dict:
        stages = {}
        for s in self._stages:
            throughput_rate = round(s.total_processed / max(self._tick, 1), 2)
            stages[s.name] = {
                "input_buffer": s.input_buffer,
                "output_buffer": s.output_buffer,
                "throughput_capacity": s.throughput_capacity,
                "target_units": s.target_units,
                "worker_state": s.worker_state,
                "total_processed": s.total_processed,
                "throughput_rate_per_tick": throughput_rate,
                "wip": s.input_buffer + s.output_buffer,
                "idle_count": s.idle_ticks,
                "is_idle": s.worker_state in ("idle", "blocked"),
            }
        return {
            "tick": self._tick,
            "approved_finished": self._approved_finished,
            "stages": stages,
            "total_wip": sum(s.input_buffer + s.output_buffer for s in self._stages),
            "total_throughput": sum(s.total_processed for s in self._stages),
        }

    def tick(self) -> None:
        self._tick += 1
        self._stages[0].input_buffer = min(
            self._stages[0].input_buffer + NATURAL_REPLENISHMENT, 300
        )
        for i in range(len(self._stages) - 1):
            pull_cap = self._stages[i + 1].target_units
            transfer = min(self._stages[i].output_buffer, pull_cap)
            self._stages[i].output_buffer -= transfer
            self._stages[i + 1].input_buffer += transfer
        for s in self._stages:
            if s.worker_state in ("idle", "blocked"):
                s.idle_ticks += 1
            else:
                s.idle_ticks = 0

    def _get_stage(self, name: str) -> Stage | None:
        for s in self._stages:
            if s.name == name:
                return s
        return None

    def get_objective_value(self) -> float:
        total_possible = sum(s.target_units * max(self._tick, 1) for s in self._stages)
        total_actual = sum(s.total_processed for s in self._stages)
        return min(1.0, total_actual / max(total_possible, 1))

    def to_json(self) -> dict:
        agents = []
        for i, s in enumerate(self._stages):
            agents.append({
                "id": s.name,
                "role": s.label,
                "x": i * 4 + 1,
                "y": 5,
                "inventory": s.output_buffer,
                "state": s.worker_state,
            })
        return {
            "scenario": "manufacturing",
            "agents": agents,
            "resources": {
                "grid_size": 10,
                "raw_input": self._stages[0].input_buffer,
                "inter_input": self._stages[1].input_buffer,
                "finished_output": self._stages[2].output_buffer,
                "approved_finished": self._approved_finished,
                "total_processed": sum(s.total_processed for s in self._stages),
            },
            "score": self.get_objective_value(),
            "tick": self._tick,
        }


# ── Alias: ManufacturingEnv → grid-based v2 engine ───────────────────────────
from game_envs.manufacturing_v2 import ManufacturingEnvV2 as ManufacturingEnv  # noqa: E402
