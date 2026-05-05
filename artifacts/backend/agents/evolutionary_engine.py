"""
Evolutionary engine: fitness scoring, semantic mutation, Graph-GRPO pruning,
Taguchi L9 sampling, and generation logging.
"""
from __future__ import annotations

import copy
import itertools
import random
import time
from dataclasses import dataclass, field
from typing import Any


def FitnessScore(success_rate: float, latency: float, cost: float) -> float:
    """FitnessScore = SuccessRate / (Latency * Cost)"""
    denominator = latency * cost
    if denominator <= 0:
        return 0.0
    return success_rate / denominator


def SemanticMutation(agent_config: dict) -> dict:
    """
    Mutate an agent config via LLM call.
    Returns a mutated copy of the config.
    """
    # STUB: replace with LLM call
    mutated = copy.deepcopy(agent_config)
    mutation_choices = [
        ("temperature", lambda v: max(0.0, min(1.5, v + random.uniform(-0.2, 0.2)))),
        ("max_tokens", lambda v: max(128, v + random.choice([-256, -128, 128, 256]))),
        ("system_prompt_suffix", lambda _: random.choice([
            " Be concise.",
            " Think step by step.",
            " Prioritise efficiency.",
        ])),
    ]
    key, mutator = random.choice(mutation_choices)
    mutated[key] = mutator(mutated.get(key, 0.7 if key == "temperature" else 1024))
    mutated["mutation_type"] = "semantic"
    return mutated


def GraphGRPOPrune(topology: dict, edge_scores: dict[str, float]) -> dict:
    """
    Prune low-scoring edges based on Graph-GRPO advantage scores.
    Returns a pruned adjacency list (topology dict).
    """
    pruned = copy.deepcopy(topology)
    threshold = 0.3
    kept_edges = []
    for edge in topology.get("edges", []):
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            src, tgt = edge
            score_key = f"{src}->{tgt}"
            score = edge_scores.get(score_key, 0.5)
            if score >= threshold:
                kept_edges.append(edge)
    pruned["edges"] = kept_edges
    return pruned


def TaguchiL9Sample(param_grid: dict[str, list]) -> list[dict]:
    """
    Returns 9 configurations using Taguchi L9 orthogonal array design.
    Requires exactly 3 parameters each with 3 levels; falls back to
    random sampling if the grid doesn't match.
    """
    keys = list(param_grid.keys())
    values = [param_grid[k] for k in keys]

    # Taguchi L9 orthogonal array (3 factors, 3 levels each)
    L9 = [
        [0, 0, 0], [0, 1, 1], [0, 2, 2],
        [1, 0, 1], [1, 1, 2], [1, 2, 0],
        [2, 0, 2], [2, 1, 0], [2, 2, 1],
    ]

    configs = []
    if len(keys) == 3 and all(len(v) >= 3 for v in values):
        for row in L9:
            cfg = {keys[i]: values[i][row[i]] for i in range(3)}
            configs.append(cfg)
    else:
        # Fallback: random combinations
        for _ in range(9):
            cfg = {k: random.choice(v) for k, v in param_grid.items()}
            configs.append(cfg)

    return configs


@dataclass
class GenerationLog:
    gen_id: int
    parent_fitness: float
    child_fitness: float
    mutation_type: str
    topology_diff: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "gen_id": self.gen_id,
            "parent_fitness": self.parent_fitness,
            "child_fitness": self.child_fitness,
            "mutation_type": self.mutation_type,
            "topology_diff": self.topology_diff,
            "timestamp": self.timestamp,
        }
