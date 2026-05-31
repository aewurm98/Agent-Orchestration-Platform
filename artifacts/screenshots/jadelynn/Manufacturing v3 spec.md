# **Architectural Specification: Manufacturing v3.0**

## **Topological Flow, Policy Optimization & Meta-Evolution**

## **1\. Executive Summary & Design Philosophy**

Manufacturing v3.0 abandons spatial grid physics and discrete multi-agent pathfinding in favor of a **Topological Flow Graph**. The factory is modeled as a network of processing nodes (Machines) connected by logistics edges (Conveyors).

The LLM Meta-Optimizer no longer micromanages agent coordinates or hires individuals. Instead, it acts as a true Executive Architect, setting global machine capacities, logistics bandwidths, maintenance policies, and order intake rates. This abstracts away trivial physical collisions, allowing the evolutionary algorithm to cleanly optimize supply chain mathematics (queuing theory, bottleneck resolution, and throughput) across episodic generations.

## **2\. Factory Topology (The Directed Acyclic Graph)**

The production pipeline is flattened into a highly readable, 3-stage graph.

### **2.1 The Nodes (Machines)**

* **Stage 1A: Molding Station** (Consumes 1 Raw Plastic \-\> Produces 1 Molded Casing)  
* **Stage 1B: Wire Drawing** (Consumes 1 Raw Copper \-\> Produces 1 Spool)  
* **Stage 2: Assembly** (Consumes 1 Molded Casing \+ 1 Spool \-\> Produces 1 Unverified Unit)  
* **Stage 3: QA & Packaging** (Consumes 1 Unverified Unit \-\> Produces 1 Finished Good)

### **2.2 The Edges (Logistics / Conveyors)**

Edges represent the transport bandwidth between nodes. They dictate how many items can move from an output queue to an input queue per tick.

* `Edge 1`: Inbound Docks \-\> Molding  
* `Edge 2`: Inbound Docks \-\> Wire Drawing  
* `Edge 3`: Molding \-\> Assembly  
* `Edge 4`: Wire Drawing \-\> Assembly  
* `Edge 5`: Assembly \-\> QA & Packaging  
* `Edge 6`: QA & Packaging \-\> Outbound Docks (Sink)

## **3\. Physics, Flow, and Execution Mechanics**

To prevent catastrophic penalty cliffs that cause LLM "quiet quitting," failure is handled via time delays rather than material destruction. The environment must strictly follow this deterministic update loop.

### **3.1 Order Generation & Inbound Sourcing**

* **Order Mapping:** The genome parameter `order_intake_rate` represents the total target orders per 500-tick episode.  
* **Spawning Math:** The engine calculates `ticks_per_order = 500 / order_intake_rate`. Every `ticks_per_order` ticks, the system:  
  1. Increments the `Active Orders` tracker.  
  2. Instantly deposits 1 Raw Plastic into the `Inbound Docks -> Molding` edge source.  
  3. Instantly deposits 1 Raw Copper into the `Inbound Docks -> Wire Drawing` edge source.

### **3.2 Processing Logic & Queuing**

* **Continuous Batching:** Machines process up to their `capacity` limit per tick.  
* **Queues:** Every Node maintains an `input_queue` (holding raw materials/sub-components) and an `output_queue` (holding processed goods).  
* **Processing Delay:** Processing a batch takes exactly **2 ticks**. A node cannot accept new inputs into its processing core until the current batch finishes and drops into the `output_queue`.

### **3.3 Soft Degradation (Machine Breakdowns)**

Instead of destroying WIP materials, a breakdown causes a Node to enter a `DOWN` state.

* **Failure Condition:** Breakdowns only roll when a machine is actively processing (not idle).  
* **Repair Time:** A broken machine remains `DOWN` for exactly **15 ticks**. Materials remain safely frozen in their current queues.  
* **Probabilities:** Breakdown frequency is governed by the `maintenance_policy`:  
  * `low`: 2.0% chance to break down per active processing tick.  
  * `medium`: 0.5% chance to break down per active processing tick.  
  * `high`: 0.05% chance to break down per active processing tick.

### **3.4 The `tick()` Execution Loop**

To prevent race conditions, the engine must execute the following sequence every tick:

1. **Spawn Orders:** Check if `current_tick % ticks_per_order == 0`. If yes, spawn raw materials at Inbound Docks.  
2. **Edge Transfers:** For every edge, move up to `bandwidth` items from the source node's `output_queue` to the destination node's `input_queue`. (For Outbound Docks, items are removed and counted as `Orders Fulfilled`).  
3. **Machine Processing:** For every node:  
   * If `DOWN`, decrement repair timer. If 0, state becomes `IDLE`.  
   * If `PROCESSING`, decrement process timer. If 0, move batch to `output_queue`, state becomes `IDLE`.  
   * If `IDLE`, roll for breakdown. If passed, pull up to `capacity` valid ingredient sets from `input_queue`, state becomes `PROCESSING`, set timer to 2\.  
4. **Metrics Collection:** Record instantaneous queue sizes, idle states, and OpEx costs for the digest.

## **4\. Economics & The CLEAR v3 Fitness Function**

The environment is evaluated over 500-tick episodes.

### **4.1 Financial Constants**

* **Finished Good Revenue:** \+$1,000 per unit shipped.  
* **Raw Material Cost:** \-$50 per Plastic, \-$50 per Copper.  
* **Missed Order Penalty:** \-$200 flat fee for orders not fulfilled by the 500-tick deadline.

### **4.2 Operational Expenditures (OpEx)**

The genome dictates fixed per-tick costs. Higher capacities cost exponentially more, forcing the LLM to find efficient balances rather than simply maxing out all stats.

* **Machine Capacity Cost:** `$1.00 * (Capacity ^ 1.2)` per tick per machine.  
* **Edge Bandwidth Cost:** `$0.50 * (Bandwidth ^ 1.1)` per tick per edge.  
* **Maintenance Policy Cost:** \* `low`: $10/tick  
  * `medium`: $30/tick  
  * `high`: $80/tick

### **4.3 The Objective Function**

`Fitness = (Total Revenue) - (Total OpEx + Material Costs) - (Penalties)`

## **5\. The LLM Meta-Optimizer (Prompts & Schemas)**

The LLM operates on generation boundaries using a $(\\mu \+ \\lambda)$ Evolutionary Algorithm. It receives a digest containing the current bottleneck metrics, queue pileups, and historical trendlines, and generates multiple candidates for evaluation.

### **5.1 System Prompt**

```
You are the Factory Executive AI. Your objective is to optimize a continuous flow manufacturing graph to maximize overall Profit (Fitness).

THE FACTORY GRAPH (DAG):
- Nodes (Machines): [molding, wire_drawing, assembly, packaging]
- Edges (Logistics): Transport items between nodes.

ECONOMICS:
- Revenue: +$1000 per finished product.
- Penalties: -$200 per unfulfilled order at the end of the episode.
- Costs: High machine capacities and wide edge bandwidths incur massive exponential per-tick OpEx. Do not over-provision!
- Maintenance: 'low' is cheap but causes frequent downtime (delays). 'high' is expensive but ensures steady flow.

YOUR TASK:
Analyze the telemetry provided by the User. Look at the Queue sizes and Utilization rates to find bottlenecks. 
- If a machine's input queue is huge but its utilization is near 100%, it needs more capacity.
- If a machine's output queue is huge, the downstream edge bandwidth needs upgrading.
- If orders are being missed but the factory is mostly idle, increase the order_intake_rate.
- Do not increase capacities uniformly. Balance the flow to minimize OpEx waste.

OUTPUT FORMAT:
Return a JSON array containing exactly 3 distinct candidate configuration objects matching this schema. No markdown formatting, no conversational text.

[
  {
    "reasoning": "<1-2 sentence chain-of-thought diagnosing the primary bottleneck>",
    "machine_capacities": {
      "molding": <int 1-50>,
      "wire_drawing": <int 1-50>,
      "assembly": <int 1-50>,
      "packaging": <int 1-50>
    },
    "edge_bandwidths": {
      "in_to_molding": <int 1-50>,
      "in_to_wire": <int 1-50>,
      "molding_to_assembly": <int 1-50>,
      "wire_to_assembly": <int 1-50>,
      "assembly_to_packaging": <int 1-50>,
      "packaging_to_out": <int 1-50>
    },
    "maintenance_policy": "<low|medium|high>",
    "order_intake_rate": <int 1-100> 
  }
]
```

### **5.2 User Prompt (The Telemetry Digest)**

This dynamically generated prompt gives the LLM local Markovian state alongside a minimal history vector to deduce trendlines.

```
CURRENT FACTORY TELEMETRY (Episode length: 500 ticks)

1. HISTORICAL TREND (Last 3 Generations)
- Gen 10: Fitness = $45,200 | Throughput = 60 units | OpEx = $12,000
- Gen 11: Fitness = $51,100 | Throughput = 75 units | OpEx = $21,000
- Gen 12 (Current Baseline): Fitness = $48,300 | Throughput = 75 units | OpEx = $23,500

2. CURRENT EPISODE PERFORMANCE (Gen 12)
- Orders Received: 90
- Orders Fulfilled: 75
- Orders Missed: 15 (Penalty incurred)
- Total OpEx spent: $23,500

3. BOTTLENECK DIAGNOSTICS (Average over episode)
Nodes (Machines):
- molding:     Utilization = 30% | Avg Input Queue = 0.5 | Avg Output Queue = 0.2
- wire_drawing:Utilization = 25% | Avg Input Queue = 0.0 | Avg Output Queue = 0.1
- assembly:    Utilization = 98% | Avg Input Queue = 45.5| Avg Output Queue = 10.2  <-- WARNING: High Utilization
- packaging:   Utilization = 40% | Avg Input Queue = 0.2 | Avg Output Queue = 0.5

Edges (Logistics Transport Rates):
- in_to_molding: 10/tick
- in_to_wire: 10/tick
- molding_to_assembly: 15/tick
- wire_to_assembly: 15/tick
- assembly_to_packaging: 5/tick   <-- WARNING: Low Bandwidth Output
- packaging_to_out: 20/tick

4. CURRENT GENOME
{
  "machine_capacities": {"molding": 15, "wire_drawing": 15, "assembly": 8, "packaging": 20},
  "edge_bandwidths": {"in_to_molding": 10, "in_to_wire": 10, "molding_to_assembly": 15, "wire_to_assembly": 15, "assembly_to_packaging": 5, "packaging_to_out": 20},
  "maintenance_policy": "medium",
  "order_intake_rate": 90
}

Based on the Diagnostics, identify the current bottleneck, adjust the capacities to smooth the flow, and output the new JSON array of 3 candidates.
```

