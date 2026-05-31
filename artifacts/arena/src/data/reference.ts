// Developer reference content for the Arena platform.
//
// Two-tabbed structure:
//   • "Inside the Arena" — scenarios, agents, and run controls visible in the UI.
//   • "Build your own" — orchestrator internals, HTTP API, and extension points.
//
// Only items actually reachable from the Arena UI (or its underlying engine)
// are documented here — legacy/retired code is excluded.

export type Param = {
  name: string;
  type: string;
  default?: string;
  required?: boolean;
  /** Highlighted as something a developer is expected to tune. */
  customizable?: boolean;
  desc: string;
};

export type EntryKind =
  | "class"
  | "function"
  | "method"
  | "endpoint"
  | "event"
  | "config"
  | "enum";

export type Entry = {
  id: string;
  name: string;
  kind: EntryKind;
  /** Method+path for endpoints, or a call signature for functions. */
  signature?: string;
  /** Source file the symbol lives in. */
  module?: string;
  desc: string;
  params?: Param[];
  returns?: string;
  /** Callout describing what a developer would change here. */
  customize?: string;
};

export type Section = {
  id: string;
  title: string;
  blurb: string;
  entries: Entry[];
};

export type Tab = {
  id: string;
  label: string;
  /** Heading shown above the section list in the main content area. */
  introTitle: string;
  /** One-paragraph intro shown under the heading. */
  introBody: string;
  sections: Section[];
};

// ── UI tab entries ────────────────────────────────────────────────────────────

const SCENARIOS_SECTION: Section = {
  id: "scenarios",
  title: "Scenarios",
  blurb:
    "The simulation worlds available in the Arena's scenario dropdown. Each is a self-contained environment with its own evolvable parameters and fitness function.",
  entries: [
    {
      id: "scenarios-map",
      name: "SCENARIOS",
      kind: "config",
      module: "main.py",
      desc: "Registry mapping an internal scenario key to its environment class.",
      params: [
        { name: "supply_chain", type: "SupplyChainEnv", desc: "Supplier → warehouses → distributor → retail. EA maximizes the Global Logistics Score (GLS)." },
        { name: "manufacturing", type: "ManufacturingEnv", desc: "3-stage topological flow graph (Molding/Wire → Assembly → Packaging). The Arena's \"Manufacturing\" runs this." },
      ],
    },
    {
      id: "scenario-label-map",
      name: "SCENARIO_LABEL_MAP",
      kind: "config",
      module: "main.py",
      desc: "Maps user-facing UI labels to internal SCENARIOS keys — this is why the Arena's \"Manufacturing\" tab runs the manufacturing env.",
      params: [
        { name: "\"Supply Chain\"", type: "→ supply_chain", desc: "The supply-chain scenario." },
        { name: "\"Manufacturing\"", type: "→ manufacturing", desc: "Routes the UI label to the flow-graph env." },
      ],
    },
    {
      id: "supply-chain-env",
      name: "SupplyChainEnv",
      kind: "class",
      module: "game_envs/supply_chain.py",
      desc: "Supplier → warehouses → distributor → retail simulation. Fitness is the Global Logistics Score (GLS).",
      params: [
        { name: "step(_action=None)", type: "method", desc: "Advance one tick of the supply-chain sim." },
        { name: "get_fitness()", type: "method → float", desc: "Returns the current GLS." },
        { name: "apply_genome(genome_config)", type: "method", customizable: true, desc: "Apply an evolved genome (fleet_size, supply_rate, transfer_amount, warehouse_restock_threshold) before/at run start." },
        { name: "GENOME_DEFAULTS", type: "dict", customizable: true, desc: "Defaults the EA evolves — see the GENOME_DEFAULTS entry below." },
      ],
    },
    {
      id: "supply-chain-genome-defaults",
      name: "SupplyChainEnv.GENOME_DEFAULTS",
      kind: "config",
      module: "game_envs/supply_chain.py",
      desc: "The evolvable parameters for the supply-chain scenario, applied via apply_genome(). These are the real supply-chain levers evolution is tuning.",
      params: [
        { name: "fleet_size", type: "int", default: "3", customizable: true, desc: "Number of delivery trucks. Clamped to 1–10." },
        { name: "supply_rate", type: "int", default: "10 (SUPPLIER_GEN_UNITS)", customizable: true, desc: "Units the supplier generates per cycle." },
        { name: "transfer_amount", type: "int", default: "50 (TRUCK_CAPACITY)", customizable: true, desc: "Cargo moved per transfer." },
        { name: "warehouse_restock_threshold", type: "float", default: "0.5", customizable: true, desc: "Stock fraction at which a warehouse restocks. Clamped to 0.0–1.0." },
      ],
    },
    {
      id: "mfg-v3-env",
      name: "ManufacturingEnv",
      kind: "class",
      module: "game_envs/manufacturing/env.py",
      desc: "The Topological Flow Graph factory. A genome is supplied to the constructor; the run is deterministic given (genome, seed, length). This is the env the Arena's Manufacturing scenario evolves.",
      params: [
        { name: "__init__(genome, length, seed)", type: "constructor", customizable: true, desc: "Build the env from a ManufacturingGenome (or dict). length defaults to EPISODE_TICKS (500); a seeded RNG makes rollouts reproducible." },
        { name: "step()", type: "method", desc: "Advance exactly one tick (no action argument — the env is genome-driven)." },
        { name: "run(ticks=None)", type: "method → self", desc: "Run to completion (or `ticks` ticks); returns the env for chaining." },
        { name: "get_fitness()", type: "method → float", desc: "Scalar objective the EA maximizes (profit-based)." },
        { name: "get_fitness_vector()", type: "method → list[float]", desc: "Component breakdown behind the scalar fitness." },
        { name: "get_metrics()", type: "method → dict", desc: "Headline metrics: orders_received/fulfilled/missed, throughput, total_revenue, total_opex, total_material_cost, penalties, fitness, node_diagnostics, edge_flow." },
        { name: "to_json()", type: "method → dict", desc: "Frontend-friendly flow-graph snapshot (nodes, edges, economics, orders)." },
      ],
    },
    {
      id: "mfg-v3-genome",
      name: "ManufacturingGenome",
      kind: "class",
      module: "game_envs/manufacturing/genome.py",
      desc: "The genome the Manufacturing scenario evolves — machine capacities, conveyor bandwidths, a maintenance policy, and order intake. Values are clamped to bounds on construction.",
      params: [
        { name: "machine_capacities", type: "dict[str, int]", default: "5 each", customizable: true, desc: "Capacity per machine. Machines: molding, wire_drawing, assembly, packaging. Each clamped to 1–50." },
        { name: "edge_bandwidths", type: "dict[str, int]", default: "5 each", customizable: true, desc: "Bandwidth per conveyor edge (in_to_molding, in_to_wire, molding_to_assembly, wire_to_assembly, assembly_to_packaging, packaging_to_out). Each clamped to 1–50." },
        { name: "maintenance_policy", type: "\"low\" | \"medium\" | \"high\"", default: "\"medium\"", customizable: true, desc: "Trades maintenance cost against breakdown probability." },
        { name: "order_intake_rate", type: "int", default: "40", customizable: true, desc: "Customer order intake rate. Clamped to 1–100." },
      ],
      customize:
        "To build your own scenario, mirror this dataclass: bounded fields plus mutate(rng), from_dict(), and to_dict() so it round-trips through the EA and your env constructor. See the \"Build your own\" tab.",
    },
  ],
};

const AGENTS_SECTION: Section = {
  id: "agents",
  title: "Agents & Roles",
  blurb:
    "The agent roster behind each scenario — each role's system prompt and the tools it may call. These are what populate the agent ↔ tool topology view.",
  entries: [
    {
      id: "node-metadata",
      name: "NODE_METADATA",
      kind: "config",
      module: "main.py",
      desc: "Per-role definition: each entry has a system_prompt and a list of callable tool names. The roles in play today:",
      params: [
        { name: "orchestrator", type: "role", customizable: true, desc: "Master delegator. Tools: plan_subtasks, assign_agent, merge_results, escalate_hitl." },
        { name: "evaluator", type: "role", customizable: true, desc: "Scorer. Tools: score_output, compute_fitness, flag_anomaly." },
        { name: "worker_1 / worker_2", type: "role", customizable: true, desc: "Generic workers. Tools: query_env, act_in_env, report_result (worker_2 also request_clarification)." },
        { name: "supply_agent", type: "role", customizable: true, desc: "Supply brain. Tools: check_stock, place_order, forecast_demand." },
        { name: "demand_agent", type: "role", customizable: true, desc: "Demand brain. Tools: read_demand, reroute_shipment, update_forecast." },
        { name: "planner_1", type: "role", customizable: true, desc: "Pipeline planner. Tools: query_pipeline_status, query_worker_status, reallocate_materials, set_production_target, dispatch_order, broadcast_to_stage, approve_release, escalate." },
        { name: "worker_raw_materials / worker_intermediates / worker_finished_product", type: "role", customizable: true, desc: "Stage operators. Tools: process_batch, inspect_input, request_replenishment, report_issue, rework_output, idle." },
      ],
      customize:
        "Change behavior with no code: rewrite a role's `system_prompt`. Change capability: add/remove tool names (and implement the matching handler).",
    },
  ],
};

const CONTROLS_SECTION: Section = {
  id: "controls",
  title: "Run controls",
  blurb:
    "The selectors set before starting a run — the agent mode that proposes candidates and the way generations are bounded in time.",
  entries: [
    {
      id: "mutation-engine",
      name: "Agent mode",
      kind: "enum",
      module: "main.py",
      desc: "Selects how candidates are proposed each generation. Set in the Arena's mode dropdown; sent as `engine` (canonical) or `mutation_strategy` (legacy alias) to POST /api/scenario/start. The default is ARENA_DEFAULT_ENGINE (\"MATH\").",
      params: [
        { name: "MATH", type: "mode", customizable: true, desc: "Fast heuristic — bounds-checked perturbations via the genome's own mutate() (math_candidates)." },
        { name: "LLM", type: "mode", customizable: true, desc: "An LLM reads an episode digest and proposes candidate genomes with reasoning (query_candidates); falls back to MATH on any failure." },
        { name: "DEAP", type: "mode", customizable: true, desc: "Accepted by the API, but currently falls back to heuristic perturbation — no distinct operator wired in yet." },
      ],
    },
    {
      id: "boundary-mode",
      name: "Boundary mode",
      kind: "enum",
      module: "main.py · agents/orchestrator.py",
      desc: "Controls how a generation is bounded in time. Passed as `boundary_mode` to POST /api/scenario/start and stored on ArenaState.",
      params: [
        { name: "INTRA", type: "mode", customizable: true, desc: "Continuous, tick-by-tick evolution within a single rollout." },
        { name: "INTER", type: "mode", customizable: true, desc: "Episodic — run inter_ticks ticks per generation." },
      ],
    },
  ],
};

// ── API tab entries ───────────────────────────────────────────────────────────

const ORCHESTRATOR_SECTION: Section = {
  id: "orchestrator",
  title: "Orchestrator",
  blurb:
    "The LangGraph state machine that runs a scenario for N generations: intake → init topology → agent step → evaluate → gate → propose → checkpoint. Drive it directly to build custom run loops.",
  entries: [
    {
      id: "run-orchestrator",
      name: "run_orchestrator",
      kind: "function",
      signature: "async run_orchestrator(scenario, run_id, max_generations=5) → dict",
      module: "agents/orchestrator.py",
      desc: "Initialize an episode and run the full evolutionary loop for up to max_generations. Streams state over the socket as it goes.",
      params: [
        { name: "scenario", type: "str", required: true, desc: "A key from SCENARIOS (e.g. \"manufacturing\")." },
        { name: "run_id", type: "str", required: true, desc: "Unique id used for streaming, traces, and checkpoints." },
        { name: "max_generations", type: "int", default: "5", customizable: true, desc: "How many evolutionary generations to run before stopping." },
      ],
      returns: "Final run state dict (best genome, accepted fitness, history).",
    },
    {
      id: "run-one-generation",
      name: "run_one_generation",
      kind: "function",
      signature: "async run_one_generation(existing_state: dict) → dict",
      module: "agents/orchestrator.py",
      desc: "Run a single LangGraph generation cycle from agent_step onward. Useful for stepping the loop externally.",
      params: [
        { name: "existing_state", type: "dict (ArenaState)", required: true, desc: "The mutable generation context to advance." },
      ],
      returns: "The updated state dict after one generation.",
    },
    {
      id: "arena-state",
      name: "ArenaState",
      kind: "class",
      module: "agents/orchestrator.py",
      desc: "TypedDict carrying the full mutable context of a run between LangGraph nodes. Selected real fields:",
      params: [
        { name: "scenario", type: "str", desc: "Active scenario key." },
        { name: "agent_configs", type: "list[dict]", customizable: true, desc: "Active agent composition for this generation." },
        { name: "topology", type: "dict", customizable: true, desc: "Agent ↔ tool connection graph (nodes + edges)." },
        { name: "edge_scores", type: "dict[str, float]", desc: "Credit-assignment scores per inter-agent edge." },
        { name: "current_fitness / parent_fitness / accepted_fitness", type: "float", desc: "Child, parent, and best-retained (elitism) fitness." },
        { name: "genome_config", type: "dict", customizable: true, desc: "Scenario-specific parameters evolution searches over." },
        { name: "boundary_mode", type: "str (INTRA | INTER)", customizable: true, desc: "How generations are bounded — see Boundary mode." },
        { name: "mutation_strategy", type: "str (MATH | LLM | DEAP)", customizable: true, desc: "Which agent mode drives candidate proposal." },
        { name: "inter_ticks", type: "int", customizable: true, desc: "Episode length in INTER mode." },
        { name: "stagnation_counter / fitness_history", type: "int / list[float]", desc: "Generations without improvement, and the fitness curve." },
      ],
      customize:
        "The graph nodes — goal_intake, topology_init, agent_step, evaluate, gate, propose, checkpoint — can be reordered or replaced to change the control flow.",
    },
    {
      id: "edge-scores",
      name: "Edge-score helpers",
      kind: "function",
      signature: "init_edge_scores(scores) · sweep_edge_scores(tick)",
      module: "agents/manufacturing_roles.py",
      desc: "Maintain the inter-agent credit-assignment scores: init_edge_scores(scores) seeds the score table; sweep_edge_scores(tick) decays/updates it as the run progresses.",
    },
  ],
};

const EVOLUTION_SECTION: Section = {
  id: "evolution",
  title: "Evolution mechanics",
  blurb:
    "Define your own search space and run loop. The genome's mutate() is the heuristic perturbation pattern; evaluate_genome scores a candidate; run_evolution wraps the whole (μ+λ) loop end-to-end.",
  entries: [
    {
      id: "mfg-v3-genome-mutate",
      name: "ManufacturingGenome.mutate",
      kind: "method",
      signature: "mutate(rng=None) → ManufacturingGenome",
      module: "game_envs/manufacturing/genome.py",
      desc: "Reference heuristic perturbation used by the MATH mode: pick one axis and nudge it within bounds — a machine capacity or edge bandwidth by ±1–3, flip the maintenance policy to a different level, or change order intake by ±15%. Mirror this pattern for your own genome.",
      params: [
        { name: "rng", type: "random.Random?", desc: "Seeded RNG for reproducible perturbations." },
      ],
      returns: "A new, clamped ManufacturingGenome (the original is unchanged).",
      customize: "Override the per-axis nudges (delta sizes, which fields move) to reshape your search.",
    },
    {
      id: "evaluate-genome",
      name: "evaluate_genome",
      kind: "function",
      signature: "evaluate_genome(genome, seeds=(42,101,777), ticks=500) → dict",
      module: "evolution/manufacturing_evolution.py",
      desc: "Run a genome once per seed and average the result — the fitness function the EA optimizes.",
      params: [
        { name: "genome", type: "ManufacturingGenome | dict", required: true, desc: "The candidate to score." },
        { name: "seeds", type: "tuple[int, …]", default: "(42, 101, 777)", customizable: true, desc: "Evaluation seeds; mean fitness is taken over them." },
        { name: "ticks", type: "int", default: "500", customizable: true, desc: "Episode length per evaluation." },
      ],
      returns: "{ fitness: float (mean), per_seed: [{seed, fitness}], metrics: dict }",
    },
    {
      id: "run-evolution",
      name: "run_evolution",
      kind: "function",
      signature: "async run_evolution(generations=10, engine=\"MATH\", seeds=…, base_genome=None, rng_seed=12345) → dict",
      module: "evolution/manufacturing_evolution.py",
      desc: "Drive the (μ+λ) loop for the manufacturing scenario for N generations and return the final state with history. Each generation proposes candidates (via the chosen engine), evaluates them across seeds, and keeps the best.",
      params: [
        { name: "generations", type: "int", default: "10", customizable: true, desc: "How many generations to run." },
        { name: "engine", type: "\"MATH\" | \"LLM\"", default: "\"MATH\"", customizable: true, desc: "Candidate source — heuristic perturbation or LLM proposals." },
        { name: "base_genome", type: "ManufacturingGenome?", desc: "Starting incumbent (defaults to ManufacturingGenome.default())." },
        { name: "rng_seed", type: "int", default: "12345", customizable: true, desc: "Seed for the evolution RNG (reproducibility)." },
      ],
      returns: "Final state dict including the genome and per-generation history.",
    },
  ],
};

const LLM_SECTION: Section = {
  id: "llm",
  title: "LLM brains",
  blurb:
    "The LLM-driven decision points: the meta-optimizer that proposes manufacturing genomes, and the supply-chain brains. Provider and model are env-configurable.",
  entries: [
    {
      id: "query-candidates",
      name: "query_candidates",
      kind: "function",
      signature: "async query_candidates(genome, metrics, history, *, model, rng=None) → list[ManufacturingGenome]",
      module: "agents/manufacturing_optimizer.py",
      desc: "The LLM candidate proposer for manufacturing: given the incumbent genome, its metrics, and run history, the model proposes exactly 3 distinct candidate genomes. Falls back to MATH (math_candidates) on any failure.",
      params: [
        { name: "genome", type: "ManufacturingGenome", required: true, desc: "The incumbent to improve on." },
        { name: "metrics", type: "dict", required: true, desc: "The incumbent's evaluated metrics." },
        { name: "history", type: "list[dict]", required: true, desc: "Prior generations, for context." },
        { name: "model", type: "str", desc: "LLM model id (defaults to the configured manufacturing model)." },
      ],
      returns: "list[ManufacturingGenome] (3 candidates).",
      customize: "Tune SYSTEM_PROMPT / build_user_prompt() in this module to steer what the optimizer optimizes for.",
    },
    {
      id: "math-candidates",
      name: "math_candidates",
      kind: "function",
      signature: "math_candidates(base, n=3, rng=None) → list[ManufacturingGenome]",
      module: "agents/manufacturing_optimizer.py",
      desc: "The MATH mode (and LLM fallback): n distinct heuristic perturbations of the incumbent via genome.mutate().",
      params: [
        { name: "base", type: "ManufacturingGenome", required: true, desc: "The incumbent to perturb." },
        { name: "n", type: "int", default: "3", customizable: true, desc: "Number of candidates to produce." },
        { name: "rng", type: "random.Random?", desc: "Seeded RNG for reproducibility." },
      ],
      returns: "list[ManufacturingGenome].",
    },
    {
      id: "run-director",
      name: "run_director",
      kind: "function",
      signature: "async run_director(digest) → list[dict] | None",
      module: "agents/supply_chain_llm.py",
      desc: "Global supply-chain reshaping run every 25 ticks — the LLM proposes a validated list of director tool calls from a telemetry digest. Returns None on failure.",
      params: [
        { name: "digest", type: "dict", required: true, desc: "Recent supply-chain telemetry (env.director_digest())." },
      ],
      returns: "list[dict] of director tool calls, or None.",
    },
    {
      id: "resolve-edge-exception",
      name: "resolve_edge_exception",
      kind: "function",
      signature: "async resolve_edge_exception(ctx) → dict | None",
      module: "agents/supply_chain_llm.py",
      desc: "Per-truck decision when an edge agent is blocked, full, or its cargo is spoiling. Returns one validated override decision, or None (caller falls back to a programmatic action).",
      params: [
        { name: "ctx", type: "dict", required: true, desc: "The blocked agent's local situation." },
      ],
      returns: "A validated decision dict, or None.",
    },
  ],
};

const POLICIES_SECTION: Section = {
  id: "policies",
  title: "Policies",
  blurb:
    "How an agent decides its next action. Swap a policy to move from scripted heuristics to LLM reasoning without touching the environment.",
  entries: [
    {
      id: "get-policy",
      name: "get_policy",
      kind: "function",
      signature: "get_policy(name, **kwargs) → BasePolicy",
      module: "agents/manufacturing_policies.py",
      desc: "Factory returning a policy instance by registry name (falls back to ScriptedGreedyPolicy for an unknown name). POLICY_REGISTRY keys:",
      params: [
        { name: "\"random\"", type: "RandomPolicy", customizable: true, desc: "Uniform random valid action — a baseline." },
        { name: "\"scripted\"", type: "ScriptedGreedyPolicy", customizable: true, desc: "Deterministic heuristic rules; overridable via apply_policy_override()." },
        { name: "\"llm\"", type: "LLMPolicy", customizable: true, desc: "Wraps async LLM role agents for reasoning-driven actions." },
      ],
      customize: "Add a policy by subclassing BasePolicy and registering the class in POLICY_REGISTRY.",
    },
    {
      id: "apply-policy-override",
      name: "apply_policy_override",
      kind: "function",
      signature: "apply_policy_override(rule, value) → (bool, str)",
      module: "agents/manufacturing_policies.py",
      desc: "Inject a rule override onto the scripted policy at runtime — e.g. force a stage's priority or cap WIP.",
      params: [
        { name: "rule", type: "str", required: true, customizable: true, desc: "The override rule name." },
        { name: "value", type: "object", required: true, customizable: true, desc: "The value to set for that rule." },
      ],
      returns: "(applied: bool, message: str)",
    },
  ],
};

const ENDPOINTS_SECTION: Section = {
  id: "endpoints",
  title: "HTTP API",
  blurb:
    "REST surface for driving runs programmatically. The GUI calls these same routes — anything the UI does, you can do over HTTP.",
  entries: [
    {
      id: "scenario-start",
      name: "Start a run",
      kind: "endpoint",
      signature: "POST /api/scenario/start",
      module: "main.py",
      desc: "Launch an orchestration run. Streams agents, metrics, and fitness over the socket as it executes.",
      params: [
        { name: "scenario", type: "str", required: true, customizable: true, desc: "A SCENARIOS key or UI label (resolved via SCENARIO_LABEL_MAP)." },
        { name: "mode", type: "str", desc: "Run mode, e.g. \"autonomous\"." },
        { name: "boundary_mode", type: "INTRA | INTER", customizable: true, desc: "Generation bounding strategy." },
        { name: "engine", type: "MATH | LLM | DEAP", customizable: true, desc: "Agent mode (canonical field)." },
        { name: "mutation_strategy", type: "MATH | LLM | DEAP", desc: "Legacy alias for engine (accepted as a fallback)." },
        { name: "inter_ticks", type: "int", customizable: true, desc: "Episode length when boundary_mode is INTER." },
        { name: "run_id", type: "str?", desc: "Optional explicit run id." },
        { name: "resume_payload", type: "dict?", desc: "Checkpoint row to warm-start from." },
      ],
    },
    {
      id: "scenario-stop",
      name: "Stop the run",
      kind: "endpoint",
      signature: "POST /api/scenario/stop",
      module: "main.py",
      desc: "Stop the active simulation (clears the running flag).",
    },
    {
      id: "scenario-resume",
      name: "Fetch checkpoint",
      kind: "endpoint",
      signature: "GET /api/scenario/resume/{run_id}",
      module: "main.py",
      desc: "Retrieve the latest checkpoint for a run, to warm-start a new run by passing it back as resume_payload.",
      params: [{ name: "run_id", type: "str", required: true, desc: "Run to fetch the checkpoint for." }],
    },
    {
      id: "ea-generations",
      name: "List generations",
      kind: "endpoint",
      signature: "GET /api/ea/generations/{run_id}",
      module: "main.py",
      desc: "All recorded generations for a run — the fitness history.",
      params: [
        { name: "run_id", type: "str", required: true, desc: "Run to query." },
        { name: "limit", type: "int", default: "500", desc: "Max generations to return." },
      ],
    },
    {
      id: "workflows",
      name: "Workflows",
      kind: "endpoint",
      signature: "GET /api/workflows · POST /api/workflows/save · POST /api/workflows/{id}/apply",
      module: "main.py",
      desc: "List, save, and re-apply known-good agent topologies. Save body: { name, scenario, best_fitness, topology }.",
    },
    {
      id: "traces-health",
      name: "Traces & health",
      kind: "endpoint",
      signature: "GET /api/traces/{run_id} · GET /api/healthz",
      module: "main.py",
      desc: "Fetch the stored agent-thought traces for a run, and a basic liveness probe.",
    },
    {
      id: "mfg-router",
      name: "Manufacturing control",
      kind: "endpoint",
      signature: "POST /api/mfg/reset · /step · /speed · /pause · /resume · /genome/validate · GET /metrics · /state · /action_space/{agent_id} · /observation/{agent_id} · /genome/default",
      module: "api/mfg_router.py",
      desc: "Fine-grained, step-level control of the manufacturing environment — reset with a config, step with actions, inspect per-agent action spaces and observations, control speed/pause/resume, and fetch or validate a genome.",
      customize: "Drive the env tick-by-tick from your own control loop instead of the autonomous orchestrator.",
    },
  ],
};

const EVENTS_SECTION: Section = {
  id: "events",
  title: "Realtime events",
  blurb:
    "Bidirectional events over /socket.io. The server streams live run state; the client steers the run as it executes.",
  entries: [
    {
      id: "server-events",
      name: "Server → client",
      kind: "event",
      module: "main.py",
      desc: "Emitted as a run progresses. Subscribe to render or log live state.",
      params: [
        { name: "game_state_update / tick_update", type: "event", desc: "Full / per-tick world snapshot (grid, agents, inventory, flow graph)." },
        { name: "metrics_update", type: "event", desc: "Aggregated throughput, cost, and latency." },
        { name: "fitness_update", type: "event", desc: "Per-generation result: generation, parent_fitness, best_fitness, mutation_type." },
        { name: "generation_complete", type: "event", desc: "Generation summary: gen_id, parent_fitness, child_fitness, mutation_type." },
        { name: "dag_update", type: "event", desc: "Agent topology with nodes and edge scores." },
        { name: "agent_thought / agent_action", type: "event", desc: "Streaming LLM reasoning and the concrete action taken." },
        { name: "alert", type: "event", desc: "Notable sim events (breakdowns, orders, sales, budget)." },
        { name: "game_over", type: "event", desc: "Run complete: metrics, fitness, ticks." },
      ],
    },
    {
      id: "client-events",
      name: "Client → server",
      kind: "event",
      module: "main.py",
      desc: "Sent from a client to steer an in-flight run.",
      params: [
        { name: "scenario_select", type: "{ scenario }", customizable: true, desc: "Select the scenario before starting." },
        { name: "start_evolution", type: "{}", customizable: true, desc: "Begin the run." },
        { name: "set_speed", type: "{ multiplier }", customizable: true, desc: "Change simulation speed." },
        { name: "pause / resume", type: "{}", customizable: true, desc: "Pause (state preserved) or resume the run." },
      ],
    },
  ],
};

const CONFIG_SECTION: Section = {
  id: "config",
  title: "Configuration",
  blurb: "Environment variables that select providers, models, storage, and defaults at startup.",
  entries: [
    {
      id: "env-vars",
      name: "Environment variables",
      kind: "config",
      module: "main.py · agents/* · state/db.py",
      desc: "Set these before launching the server to configure the engine.",
      params: [
        { name: "ANTHROPIC_API_KEY", type: "str", customizable: true, desc: "Enables Anthropic LLM modes (preferred provider)." },
        { name: "OPENAI_API_KEY", type: "str", customizable: true, desc: "OpenAI provider credential (fallback)." },
        { name: "META_OPTIMIZER_PROVIDER", type: "anthropic | openai", default: "auto-detect", customizable: true, desc: "Force the optimizer's provider (resolved by _resolve_engine())." },
        { name: "MANUFACTURING_LLM_MODEL", type: "str", default: "claude-haiku-4-5", customizable: true, desc: "Model for manufacturing agent reasoning." },
        { name: "SUPPLY_CHAIN_LLM_MODEL", type: "str", default: "claude-haiku-4-5", customizable: true, desc: "Model for the supply-chain director and edge agents." },
        { name: "ARENA_DEFAULT_ENGINE", type: "str", default: "MATH", customizable: true, desc: "Default agent mode when none is specified." },
        { name: "ARENA_EA_SEED", type: "int", default: "0", customizable: true, desc: "Seed for reproducible evolution runs." },
        { name: "ARENA_DB_URL", type: "str", default: "sqlite+aiosqlite:///./arena.db", customizable: true, desc: "Checkpoint / workflow / trace database (SQLAlchemy URL)." },
      ],
    },
  ],
};

// ── The two tabs ──────────────────────────────────────────────────────────────

export const REFERENCE_TABS: Tab[] = [
  {
    id: "ui",
    label: "Inside the Arena",
    introTitle: "Inside the Arena",
    introBody:
      "A guided reference to the scenarios, agents, and controls you see when you run AERA.",
    sections: [SCENARIOS_SECTION, AGENTS_SECTION, CONTROLS_SECTION],
  },
  {
    id: "api",
    label: "Build your own",
    introTitle: "Build your own",
    introBody:
      "The orchestration engine, HTTP API, and extension points to drive AERA from your own code — define a custom scenario, plug in your own evaluator, and run the loop programmatically.",
    sections: [
      ORCHESTRATOR_SECTION,
      EVOLUTION_SECTION,
      LLM_SECTION,
      POLICIES_SECTION,
      ENDPOINTS_SECTION,
      EVENTS_SECTION,
      CONFIG_SECTION,
    ],
  },
];
