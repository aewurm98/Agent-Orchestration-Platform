import { useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useSocket } from "@/hooks/useSocket";

import GameViewport from "@/components/GameViewport";
import MetricsBar from "@/components/MetricsBar";
import DAGVisualizer from "@/components/DAGVisualizer";
import EvoDashboard from "@/components/EvoDashboard";
import TracePanel from "@/components/TracePanel";
import WorkflowLibrary from "@/components/WorkflowLibrary";
import HITLModal from "@/components/HITLModal";
import PixelGradient from "@/components/PixelGradient";

export default function Arena() {
  const { isRunning, currentGeneration, emitScenarioSelect, emitStartEvolution, clearSessionState, mfgState } = useSocket();
  const [scenario, setScenario] = useState("Supply Chain");
  const [boundaryMode, setBoundaryMode] = useState<"INTRA" | "INTER">("INTRA");
  const [mutationStrategy, setMutationStrategy] = useState<"MATH" | "LLM">("MATH");
  const [interTicks, setInterTicks] = useState(100);
  const [isHitl, setIsHitl] = useState(false);
  const [sidePanelOpen, setSidePanelOpen] = useState(true);

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
          inter_ticks: interTicks,
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

  const selectTriggerClass =
    "h-9 text-xs bg-white border border-[#ebe5d6] text-[#14120e] rounded-lg hover:border-[#14120e]/30 transition-colors shadow-none";
  const selectContentClass = "bg-white border border-[#ebe5d6] text-[#14120e] rounded-xl shadow-lg";

  return (
    <div className="flex flex-col h-[100dvh] w-full p-3 gap-3 text-foreground overflow-hidden font-sans">
      <HITLModal />
      <WorkflowLibrary />

      {/* TOP BAR — white tile */}
      <header className="shrink-0 tile rounded-2xl px-4 h-[60px] flex items-center justify-between z-10 shadow-sm">
        <div className="flex items-center gap-3">
          {/* Brand: pixel-gradient dot + wordmark */}
          <div className="flex items-center gap-2.5 mr-2">
            <div className="w-8 h-8 rounded-lg overflow-hidden pixel-gradient" aria-hidden="true" />
            <span className="font-semibold tracking-tight text-[15px] text-[#14120e]">
              AE&nbsp;<span className="text-[#6b6359] font-medium">Arena</span>
            </span>
          </div>

          {/* Scenario selector */}
          <Select value={scenario} onValueChange={handleScenarioChange} disabled={isRunning}>
            <SelectTrigger
              className={`w-[160px] ${selectTriggerClass}`}
              data-testid="select-scenario"
            >
              <SelectValue placeholder="Scenario" />
            </SelectTrigger>
            <SelectContent className={selectContentClass}>
              <SelectItem value="Supply Chain">Supply Chain</SelectItem>
              <SelectItem value="Disaster Relief">Disaster Relief</SelectItem>
              <SelectItem value="Peer Agents">Peer Agents</SelectItem>
              <SelectItem value="Manufacturing">Manufacturing</SelectItem>
            </SelectContent>
          </Select>

          {/* Boundary mode selector */}
          <Select
            value={boundaryMode}
            onValueChange={(v) => {
              const bm = v as "INTRA" | "INTER";
              setBoundaryMode(bm);
              if (bm === "INTRA") setMutationStrategy("MATH");
            }}
            disabled={isRunning}
          >
            <SelectTrigger
              className={`w-[110px] ${selectTriggerClass}`}
              data-testid="select-boundary-mode"
            >
              <SelectValue placeholder="Boundary" />
            </SelectTrigger>
            <SelectContent className={selectContentClass}>
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
              className={`w-[100px] ${selectTriggerClass}`}
              data-testid="select-mutation-strategy"
            >
              <SelectValue placeholder="Mutate" />
            </SelectTrigger>
            <SelectContent className={selectContentClass}>
              <SelectItem value="MATH">
                <span className="font-mono">MATH</span>
              </SelectItem>
              <SelectItem value="LLM" disabled={boundaryMode === "INTRA"}>
                <span className="font-mono">LLM</span>
              </SelectItem>
            </SelectContent>
          </Select>

          {/* Episode length — only visible in INTER mode */}
          {boundaryMode === "INTER" && (
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-[#6b6359] font-mono uppercase tracking-wider">T=</span>
              <input
                type="number"
                min={10}
                max={500}
                step={10}
                value={interTicks}
                onChange={(e) => setInterTicks(Math.max(10, Math.min(500, Number(e.target.value))))}
                disabled={isRunning}
                className="w-[60px] h-9 text-xs bg-white border border-[#ebe5d6] text-[#14120e] rounded-lg px-2 font-mono focus:outline-none focus:border-[#14120e] disabled:opacity-40"
              />
            </div>
          )}

          {/* Primary CTA — charcoal pill (matches "Start Free Trial") */}
          <Button
            size="sm"
            className="h-9 px-5 text-xs font-semibold bg-[#14120e] text-[#f4f0e7] hover:bg-[#2a2620] rounded-lg shadow-none disabled:opacity-40"
            onClick={handleStart}
            disabled={isRunning}
            data-testid="btn-start"
          >
            Start Free Trial
          </Button>

          {/* Stop button — outlined danger */}
          {isRunning && (
            <Button
              size="sm"
              className="h-9 px-5 text-xs font-semibold bg-white text-[#b91c1c] border border-[#b91c1c]/30 hover:bg-[#b91c1c]/5 rounded-lg shadow-none"
              onClick={handleStop}
              data-testid="btn-stop"
            >
              Stop
            </Button>
          )}
        </div>

        <div className="flex items-center gap-5">
          {/* Mode indicator badges */}
          {isRunning && (
            <div className="flex items-center gap-2">
              <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-semibold border ${
                boundaryMode === "INTER"
                  ? "border-[#14120e]/20 text-[#14120e] bg-white"
                  : "border-[#ebe5d6] text-[#6b6359] bg-[#efe9d9]"
              }`}>
                {boundaryMode}
              </span>
              <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-semibold border ${
                mutationStrategy === "LLM"
                  ? "border-[#14120e]/20 text-[#14120e] bg-white"
                  : "border-[#ebe5d6] text-[#6b6359] bg-[#efe9d9]"
              }`}>
                {mutationStrategy}
              </span>
            </div>
          )}

          <div className="flex items-center gap-2">
            <Label htmlFor="mode-toggle" className="text-[11px] text-[#6b6359] uppercase tracking-wider">
              {isHitl ? "HITL" : "Auto"}
            </Label>
            <Switch
              id="mode-toggle"
              checked={isHitl}
              onCheckedChange={setIsHitl}
              disabled={isRunning}
              className="data-[state=checked]:bg-[#14120e]"
            />
          </div>

          {/* Generation counter — dark pill (matches "01 AI sorts" ring in inspo) */}
          <div className="flex items-center gap-3 tile-dark rounded-full pl-3 pr-4 py-1.5">
            <span className="text-[10px] uppercase tracking-widest text-[#f4f0e7]/60">Gen</span>
            <span className="font-mono text-[#f4f0e7] font-bold text-base leading-none tabular-nums">
              {currentGeneration.toString().padStart(4, "0")}
            </span>
          </div>
        </div>
      </header>

      {/* CONTENT — modular tiles */}
      <main className="flex-1 flex gap-3 overflow-hidden">
        {/* LEFT COLUMN — full height for manufacturing (no metrics bar) */}
        <div className={`flex flex-col gap-3 transition-all duration-300 ${sidePanelOpen ? "w-[55%]" : "flex-1"}`}>
          {mfgState?.grid ? (
            <div className="flex-1 tile rounded-2xl overflow-hidden shadow-sm relative">
              <GameViewport />
            </div>
          ) : (
            <>
              <div className="h-[65%] tile rounded-2xl overflow-hidden shadow-sm relative">
                <GameViewport />
              </div>
              <div className="h-[35%] tile rounded-2xl overflow-hidden shadow-sm">
                <MetricsBar />
              </div>
            </>
          )}
        </div>

        {/* RIGHT COLUMN — light tile with charcoal tab pills */}
        {sidePanelOpen ? (
          <div className="w-[45%] tile rounded-2xl overflow-hidden shadow-sm flex flex-col relative">
            <button
              onClick={() => setSidePanelOpen(false)}
              className="absolute top-3 right-3 z-20 w-7 h-7 rounded-full flex items-center justify-center text-[#6b6359] hover:text-[#14120e] hover:bg-[#efe9d9] transition-colors"
              aria-label="Collapse side panel"
              data-testid="btn-collapse-side"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <Tabs defaultValue="dag" className="w-full h-full flex flex-col">
              <div className="px-3 pt-3 pr-12 shrink-0 border-b border-[#ebe5d6]">
                <TabsList className="bg-transparent border-none gap-1 p-0 h-auto">
                  {["DAG", "Evolution", "Traces", "Library"].map((tab) => (
                    <TabsTrigger
                      key={tab}
                      value={tab.toLowerCase()}
                      className="data-[state=active]:bg-[#14120e] data-[state=active]:text-[#f4f0e7] data-[state=inactive]:text-[#6b6359] data-[state=inactive]:hover:text-[#14120e] data-[state=inactive]:hover:bg-[#efe9d9] rounded-full px-3.5 py-1.5 text-xs font-medium tracking-wide transition-colors mb-2"
                    >
                      {tab}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </div>

              <div className="flex-1 overflow-hidden relative bg-white">
                <TabsContent value="dag" className="m-0 h-full data-[state=inactive]:hidden">
                  <DAGVisualizer />
                </TabsContent>
                <TabsContent value="evolution" className="m-0 h-full data-[state=inactive]:hidden">
                  <EvoDashboard />
                </TabsContent>
                <TabsContent value="traces" className="m-0 h-full data-[state=inactive]:hidden">
                  <TracePanel />
                </TabsContent>
                <TabsContent value="library" className="m-0 h-full data-[state=inactive]:hidden p-6">
                  <div className="text-[#6b6359] text-sm">
                    Expand the library sidebar on the left to view and apply saved workflows.
                  </div>
                </TabsContent>
              </div>
            </Tabs>
          </div>
        ) : (
          <button
            onClick={() => setSidePanelOpen(true)}
            className="tile rounded-2xl shadow-sm w-11 flex items-center justify-center text-[#6b6359] hover:text-[#14120e] hover:bg-[#efe9d9] transition-colors"
            aria-label="Expand side panel"
            data-testid="btn-expand-side"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}
      </main>

      {/* Subtle decorative pixel-gradient strip behind the layout (bottom-left) */}
      <div className="pointer-events-none fixed -bottom-12 -left-12 w-[340px] h-[110px] opacity-40 -z-0">
        <PixelGradient cols={26} rows={6} cell={12} gap={2} />
      </div>
    </div>
  );
}
