import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { useSocket } from "@/hooks/useSocket";
import { Save, LibraryBig, X, Plus } from "lucide-react";

type Workflow = {
  id: string;
  name: string;
  scenario: string;
  best_fitness: number;
  created_at: string;
};

export default function WorkflowLibrary() {
  const [expanded, setExpanded] = useState(false);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const { emitScenarioSelect, evolutionData, gameState } = useSocket();

  const fetchWorkflows = async () => {
    try {
      const res = await fetch("/api/workflows");
      if (res.ok) {
        const data = await res.json();
        setWorkflows(data.workflows || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (expanded) {
      fetchWorkflows();
    }
  }, [expanded]);

  const handleSaveCurrent = async () => {
    if (!gameState) return;
    const latestFitness = evolutionData[evolutionData.length - 1]?.best_fitness || 0;
    try {
      await fetch("/api/workflows/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `WF-${Math.floor(Math.random() * 1000)}`,
          scenario: gameState.scenario,
          best_fitness: latestFitness
        })
      });
      fetchWorkflows();
    } catch (e) {
      console.error(e);
    }
  };

  if (!expanded) {
    return (
      <div 
        className="absolute left-0 top-1/2 -translate-y-1/2 w-8 h-32 bg-[#161b22] border border-l-0 border-[#30363d] rounded-r-md cursor-pointer flex items-center justify-center hover:bg-[#30363d] transition-colors z-40 shadow-xl"
        onClick={() => setExpanded(true)}
        data-testid="btn-expand-library"
      >
        <span className="text-xs text-muted-foreground rotate-90 tracking-widest uppercase flex items-center gap-2">
          <LibraryBig size={12} className="-rotate-90" /> Library
        </span>
      </div>
    );
  }

  return (
    <div className="absolute left-0 top-0 bottom-0 w-80 bg-[#0d1117] border-r border-[#30363d] z-40 flex flex-col shadow-2xl animate-in slide-in-from-left-full">
      <div className="flex items-center justify-between p-4 border-b border-[#30363d]">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <LibraryBig size={16} /> Workflow Library
        </h2>
        <Button variant="ghost" size="icon" onClick={() => setExpanded(false)} data-testid="btn-close-library">
          <X size={16} />
        </Button>
      </div>

      <div className="p-4 border-b border-[#30363d]">
        <Button 
          className="w-full bg-[#00d9ff] text-[#0d1117] hover:bg-[#00d9ff]/80"
          onClick={handleSaveCurrent}
          disabled={!gameState}
          data-testid="btn-save-current"
        >
          <Save size={16} className="mr-2" /> Save Current State
        </Button>
      </div>

      <ScrollArea className="flex-1 p-4">
        <div className="flex flex-col gap-3">
          {workflows.map(wf => (
            <div key={wf.id} className="bg-[#161b22] p-3 rounded-md border border-[#30363d] flex flex-col gap-2 group">
              <div className="flex justify-between items-start">
                <span className="font-mono text-sm">{wf.name}</span>
                <Badge variant="outline" className="text-[10px] text-[#00d9ff] border-[#00d9ff]/30 bg-[#00d9ff]/10">
                  {wf.scenario}
                </Badge>
              </div>
              <div className="flex justify-between items-center text-xs text-muted-foreground">
                <span>Fitness: <span className="text-[#f59e0b]">{wf.best_fitness}</span></span>
                <span>{new Date(wf.created_at).toLocaleDateString()}</span>
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                className="w-full mt-2 opacity-0 group-hover:opacity-100 transition-opacity h-7 text-xs border-[#30363d]"
                onClick={() => emitScenarioSelect(wf.scenario)}
                data-testid={`btn-apply-workflow-${wf.id}`}
              >
                <Plus size={14} className="mr-1" /> Apply Topologies
              </Button>
            </div>
          ))}
          {workflows.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-8">
              No saved workflows
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
