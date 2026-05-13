import { useSocket } from "@/hooks/useSocket";
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line, ComposedChart } from "recharts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { GenomeSnapshot } from "@/context/SocketContext";

const SPEED_COLOR: Record<string, string> = {
  low:    "#f87171",
  normal: "#8b949e",
  high:   "#7ee787",
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
    <div className="bg-[#161b22] rounded-md border border-[#30363d] p-3 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">Current Genome</span>
        <Badge
          variant="outline"
          className="text-[9px]"
          style={{
            borderColor: improved ? "#7ee787" : "#f59e0b",
            color:       improved ? "#7ee787" : "#f59e0b",
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
                color: SPEED_COLOR[spd] ?? "#e6edf3",
                borderColor: (SPEED_COLOR[spd] ?? "#e6edf3") + "55",
                backgroundColor: (SPEED_COLOR[spd] ?? "#e6edf3") + "11",
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
                <span className="text-[10px] font-mono font-bold text-[#00d9ff]">{count}</span>
                <span className="text-[8px] text-muted-foreground">{ROLE_LABEL[role] ?? role}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="text-right">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wider mb-1">Order Rate</p>
          <span className="text-sm font-mono text-[#f59e0b]">
            {genome.order_arrival_rate} ticks
          </span>
        </div>
      </div>
    </div>
  );
}

export default function EvoDashboard() {
  const { evolutionData } = useSocket();

  if (!evolutionData || evolutionData.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center text-muted-foreground text-sm font-mono bg-[#0d1117]" data-testid="evo-empty">
        Waiting for evolution data...
      </div>
    );
  }

  const chartData = evolutionData.map(d => ({
    generation: d.generation,
    parentFitness: d.parent_fitness,
    bestFitness: d.best_fitness,
  }));

  const recentRecords = [...evolutionData].sort((a, b) => b.generation - a.generation).slice(0, 5);
  const latestRecord = evolutionData[evolutionData.length - 1];
  const stagnation = latestRecord?.stagnation ?? 0;
  const isStagnating = stagnation >= 3;

  return (
    <div className="w-full h-full flex flex-col bg-[#0d1117] p-4 gap-4 overflow-y-auto" data-testid="evo-dashboard">

      {/* Stagnation warning banner — fires when EA hasn't improved for 3+ generations */}
      {isStagnating && (
        <div
          className="flex items-center justify-between rounded-md px-3 py-2 text-[11px] font-mono font-semibold uppercase tracking-widest"
          style={{
            backgroundColor: "#f59e0b18",
            border: "1px solid #f59e0b88",
            color: "#f59e0b",
            animation: "stagnation-pulse 1.4s ease-in-out infinite",
          }}
          data-testid="stagnation-banner"
        >
          <span>⚠ Stagnation — {stagnation} gens without improvement</span>
          <span style={{ color: "#f87171", fontSize: "10px" }}>HITL Recommended</span>
        </div>
      )}

      {/* Genome panel — only shown when backend sends genome data */}
      {latestRecord?.genome && (
        <GenomePanel genome={latestRecord.genome} improved={latestRecord.improved ?? true} />
      )}

      <style>{`
        @keyframes stagnation-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.55; }
        }
      `}</style>

      <div className="h-[220px] w-full border border-[#30363d] rounded-md bg-[#161b22] p-4">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#30363d" vertical={false} />
            <XAxis dataKey="generation" type="number" stroke="#8b949e" fontSize={12} tickLine={false} label={{ value: 'Generation', position: 'insideBottom', offset: -10, fill: '#8b949e', fontSize: 12 }} />
            <YAxis stroke="#8b949e" fontSize={12} tickLine={false} label={{ value: 'Fitness', angle: -90, position: 'insideLeft', fill: '#8b949e', fontSize: 12 }} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#161b22', borderColor: '#30363d', fontSize: '12px' }}
              itemStyle={{ color: '#e6edf3' }}
            />
            <Scatter name="Parent Population" dataKey="parentFitness" fill="#8b949e" opacity={0.6} />
            <Scatter name="Best Mutant" dataKey="bestFitness" fill="#00d9ff" r={6} />
            <Line type="monotone" dataKey="bestFitness" stroke="#00d9ff" strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="flex-1 bg-[#161b22] rounded-md border border-[#30363d] overflow-hidden flex flex-col">
        <div className="p-3 border-b border-[#30363d] bg-[#0d1117]">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">Evolution History</h3>
        </div>
        <div className="flex-1 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-[#30363d] hover:bg-transparent">
                <TableHead className="text-xs text-[#8b949e]">Gen</TableHead>
                <TableHead className="text-xs text-[#8b949e]">Best Fitness</TableHead>
                <TableHead className="text-xs text-[#8b949e]">Mutation</TableHead>
                <TableHead className="text-xs text-[#8b949e]">Topology</TableHead>
                <TableHead className="text-xs text-[#8b949e] text-right">Cost/Task</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recentRecords.map((record, i) => (
                <TableRow key={`${record.generation}-${i}`} className="border-[#30363d] hover:bg-[#30363d]/30">
                  <TableCell className="font-mono text-xs text-[#e6edf3]">{record.generation}</TableCell>
                  <TableCell className="font-mono text-xs text-[#00d9ff]">{record.best_fitness}</TableCell>
                  <TableCell className="text-xs">
                    <Badge variant="outline" className="bg-[#161b22] border-[#30363d] text-[#e6edf3] text-[10px]">
                      {record.mutation_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-[#f59e0b] truncate max-w-[150px]">{record.topology_diff}</TableCell>
                  <TableCell className="text-xs font-mono text-right text-[#7ee787]">${record.cost_per_task.toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
