import { useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useSocket } from "@/hooks/useSocket";

import GameViewport from "@/components/GameViewport";
import MetricsBar from "@/components/MetricsBar";
import DAGVisualizer from "@/components/DAGVisualizer";
import EvoDashboard from "@/components/EvoDashboard";
import TracePanel from "@/components/TracePanel";
import WorkflowLibrary from "@/components/WorkflowLibrary";
import HITLModal from "@/components/HITLModal";

export default function Arena() {
  const { isRunning, currentGeneration, emitScenarioSelect, emitStartEvolution, clearSessionState } = useSocket();
  const [scenario, setScenario] = useState("Supply Chain");
  const [boundaryMode, setBoundaryMode] = useState<"INTRA" | "INTER">("INTRA");
  const [mutationStrategy, setMutationStrategy] = useState<"MATH" | "LLM">("MATH");
  const [isHitl, setIsHitl] = useState(false);

  const handleStart = async () => {
    try {
      await fetch("/api/scenario/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario,
          mode: isHitl ? "hitl" : "autonomous",
          boundary_mode: boundaryMode,
          mutation_strategy: mutationStrategy,
        }),
      });
      emitStartEvolution();
    } catch (e) {
      console.error(e);
    }
  };

  const handleStop = async () => {
    try {
      await fetch("/api/scenario/stop", { method: "POST" });
      clearSessionState();
    } catch (e) {
      console.error(e);
    }
  };

  const handleScenarioChange = (val: string) => {
    setScenario(val);
    emitScenarioSelect(val);
  };

  return (
    <div className="flex flex-col h-[100dvh] w-full bg-[#0d1117] text-foreground overflow-hidden font-sans">
      <HITLModal />
      <WorkflowLibrary />

      {/* TOP BAR */}
      <header className="h-[50px] shrink-0 border-b border-[#30363d] bg-[#161b22] px-4 flex items-center justify-between z-10 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-[#e6edf3] font-bold tracking-widest text-sm mr-2">
            <div className="w-2 h-2 rounded-full bg-[#00d9ff] animate-pulse shadow-[0_0_8px_#00d9ff]"></div>
            AE:ARENA
          </div>

          {/* Scenario selector */}
          <Select value={scenario} onValueChange={handleScenarioChange} disabled={isRunning}>
            <SelectTrigger
              className="w-[160px] h-8 text-xs bg-[#0d1117] border-[#30363d] text-[#e6edf3]"
              data-testid="select-scenario"
            >
              <SelectValue placeholder="Scenario" />
            </SelectTrigger>
            <SelectContent className="bg-[#161b22] border-[#30363d] text-[#e6edf3]">
              <SelectItem value="Supply Chain">Supply Chain</SelectItem>
              <SelectItem value="Disaster Relief">Disaster Relief</SelectItem>
              <SelectItem value="Peer Agents">Peer Agents</SelectItem>
              <SelectItem value="Manufacturing">Manufacturing</SelectItem>
            </SelectContent>
          </Select>

          {/* Boundary mode selector */}
          <Select
            value={boundaryMode}
            onValueChange={(v) => setBoundaryMode(v as "INTRA" | "INTER")}
            disabled={isRunning}
          >
            <SelectTrigger
              className="w-[110px] h-8 text-xs bg-[#0d1117] border-[#30363d] text-[#e6edf3]"
              data-testid="select-boundary-mode"
            >
              <SelectValue placeholder="Boundary" />
            </SelectTrigger>
            <SelectContent className="bg-[#161b22] border-[#30363d] text-[#e6edf3]">
              <SelectItem value="INTRA">
                <span className="font-mono">INTRA</span>
              </SelectItem>
              <SelectItem value="INTER">
                <span className="font-mono">INTER</span>
              </SelectItem>
            </SelectContent>
          </Select>

          {/* Mutation strategy selector */}
          <Select
            value={mutationStrategy}
            onValueChange={(v) => setMutationStrategy(v as "MATH" | "LLM")}
            disabled={isRunning}
          >
            <SelectTrigger
              className="w-[100px] h-8 text-xs bg-[#0d1117] border-[#30363d] text-[#e6edf3]"
              data-testid="select-mutation-strategy"
            >
              <SelectValue placeholder="Mutate" />
            </SelectTrigger>
            <SelectContent className="bg-[#161b22] border-[#30363d] text-[#e6edf3]">
              <SelectItem value="MATH">
                <span className="font-mono">MATH</span>
              </SelectItem>
              <SelectItem value="LLM">
                <span className="font-mono">LLM</span>
              </SelectItem>
            </SelectContent>
          </Select>

          {/* Distinct Start button */}
          <Button
            size="sm"
            className="h-8 px-5 text-xs font-semibold bg-[#00d9ff] text-[#0d1117] hover:bg-[#00d9ff]/80 disabled:opacity-40"
            onClick={handleStart}
            disabled={isRunning}
            data-testid="btn-start"
          >
            INITIATE
          </Button>

          {/* Distinct Stop button — only rendered while running */}
          {isRunning && (
            <Button
              size="sm"
              variant="destructive"
              className="h-8 px-5 text-xs font-semibold"
              onClick={handleStop}
              data-testid="btn-stop"
            >
              STOP
            </Button>
          )}
        </div>

        <div className="flex items-center gap-6">
          {/* Mode indicator badges */}
          {isRunning && (
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold border ${
                boundaryMode === "INTER"
                  ? "border-[#f59e0b] text-[#f59e0b] bg-[#f59e0b]/10"
                  : "border-[#30363d] text-[#8b949e]"
              }`}>
                {boundaryMode}
              </span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold border ${
                mutationStrategy === "LLM"
                  ? "border-[#a78bfa] text-[#a78bfa] bg-[#a78bfa]/10"
                  : "border-[#30363d] text-[#8b949e]"
              }`}>
                {mutationStrategy}
              </span>
            </div>
          )}

          <div className="flex items-center gap-2">
            <Label htmlFor="mode-toggle" className="text-xs text-muted-foreground uppercase tracking-wider">
              {isHitl ? "HITL Mode" : "Autonomous"}
            </Label>
            <Switch
              id="mode-toggle"
              checked={isHitl}
              onCheckedChange={setIsHitl}
              disabled={isRunning}
              className="data-[state=checked]:bg-[#f59e0b]"
            />
          </div>

          <div className="flex items-center gap-2 border-l border-[#30363d] pl-6">
            <span className="text-xs text-[#8b949e] uppercase tracking-wider">Generation</span>
            <span className="font-mono text-[#00d9ff] font-bold text-lg">
              {currentGeneration.toString().padStart(4, "0")}
            </span>
          </div>
        </div>
      </header>

      {/* CONTENT AREA */}
      <main className="flex-1 flex overflow-hidden">
        {/* LEFT COLUMN */}
        <div className="w-[55%] flex flex-col border-r border-[#30363d]">
          <div className="h-[65%] w-full relative">
            <GameViewport />
          </div>
          <div className="h-[35%] w-full border-t border-[#30363d]">
            <MetricsBar />
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div className="w-[45%] flex flex-col bg-[#161b22]">
          <Tabs defaultValue="dag" className="w-full h-full flex flex-col">
            <div className="border-b border-[#30363d] bg-[#0d1117] px-2 pt-2 shrink-0">
              <TabsList className="bg-transparent border-none gap-2 p-0 h-auto">
                {["DAG", "Evolution", "Traces", "Library"].map((tab) => (
                  <TabsTrigger
                    key={tab}
                    value={tab.toLowerCase()}
                    className="data-[state=active]:bg-[#161b22] data-[state=active]:text-[#00d9ff] data-[state=active]:border-b-2 data-[state=active]:border-[#00d9ff] rounded-none px-4 py-2 text-xs uppercase tracking-wider text-muted-foreground hover:text-[#e6edf3] transition-colors"
                  >
                    {tab}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>

            <div className="flex-1 overflow-hidden relative">
              <TabsContent value="dag" className="m-0 h-full data-[state=inactive]:hidden">
                <DAGVisualizer />
              </TabsContent>
              <TabsContent value="evolution" className="m-0 h-full data-[state=inactive]:hidden">
                <EvoDashboard />
              </TabsContent>
              <TabsContent value="traces" className="m-0 h-full data-[state=inactive]:hidden">
                <TracePanel />
              </TabsContent>
              <TabsContent value="library" className="m-0 h-full data-[state=inactive]:hidden p-4">
                <div className="text-muted-foreground text-sm">
                  Expand the library sidebar on the left to view and apply saved workflows.
                </div>
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </main>
    </div>
  );
}
