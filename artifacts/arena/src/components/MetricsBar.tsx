import { useSocket } from "@/hooks/useSocket";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";

export default function MetricsBar() {
  const { evolutionData, gameState, socket } = useSocket();

  const latestFitness = evolutionData[evolutionData.length - 1] ?? null;
  const costPerTask = latestFitness?.cost_per_task ?? 0;
  const latencyMs = latestFitness ? latestFitness.latency * 1000 : 0;
  const bestFitness = latestFitness?.best_fitness ?? 0;
  const tick = gameState?.tick ?? 0;
  const scenario = gameState?.scenario ?? "None";

  // Use the stable socket ID (backend-provided, persists for the connection lifetime)
  // Formatted as RUN-XXXX using last 4 hex chars of the socket id
  const socketId = socket?.id ?? "";
  const runLabel = socketId
    ? "RUN-" + socketId.slice(-4).toUpperCase()
    : "RUN-––––";

  return (
    <div className="w-full h-full flex flex-col p-4 bg-[#161b22] gap-4" data-testid="container-metrics-bar">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Live Metrics</h3>
        <div className="flex gap-2">
          <Badge variant="outline" className="text-xs border-[#30363d] text-muted-foreground">
            Tick: {tick}
          </Badge>
          <Badge variant="outline" className="text-xs border-[#30363d] text-primary">
            Scen: {scenario}
          </Badge>
          <Badge variant="outline" className="text-xs border-[#30363d] text-secondary font-mono">
            {runLabel}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6 h-full">
        {/* Cost / Task */}
        <div className="flex flex-col gap-2 p-4 bg-[#0d1117] rounded-md border border-[#30363d]">
          <span className="text-xs text-muted-foreground">Cost / Task</span>
          <span className="text-2xl font-mono text-[#00d9ff]" data-testid="metric-cost">
            ${costPerTask.toFixed(5)}
          </span>
        </div>

        {/* Latency */}
        <div className="flex flex-col gap-2 p-4 bg-[#0d1117] rounded-md border border-[#30363d]">
          <span className="text-xs text-muted-foreground">Latency</span>
          <span className="text-2xl font-mono text-[#f59e0b]" data-testid="metric-latency">
            {latencyMs.toFixed(0)} ms
          </span>
        </div>

        {/* Pass@k */}
        <div className="flex flex-col gap-2 p-4 bg-[#0d1117] rounded-md border border-[#30363d]">
          <div className="flex justify-between items-end">
            <span className="text-xs text-muted-foreground">Pass@k (Fitness)</span>
            <span className="text-sm font-mono text-[#7ee787]" data-testid="metric-fitness">
              {bestFitness}
            </span>
          </div>
          <Progress value={(bestFitness / 1000) * 100} className="h-2 bg-[#161b22]" />
        </div>
      </div>
    </div>
  );
}
