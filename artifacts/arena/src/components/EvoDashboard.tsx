import { useSocket } from "@/hooks/useSocket";
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line, ComposedChart } from "recharts";
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

export default function EvoDashboard() {
  const { evolutionData } = useSocket();

  if (!evolutionData || evolutionData.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center text-[#6b6359] text-sm font-mono bg-transparent" data-testid="evo-empty">
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
    <div className="w-full h-full flex flex-col bg-transparent p-4 gap-4 overflow-y-auto" data-testid="evo-dashboard">

      {/* Stagnation warning banner — fires when EA hasn't improved for 3+ generations */}
      {isStagnating && (
        <div
          className="flex items-center justify-between rounded-md px-3 py-2 text-[11px] font-mono font-semibold uppercase tracking-widest"
          style={{
            backgroundColor: "#b4530918",
            border: "1px solid #b4530988",
            color: "#b45309",
            animation: "stagnation-pulse 1.4s ease-in-out infinite",
          }}
          data-testid="stagnation-banner"
        >
          <span>⚠ Stagnation — {stagnation} gens without improvement</span>
          <span style={{ color: "#b91c1c", fontSize: "10px" }}>HITL Recommended</span>
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

      <div className="h-[220px] w-full border border-[#ebe5d6] rounded-lg bg-[#faf6ed] shadow-sm p-4">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ebe5d6" vertical={false} />
            <XAxis dataKey="generation" type="number" stroke="#6b6359" fontSize={12} tickLine={false} label={{ value: 'Generation', position: 'insideBottom', offset: -10, fill: '#6b6359', fontSize: 12 }} />
            <YAxis stroke="#6b6359" fontSize={12} tickLine={false} label={{ value: 'Fitness', angle: -90, position: 'insideLeft', fill: '#6b6359', fontSize: 12 }} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#ffffff', borderColor: '#ebe5d6', fontSize: '12px' }}
              itemStyle={{ color: '#14120e' }}
            />
            <Scatter name="Parent Population" dataKey="parentFitness" fill="#6b6359" opacity={0.6} />
            <Scatter name="Best Mutant" dataKey="bestFitness" fill="#14120e" r={6} />
            <Line type="monotone" dataKey="bestFitness" stroke="#14120e" strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="flex-1 bg-[#faf6ed] rounded-lg border border-[#ebe5d6] shadow-sm overflow-hidden flex flex-col">
        <div className="p-3 border-b border-[#ebe5d6] bg-[#efe9d9]">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">Evolution History</h3>
        </div>
        <div className="flex-1 overflow-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-[#ebe5d6] hover:bg-transparent">
                <TableHead className="text-xs text-[#6b6359]">Gen</TableHead>
                <TableHead className="text-xs text-[#6b6359]">Best Fitness</TableHead>
                <TableHead className="text-xs text-[#6b6359]">Mutation</TableHead>
                <TableHead className="text-xs text-[#6b6359]">Topology</TableHead>
                <TableHead className="text-xs text-[#6b6359] text-right">Cost/Task</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recentRecords.map((record, i) => (
                <TableRow key={`${record.generation}-${i}`} className="border-[#ebe5d6] hover:bg-[#ebe5d6]/30">
                  <TableCell className="font-mono text-xs text-[#14120e]">{record.generation}</TableCell>
                  <TableCell className="font-mono text-xs text-[#14120e]">{record.best_fitness}</TableCell>
                  <TableCell className="text-xs">
                    <Badge variant="outline" className="bg-[#ffffff] border-[#ebe5d6] text-[#14120e] text-[10px]">
                      {record.mutation_type}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-[#b45309] truncate max-w-[150px]">{record.topology_diff}</TableCell>
                  <TableCell className="text-xs font-mono text-right text-[#15803d]">${record.cost_per_task.toFixed(4)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
