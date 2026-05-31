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

const MAINT_COLOR: Record<string, string> = {
  low:    "#b91c1c",
  medium: "#b45309",
  high:   "#15803d",
};

function GenomeHeader({ improved }: { improved: boolean }) {
  return (
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
  );
}

// Manufacturing v3 (flow graph): machine capacities, conveyor bandwidths,
// maintenance policy, and order intake rate.
function GenomePanelV3({ genome, improved }: { genome: GenomeSnapshot; improved: boolean }) {
  const maint = genome.maintenance_policy ?? "medium";
  return (
    <div className="bg-[#faf6ed] rounded-lg border border-[#ebe5d6] shadow-sm p-3 flex flex-col gap-3">
      <GenomeHeader improved={improved} />

      {/* Machine capacities */}
      <div>
        <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1.5">Machine Capacities</p>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(genome.machine_capacities ?? {}).map(([mid, cap]) => (
            <div
              key={mid}
              className="text-[9px] font-mono px-2 py-0.5 rounded border border-[#14120e]/30 bg-white text-[#14120e]"
            >
              {mid.replace(/_/g, " ")} · {cap}
            </div>
          ))}
        </div>
      </div>

      {/* Edge bandwidths */}
      <div>
        <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1.5">Conveyor Bandwidths</p>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(genome.edge_bandwidths ?? {}).map(([eid, bw]) => (
            <div
              key={eid}
              className="text-[9px] font-mono px-2 py-0.5 rounded border border-[#b45309]/40 bg-white text-[#b45309]"
            >
              {eid.replace(/_/g, " ")} · {bw}
            </div>
          ))}
        </div>
      </div>

      {/* Maintenance + intake */}
      <div className="flex items-end gap-4">
        <div className="flex-1">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1.5">Maintenance</p>
          <span
            className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded border"
            style={{
              color: MAINT_COLOR[maint] ?? "#14120e",
              borderColor: (MAINT_COLOR[maint] ?? "#14120e") + "55",
              backgroundColor: (MAINT_COLOR[maint] ?? "#14120e") + "11",
            }}
          >
            {maint}
          </span>
        </div>
        <div className="text-right">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1">Order Intake</p>
          <span className="text-sm font-mono text-[#b45309]">
            {genome.order_intake_rate} / ep
          </span>
        </div>
      </div>
    </div>
  );
}

// Legacy v2 (grid factory): machine speeds, agent counts, order arrival rate.
function GenomePanelV2({ genome, improved }: { genome: GenomeSnapshot; improved: boolean }) {
  return (
    <div className="bg-[#faf6ed] rounded-lg border border-[#ebe5d6] shadow-sm p-3 flex flex-col gap-3">
      <GenomeHeader improved={improved} />

      {/* Machine speeds */}
      <div>
        <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1.5">Machine Speeds</p>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(genome.machine_speeds ?? {}).map(([mid, spd]) => (
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
            {Object.entries(genome.agent_counts ?? {}).map(([role, count]) => (
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

function GenomePanel({ genome, improved }: { genome: GenomeSnapshot; improved: boolean }) {
  // v3 flow-graph genomes carry machine_capacities; v2 grid genomes carry machine_speeds.
  return genome.machine_capacities
    ? <GenomePanelV3 genome={genome} improved={improved} />
    : <GenomePanelV2 genome={genome} improved={improved} />;
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

  // Plot only the most recent window so the Y axis can zoom into the live range.
  // Across a whole run fitness spans a huge band (e.g. -2k → 60k), which dwarfs the
  // small per-generation gains the user cares about once the search plateaus.
  const CHART_WINDOW = 25;
  const chartData = evolutionData.slice(-CHART_WINDOW).map(d => ({
    generation: d.generation,
    parentFitness: d.parent_fitness,
    bestFitness: d.best_fitness,
  }));

  // Auto-zoom the Y axis to the visible window (instead of anchoring at 0) and pad
  // the band slightly. A +$300 step on a 40k baseline then occupies a real fraction
  // of the chart height instead of rendering as a flat line.
  const fitVals = chartData
    .flatMap(d => [d.parentFitness, d.bestFitness])
    .filter((v): v is number => Number.isFinite(v));
  const dataMin = fitVals.length ? Math.min(...fitVals) : 0;
  const dataMax = fitVals.length ? Math.max(...fitVals) : 1;
  const yPad = Math.max((dataMax - dataMin) * 0.18, Math.abs(dataMax) * 0.03, 1);
  const yMin = Math.floor(dataMin - yPad);
  const yMax = Math.ceil(dataMax + yPad);
  const fmtK = (v: number) =>
    Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${Math.round(v)}`;

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
      <div className="flex items-center justify-between px-1 shrink-0">
        <span className="text-[9px] uppercase tracking-widest text-[#6b6359] font-semibold">Fitness Curve</span>
        {evolutionData.length > CHART_WINDOW && (
          <span className="text-[9px] font-mono text-[#a89e8e]">last {CHART_WINDOW} gens · zoomed</span>
        )}
      </div>
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
            <YAxis
              stroke="#6b6359"
              fontSize={10}
              tickLine={false}
              width={44}
              domain={[yMin, yMax]}
              allowDecimals={false}
              tickFormatter={fmtK}
            />
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
              baseValue={yMin}
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
