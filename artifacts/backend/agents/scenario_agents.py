"""
Scenario-specific agent definitions for Supply Chain, Disaster Relief, and Peer Agents.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class AgentConfig:
    agent_id: str
    role: str
    scenario: str
    system_prompt: str
    tools: list[str]
    temperature: float = 0.7
    max_tokens: int = 1024
    last_actions: list[str] = None

    def __post_init__(self):
        if self.last_actions is None:
            self.last_actions = []

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "scenario": self.scenario,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "last_actions": self.last_actions[-3:],
            "ctx_util": random.uniform(0.2, 0.9),
            "status": random.choice(["idle", "active", "active"]),
        }


SUPPLY_CHAIN_AGENTS = [
    AgentConfig(
        agent_id="sc_orchestrator",
        role="Supply Chain Orchestrator",
        scenario="supply_chain",
        system_prompt="You coordinate inventory levels across warehouses. Minimise stockouts while controlling carrying costs.",
        tools=["reorder", "transfer_stock", "forecast_demand"],
    ),
    AgentConfig(
        agent_id="sc_demand",
        role="Demand Forecaster",
        scenario="supply_chain",
        system_prompt="You analyse demand signals and produce 7-day rolling forecasts for each SKU.",
        tools=["read_sales_data", "predict_demand", "emit_forecast"],
    ),
    AgentConfig(
        agent_id="sc_logistics",
        role="Logistics Coordinator",
        scenario="supply_chain",
        system_prompt="You schedule shipments to minimise delivery latency and transportation cost.",
        tools=["schedule_shipment", "reroute", "query_carrier"],
    ),
]

DISASTER_RELIEF_AGENTS = [
    AgentConfig(
        agent_id="dr_commander",
        role="Relief Commander",
        scenario="disaster_relief",
        system_prompt="You coordinate resource allocation across disaster zones. Maximise survivor rescue rate.",
        tools=["deploy_team", "reallocate_resources", "declare_priority_zone"],
    ),
    AgentConfig(
        agent_id="dr_medic",
        role="Medical Coordinator",
        scenario="disaster_relief",
        system_prompt="You triage medical supply distribution and coordinate field hospital placement.",
        tools=["dispatch_medics", "request_supplies", "triage"],
    ),
]

PEER_AGENTS = [
    AgentConfig(
        agent_id="pa_agent_1",
        role="Resource Bidder A",
        scenario="peer_agents",
        system_prompt="You bid for shared computational resources in a multi-agent auction. Maximise your task throughput.",
        tools=["bid", "negotiate", "yield_resource"],
    ),
    AgentConfig(
        agent_id="pa_agent_2",
        role="Resource Bidder B",
        scenario="peer_agents",
        system_prompt="You bid for shared computational resources. Seek Nash equilibrium strategies.",
        tools=["bid", "negotiate", "yield_resource"],
    ),
    AgentConfig(
        agent_id="pa_arbiter",
        role="Market Arbiter",
        scenario="peer_agents",
        system_prompt="You referee the resource auction and enforce allocation fairness.",
        tools=["allocate", "penalise", "publish_results"],
    ),
]


def get_agents_for_scenario(scenario: str) -> list[AgentConfig]:
    mapping = {
        "supply_chain": SUPPLY_CHAIN_AGENTS,
        "disaster_relief": DISASTER_RELIEF_AGENTS,
        "peer_agents": PEER_AGENTS,
    }
    return mapping.get(scenario, SUPPLY_CHAIN_AGENTS)
