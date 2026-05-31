import { useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ChevronLeft, ChevronRight, BookOpen, Pause, Play } from "lucide-react";
import { Link } from "wouter";
import { useSocket } from "@/hooks/useSocket";

// ── Option metadata ─────────────────────────────────────────────────────────

const SCENARIOS = [
  {
    value: "Supply Chain",
    label: "Supply Chain",
    desc: "Supplier → Warehouses → Distributor → Retail shelves. EA learns to meet customer demand without stockouts.",
  },
  {
    value: "Manufacturing",
    label: "Manufacturing",
    desc: "3-stage factory flow graph (Molding/Wire → Assembly → Packaging). EA tunes machine capacities, conveyor bandwidths & maintenance to maximise profit.",
  },
] as const;

type MutationStrategy = "MATH" | "DEAP" | "LLM";

// The first tab swaps by scenario: manufacturing shows the agent DAG, while
// supply chain (no agent↔tool graph to draw) shows live network telemetry.
const DAG_INFO =
  "Topology of agent ↔ tool connections. Click a node to inspect its tools, recent actions, and system prompt.";
const NETWORK_INFO =
  "Live supply-chain telemetry — GLS trend, fleet status, and per-node stock & demand fulfilment as the sim runs.";
const TAB_INFO: Record<string, string> = {
  Evolution: "Fitness curve over generations + recent evolutionary history. Tracks genome improvements.",
  Traces: "Live agent thought stream — each agent's reasoning as it acts. Streams as the simulation runs.",
  Library: "Saved workflows from past runs. Apply a known-good topology to a new run.",
};

// Renders a dropdown row: short label + small description below.
function OptionRow({ label, desc, mono }: { label: string; desc: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 py-0.5 max-w-[280px]">
      <span className={`text-[12px] font-semibold text-[#14120e] ${mono ? "font-mono" : ""}`}>
        {label}
      </span>
      <span className="text-[10px] text-[#6b6359] leading-snug whitespace-normal">
        {desc}
      </span>
    </div>
  );
}

import GameViewport from "@/components/GameViewport";
import MetricsBar from "@/components/MetricsBar";
import DAGVisualizer from "@/components/DAGVisualizer";
import SupplyChainDashboard from "@/components/SupplyChainDashboard";
import EvoDashboard from "@/components/EvoDashboard";
import TracePanel from "@/components/TracePanel";
import WorkflowLibrary from "@/components/WorkflowLibrary";
import HITLModal from "@/components/HITLModal";

export default function Arena() {
  const { isRunning, isPaused, currentGeneration, emitScenarioSelect, emitStartEvolution, emitPause, emitResume, emitSetSpeed, clearSessionState, mfgState } = useSocket();
  const [scenario, setScenario] = useState("Supply Chain");
  const [boundaryMode, setBoundaryMode] = useState<"INTRA" | "INTER">("INTRA");
  const [mutationStrategy, setMutationStrategy] = useState<MutationStrategy>("LLM");
  const [interTicks, setInterTicks] = useState(500);
  const [speed, setSpeed] = useState("1");
  const [sidePanelOpen, setSidePanelOpen] = useState(true);
  const [libraryOpen, setLibraryOpen] = useState(false);

  const handleSpeedChange = (val: string) => {
    setSpeed(val);
    emitSetSpeed(parseFloat(val));
  };

  const handleStart = async () => {
    try {
      await fetch("/api/scenario/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario,
          mode: "autonomous",
          boundary_mode: boundaryMode,
          // `engine` is the canonical field name on the backend; `mutation_strategy`
          // is the legacy name and is still accepted as a fallback.
          engine: mutationStrategy,
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
    if (val === "Manufacturing") {
      setBoundaryMode("INTER");
      setInterTicks(500);
    } else {
      setBoundaryMode("INTRA");
      setInterTicks(500);
    }
  };

  const selectTriggerClass =
    "h-9 text-xs bg-white border border-[#ebe5d6] text-[#14120e] rounded-lg hover:border-[#14120e]/30 transition-colors shadow-none";
  const selectContentClass = "bg-white border border-[#ebe5d6] text-[#14120e] rounded-xl shadow-lg";

  // The first side-panel tab swaps by scenario: manufacturing keeps the agent
  // DAG; supply chain has no such graph, so it shows a network telemetry board.
  const isSupplyChain = scenario === "Supply Chain";
  const firstTab = isSupplyChain
    ? { label: "Network", value: "dag", info: NETWORK_INFO }
    : { label: "DAG", value: "dag", info: DAG_INFO };
  const tabs = [
    firstTab,
    { label: "Evolution", value: "evolution", info: TAB_INFO.Evolution },
    { label: "Traces", value: "traces", info: TAB_INFO.Traces },
    { label: "Library", value: "library", info: TAB_INFO.Library },
  ];

  return (
    <div className="flex flex-col h-[100dvh] w-full p-3 gap-3 text-foreground overflow-hidden font-sans">
      <HITLModal />
      <WorkflowLibrary open={libraryOpen} onOpenChange={setLibraryOpen} />

      {/* TOP BAR — white tile */}
      <header className="shrink-0 tile rounded-2xl px-5 h-[60px] flex items-center justify-between z-10 shadow-sm">
        <div className="flex items-center gap-2">
          {/* Brand: organic morphing blob + wordmark — links to the landing page */}
          <Link href="/" className="flex items-center gap-2.5 mr-2 cursor-pointer" data-testid="brand-home">
            <div className="w-8 h-8 blob-stretch" aria-hidden="true">
              <div className="w-full h-full overflow-hidden pixel-gradient blob" />
            </div>
            <span className="font-serif text-[26px] leading-none text-[#14120e]">AERA</span>
          </Link>

          {/* Scenario selector — compact trigger, rich dropdown */}
          <Select value={scenario} onValueChange={handleScenarioChange} disabled={isRunning}>
            <SelectTrigger
              className={`w-[160px] ${selectTriggerClass}`}
              data-testid="select-scenario"
            >
              <SelectValue placeholder="Scenario">{scenario}</SelectValue>
            </SelectTrigger>
            <SelectContent className={selectContentClass}>
              {SCENARIOS.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  <OptionRow label={s.label} desc={s.desc} />
                </SelectItem>
              ))}
            </SelectContent>
          </Select>



          {/* Divider between config selectors and run controls */}
          <div className="w-px h-5 bg-[#ebe5d6] mx-2" />

          {/* Run controls — given their own flex group for consistent spacing */}
          <div className="flex items-center gap-2 shrink-0">
            <Button
              size="sm"
              className="h-9 px-4 text-xs font-semibold bg-[#14120e] text-[#f4f0e7] hover:bg-[#2a2620] rounded-lg shadow-none disabled:opacity-40"
              onClick={handleStart}
              disabled={isRunning}
              data-testid="btn-start"
            >
              Run Evolution
            </Button>

            {isRunning && (
              <>
                <Tooltip delayDuration={250}>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      className="h-9 w-9 p-0 bg-white text-[#14120e] border border-[#ebe5d6] hover:border-[#14120e]/30 hover:bg-[#faf7f0] rounded-lg shadow-none"
                      onClick={isPaused ? emitResume : emitPause}
                      data-testid="btn-pause"
                      aria-label={isPaused ? "Resume" : "Pause"}
                    >
                      {isPaused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" sideOffset={6} className="text-[11px] bg-[#14120e] text-[#f4f0e7] border-[#14120e]">
                    {isPaused ? "Resume run" : "Pause run (state is kept)"}
                  </TooltipContent>
                </Tooltip>
                <Button
                  size="sm"
                  className="h-9 px-4 text-xs font-semibold bg-white text-[#b91c1c] border border-[#b91c1c]/30 hover:bg-[#b91c1c]/5 rounded-lg shadow-none"
                  onClick={handleStop}
                  data-testid="btn-stop"
                >
                  Stop Run
                </Button>

                {/* Playback speed — controls how fast each episode streams */}
                <Tooltip delayDuration={250}>
                  <TooltipTrigger asChild>
                    <div>
                      <Select value={speed} onValueChange={handleSpeedChange}>
                        <SelectTrigger
                          className={`w-[72px] ${selectTriggerClass}`}
                          data-testid="select-speed"
                        >
                          <SelectValue>{speed}×</SelectValue>
                        </SelectTrigger>
                        <SelectContent className={selectContentClass}>
                          {["0.5", "1", "2", "4", "8"].map((s) => (
                            <SelectItem key={s} value={s}>
                              {s}×
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" sideOffset={6} className="max-w-[240px] text-[11px] leading-snug bg-[#14120e] text-[#f4f0e7] border-[#14120e]">
                    Episode playback speed. Note: the LLM optimizer's per-generation thinking time is fixed and not affected by this.
                  </TooltipContent>
                </Tooltip>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Mode indicator badges — shown while running */}
          {isRunning && (
            <>
              <div className="flex items-center gap-2">
                <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-semibold border ${
                  boundaryMode === "INTER"
                    ? "border-[#4F7CFF]/30 text-[#4F7CFF] bg-[#EEF3FF]"
                    : "border-[#ebe5d6] text-[#6b6359] bg-[#efe9d9]"
                }`}>
                  {boundaryMode}
                </span>
                <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-semibold border ${
                  mutationStrategy === "LLM"
                    ? "border-[#8B5CF6]/30 text-[#8B5CF6] bg-[#F5F3FF]"
                    : mutationStrategy === "DEAP"
                    ? "border-[#10b981]/30 text-[#10b981] bg-[#ecfdf5]"
                    : "border-[#ebe5d6] text-[#6b6359] bg-[#efe9d9]"
                }`}>
                  {mutationStrategy}
                </span>
              </div>
              <div className="w-px h-6 bg-[#ebe5d6]" />
            </>
          )}

          {/* Generation counter — dark pill */}
          <Tooltip delayDuration={250}>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-3 tile-dark rounded-full pl-3 pr-4 py-1.5 cursor-help">
                <span className="text-[10px] uppercase tracking-widest text-[#f4f0e7]/60">Gen</span>
                <span className="font-mono text-[#f4f0e7] font-bold text-base leading-none tabular-nums">
                  {currentGeneration.toString().padStart(4, "0")}
                </span>
              </div>
            </TooltipTrigger>
            <TooltipContent
              side="bottom"
              sideOffset={6}
              className="max-w-[240px] text-[11px] leading-snug bg-[#14120e] text-[#f4f0e7] border-[#14120e]"
            >
              Generation count — how many evolutionary cycles have completed since the run started.
            </TooltipContent>
          </Tooltip>

          <div className="w-px h-6 bg-[#ebe5d6]" />

          {/* Developer reference — the API-docs view of the engine */}
          <Link
            href="/docs"
            className="flex items-center gap-1.5 h-9 px-3.5 text-xs font-semibold text-[#14120e] border border-[#ebe5d6] rounded-lg hover:border-[#14120e]/30 hover:bg-[#faf7f0] transition-colors"
            data-testid="link-docs"
          >
            <BookOpen className="w-3.5 h-3.5" />
            Docs
          </Link>
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
                  {tabs.map((tab) => (
                    <Tooltip key={tab.value} delayDuration={250}>
                      <TooltipTrigger asChild>
                        <TabsTrigger
                          value={tab.value}
                          className="data-[state=active]:bg-[#14120e] data-[state=active]:text-[#f4f0e7] data-[state=inactive]:text-[#6b6359] data-[state=inactive]:hover:text-[#14120e] data-[state=inactive]:hover:bg-[#efe9d9] rounded-full px-3.5 py-1.5 text-xs font-medium tracking-wide transition-colors mb-2"
                        >
                          {tab.label}
                        </TabsTrigger>
                      </TooltipTrigger>
                      <TooltipContent
                        side="bottom"
                        sideOffset={6}
                        className="max-w-[260px] text-[11px] leading-snug bg-[#14120e] text-[#f4f0e7] border-[#14120e]"
                      >
                        {tab.info}
                      </TooltipContent>
                    </Tooltip>
                  ))}
                </TabsList>
              </div>

              <div className="flex-1 overflow-hidden relative bg-white">
                <TabsContent value="dag" className="m-0 h-full data-[state=inactive]:hidden">
                  {isSupplyChain ? <SupplyChainDashboard /> : <DAGVisualizer />}
                </TabsContent>
                <TabsContent value="evolution" className="m-0 h-full data-[state=inactive]:hidden">
                  <EvoDashboard />
                </TabsContent>
                <TabsContent value="traces" className="m-0 h-full data-[state=inactive]:hidden">
                  <TracePanel />
                </TabsContent>
                <TabsContent value="library" className="m-0 h-full data-[state=inactive]:hidden">
                  <div className="w-full h-full flex flex-col items-center justify-center gap-4 p-8">
                    <div className="text-[#6b6359] text-sm text-center leading-relaxed max-w-[240px]">
                      Browse saved workflow topologies and load them into a new run.
                    </div>
                    <button
                      onClick={() => setLibraryOpen(true)}
                      className="h-9 px-5 text-xs font-semibold bg-[#14120e] text-[#f4f0e7] hover:bg-[#2a2620] rounded-lg transition-colors"
                    >
                      Open Workflow Library
                    </button>
                  </div>
                </TabsContent>
              </div>
            </Tabs>
          </div>
        ) : (
          <button
            onClick={() => setSidePanelOpen(true)}
            className="tile rounded-2xl shadow-sm w-11 flex flex-col items-center justify-center gap-3 py-4 text-[#6b6359] hover:text-[#14120e] hover:bg-[#efe9d9] transition-colors"
            aria-label="Expand side panel"
            data-testid="btn-expand-side"
          >
            <ChevronLeft className="w-4 h-4 shrink-0" />
            {[isSupplyChain ? "Net" : "DAG", "Evo", "Traces", "Lib"].map((t) => (
              <span key={t} className="text-[8px] font-semibold uppercase tracking-widest [writing-mode:vertical-rl] rotate-180 text-[#a89e8e]">
                {t}
              </span>
            ))}
          </button>
        )}
      </main>
    </div>
  );
}
