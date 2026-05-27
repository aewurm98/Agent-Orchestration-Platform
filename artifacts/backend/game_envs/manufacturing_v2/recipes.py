"""
Recipe DAG and processing engine for the Manufacturing v2 simulation.

Full production chain:
  Path A: Raw Ore (x2) → [Smelter] → Metal Ingot
          Metal Ingot (x1) → [Stamping Press] → Stamped Part
  Path B: Raw Silicon (x1) → [Circuit Fab] → Circuit
  Merge:  Stamped Part (x2) + Circuit (x1) → [Assembly] → Subassembly
          Subassembly (x1) → [QC] → Inspected Unit | Reject
          Inspected Unit (x1) → [Packaging] → Finished Product
"""
from __future__ import annotations

import random
from typing import Optional

from .entities import (
    Item, ItemType, Machine, MachineState, MachineType, SpeedMode,
    MACHINE_BASE_TICKS, SPEED_MULTIPLIERS,
)


Recipe = dict  # {inputs: [(ItemType, qty)], outputs: [(ItemType, qty)], reject_rate: float}

RECIPES: dict[MachineType, Recipe] = {
    MachineType.SMELTER: {
        "inputs": [(ItemType.RAW_ORE, 2)],
        "outputs": [(ItemType.METAL_INGOT, 1)],
        "reject_rate": 0.05,
    },
    MachineType.STAMPING_PRESS: {
        "inputs": [(ItemType.METAL_INGOT, 1)],
        "outputs": [(ItemType.STAMPED_PART, 1)],
        "reject_rate": 0.03,
    },
    MachineType.CIRCUIT_FAB: {
        "inputs": [(ItemType.RAW_SILICON, 1)],
        "outputs": [(ItemType.CIRCUIT, 1)],
        "reject_rate": 0.05,
    },
    MachineType.ASSEMBLY_STATION: {
        "inputs": [(ItemType.STAMPED_PART, 2), (ItemType.CIRCUIT, 1)],
        "outputs": [(ItemType.SUBASSEMBLY, 1)],
        "reject_rate": 0.04,
    },
    MachineType.QC: {
        "inputs": [(ItemType.SUBASSEMBLY, 1)],
        "outputs": [(ItemType.INSPECTED_UNIT, 1)],
        "reject_rate": 0.08,
    },
    MachineType.PACKAGING: {
        "inputs": [(ItemType.INSPECTED_UNIT, 1)],
        "outputs": [(ItemType.FINISHED_PRODUCT, 1)],
        "reject_rate": 0.01,
    },
}


class RecipeEngine:
    """Drives machine state transitions each tick."""

    def __init__(self, rng: random.Random):
        self._rng = rng
        self._item_counter = 0

    def _new_item_id(self, prefix: str) -> str:
        self._item_counter += 1
        return f"{prefix}_{self._item_counter}"

    def can_start(self, machine: Machine) -> bool:
        """Check if machine has all required inputs to start processing."""
        if machine.state != MachineState.IDLE:
            return False
        recipe = RECIPES.get(machine.machine_type)
        if not recipe:
            return False
        input_counts: dict[ItemType, int] = {}
        for item in machine.input_queue:
            input_counts[item.item_type] = input_counts.get(item.item_type, 0) + 1
        for item_type, qty in recipe["inputs"]:
            if input_counts.get(item_type, 0) < qty:
                return False
        return True

    def start_processing(self, machine: Machine) -> None:
        """Consume inputs and begin processing countdown."""
        recipe = RECIPES[machine.machine_type]
        for item_type, qty in recipe["inputs"]:
            removed = 0
            new_queue = []
            for item in machine.input_queue:
                if item.item_type == item_type and removed < qty:
                    removed += 1
                else:
                    new_queue.append(item)
            machine.input_queue = new_queue
        ticks = machine.base_ticks()
        machine.processing_ticks_remaining = ticks
        machine.state = MachineState.PROCESSING

    def advance_tick(self, machine: Machine, alerts: list) -> list[Item]:
        """
        Advance one tick for this machine.
        Returns a list of newly produced items (placed in output_queue on the machine).
        """
        produced: list[Item] = []

        if machine.state == MachineState.OFFLINE:
            return produced

        if machine.state == MachineState.BROKEN:
            return produced

        if machine.state == MachineState.PROCESSING:
            machine.processing_ticks_remaining -= 1

            roll = self._rng.random()
            if roll < machine.failure_rate():
                machine.state = MachineState.BROKEN
                machine.health = max(0.0, machine.health - 0.2)
                alerts.append({
                    "type": "alert",
                    "event": "machine_failure",
                    "machine_id": machine.id,
                    "machine_type": machine.machine_type.value,
                })
                return produced

            if machine.processing_ticks_remaining <= 0:
                recipe = RECIPES.get(machine.machine_type, {})
                reject_rate = recipe.get("reject_rate", 0.0)
                if self._rng.random() < reject_rate:
                    if machine.machine_type == MachineType.QC:
                        reject = Item(
                            id=self._new_item_id("reject"),
                            item_type=ItemType.REJECT,
                        )
                        machine.output_queue.append(reject)
                        produced.append(reject)
                        alerts.append({
                            "type": "alert",
                            "event": "qc_reject",
                            "machine_id": machine.id,
                            "message": f"QC Station {machine.id} rejected subassembly to scrap",
                        })
                    else:
                        alerts.append({
                            "type": "alert",
                            "event": "machine_reject",
                            "machine_id": machine.id,
                            "message": f"{machine.machine_type.value.title()} {machine.id} material reject (zero output)",
                        })
                else:
                    for out_type, qty in recipe.get("outputs", []):
                        for _ in range(qty):
                            new_item = Item(
                                id=self._new_item_id(out_type.value),
                                item_type=out_type,
                            )
                            machine.output_queue.append(new_item)
                            produced.append(new_item)
                machine.total_produced += 1
                machine.state = MachineState.OUTPUT_READY

        if machine.state == MachineState.IDLE and self.can_start(machine):
            self.start_processing(machine)

        return produced

    def input_types_needed(self, machine_type: MachineType) -> list[ItemType]:
        recipe = RECIPES.get(machine_type, {})
        return [item_type for item_type, _ in recipe.get("inputs", [])]

    def output_types(self, machine_type: MachineType) -> list[ItemType]:
        recipe = RECIPES.get(machine_type, {})
        return [item_type for item_type, _ in recipe.get("outputs", [])]
