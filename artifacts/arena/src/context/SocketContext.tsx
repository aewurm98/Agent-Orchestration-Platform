import { createContext, useEffect, useState, ReactNode, useCallback } from "react";
import { io, Socket } from "socket.io-client";

export type GameAgent = {
  id: string;
  x: number;
  y: number;
  role: string;
  inventory: number;
  state: string;
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
    // manufacturing resources
    raw_input?: number;
    inter_input?: number;
    finished_output?: number;
    approved_finished?: number;
    total_processed?: number;
  };
  score: number;
  tick: number;
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
  // enriched manufacturing fields (optional)
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

export type FitnessUpdate = {
  generation: number;
  parent_fitness: number;
  best_fitness: number;
  mutation_type: string;
  topology_diff: string;
  cost_per_task: number;
  latency: number;
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
  dagData: DagData | null;
  evolutionData: FitnessUpdate[];
  traces: AgentThought[];
  hitlRequest: HitlRequest | null;
  isRunning: boolean;
  currentGeneration: number;
  emitHitlResponse: (action: "approve" | "override" | "stop", constraint?: string) => void;
  emitScenarioSelect: (scenario: string) => void;
  emitStartEvolution: () => void;
  setIsRunning: (running: boolean) => void;
  clearHitlRequest: () => void;
};

export const SocketContext = createContext<SocketContextType | undefined>(undefined);

export function SocketProvider({ children }: { children: ReactNode }) {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [dagData, setDagData] = useState<DagData | null>(null);
  const [evolutionData, setEvolutionData] = useState<FitnessUpdate[]>([]);
  const [traces, setTraces] = useState<AgentThought[]>([]);
  const [hitlRequest, setHitlRequest] = useState<HitlRequest | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [currentGeneration, setCurrentGeneration] = useState(0);

  useEffect(() => {
    const newSocket = io("/", { path: "/socket.io" });
    setSocket(newSocket);

    newSocket.on("game_state_update", (data: GameState) => {
      setGameState(data);
    });

    newSocket.on("dag_update", (data: DagData) => {
      setDagData(data);
    });

    newSocket.on("agent_thought", (data: AgentThought) => {
      setTraces((prev) => [...prev, data]);
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

    newSocket.on("generation_complete", (_data: GenerationComplete) => {
      // Reserved for future use
    });

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

  const emitScenarioSelect = useCallback(
    (scenario: string) => {
      if (socket) socket.emit("scenario_select", { scenario });
    },
    [socket]
  );

  const emitStartEvolution = useCallback(() => {
    if (socket) {
      socket.emit("start_evolution", {});
      setIsRunning(true);
    }
  }, [socket]);

  const clearHitlRequest = useCallback(() => setHitlRequest(null), []);

  return (
    <SocketContext.Provider
      value={{
        socket,
        gameState,
        dagData,
        evolutionData,
        traces,
        hitlRequest,
        isRunning,
        currentGeneration,
        emitHitlResponse,
        emitScenarioSelect,
        emitStartEvolution,
        setIsRunning,
        clearHitlRequest,
      }}
    >
      {children}
    </SocketContext.Provider>
  );
}
