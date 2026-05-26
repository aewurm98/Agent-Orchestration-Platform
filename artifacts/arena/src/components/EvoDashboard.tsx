import { useSocket } from "@/hooks/useSocket";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Scatter, ComposedChart, Line, ScatterChart } from "recharts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { GenomeSnapshot } from "@/context/SocketContext";

const SPEED_COLOR: Record<string, string> = {
  low:    "#b91c1c",
  normal: "#6b6359",
  high:   "#15803d",
};

const ROLE_LABEL: Record<string, string> = {
  procurement: "Proc",
  operations:  "Ops",
  engineering: "Eng",
  sales:       "Sales",
  management:  "Mgmt",
};

function GenomePanel({ genome, improved }: { genome: GenomeSnapshot; improved: boolean }) {
  return (
    <div className="bg-[#faf6ed] rounded-lg border border-[#ebe5d6] shadow-sm p-3 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">Current Genome</span>
        <Badge
          variant="outline"
          className="text-[9px]"
          style={{
            borderColor: improved ? "#15803d" : "#b45309",
            color:       improved ? "#15803d" : "#b45309",
          }}
        >
          {improved ? "▲ Improved" : "▼ Reverted"}
        </Badge>
      </div>

      {/* Machine speeds */}
      <div>
        <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1.5">Machine Speeds</p>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(genome.machine_speeds).map(([mid, spd]) => (
            <div
              key={mid}
              className="text-[9px] font-mono px-2 py-0.5 rounded border"
              style={{
                color: SPEED_COLOR[spd] ?? "#14120e",
                borderColor: (SPEED_COLOR[spd] ?? "#14120e") + "55",
                backgroundColor: (SPEED_COLOR[spd] ?? "#14120e") + "11",
              }}
            >
              {mid.replace("_1", "")} · {spd.toUpperCase()}
            </div>
          ))}
        </div>
      </div>

      {/* Agent counts + order rate */}
      <div className="flex items-end gap-4">
        <div className="flex-1">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1.5">Agent Counts</p>
          <div className="flex gap-2">
            {Object.entries(genome.agent_counts).map(([role, count]) => (
              <div key={role} className="flex flex-col items-center gap-0.5">
                <span className="text-[10px] font-mono font-bold text-[#14120e]">{count}</span>
                <span className="text-[8px] text-muted-foreground">{ROLE_LABEL[role] ?? role}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="text-right">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1">Order Rate</p>
          <span className="text-sm font-mono text-[#b45309]">
            {genome.order_arrival_rate} ticks
          </span>
        </div>
      </div>
    </div>
  );
}

const MUTATION_COLORS: Record<string, string> = {
  add_agent:    "#4F7CFF",
  remove_agent: "#F43F5E",
  swap_speed:   "#8B5CF6",
  change_rate:  "#F59E0B",
  // Engine identifiers — appear when the backend stamps the row with the
  // active mutation strategy rather than a per-generation mutation label.
  MATH:         "#6b6359",
  math:         "#6b6359",
  DEAP:         "#10b981",
  deap:         "#10b981",
  LLM:          "#8B5CF6",
  llm:          "#8B5CF6",
  default:      "#6b6359",
};

function mutationColor(type: string): string {
  return MUTATION_COLORS[type] ?? MUTATION_COLORS.default;
}

export default function EvoDashboard() {
  const { evolutionData } = useSocket();

  if (!evolutionData || evolutionData.length === 0) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center gap-3 bg-transparent" data-testid="evo-empty">
        <div className="w-10 h-10 rounded-xl bg-[#efe9d9] flex items-center justify-center text-[18px]">📈</div>
        <p className="text-[12px] text-[#6b6359] font-mono">Waiting for evolution data</p>
        <p className="text-[11px] text-[#a89e8e]">Run an evolution to see fitness curves here</p>
      </div>
    );
  }

  const chartData = evolutionData.map(d => ({
    generation: d.generation,
    parentFitness: d.parent_fitness,
    bestFitness: d.best_fitness,
  }));

  const sortedRecords = [...evolutionData].sort((a, b) => b.generation - a.generation);
  const latestRecord = evolutionData[evolutionData.length - 1];
  const firstRecord = evolutionData[0];
  const stagnation = latestRecord?.stagnation ?? 0;
  const isStagnating = stagnation >= 3;

  const overallImprovement = latestRecord && firstRecord
    ? ((latestRecord.best_fitness - firstRecord.best_fitness) / Math.max(1, Math.abs(firstRecord.best_fitness)) * 100)
    : 0;

  return (
    <div className="w-full h-full flex flex-col bg-transparent p-4 gap-4 overflow-y-auto" data-testid="evo-dashboard">

      <style>{`
        @keyframes stagnation-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.55; }
        }
      `}</style>

      {/* Summary stats row */}
      <div className="grid grid-cols-3 gap-2 shrink-0">
        <div className="bg-white rounded-xl border border-[#ebe5d6] px-3 py-2 flex flex-col gap-0.5">
          <span className="text-[9px] uppercase tracking-widest text-[#6b6359] font-semibold">Best Fitness</span>
          <span className="text-lg font-semibold font-mono text-[#14120e] tabular-nums leading-tight">
            {latestRecord.best_fitness}
          </span>
        </div>
        <div className="bg-white rounded-xl border border-[#ebe5d6] px-3 py-2 flex flex-col gap-0.5">
          <span className="text-[9px] uppercase tracking-widest text-[#6b6359] font-semibold">Generations</span>
          <span className="text-lg font-semibold font-mono text-[#14120e] tabular-nums leading-tight">
            {latestRecord.generation}
          </span>
        </div>
        <div className="bg-white rounded-xl border border-[#ebe5d6] px-3 py-2 flex flex-col gap-0.5">
          <span className="text-[9px] uppercase tracking-widest text-[#6b6359] font-semibold">Improvement</span>
          <span
            className="text-lg font-semibold font-mono tabular-nums leading-tight"
            style={{ color: overallImprovement >= 0 ? "#15803d" : "#b91c1c" }}
          >
            {overallImprovement >= 0 ? "+" : ""}{overallImprovement.toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Stagnation warning banner */}
      {isStagnating && (
        <div
          className="flex items-center justify-between rounded-md px-3 py-2 text-[11px] font-mono font-semibold uppercase tracking-widest shrink-0"
          style={{
            backgroundColor: "#b4530918",
            border: "1px solid #b4530988",
            color: "#b45309",
            animation: "stagnation-pulse 1.4s ease-in-out infinite",
          }}
          data-testid="stagnation-banner"
        >
          <span>⚠ Stagnation — {stagnation} gens without improvement</span>
          <span style={{ color: "#b91c1c", fontSize: "10px" }}>Consider HITL</span>
        </div>
      )}

      {/* Genome panel */}
      {latestRecord?.genome && (
        <GenomePanel genome={latestRecord.genome} improved={latestRecord.improved ?? true} />
      )}

      {/* Fitness area chart with gradient fill */}
      <div className="h-[200px] w-full border border-[#ebe5d6] rounded-xl bg-[#faf6ed] shadow-sm p-3 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 6, right: 12, bottom: 16, left: 4 }}>
            <defs>
              <linearGradient id="fitnessGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#4F7CFF" stopOpacity={0.18} />
                <stop offset="95%" stopColor="#4F7CFF" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#ebe5d6" vertical={false} />
            <XAxis
              dataKey="generation"
              stroke="#6b6359"
              fontSize={10}
              tickLine={false}
              label={{ value: "Generation", position: "insideBottom", offset: -8, fill: "#6b6359", fontSize: 10 }}
            />
            <YAxis stroke="#6b6359" fontSize={10} tickLine={false} width={36} />
            <Tooltip
              contentStyle={{ backgroundColor: "#ffffff", borderColor: "#ebe5d6", fontSize: "11px", borderRadius: "8px" }}
              itemStyle={{ color: "#14120e" }}
            />
            <Area
              type="monotone"
              dataKey="parentFitness"
              stroke="#d8dfea"
              strokeWidth={1}
              fill="none"
              dot={false}
              name="Parent"
            />
            <Area
              type="monotone"
              dataKey="bestFitness"
              stroke="#4F7CFF"
              strokeWidth={2}
              fill="url(#fitnessGradient)"
              dot={false}
              name="Best"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Evolution history table — all records, scrollable */}
      <div className="flex-1 bg-[#faf6ed] rounded-xl border border-[#ebe5d6] shadow-sm overflow-hidden flex flex-col min-h-0">
        <div className="p-3 border-b border-[#ebe5d6] bg-[#efe9d9] shrink-0">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">
            Evolution History ({sortedRecords.length})
          </h3>
        </div>
        <div className="flex-1 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-[#ebe5d6] hover:bg-transparent">
                <TableHead className="text-xs text-[#6b6359]">Gen</TableHead>
                <TableHead className="text-xs text-[#6b6359]">Best</TableHead>
                <TableHead className="text-xs text-[#6b6359]">Mutation</TableHead>
                <TableHead className="text-xs text-[#6b6359] text-right">Cost/Task</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedRecords.map((record, i) => (
                <TableRow key={`${record.generation}-${i}`} className="border-[#ebe5d6] hover:bg-[#ebe5d6]/30">
                  <TableCell className="font-mono text-xs text-[#14120e]">{record.generation}</TableCell>
                  <TableCell className="font-mono text-xs text-[#14120e]">
                    <span className="flex items-center gap-1">
                      {record.best_fitness}
                      {record.improved && <span className="text-[#15803d] text-[9px]">▲</span>}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs">
                    <Badge
                      variant="outline"
                      className="text-[9px] px-1.5"
                      style={{
                        color: mutationColor(record.mutation_type),
                        borderColor: mutationColor(record.mutation_type) + "55",
                        backgroundColor: mutationColor(record.mutation_type) + "11",
                      }}
                    >
                      {record.mutation_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs font-mono text-right text-[#15803d]">
                    ${record.cost_per_task.toFixed(4)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
