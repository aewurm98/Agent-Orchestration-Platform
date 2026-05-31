import { useSocket } from "@/hooks/useSocket";
import { Progress } from "@/components/ui/progress";

// Friendly display names for the raw scenario keys the backend emits. The
// manufacturing flow-graph env is keyed "manufacturing_v3" internally, but it is
// THE manufacturing scenario now — never surface the "v3" to the user.
const SCENARIO_LABELS: Record<string, string> = {
  manufacturing_v3: "Manufacturing",
  manufacturing: "Manufacturing",
  supply_chain: "Supply Chain",
  disaster_relief: "Disaster Relief",
  peer_agents: "Peer Agents",
};

function scenarioLabel(s: string): string {
  return SCENARIO_LABELS[s] ?? s.replace(/_/g, " ").replace(/\bv\d+\b/gi, "").trim();
}

export default function MetricsBar() {
  const { evolutionData, gameState, mfgState, socket } = useSocket();

  const latestFitness = evolutionData[evolutionData.length - 1] ?? null;
  const prevFitness = evolutionData.length >= 2 ? evolutionData[evolutionData.length - 2] : null;
  const costPerTask = latestFitness?.cost_per_task ?? 0;
  const latencyMs = latestFitness ? latestFitness.latency * 1000 : 0;
  const bestFitness = latestFitness?.best_fitness ?? 0;
  const prevBest = prevFitness?.best_fitness ?? bestFitness;
  const fitnessDelta = bestFitness - prevBest;
  const mutationType = latestFitness?.mutation_type ?? null;
  const tick = mfgState?.tick ?? gameState?.tick ?? 0;
  const rawScenario = mfgState?.scenario ?? gameState?.scenario ?? "None";
  const scenario = rawScenario === "None" ? "None" : scenarioLabel(rawScenario);

  const socketId = socket?.id ?? "";
  const runLabel = socketId
    ? "RUN-" + socketId.slice(-4).toUpperCase()
    : "RUN-––––";

  return (
    <div className="w-full h-full flex flex-col px-6 py-5 gap-5" data-testid="container-metrics-bar">
      <div className="flex justify-between items-center gap-4">
        <h3 className="text-[11px] font-semibold text-[#6b6359] uppercase tracking-[0.18em] shrink-0">Live Metrics</h3>
        <div className="flex items-center gap-x-3 gap-y-0.5 flex-wrap justify-end text-[10px] font-mono text-[#6b6359]">
          <span className="flex items-center gap-1">
            <span className="text-[#9b9285] uppercase tracking-wider">Tick</span>
            <span className="text-[#14120e] tabular-nums">{tick}</span>
          </span>
          <span className="text-[#d8cdb4]" aria-hidden="true">·</span>
          <span className="flex items-center gap-1">
            <span className="text-[#9b9285] uppercase tracking-wider">Scenario</span>
            <span className="text-[#14120e]">{scenario}</span>
          </span>
          {mutationType && (
            <>
              <span className="text-[#d8cdb4]" aria-hidden="true">·</span>
              <span className="flex items-center gap-1">
                <span className="text-[#9b9285] uppercase tracking-wider">Mode</span>
                <span className="text-[#14120e]">{mutationType}</span>
              </span>
            </>
          )}
          <span className="text-[#d8cdb4]" aria-hidden="true">·</span>
          <span className="flex items-center gap-1">
            <span className="text-[#9b9285] uppercase tracking-wider">Run</span>
            <span className="text-[#14120e] tabular-nums">{runLabel}</span>
          </span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 flex-1">
        <StatTile
          label="Cost / Task"
          value={`$${costPerTask.toFixed(5)}`}
          testId="metric-cost"
        />
        <StatTile
          label="Latency"
          value={`${latencyMs.toFixed(0)} ms`}
          testId="metric-latency"
        />
        <div className="flex flex-col justify-between p-4 rounded-2xl border border-[#ebe5d6] bg-white relative">
          <div className="flex flex-col gap-1">
            <span className="text-[11px] text-[#6b6359] uppercase tracking-wider">Best Fitness</span>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-semibold tracking-tight text-[#14120e] tabular-nums" data-testid="metric-fitness">
                {bestFitness}
              </span>
              {fitnessDelta !== 0 && (
                <span
                  className="text-[11px] font-mono font-semibold"
                  style={{ color: fitnessDelta > 0 ? "#15803d" : "#b91c1c" }}
                >
                  {fitnessDelta > 0 ? "▲" : "▼"} {Math.abs(fitnessDelta).toFixed(2)}
                </span>
              )}
            </div>
          </div>
          <Progress value={(bestFitness / 1000) * 100} className="h-1.5 bg-[#efe9d9]" />
          <span className="absolute top-3 right-3 w-1.5 h-1.5 rounded-full bg-[#14120e]" />
        </div>
      </div>
    </div>
  );
}

function StatTile({ label, value, testId }: { label: string; value: string; testId?: string }) {
  return (
    <div className="flex flex-col justify-between p-4 rounded-2xl border border-[#ebe5d6] bg-white relative">
      <div className="flex flex-col gap-1">
        <span className="text-[11px] text-[#6b6359] uppercase tracking-wider">{label}</span>
        <span className="text-2xl font-semibold tracking-tight text-[#14120e] tabular-nums" data-testid={testId}>
          {value}
        </span>
      </div>
      <span className="absolute top-3 right-3 w-1.5 h-1.5 rounded-full bg-[#14120e]" />
    </div>
  );
}
