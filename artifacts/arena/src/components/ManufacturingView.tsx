import { useMemo } from "react";
import { useSocket } from "@/hooks/useSocket";
import type { GameState, AgentThought, MfgGameState } from "@/context/SocketContext";
import GridCanvas from "@/components/manufacturing/GridCanvas";
import ManufacturingHUD from "@/components/manufacturing/ManufacturingHUD";

// ── V2 Grid-based Manufacturing View ─────────────────────────────────────────

function ManufacturingV2({ state }: { state: MfgGameState }) {
  return (
    <div className="w-full h-full flex bg-[#ebe5d6] overflow-hidden">
      <div className="flex-1 min-w-0 relative">
        <GridCanvas state={state} />
      </div>
      <div
        className="shrink-0 overflow-y-auto border-l border-[#faf6ed]"
        style={{ width: "220px" }}
      >
        <ManufacturingHUD state={state} />
      </div>
    </div>
  );
}

// ── Legacy 3-stage Pipeline View ──────────────────────────────────────────────

const STAGE_CONFIG = [
  {
    id:       "raw_materials",
    agentId:  "worker_raw_materials",
    label:    "Raw Materials",
    emoji:    "⛏️",
    color:    "#b91c1c",
    inputKey: "raw_input" as const,
    cap:      300,
  },
  {
    id:       "intermediates",
    agentId:  "worker_intermediates",
    label:    "Intermediates",
    emoji:    "⚙️",
    color:    "#b45309",
    inputKey: "inter_input" as const,
    cap:      200,
  },
  {
    id:       "finished_product",
    agentId:  "worker_finished_product",
    label:    "Finished Product",
    emoji:    "📦",
    color:    "#15803d",
    inputKey: "finished_output" as const,
    cap:      150,
  },
] as const;

const STATE_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  processing: { label: "⚡ Processing", color: "#14120e", bg: "#14120e18" },
  blocked:    { label: "🔴 Blocked",    color: "#b91c1c", bg: "#b91c1c18" },
  idle:       { label: "💤 Idle",       color: "#6b6359", bg: "#6b635918" },
};

function BufferBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = Math.min((value / Math.max(max, 1)) * 100, 100);
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-[10px] font-mono">
        <span className="text-[#6b6359]">{label}</span>
        <span style={{ color }}>{value}</span>
      </div>
      <div className="h-[6px] rounded-full bg-[#faf6ed] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function AgentCard({
  emoji, label, color, state, inputBuffer, outputBuffer,
  inputCap, outputCap, lastTrace,
}: {
  emoji: string; label: string; color: string; state: string;
  inputBuffer: number; outputBuffer: number; inputCap: number; outputCap: number;
  lastTrace: AgentThought | null;
}) {
  const badge = STATE_BADGE[state] ?? STATE_BADGE.idle;
  return (
    <div
      className="flex flex-col gap-2 rounded-lg p-3 border transition-all duration-300"
      style={{
        borderColor: color + "44",
        backgroundColor: color + "08",
        boxShadow: state === "processing" ? `0 0 12px ${color}22` : undefined,
      }}
    >
      <div className="flex items-center gap-2">
        <span className="text-xl">{emoji}</span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold truncate" style={{ color }}>{label}</p>
          <p className="text-[10px] text-[#6b6359]">Worker Agent</p>
        </div>
      </div>
      <div
        className="text-[10px] font-mono px-2 py-0.5 rounded-full w-fit"
        style={{ color: badge.color, backgroundColor: badge.bg, border: `1px solid ${badge.color}44` }}
      >
        {badge.label}
      </div>
      <div className="space-y-1.5">
        <BufferBar label="IN BUFFER"  value={inputBuffer}  max={inputCap}  color={color} />
        <BufferBar label="OUT BUFFER" value={outputBuffer} max={outputCap} color={color + "bb"} />
      </div>
      {lastTrace?.reasoning && (
        <div className="text-[9px] font-mono text-[#6b6359] italic border-t border-[#ebe5d6] pt-1.5 line-clamp-3 leading-relaxed">
          "{lastTrace.reasoning}"
        </div>
      )}
      {lastTrace?.action && (
        <div className="text-[10px] font-mono" style={{ color }}>
          → {lastTrace.action}
          {lastTrace.parameters && Object.keys(lastTrace.parameters).length > 0 && (
            <span className="text-[#6b6359] ml-1">({JSON.stringify(lastTrace.parameters)})</span>
          )}
        </div>
      )}
    </div>
  );
}

function PlannerCard({ lastTrace }: { lastTrace: AgentThought | null }) {
  return (
    <div className="flex items-start gap-3 rounded-lg p-3 border" style={{ borderColor: "#7c3aed44", backgroundColor: "#7c3aed08" }}>
      <span className="text-2xl mt-0.5">🧠</span>
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2">
          <p className="text-xs font-semibold text-[#7c3aed]">Planner Agent</p>
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded-full"
            style={{ color: "#7c3aed", backgroundColor: "#7c3aed18", border: "1px solid #7c3aed44" }}
          >
            {lastTrace?.action ?? "querying"}
          </span>
        </div>
        {lastTrace?.reasoning ? (
          <p className="text-[10px] font-mono text-[#6b6359] italic leading-relaxed line-clamp-2">
            "{lastTrace.reasoning}"
          </p>
        ) : (
          <p className="text-[10px] text-[#8b8378]">Awaiting pipeline data…</p>
        )}
        {lastTrace?.content && (
          <p className="text-[10px] font-mono text-[#8b8378] truncate">{lastTrace.content}</p>
        )}
      </div>
    </div>
  );
}

function FlowArrow({ color }: { color: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-1 shrink-0 self-center">
      <div className="w-6 h-[2px] relative" style={{ backgroundColor: color + "66" }}>
        <div
          className="absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0"
          style={{ borderTop: "4px solid transparent", borderBottom: "4px solid transparent", borderLeft: `6px solid ${color}66` }}
        />
      </div>
      <span className="text-[8px] font-mono" style={{ color: color + "88" }}>flow</span>
    </div>
  );
}

function ManufacturingLegacy({ gameState }: { gameState: GameState }) {
  const { traces } = useSocket();

  const latestByAgent = useMemo(() => {
    const map: Record<string, AgentThought> = {};
    for (const t of traces) {
      if (t.agent_name) map[t.agent_name] = t;
    }
    return map;
  }, [traces]);

  const res = gameState.resources;
  const agents = Array.isArray(gameState.agents) ? gameState.agents : [];
  const stateByStageId: Record<string, string> = {};
  const outputByStageId: Record<string, number> = {};
  for (const a of agents) {
    stateByStageId[a.id] = a.state;
    outputByStageId[a.id] = a.inventory;
  }

  const plannerTrace = latestByAgent["planner_1"] ?? null;
  const inputBuffers: Record<string, number> = {
    raw_materials:    res.raw_input    ?? 0,
    intermediates:    res.inter_input  ?? 0,
    finished_product: res.finished_output ?? 0,
  };

  return (
    <div className="w-full h-full flex flex-col bg-transparent p-3 gap-3 overflow-hidden">
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-[#7c3aed] animate-pulse shadow-[0_0_6px_#7c3aed]" />
          <span className="text-xs font-semibold tracking-widest text-[#7c3aed]">MANUFACTURING PIPELINE</span>
        </div>
        <div className="flex items-center gap-4 text-[10px] font-mono text-[#6b6359]">
          <span>Tick: <span className="text-[#14120e]">{gameState.tick}</span></span>
          <span>Score: <span className="text-[#15803d]">{gameState.score.toFixed(3)}</span></span>
          <span>Approved: <span className="text-[#b45309]">{res.approved_finished ?? 0}</span></span>
        </div>
      </div>
      <div className="shrink-0"><PlannerCard lastTrace={plannerTrace} /></div>
      <div className="flex-1 flex items-stretch gap-0 min-h-0">
        {STAGE_CONFIG.map((stage, idx) => (
          <div key={stage.id} className="flex items-stretch flex-1">
            <AgentCard
              emoji={stage.emoji}
              label={stage.label}
              color={stage.color}
              state={stateByStageId[stage.id] ?? "idle"}
              inputBuffer={inputBuffers[stage.id] ?? 0}
              outputBuffer={outputByStageId[stage.id] ?? 0}
              inputCap={stage.cap}
              outputCap={Math.floor(stage.cap * 0.6)}
              lastTrace={latestByAgent[stage.agentId] ?? null}
            />
            {idx < STAGE_CONFIG.length - 1 && <FlowArrow color={STAGE_CONFIG[idx + 1].color} />}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main export — routes between v2 grid and legacy pipeline ──────────────────

export default function ManufacturingView({ gameState }: { gameState: GameState }) {
  const { mfgState } = useSocket();

  if (mfgState && mfgState.grid) {
    return <ManufacturingV2 state={mfgState} />;
  }

  return <ManufacturingLegacy gameState={gameState} />;
}
