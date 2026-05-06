"""
LangGraph StateGraph orchestrator for the Agentic Engineering Arena.
All 7 nodes wired: goal_intake, topology_init, agent_step, evaluate,
hitl_gate (proper node), mutate, checkpoint.
"""
from __future__ import annotations

import random
import time
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END

from agents.evolutionary_engine import (
    FitnessScore,
    SemanticMutation,
    GraphGRPOPrune,
    TaguchiL9Sample,
    GenerationLog,
)


class ArenaState(TypedDict):
    scenario: str
    objective: str
    agent_configs: list[dict]
    topology: dict
    current_fitness: float
    generation: int
    max_generations: int
    hitl_pending: bool
    confidence: float
    edge_scores: dict[str, float]
    checkpoint_key: str
    run_id: str
    traces: list[dict]


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def goal_intake(state: ArenaState) -> ArenaState:
    """Parse scenario and set high-level objective."""
    # STUB: replace with LLM call to parse and clarify objective
    objective_map = {
        "supply_chain": "Minimise stockout rate while reducing carrying cost",
        "disaster_relief": "Maximise survivor rescue rate within 24 simulated hours",
        "peer_agents": "Achieve Nash equilibrium in multi-agent resource allocation",
    }
    state["objective"] = objective_map.get(state["scenario"], "Optimise agent performance")
    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": f"Goal intake complete: {state['objective']}",
        "timestamp": time.time(),
    }]
    return state


def topology_init(state: ArenaState) -> ArenaState:
    """Initialise the agent graph topology from Taguchi L9 sample."""
    # STUB: replace with LLM call to design initial topology
    sample_configs = TaguchiL9Sample({
        "model": ["claude-3-haiku", "claude-3-sonnet", "claude-3-5-sonnet"],
        "temperature": [0.3, 0.7, 1.0],
        "max_tokens": [512, 1024, 2048],
    })
    state["agent_configs"] = sample_configs[:3]
    state["topology"] = {
        "nodes": ["orchestrator", "evaluator", "worker_1", "worker_2"],
        "edges": [
            ("orchestrator", "evaluator"),
            ("orchestrator", "worker_1"),
            ("orchestrator", "worker_2"),
            ("evaluator", "orchestrator"),
        ],
    }
    state["edge_scores"] = {
        "orchestrator->evaluator": 0.8,
        "orchestrator->worker_1": 0.6,
        "orchestrator->worker_2": 0.5,
        "evaluator->orchestrator": 0.9,
    }
    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": f"Topology initialised with {len(state['topology']['nodes'])} agents",
        "timestamp": time.time(),
    }]
    return state


def agent_step(state: ArenaState) -> ArenaState:
    """Run one tick of the active agent population."""
    # STUB: replace with LLM call for each active agent
    for _cfg in state.get("agent_configs", []):
        pass  # agents would take actions here

    state["traces"] = state.get("traces", []) + [{
        "role": "orchestrator",
        "content": f"[Gen {state['generation']}] Agent step complete",
        "timestamp": time.time(),
    }]
    return state


def evaluate(state: ArenaState) -> ArenaState:
    """Score generation with CLEAR fitness function."""
    # STUB: replace with LLM call for evaluator agent
    latency = random.uniform(0.2, 1.5)
    cost = random.uniform(0.001, 0.05)
    success_rate = random.uniform(0.3, 0.95)
    fitness = FitnessScore(success_rate=success_rate, latency=latency, cost=cost)
    state["current_fitness"] = round(fitness, 4)
    state["confidence"] = round(random.uniform(0.3, 0.95), 2)
    state["traces"] = state.get("traces", []) + [{
        "role": "evaluator",
        "content": f"Fitness={state['current_fitness']}, confidence={state['confidence']}",
        "timestamp": time.time(),
    }]
    return state


def hitl_gate(state: ArenaState) -> ArenaState:
    """Node 5: mark state for HITL pause when confidence < 0.6."""
    state["hitl_pending"] = state.get("confidence", 1.0) < 0.6
    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": (
            "HITL gate: pausing for human review"
            if state["hitl_pending"]
            else "HITL gate: confidence OK, continuing"
        ),
        "timestamp": time.time(),
    }]
    return state


def mutate(state: ArenaState) -> ArenaState:
    """Apply semantic mutation + Graph-GRPO edge pruning."""
    for i, cfg in enumerate(state.get("agent_configs", [])):
        # STUB: replace with LLM call for semantic mutation
        state["agent_configs"][i] = SemanticMutation(cfg)

    pruned = GraphGRPOPrune(state["topology"], state["edge_scores"])
    state["topology"] = pruned
    state["generation"] = state.get("generation", 0) + 1
    state["traces"] = state.get("traces", []) + [{
        "role": "system",
        "content": f"Mutation complete. Now at generation {state['generation']}",
        "timestamp": time.time(),
    }]
    return state


def checkpoint(state: ArenaState) -> ArenaState:
    """Serialize state snapshot (stubbed as in-memory; wire Redis here later)."""
    # STUB: replace with Redis snapshot
    key = f"arena:{state.get('run_id', 'default')}:gen:{state.get('generation', 0)}"
    state["checkpoint_key"] = key
    GenerationLog(
        generation=state["generation"],
        fitness=state["current_fitness"],
        mutation_type="stub",
        topology_nodes=len(state.get("topology", {}).get("nodes", [])),
    )
    return state


# ---------------------------------------------------------------------------
# Routing helpers (not graph nodes)
# ---------------------------------------------------------------------------

def _hitl_route(state: ArenaState) -> str:
    """Route after hitl_gate: pause for human or continue to mutate."""
    return "hitl" if state.get("hitl_pending") else "continue"


def _continue_route(state: ArenaState) -> str:
    """Route after checkpoint: stop at max generations or loop back."""
    if state.get("generation", 0) >= state.get("max_generations", 10):
        return "done"
    return "next"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(ArenaState)

    # Register all 7 nodes
    graph.add_node("goal_intake", goal_intake)
    graph.add_node("topology_init", topology_init)
    graph.add_node("agent_step", agent_step)
    graph.add_node("evaluate", evaluate)
    graph.add_node("hitl_gate", hitl_gate)
    graph.add_node("mutate", mutate)
    graph.add_node("checkpoint", checkpoint)

    # Linear init chain
    graph.set_entry_point("goal_intake")
    graph.add_edge("goal_intake", "topology_init")
    graph.add_edge("topology_init", "agent_step")
    graph.add_edge("agent_step", "evaluate")

    # hitl_gate is now a real node; routing is a separate conditional
    graph.add_edge("evaluate", "hitl_gate")
    graph.add_conditional_edges("hitl_gate", _hitl_route, {
        "hitl": "checkpoint",
        "continue": "mutate",
    })
    graph.add_edge("mutate", "checkpoint")

    # Loop back or terminate
    graph.add_conditional_edges("checkpoint", _continue_route, {
        "done": END,
        "next": "agent_step",
    })

    return graph.compile()


async def run_orchestrator(
    scenario: str,
    run_id: str,
    max_generations: int = 5,
) -> dict:
    """Run the orchestrator graph for one episode, returning the final state."""
    graph = build_graph()
    initial_state: ArenaState = {
        "scenario": scenario,
        "objective": "",
        "agent_configs": [],
        "topology": {},
        "current_fitness": 0.0,
        "generation": 0,
        "max_generations": max_generations,
        "hitl_pending": False,
        "confidence": 1.0,
        "edge_scores": {},
        "checkpoint_key": "",
        "run_id": run_id,
        "traces": [],
    }
    result = await graph.ainvoke(
        initial_state,
        config={"recursion_limit": max_generations * 10 + 20},
    )
    return dict(result)
