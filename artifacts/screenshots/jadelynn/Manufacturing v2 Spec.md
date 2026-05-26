# **Manufacturing Simulation: Inter-Episode Evolutionary Architecture (v2.0)**

This document serves as the technical specification for the Manufacturing Factory simulator. This is a high-speed, fully programmatic, multi-agent environment.

The optimization is handled via **Inter-Episode Evolution**: The LLM Meta-Optimizer seeds a "Factory Genome", the simulation engine runs that genome across a mini-batch of stochastic episodes (e.g., 1,000 ticks each) in milliseconds, and the LLM evaluates the aggregated results to architect the next generation.

## **1\. Global Simulation Mechanics & Physics**

The factory operates on a continuous programmatic tick loop over a discrete grid.

### **1.1 The Spatial Grid & Entities**

* **Dimensions:** A $12 \\times 12$ discrete grid.  
* **Cell Types:** floor (walkable), wall (unwalkable), machine\_slot (unwalkable, interaction point), loading\_dock, shipping\_dock.  
* **Programmatic Agents:** Agents calculate A\* paths to execute macro-goals (e.g., deliver\_to\_machine).

### **1.2 The Fixed Factory Floorplan**

Because the LLM is optimizing parameters and agent counts, the physical layout of the grid is fixed to provide a consistent control variable across episodes.

```

 0 1 2 3 4 5 6 7 8 9 0 1
0 W W W W W W W W W W W W
1 L . . . . . . . . . . W
2 L . [SML] . [STP] . . W
3 L . . . . . . . . . . W
4 W . . . . . . . . . . S
5 W . [FAB] . [ASM] . . S
6 W . . . . . . . . . . S
7 W . . . . . [Q_C] . . W
8 W . . . . . . . . . . W
9 W . . . . . [PKG] . . W
0 W . . . . . . . . . . W
1 W W W W W W W W W W W W

KEY:
W: Wall          L: Loading Dock (Buy Raw Materials)
S: Shipping Dock [MCH]: 2x1 Machine Slots
.: Floor         

```

* **Machine Coordinates (Interaction Points are adjacent floor tiles):**  
  * Smelter \[SML\]: (2,2), Stamping \[STP\]: (6,2)  
  * Circuit Fab \[FAB\]: (2,5), Assembly \[ASM\]: (6,5)  
  * QC Station \[Q\_C\]: (6,7), Packaging \[PKG\]: (6,9)

### **1.3 The Production DAG (Directed Acyclic Graph)**

Machines process items over time. They are strictly governed by the genome's speed multipliers, which affect processing time, power draw, and stochastic failure rates.

*Each machine has an input\_buffer (max 5\) and an output\_buffer (max 5).*

| Machine | Inputs | Output | Base Time | Base Power | Base Fail Rate | Reject Rate |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| **Smelter** | 2x Raw Ore | 1x Ingot | 4 ticks | $2.0/tick | 3% | 5% |
| **Circuit Fab** | 1x Raw Silicon | 1x Circuit | 5 ticks | $3.0/tick | 3% | 5% |
| **Stamping Press** | 1x Ingot | 1x Stamped Part | 3 ticks | $3.0/tick | 2% | 3% |
| **Assembly** | 2x Part \+ 1x Circuit | 1x Subassembly | 6 ticks | $4.0/tick | 2% | 4% |
| **QC Station** | 1x Subassembly | 1x Inspected Unit | 2 ticks | $1.0/tick | 1% | 8% (Rejects) |
| **Packaging** | 1x Inspected Unit | 1x Finished | 2 ticks | $1.0/tick | 1% | 1% |

**Speed Multipliers (Set by Genome):**

* low: Time $= 1.5\\times$, Power $= 0.5\\times$, Fail Rate $= 0.5\\times$  
* normal: Time $= 1.0\\times$, Power $= 1.0\\times$, Fail Rate $= 1.0\\times$  
* high: Time $= 0.6\\times$, Power $= 2.0\\times$, Fail Rate $= 2.5\\times$

### **1.4 Economic Physics (The Ledger)**

* **Revenues:**  
  * Standard Finished Product: $+\\$200.0$  
  * Rush Order (20% stochastic probability): $+\\$300.0$  
  * Scrap (Selling QC Rejects): $+\\$5.0$  
* **Expenses (OpEx):**  
  * Raw Materials: Ore ($\\$10$), Silicon ($\\$15$).  
  * Agent Wages: Deducted every tick based on role (e.g., Engineering is $5/tick, Operations is $2/tick).  
  * Power Costs: Calculated per machine while actively processing.  
* **Penalties:**  
  * Late Delivery: $-\\$20.0$ per tick past the customer deadline.  
  * Missed Order: $-\\$50.0$ flat penalty if the order expires entirely.

## **2\. The Deterministic Engine & Agent State Machines**

Because this environment is heavily multi-agent, A\* deadlocks and task assignments must be solved programmatically to allow the simulation to run unattended.

### **2.1 Programmatic Agent Logic (Task Allocation)**

Agents operate on a strict localized state machine. Every tick an agent is IDLE, it scans the grid for its designated job type.

* **Procurement Agents (Wage $3):**  
  * *Scan:* Finds Smelter or Circuit Fab where input\_buffer \< 5.  
  * *Action:* Path to Loading Dock $\\rightarrow$ Buy required raw material $\\rightarrow$ Path to Machine $\\rightarrow$ Deposit in input\_buffer.  
* **Operations Agents (Wage $2):**  
  * *Scan:* Finds any machine where output\_buffer \> 0.  
  * *Action:* Path to Machine $\\rightarrow$ Pick up output $\\rightarrow$ Determine next DAG machine (e.g., Ingot goes to Stamping Press) $\\rightarrow$ Path to next machine $\\rightarrow$ Deposit in input\_buffer.  
  * *Scrap Exception:* If the picked-up item is a Reject from QC, path to Shipping Dock to sell as scrap.  
* **Engineering Agents (Wage $5):**  
  * *Scan:* Finds any machine where state \== 'BROKEN'.  
  * *Action:* Path to Machine $\\rightarrow$ Enter WORKING state for 10 ticks $\\rightarrow$ Set machine state to IDLE (Fixed).  
* **Sales Agents (Wage $4):**  
  * *Scan:* Finds Packaging where output\_buffer \> 0 AND a Customer Order exists in the queue.  
  * *Action:* Path to Packaging $\\rightarrow$ Pick up Finished Product $\\rightarrow$ Path to Shipping Dock $\\rightarrow$ Fulfill Customer Order.

### **2.2 Deadlock-Free Execution Loop & Pseudocode**

```

def run_episode(genome_config, seed, total_ticks=1000):
    env = Environment(seed=seed)
    env.apply_genome(genome_config)
    
    for T in range(1, total_ticks + 1):
        
        # 1. Stochastic Event Generation
        env.generate_customer_orders(genome_config.order_arrival_rate)
        env.roll_machine_failures() 
        
        # 2. Agent Execution & MAPF (Multi-Agent Pathfinding) Resolution
        # Sort agents by hardcoded hierarchy to resolve ties (Sales > Eng > Proc > Ops)
        active_agents = sorted(env.agents, key=lambda a: a.priority, reverse=True)
        
        for agent in active_agents:
            env.ledger -= agent.wage
            
            # Agent Task Assignment
            if agent.state == 'IDLE':
                task = agent.find_job(env.grid, env.machines)
                if task:
                    agent.assign_task(task) # Generates A* Path Array
                    
            if agent.state == 'MOVING':
                next_cell = agent.path[0]
                
                # Dynamic Collision Check
                occupying_agent = env.get_agent_at(next_cell)
                if occupying_agent:
                    # LOCAL MAPF RESOLUTION: Right-of-Way Rule
                    if agent.priority > occupying_agent.priority:
                        # High priority forces lower priority to yield or swap
                        if occupying_agent.state == 'IDLE':
                            occupying_agent.shove_to_adjacent_empty_cell(env.grid)
                            agent.step_forward()
                        else:
                            agent.wait() # Yield for 1 tick if the other is actively moving
                    else:
                        agent.wait() # Lower priority always yields
                else:
                    agent.step_forward()
            
            elif agent.state == 'WORKING':
                agent.execute_micro_action(env) # Load machine, fix machine, buy stock

        # 3. Machine Ticking
        for machine in env.machines:
            if machine.state == 'PROCESSING':
                env.ledger -= machine.power_cost
                machine.progress += 1
                if machine.progress >= machine.target_time:
                    machine.finish_product()
                # Stochastic Failure check while running
                if env.random.random() < machine.fail_rate:
                    machine.state = 'BROKEN'
                    
        # 4. Check Customer Order Expirations
        env.process_order_penalties()
                    
    return env.calculate_fitness_metrics()

```

## **3\. The Evolutionary Loop & Fitness Vector**

To prevent the LLM from over-optimizing for a single lucky sequence of rush orders or a lack of machine failures, the LangGraph orchestrator utilizes **Mini-Batch Evaluation**.

### **3.1 The Mini-Batch Strategy**

Every generation, the LangGraph orchestrator runs the provided genome exactly $3$ times using fixed stochastic seeds (e.g., \[42, 101, 777\]). The resulting fitness vectors are averaged before being presented to the Meta-Optimizer.

### **3.2 The Fitness Calculation**

The final score evaluated by the LLM is a dot product of weights $\\vec{w}$ and the averaged metrics vector $\\vec{f}$.

$$\\vec{f} \= \\begin{bmatrix} \\text{Profit}, \\text{Throughput}, \\text{Missed Rate}, \\text{Idle Ratio}, \\text{Machine Util} \\end{bmatrix}$$  
$$\\vec{w} \= \\begin{bmatrix} 0.50, 0.30, \-0.15, \-0.05, \+0.05 \\end{bmatrix}$$  
$$\\text{Fitness} \= \\vec{w} \\cdot \\vec{f}$$

## **4\. The Meta-Optimizer (LLM) Layer**

Between generations, the LLM ingests the averaged results of the mini-batch and mutates the factory's structural parameters via strict Pydantic-validated tool calls.

### **4.1 Action Space (The Genome Tools)**

The LLM output is strictly forced into an overarching mutate\_genome tool schema, directly mapping to the simulation config.

| Parameter Axis | Valid Boundaries | Description |
| :---- | :---- | :---- |
| procurement\_count | 1 to 5 | How many agents ferry raw materials. |
| operations\_count | 1 to 8 | How many agents ferry items between machines. |
| engineering\_count | 1 to 3 | How many agents repair broken machines. |
| sales\_count | 1 to 4 | How many agents deliver finished products. |
| machine\_speeds | Dict \[str, str\] | IDs map to exactly "low", "normal", or "high". |
| order\_arrival\_rate | 5.0 to 30.0 | Ticks between new customer orders (lower \= faster). |

### **4.2 The Meta-Optimizer System Prompt**

```

You are the Factory Meta-Optimizer, an AI architect managing a continuous manufacturing simulation.
The simulation operates on a fixed 12x12 spatial grid. 
Your goal is to maximize the overall Fitness Score over a mini-batch of stochastic episodes (1000 ticks each).

FITNESS TARGET & ECONOMICS:
The final Fitness Score is a weighted calculation: 
(50% Profit) + (30% Throughput) - (15% Missed Orders) - (5% Idle Agents) + (5% Machine Util).
- Revenues: Standard Product (+$200), Rush Order (+$300), Scrap (+$5).
- OpEx: Agent Wages (Eng: $5/t, Sales: $4/t, Proc: $3/t, Ops: $2/t), Material Costs, Machine Power.
- Penalties: Late Delivery (-$20/t), Missed Order (-$50 flat).

THE PRODUCTION DAG:
1. Raw Ore -> Smelter -> Ingot
2. Raw Silicon -> Circuit Fab -> Circuit
3. Ingot -> Stamping Press -> Stamped Part
4. (Stamped Part x2 + Circuit x1) -> Assembly -> Subassembly
5. Subassembly -> QC Station -> Inspected Unit
6. Inspected Unit -> Packaging -> Finished Product

PHYSICS & TRADEOFFS:
- Agents physically move items on the grid. 
- Too many agents = pathfinding traffic jams and bloated wage costs. 
- Too few agents = idle machines and supply chain bottlenecks.
- Speed Multipliers: 'low' (slow, cheap, reliable), 'normal', 'high' (fast, 2x power cost, 2.5x fail rate).
- High failure rates require more Engineering agents to repair broken machines, draining wages.

YOUR ACTION SPACE (`mutate_genome` tool):
You must output a single JSON tool call setting the ENTIRE genome for the next generation.
1. Agent Counts: `procurement` (1 to 5), `operations` (1 to 8), `engineering` (1 to 3), `sales` (1 to 4).
2. Machine Speeds: Must map all 6 machine IDs ('Smelter', 'Circuit Fab', 'Stamping Press', 'Assembly', 'QC Station', 'Packaging') to either "low", "normal", or "high".
3. Order Arrival Rate: (5.0 to 30.0). A lower number means orders arrive faster. WARNING: Accepting too many orders if your factory pipeline is slow will cause catastrophic Late/Missed penalties.

```

### **4.3 The Dynamic Context Prompt (Episode Digest)**

*Injected at the start of each new generation.*

```

GENERATION {generation_id} RESULTS:
The previous genome was evaluated across 3 stochastic episodes (1000 ticks each). 

PREVIOUS GENOME:
- Procurement: {prev_proc}, Operations: {prev_ops}, Engineering: {prev_eng}, Sales: {prev_sales}
- Speeds: Smelter [{smelt_spd}], Assembly [{asm_spd}], Packaging [{pkg_spd}] ...
- Intake Rate: 1 order every {prev_rate} ticks.

AVERAGED METRICS:
- Overall Fitness Score: {fitness_score}
- Average Profit: ${avg_profit}
- Order Fulfillment Rate: {fulfill_rate}% (Missed Orders: {avg_missed})
- Agent Idle Ratios: Ops ({ops_idle}%), Eng ({eng_idle}%)
- Average Machine Downtime: {downtime_pct}%

ANALYSIS REQUEST:
Analyze the bottlenecks in the metrics above. 
If Engineering is 90% idle but Downtime is low, fire an engineer to save wages.
If the Fulfillment Rate is 40% with high missed orders, the intake rate is too aggressive or your bottleneck machines are too slow.
Output your complete, modified genome via tool call now.

```

## **5\. Implementation Safeties**

1. **Strict Pydantic Validation:** The LangGraph orchestrator forces the LLM output through a Pydantic BaseModel that mirrors the GenomeConfig dataclass in Python.  
2. **Auto-Retry Loop:** If the LLM hallucinates a string like "super-fast" for a machine speed, Pydantic throws a ValidationError. The LangGraph edge catches this, increments a retry\_count, and feeds the exact error string back to the LLM ("Error: machine\_speeds must be 'low', 'normal', or 'high'. Try again."), ensuring the automated loop never crashes.  
3. **Stagnation Break:** If the LLM's proposed genome scores lower than the previous generation for 3 consecutive generations, the LangGraph orchestrator injects a programmatic mutation (randomly altering one parameter by 20%) to force the LLM out of a local minimum.

