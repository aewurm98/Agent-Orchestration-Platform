import { createContext, useEffect, useState, ReactNode, useCallback } from "react";
import { io, Socket } from "socket.io-client";

export type GameAgent = {
  id: string;
  x: number;
  y: number;
  role: string;
  inventory: number;
  state: string;
  // Retailer-only fields (present when role === "retailer")
  delivered?: number;
  demand?: number;
  last_demand?: number;
  last_sold?: number;
  stockout?: boolean;
  capacity?: number;
};

export type GameState = {
  scenario: string;
  agents: GameAgent[];
  resources: {
    grid_size?: number;
    stock_level?: number;
    demand_queue?: number;
    backlog?: number;
    carrying_cost?: number;
    total_delivered?: number;
    raw_input?: number;
    inter_input?: number;
    finished_output?: number;
    approved_finished?: number;
    total_processed?: number;
    // Supply chain extras
    supply_rate?: number;
    demand_base?: number;
    transfer_amount?: number;
    customers_served?: number;
    service_level?: number;
    stockout_ticks?: number;
    supply_override?: boolean;
    demand_override?: boolean;
  };
  score: number;
  tick: number;
};

export type MfgV2Agent = {
  id: string;
  role: string;
  row: number;
  col: number;
  state: string;
  inventory: Array<{ id: string; type: string }>;
  inventory_count: number;
  is_standby: boolean;
  active_macro: string | null;
  wage_per_tick: number;
  messages: Array<unknown>;
  path: Array<[number, number]>;
};

export type MfgV2Machine = {
  id: string;
  type: string;
  row: number;
  col: number;
  state: string;
  speed: string;
  input_queue_len: number;
  output_queue_len: number;
  input_queue: Array<{ id: string; type: string }>;
  output_queue: Array<{ id: string; type: string }>;
  processing_ticks_remaining: number;
  health: number;
  total_produced: number;
  power_cost_per_tick: number;
};

export type MfgV2Item = {
  id: string;
  type: string;
  row: number | null;
  col: number | null;
  carrier_id: string | null;
};

export type MfgOrder = {
  id: string;
  product_type: string;
  quantity: number;
  deadline_tick: number;
  base_price: number;
  effective_price: number;
  arrival_tick: number;
  fulfilled: number;
  is_rush: boolean;
  remaining: number;
};

export type MfgMetrics = {
  tick: number;
  throughput: number;
  avg_latency: number;
  total_revenue: number;
  total_costs: number;
  current_profit: number;
  agent_idle_ratio: number;
  machine_utilization: number;
  queue_lengths: Record<string, number>;
  orders_fulfilled: number;
  orders_missed: number;
  budget: number;
  pl: Record<string, number>;
};

export type MfgAlert = {
  type: string;
  event?: string;
  message?: string;
  machine_id?: string;
  machine_type?: string;
  agent_id?: string;
  budget?: number;
  order_id?: string;
  // Order-specific fields
  is_rush?: boolean;
  deadline_tick?: number;
  base_price?: number;
  revenue?: number;
  // Sale-specific fields
  item_type?: string;
};

export type MfgGameState = {
  scenario: string;
  tick: number;
  done: boolean;
  grid: string[][];
  grid_rows: number;
  grid_cols: number;
  agents: Record<string, MfgV2Agent>;
  machines: Record<string, MfgV2Machine>;
  items: MfgV2Item[];
  budget: number;
  starting_budget: number;
  active_orders: MfgOrder[];
  metrics: MfgMetrics;
  fitness: number;
  score: number;
  alerts: MfgAlert[];
  simulation_length: number;
  resources: Record<string, number>;
};

export type DagNode = {
  id: string;
  label: string;
  status: "active" | "idle" | "evolved" | "failed";
  ctx_util: number;
  system_prompt: string;
  tools: string[];
  last_actions: string[];
};

export type DagEdge = {
  source: string;
  target: string;
  payload_size: number;
  grpo_score: number;
};

export type DagData = {
  nodes: DagNode[];
  edges: DagEdge[];
};

export type AgentThought = {
  run_id: string;
  role: string;
  content: string;
  timestamp: number;
  agent_name?: string;
  agent_role?: string;
  stage?: string | null;
  action?: string;
  parameters?: Record<string, unknown>;
  reasoning?: string;
};

export type HitlRequest = {
  run_id: string;
  generation: number;
  plan: string;
  confidence: number;
  proposed_action: string;
};

export type GenomeSnapshot = {
  agent_counts: Record<string, number>;
  machine_speeds: Record<string, string>;
  order_arrival_rate: number;
};

export type FitnessUpdate = {
  generation: number;
  parent_fitness: number;
  best_fitness: number;
  mutation_type: string;
  topology_diff: string;
  cost_per_task: number;
  latency: number;
  // Extended fields populated by the generational EA loop
  genome?: GenomeSnapshot;
  improved?: boolean;
  // Number of consecutive generations without fitness improvement
  stagnation?: number;
};

export type GenerationComplete = {
  gen_id: number;
  parent_fitness: number;
  child_fitness: number;
  mutation_type: string;
};

type SocketContextType = {
  socket: Socket | null;
  gameState: GameState | null;
  mfgState: MfgGameState | null;
  mfgMetrics: MfgMetrics | null;
  mfgAlerts: MfgAlert[];
  dagData: DagData | null;
  evolutionData: FitnessUpdate[];
  traces: AgentThought[];
  hitlRequest: HitlRequest | null;
  isRunning: boolean;
  currentGeneration: number;
  emitHitlResponse: (action: "approve" | "override" | "stop", constraint?: string) => void;
  emitScenarioSelect: (scenario: string) => void;
  emitStartEvolution: () => void;
  emitMfgAction: (agentId: string, actionType: string, params?: Record<string, unknown>) => void;
  emitSupplyChainKnobs: (knobs: { supply_rate?: number | null; retail_demand_base?: number | null }) => void;
  setIsRunning: (running: boolean) => void;
  clearHitlRequest: () => void;
  clearSessionState: () => void;
};

export const SocketContext = createContext<SocketContextType | undefined>(undefined);

const MAX_ALERTS = 20;

export function SocketProvider({ children }: { children: ReactNode }) {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [mfgState, setMfgState] = useState<MfgGameState | null>(null);
  const [mfgMetrics, setMfgMetrics] = useState<MfgMetrics | null>(null);
  const [mfgAlerts, setMfgAlerts] = useState<MfgAlert[]>([]);
  const [dagData, setDagData] = useState<DagData | null>(null);
  const [evolutionData, setEvolutionData] = useState<FitnessUpdate[]>([]);
  const [traces, setTraces] = useState<AgentThought[]>([]);
  const [hitlRequest, setHitlRequest] = useState<HitlRequest | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [currentGeneration, setCurrentGeneration] = useState(0);

  useEffect(() => {
    const newSocket = io("/", { path: "/socket.io" });
    setSocket(newSocket);

    newSocket.on("game_state_update", (data: unknown) => {
      const d = data as Record<string, unknown>;
      if (d.scenario === "manufacturing" && d.grid) {
        // Manufacturing state update — populate mfg UI, clear non-mfg state
        setMfgState(d as unknown as MfgGameState);
        setGameState(null);
      } else {
        // Non-manufacturing scenario — clear mfg state so it doesn't bleed in
        setMfgState(null);
        setMfgMetrics(null);
        setMfgAlerts([]);
        setGameState(data as GameState);
      }
    });

    newSocket.on("tick_update", (data: unknown) => {
      const d = data as Record<string, unknown>;
      if (d.grid) {
        setMfgState(d as unknown as MfgGameState);
      }
    });

    newSocket.on("metrics_update", (data: MfgMetrics) => {
      setMfgMetrics(data);
    });

    newSocket.on("alert", (data: MfgAlert) => {
      setMfgAlerts((prev) => {
        const updated = [...prev, data];
        return updated.slice(-MAX_ALERTS);
      });
    });

    newSocket.on("game_over", (data: unknown) => {
      const d = data as Record<string, unknown>;
      if (d.metrics) {
        setMfgMetrics(d.metrics as MfgMetrics);
      }
    });

    newSocket.on("dag_update", (data: DagData) => {
      setDagData(data);
    });

    newSocket.on("agent_thought", (data: AgentThought) => {
      setTraces((prev) => [...prev.slice(-200), data]);
    });

    newSocket.on("hitl_request", (data: HitlRequest) => {
      setHitlRequest(data);
    });

    newSocket.on("fitness_update", (data: FitnessUpdate) => {
      setEvolutionData((prev) => {
        const filtered = prev.filter((d) => d.generation !== data.generation);
        return [...filtered, data];
      });
      setCurrentGeneration(data.generation);
    });

    newSocket.on("generation_complete", (_data: GenerationComplete) => {});

    return () => {
      newSocket.disconnect();
    };
  }, []);

  const emitHitlResponse = useCallback(
    (action: "approve" | "override" | "stop", constraint?: string) => {
      if (socket) socket.emit("hitl_response", { action, constraint });
    },
    [socket]
  );

  const clearSessionState = useCallback(() => {
    setEvolutionData([]);
    setTraces([]);
    setDagData(null);
    setMfgState(null);
    setMfgMetrics(null);
    setMfgAlerts([]);
    setHitlRequest(null);
    setCurrentGeneration(0);
    setGameState(null);
    setIsRunning(false);
  }, []);

  const emitScenarioSelect = useCallback(
    (scenario: string) => {
      clearSessionState();
      if (socket) socket.emit("scenario_select", { scenario });
    },
    [socket, clearSessionState]
  );

  const emitStartEvolution = useCallback(() => {
    if (socket) {
      socket.emit("start_evolution", {});
      setIsRunning(true);
    }
  }, [socket]);

  const emitMfgAction = useCallback(
    (agentId: string, actionType: string, params: Record<string, unknown> = {}) => {
      if (socket) {
        socket.emit("mfg_action", { agent_id: agentId, type: actionType, params });
      }
    },
    [socket]
  );

  const emitSupplyChainKnobs = useCallback(
    (knobs: { supply_rate?: number | null; retail_demand_base?: number | null }) => {
      if (socket) socket.emit("set_supply_chain_knobs", knobs);
    },
    [socket]
  );

  const clearHitlRequest = useCallback(() => setHitlRequest(null), []);

  return (
    <SocketContext.Provider
      value={{
        socket,
        gameState,
        mfgState,
        mfgMetrics,
        mfgAlerts,
        dagData,
        evolutionData,
        traces,
        hitlRequest,
        isRunning,
        currentGeneration,
        emitHitlResponse,
        emitScenarioSelect,
        emitStartEvolution,
        emitMfgAction,
        emitSupplyChainKnobs,
        setIsRunning,
        clearHitlRequest,
        clearSessionState,
      }}
    >
      {children}
    </SocketContext.Provider>
  );
}
