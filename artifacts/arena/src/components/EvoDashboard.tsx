import { useSocket } from "@/hooks/useSocket";
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Line, ComposedChart } from "recharts";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

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

  return (
    <div className="w-full h-full flex flex-col bg-[#0d1117] p-4 gap-4 overflow-y-auto" data-testid="evo-dashboard">
      <div className="h-[300px] w-full border border-[#30363d] rounded-md bg-[#161b22] p-4">
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
              {recentRecords.map((record) => (
                <TableRow key={record.generation} className="border-[#30363d] hover:bg-[#30363d]/30">
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
