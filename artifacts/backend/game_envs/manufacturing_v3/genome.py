"""
Manufacturing v3 genome (spec §5).

The v3 genome is the LLM Meta-Optimizer's full action space. Unlike v2 it does
NOT describe agent coordinates or hiring — it sets global structural knobs over
the Topological Flow Graph:

  - machine_capacities: items each machine processes per batch    (4 ints, 1-50)
  - edge_bandwidths:    items each conveyor moves per tick         (6 ints, 1-50)
  - maintenance_policy: low | medium | high                        (categorical)
  - order_intake_rate:  total target orders per 500-tick episode   (int, 1-100)
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Optional

# ── Bounds (spec §5.1 schema) ────────────────────────────────────────────────
MACHINE_IDS: tuple[str, ...] = ("molding", "wire_drawing", "assembly", "packaging")
EDGE_IDS: tuple[str, ...] = (
    "in_to_molding",
    "in_to_wire",
    "molding_to_assembly",
    "wire_to_assembly",
    "assembly_to_packaging",
    "packaging_to_out",
)
MAINTENANCE_POLICIES: tuple[str, ...] = ("low", "medium", "high")

CAPACITY_MIN, CAPACITY_MAX = 1, 50
BANDWIDTH_MIN, BANDWIDTH_MAX = 1, 50
INTAKE_MIN, INTAKE_MAX = 1, 100


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


@dataclass
class ManufacturingV3Genome:
    machine_capacities: dict[str, int] = field(default_factory=dict)
    edge_bandwidths: dict[str, int] = field(default_factory=dict)
    maintenance_policy: str = "medium"
    order_intake_rate: int = 40

    # ── Construction ─────────────────────────────────────────────────────────
    def __post_init__(self) -> None:
        # Fill any missing keys with balanced defaults, then clamp everything to
        # the spec bounds so an out-of-range genome can never reach the engine.
        caps = dict(self.machine_capacities or {})
        bws = dict(self.edge_bandwidths or {})
        self.machine_capacities = {
            mid: _clamp_int(caps.get(mid, 5), CAPACITY_MIN, CAPACITY_MAX, 5)
            for mid in MACHINE_IDS
        }
        self.edge_bandwidths = {
            eid: _clamp_int(bws.get(eid, 5), BANDWIDTH_MIN, BANDWIDTH_MAX, 5)
            for eid in EDGE_IDS
        }
        if self.maintenance_policy not in MAINTENANCE_POLICIES:
            self.maintenance_policy = "medium"
        self.order_intake_rate = _clamp_int(
            self.order_intake_rate, INTAKE_MIN, INTAKE_MAX, 40
        )

    @classmethod
    def default(cls) -> "ManufacturingV3Genome":
        """A balanced, valid starting genome (not pre-optimised)."""
        return cls(
            machine_capacities={mid: 5 for mid in MACHINE_IDS},
            edge_bandwidths={eid: 5 for eid in EDGE_IDS},
            maintenance_policy="medium",
            order_intake_rate=40,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "ManufacturingV3Genome":
        d = d or {}
        return cls(
            machine_capacities=dict(d.get("machine_capacities", {})),
            edge_bandwidths=dict(d.get("edge_bandwidths", {})),
            maintenance_policy=str(d.get("maintenance_policy", "medium")),
            order_intake_rate=d.get("order_intake_rate", 40),
        )

    def to_dict(self) -> dict:
        return {
            "machine_capacities": dict(self.machine_capacities),
            "edge_bandwidths": dict(self.edge_bandwidths),
            "maintenance_policy": self.maintenance_policy,
            "order_intake_rate": self.order_intake_rate,
        }

    def clone(self) -> "ManufacturingV3Genome":
        return ManufacturingV3Genome.from_dict(copy.deepcopy(self.to_dict()))

    # ── Evolution operators ───────────────────────────────────────────────────
    def mutate(self, rng: Optional[random.Random] = None) -> "ManufacturingV3Genome":
        """MATH fallback mutation: perturb one randomly-chosen genome axis.

        Used when the LLM meta-optimizer is unavailable, and to seed the λ
        offspring with diversity.
        """
        rng = rng or random.Random()
        caps = dict(self.machine_capacities)
        bws = dict(self.edge_bandwidths)
        maint = self.maintenance_policy
        intake = self.order_intake_rate

        axis = rng.choice(["capacity", "bandwidth", "maintenance", "intake"])
        if axis == "capacity":
            mid = rng.choice(MACHINE_IDS)
            caps[mid] = _clamp_int(
                caps[mid] + rng.choice([-3, -2, -1, 1, 2, 3]),
                CAPACITY_MIN, CAPACITY_MAX, caps[mid],
            )
        elif axis == "bandwidth":
            eid = rng.choice(EDGE_IDS)
            bws[eid] = _clamp_int(
                bws[eid] + rng.choice([-3, -2, -1, 1, 2, 3]),
                BANDWIDTH_MIN, BANDWIDTH_MAX, bws[eid],
            )
        elif axis == "maintenance":
            maint = rng.choice([p for p in MAINTENANCE_POLICIES if p != maint])
        else:  # intake
            delta = int(round(intake * rng.uniform(-0.15, 0.15))) or rng.choice([-1, 1])
            intake = _clamp_int(intake + delta, INTAKE_MIN, INTAKE_MAX, intake)

        return ManufacturingV3Genome(
            machine_capacities=caps,
            edge_bandwidths=bws,
            maintenance_policy=maint,
            order_intake_rate=intake,
        )

    @classmethod
    def random(cls, rng: Optional[random.Random] = None) -> "ManufacturingV3Genome":
        """Uniformly random valid genome — used for stress testing and diversity."""
        rng = rng or random.Random()
        return cls(
            machine_capacities={
                mid: rng.randint(CAPACITY_MIN, CAPACITY_MAX) for mid in MACHINE_IDS
            },
            edge_bandwidths={
                eid: rng.randint(BANDWIDTH_MIN, BANDWIDTH_MAX) for eid in EDGE_IDS
            },
            maintenance_policy=rng.choice(MAINTENANCE_POLICIES),
            order_intake_rate=rng.randint(INTAKE_MIN, INTAKE_MAX),
        )

    def apply_delta(self, delta: dict) -> "ManufacturingV3Genome":
        """Merge a (possibly partial / malformed) candidate dict from the LLM into
        a fresh, fully-clamped genome. Never raises — invalid fields are dropped.
        """
        delta = delta or {}
        caps = dict(self.machine_capacities)
        for mid, val in (delta.get("machine_capacities") or {}).items():
            if mid in caps and val is not None:
                caps[mid] = _clamp_int(val, CAPACITY_MIN, CAPACITY_MAX, caps[mid])

        bws = dict(self.edge_bandwidths)
        for eid, val in (delta.get("edge_bandwidths") or {}).items():
            if eid in bws and val is not None:
                bws[eid] = _clamp_int(val, BANDWIDTH_MIN, BANDWIDTH_MAX, bws[eid])

        maint = delta.get("maintenance_policy")
        maint = maint if maint in MAINTENANCE_POLICIES else self.maintenance_policy

        intake = delta.get("order_intake_rate")
        intake = (
            _clamp_int(intake, INTAKE_MIN, INTAKE_MAX, self.order_intake_rate)
            if intake is not None
            else self.order_intake_rate
        )

        return ManufacturingV3Genome(
            machine_capacities=caps,
            edge_bandwidths=bws,
            maintenance_policy=maint,
            order_intake_rate=intake,
        )
