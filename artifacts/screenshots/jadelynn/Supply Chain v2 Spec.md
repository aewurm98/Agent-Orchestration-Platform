# **Real-Time Evolutionary Supply Chain Architecture (v2.0)**

This document serves as the complete technical specification for the dual-tier LLM supply chain simulation. It transitions the system from a static parameter-tuning game into a real-time, deterministic, network-building scenario where a global "Meta-Optimizer" LLM evolves the infrastructure and rules, while autonomous programmatic "Edge Agents" navigate localized physical and economic exceptions using localized LLM calls.

## **1\. Global Simulation Mechanics & Physics**

The environment is modeled as a continuous, deterministic spatial graph governed by strict economic rules.

### **1.1 The Spatial Grid**

* **Dimensions:** A $20 \\times 20$ discrete grid.  
* **Terrain Types & Movement Costs:**  
  * `highway`: Costs $\\$1.0$ per tick to traverse.  
  * `off_road`: Costs $\\$3.0$ per tick to traverse.  
  * `obstacle`: Impassable (A\* pathfinder must route around).

### **1.2 System Ledger & The Objective Function**

The simulation tracks a global ledger across a strict **500-tick episode**. The ultimate objective of the simulation (optimized by the Meta-Optimizer) is to maximize the **Global Liquidity Score (GLS)**:

$$\\text{GLS} \= \\text{Total Revenue} \- (\\text{CapEx} \+ \\text{OpEx} \+ \\text{Penalties})$$

### **1.3 Entity Types (Nodes)**

Nodes occupy single grid coordinates and operate programmatic state updates every tick.

1. **Suppliers (Fixed):**  
   * *Under-the-hood:* Generates $10$ units of raw cargo every $5$ ticks. Uncapped capacity. Standard purchase price: $\\$20/\\text{unit}$.  
2. **Demand Zones (Fixed):**  
   * *Under-the-hood:* Base demand accumulates at $5$ units per tick. Base buying price is $\\$100/\\text{unit}$. If `accumulated_demand > 0`, it triggers a penalty of $\\$50/\\text{tick}$ applied to the GLS.  
   * *Market Shocks:* Driven by a Poisson process ($\\lambda \= 0.02$). When a shock occurs, `current_price = base_price \times 2.5` for a random duration between $10$ and $30$ ticks.  
3. **Warehouses (Mutable):**  
   * *Under-the-hood:* Built dynamically by the Meta-Optimizer. They serve as inventory buffers. They charge a $\\$2/\\text{tick}$ holding fee for stored cargo. If `current_inventory == max_capacity`, the `transfer_stock()` method strictly returns `False`.

### **1.4 Edge Agents (Trucks)**

Agents are the physical movers of cargo.

* **Capacity:** Max 50 units.  
* **Upkeep:** $\\$5.0$ per tick operating cost (incurred every tick regardless of movement or state).  
* **Spoilage Mechanics:**  
  * Cargo has a `health_score` starting at $100\\%$.  
  * `health_score` decays by exactly $1.0\\%$ per tick in transit.  
  * If `health_score` drops to $0\\%$, the cargo is programmatically destroyed (set to $0$), and the agent incurs a $\\$50$ bio-hazard cleanup penalty to its local ledger.

## **2\. The Deterministic Execution Engine & Tick Pseudocode**

To avoid race conditions and ensure reproducible evolutionary runs, the simulation divorces itself from wall-clock time. Time advances in strictly controlled increments. The simulation orchestrator runs the following deterministic loop.

### **2.1 The Engine Pseudocode**

```
def run_simulation(total_ticks=500):
    for T in range(1, total_ticks + 1):
        
        # ---------------------------------------------------------
        # A. META-OPTIMIZER INTERVENTION (Every 25 Ticks)
        # ---------------------------------------------------------
        if T % 25 == 0:
            global_digest = build_global_digest()
            # The global simulation freezes here. 
            # We wait for the synchronous LLM call to complete.
            director_tool_calls = call_meta_optimizer_llm(global_digest)
            apply_director_mutations(director_tool_calls)

        # ---------------------------------------------------------
        # B. PROGRAMMATIC EDGE AGENT UPDATES
        # ---------------------------------------------------------
        exceptions_this_tick = []
        
        for agent in active_agents:
            # 1. Mandatory Upkeep & Physics
            agent.ledger -= 5.0
            if agent.cargo > 0:
                agent.cargo_health -= 1.0
                if agent.cargo_health <= 0.0:
                    agent.cargo = 0
                    agent.ledger -= 50.0  # Spoilage penalty
            
            # 2. State Machine Execution
            if agent.state == 'EXECUTING_OVERRIDE':
                agent.step_override_logic()
                continue
                
            elif agent.state == 'AUTOPILOT':
                try:
                    # step_a_star moves the agent 1 tile and updates coordinates
                    agent.step_a_star() 
                    agent.check_for_passive_tripwires() # Checks for Market shocks nearby
                except EdgeException as e:
                    # Agent hit a tripwire. Catch the exception.
                    exceptions_this_tick.append((agent, e))
            
            elif agent.state == 'THINKING':
                # Agent hit an exception on a previous tick and is awaiting LLM.
                pass 
                
        # ---------------------------------------------------------
        # C. LOCAL EXCEPTION RESOLUTION (Concurrent LLM Batching)
        # ---------------------------------------------------------
        if exceptions_this_tick:
            llm_futures = []
            
            for agent, exception_data in exceptions_this_tick:
                agent.state = 'THINKING'
                prompt = agent.build_context_prompt(exception_data)
                # Dispatch async LLM call
                llm_futures.append(call_edge_agent_llm_async(prompt, agent.persona_traits))
            
            # The global clock halts here. We await all Edge Agents concurrently.
            # Time cost: < 5 seconds wall-clock time. 0 ticks elapsed.
            llm_results = asyncio.run(asyncio.gather(*llm_futures))
            
            # Apply decisions and penalize exactly 1 Tick of "Thinking time"
            for agent, action_tool in zip([a for a, e in exceptions_this_tick], llm_results):
                agent.ledger -= 5.0 # The 1-tick time penalty for thinking
                agent.cargo_health -= 1.0
                agent.queued_override = action_tool
                agent.state = 'EXECUTING_OVERRIDE'

        # ---------------------------------------------------------
        # D. NODE UPDATES
        # ---------------------------------------------------------
        for node in environment_nodes:
            node.tick_logic() # Suppliers generate stock, Warehouses charge rent, etc.
```

## **3\. The Edge Agents (Local Execution Layer)**

Edge Agents operate a Finite State Machine (FSM): `AUTOPILOT` $\\rightarrow$ `THINKING` $\\rightarrow$ `EXECUTING_OVERRIDE`.

### **3.1 Exception Tripwires (Python Logic)**

An agent only enters the `THINKING` state if one of these exact conditions evaluates to `True` during the `try/except` block in the tick cycle:

1. **`PathImpassableException`:** The agent's pre-calculated `path_array` contains a coordinate whose state has changed to `obstacle`. A\* returns `None` for a reroute attempt.  
2. **`NodeRefusalException`:** The agent reaches distance $d=0$ to its target node. It calls `node.transfer_stock()`. The node returns `False` because `node.current_inventory >= node.max_capacity`.  
3. **`MarketShockException`:** The agent's `(x, y)` coordinate falls within radius $R=3$ of a Demand Zone where `current_price > 1.5 * base_price`.  
4. **`CargoCriticalException`:** The agent's cargo `health_score` drops below $15\\%$.  
5. **`GridlockException`:** An agent's `(x, y)` coordinate has not changed for 3 consecutive ticks, despite having a valid path (caused by agent-on-agent A\* collision blocks).

### **3.2 Action Space (JSON Tools Schema)**

When the LLM is invoked, it must return exactly one of these JSON function calls:

* `reroute(target_node_id: str)`: Generates a new A\* path to the specified node. Transitions back to `AUTOPILOT`.  
* `wait(ticks: int)`: Forces the agent to remain in its current cell for `ticks` duration, paying upkeep, before retrying its original action.  
* `liquidate_cargo(discount_percent: float)`: Deletes the current inventory locally, granting `(base_value * discount_percent)` to the ledger, freeing the truck's capacity.  
* `bribe_node(target_node_id: str, amount: float)`: Deducts `amount` from the agent's ledger. If `amount > node.bribe_threshold`, the node deletes older inventory to accept the agent's cargo.  
* `ignore()`: Dismisses a localized shock and resumes the original `AUTOPILOT` path.

### **3.3 Edge Agent System Prompt**

*Injected only when a local exception occurs.*

```
You are the autonomous navigation and trading brain for Transport Vehicle {agent_id}.
You operate within a 20x20 supply chain grid. 

YOUR GOAL: 
Maximize your individual ledger balance by delivering cargo while minimizing operating costs and delays.

GAME MECHANICS & PHYSICS:
- Upkeep: You pay $5 for every tick you exist. 
- Movement: Highways cost $1/tick. Off-road costs $3/tick.
- Time Penalty: You have encountered an exception. Making this decision will cost you exactly 1 Tick of time and $5 in upkeep.
- Exceptions: Your programmatic autopilot has failed. You must choose a manual override action.

YOUR BEHAVIORAL TRAITS (Assigned by the Meta-Optimizer):
- Risk Tolerance: {trait_risk}
- Greed vs Reliability: {trait_greed}
*You MUST roleplay and base your strategic decisions heavily on these traits.*

YOUR ACTION SPACE (TOOLS):
You must resolve the exception by calling exactly one of these tools:
1. `reroute(target_node_id: str)`
2. `wait(ticks: int)`
3. `liquidate_cargo(discount_percent: float)`
4. `bribe_node(target_node_id: str, amount: float)`
5. `ignore()`

Failure to use a tool, or hallucinating a tool, will result in an automatic 5-tick penalty.
```

### **3.4 Edge Agent Context Prompt (Dynamic)**

*Appended to the System Prompt, populated with live Python state.*

```
CURRENT STATUS:
- Current Tick: {current_tick}
- Grid Position: ({x}, {y})
- Ledger Balance: ${balance}
- Cargo: {cargo_amount}/50 units (Health: {health_score}%)
- Intended Destination: {target_node}

🚨 EXCEPTION TRIGGERED: {exception_type}
{exception_details}

LOCAL RADAR (Entities within 5 cells):
{local_entities_list_formatted}

TASK:
Analyze the exception, review your local radar, apply your behavioral traits, and execute exactly ONE tool call.
```

## **4\. The Meta-Optimizer (Global Director Layer)**

Every 25 ticks, the LangGraph orchestrator runs the `director_intervention` node.

### **4.1 Action Space (JSON Tools Schema)**

The Meta-Optimizer may return an array of zero or more tool calls.

* `build_infrastructure(node_type: str, x: int, y: int)`: Valid types: `Micro_Fulfillment` (Costs $\\$5,000$, Capacity 100), `Mega_Warehouse` (Costs $\\$20,000$, Capacity 500), `Toll_Road` (Costs $\\$1,000$, changes one grid cell to `highway`).  
* `mutate_persona(group_id: str, trait: str, new_value: str)`: Valid traits: `Risk_Tolerance`, `Greed`. Valid values: `Low`, `Medium`, `High`. Cost: $\\$0$.  
* `spawn_fleet(count: int, start_node_id: str)`: Spawns `count` Edge Agents. Cost: $\\$2,000$ per truck.  
* `adjust_incentives(node_id: str, price_mod: float)`: Multiplies a node's baseline payout by `price_mod` (e.g., $1.5$). Cost: $\\$0$ upfront, but drains global GLS faster when Edge Agents deliver there.

### **4.2 Meta-Optimizer System Prompt**

*Injected every 25 ticks.*

```
You are the Meta-Optimizer, the global orchestrator of a real-time, 20x20 grid-based supply chain simulation.
The simulation is currently PAUSED. You must analyze the global digest and execute structural changes.

YOUR OBJECTIVE:
Maximize the Global Liquidity Score (GLS) over the 500-tick episode.
GLS = Total Fulfullment Revenue - (CapEx + OpEx + Penalties)

GAME MECHANICS & PHYSICS:
1. The Environment: A 20x20 continuous grid. Moving across highways costs $1/tick. Off-road terrain costs $3/tick.
2. Nodes (Fixed & Mutable):
   - Suppliers: Generate raw cargo. (Fixed)
   - Warehouses: Buffer inventory with strict capacity limits. Charge $2/tick holding fees. (Mutable: You can build more).
   - Demand Zones: Consume inventory. Unfulfilled demand generates stacking cash penalties. (Fixed)
3. Edge Agents (Trucks):
   - Capacity: 50 units. 
   - Upkeep: $5/tick just to exist, plus movement costs.
   - Behavior: Agents operate on programmatic A* routing but utilize an LLM brain during exceptions. Their decisions are governed by their Persona Traits.

YOUR ACTION SPACE (TOOLS):
You may call one or more of the following tools to evolve the simulation:
1. `build_infrastructure(type: str, x: int, y: int)`
2. `mutate_persona(group_id: str, trait: str, new_value: str)`
3. `spawn_fleet(count: int, start_node_id: str)`
4. `adjust_incentives(node_id: str, price_mod: float)`

INSTRUCTIONS:
1. Review the CURRENT GLOBAL DIGEST below.
2. Identify gridlock, stockouts, or capital inefficiencies.
3. Output your strategy strictly by invoking the provided JSON tools. You may invoke multiple tools. If the network is healthy, you may choose to output no tools and save your capital.
```

### **4.3 Meta-Optimizer Context Prompt (Dynamic)**

*Appended to the System Prompt, populated with aggregated global state.*

```
CURRENT GLOBAL DIGEST:
- Current Tick: {current_tick} / 500
- GLS: ${gls_score} (Trend: {gls_trend_percentage}% since last intervention)
- Active Fleet: {fleet_count} trucks
- Available Capital: ${capital_remaining}

SYSTEM BOTTLENECKS & ALERTS:
{global_alerts_list_formatted}

FLEET PERSONA STATES:
{fleet_profiles_formatted}

TASK:
Deploy capital, mutate agent psychology, or adjust economic incentives to clear bottlenecks and maximize GLS. Output your structured JSON tool calls now.
```

## **5\. Implementation Specifications**

1. **Strict Validation:** All LLM outputs must be parsed using `pydantic` schemas. If the Meta-Optimizer hallucinates coordinates out of bounds (e.g., $x=25$), or the Edge Agent calls a non-existent tool, the orchestrator catches the `ValidationError`, docks the agent/system a programmatic penalty (e.g., 5 ticks lost, or $\\$500$ fine), and forces a default programmatic behavior (e.g., `wait(5)`) rather than crashing the simulation.  
2. **Concurrency Validation:** The `asyncio.gather()` block in the tick engine ensures that even if 15 trucks hit exceptions simultaneously, the system awaits all API calls concurrently before advancing to the next tick, ensuring zero race conditions.  
3. **State Management:** The LangGraph state schema holds `environment_grid` (2D array), `agents` (dict of FSM objects), `nodes` (dict of node objects), and `metrics` (dict of running totals). The Meta-Optimizer intervention explicitly mutates this state dictionary before passing it back to the loop.

