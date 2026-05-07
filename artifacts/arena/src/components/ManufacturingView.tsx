import { useMemo } from "react";
import { useSocket } from "@/hooks/useSocket";
import type { GameState, AgentThought } from "@/context/SocketContext";

// ── constants ────────────────────────────────────────────────────────────────

const STAGE_CONFIG = [
  {
    id:       "raw_materials",
    agentId:  "worker_raw_materials",
    label:    "Raw Materials",
    emoji:    "⛏️",
    color:    "#f87171",   // red
    inputKey: "raw_input" as const,
    cap:      300,
  },
  {
    id:       "intermediates",
    agentId:  "worker_intermediates",
    label:    "Intermediates",
    emoji:    "⚙️",
    color:    "#f59e0b",   // amber
    inputKey: "inter_input" as const,
    cap:      200,
  },
  {
    id:       "finished_product",
    agentId:  "worker_finished_product",
    label:    "Finished Product",
    emoji:    "📦",
    color:    "#7ee787",   // green
    inputKey: "finished_output" as const,
    cap:      150,
  },
] as const;

const STATE_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  processing: { label: "⚡ Processing", color: "#00d9ff", bg: "#00d9ff18" },
  blocked:    { label: "🔴 Blocked",    color: "#f87171", bg: "#f8717118" },
  idle:       { label: "💤 Idle",       color: "#8b949e", bg: "#8b949e18" },
};

// ── helpers ───────────────────────────────────────────────────────────────────

function BufferBar({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number;
  max: number;
  color: string;
}) {
  const pct = Math.min((value / Math.max(max, 1)) * 100, 100);
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-[10px] font-mono">
        <span className="text-[#8b949e]">{label}</span>
        <span style={{ color }}>{value}</span>
      </div>
      <div className="h-[6px] rounded-full bg-[#21262d] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function AgentCard({
  emoji,
  label,
  color,
  state,
  inputBuffer,
  outputBuffer,
  inputCap,
  outputCap,
  lastTrace,
}: {
  emoji: string;
  label: string;
  color: string;
  state: string;
  inputBuffer: number;
  outputBuffer: number;
  inputCap: number;
  outputCap: number;
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
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="text-xl">{emoji}</span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold truncate" style={{ color }}>
            {label}
          </p>
          <p className="text-[10px] text-[#8b949e]">Worker Agent</p>
        </div>
      </div>

      {/* State badge */}
      <div
        className="text-[10px] font-mono px-2 py-0.5 rounded-full w-fit"
        style={{ color: badge.color, backgroundColor: badge.bg, border: `1px solid ${badge.color}44` }}
      >
        {badge.label}
      </div>

      {/* Buffer bars */}
      <div className="space-y-1.5">
        <BufferBar label="IN BUFFER"  value={inputBuffer}  max={inputCap}  color={color} />
        <BufferBar label="OUT BUFFER" value={outputBuffer} max={outputCap} color={color + "bb"} />
      </div>

      {/* Latest reasoning */}
      {lastTrace?.reasoning && (
        <div className="text-[9px] font-mono text-[#8b949e] italic border-t border-[#30363d] pt-1.5 line-clamp-3 leading-relaxed">
          "{lastTrace.reasoning}"
        </div>
      )}
      {lastTrace?.action && (
        <div className="text-[10px] font-mono" style={{ color }}>
          → {lastTrace.action}
          {lastTrace.parameters && Object.keys(lastTrace.parameters).length > 0 && (
            <span className="text-[#8b949e] ml-1">
              ({JSON.stringify(lastTrace.parameters)})
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function PlannerCard({ lastTrace }: { lastTrace: AgentThought | null }) {
  const badge = {
    label: lastTrace?.action ?? "querying",
    color: "#a371f7",
  };

  return (
    <div
      className="flex items-start gap-3 rounded-lg p-3 border"
      style={{ borderColor: "#a371f744", backgroundColor: "#a371f708" }}
    >
      <span className="text-2xl mt-0.5">🧠</span>
      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2">
          <p className="text-xs font-semibold text-[#a371f7]">Planner Agent</p>
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded-full"
            style={{ color: "#a371f7", backgroundColor: "#a371f718", border: "1px solid #a371f744" }}
          >
            {badge.label}
          </span>
        </div>
        {lastTrace?.reasoning ? (
          <p className="text-[10px] font-mono text-[#8b949e] italic leading-relaxed line-clamp-2">
            "{lastTrace.reasoning}"
          </p>
        ) : (
          <p className="text-[10px] text-[#4d5566]">Awaiting pipeline data…</p>
        )}
        {lastTrace?.content && (
          <p className="text-[10px] font-mono text-[#6e7681] truncate">
            {lastTrace.content}
          </p>
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
          style={{
            borderTop: "4px solid transparent",
            borderBottom: "4px solid transparent",
            borderLeft: `6px solid ${color}66`,
          }}
        />
      </div>
      <span className="text-[8px] font-mono" style={{ color: color + "88" }}>flow</span>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function ManufacturingView({ gameState }: { gameState: GameState }) {
  const { traces } = useSocket();

  // Latest trace per agent_name (only manufacturing traces have agent_name)
  const latestByAgent = useMemo(() => {
    const map: Record<string, AgentThought> = {};
    for (const t of traces) {
      if (t.agent_name) map[t.agent_name] = t;
    }
    return map;
  }, [traces]);

  const res = gameState.resources;
  const agents = gameState.agents;

  // Find state per stage from the agents array (manufacturing to_json sends stages as agents)
  const stateByStageId = useMemo(() => {
    const m: Record<string, string> = {};
    for (const a of agents) {
      m[a.id] = a.state;
    }
    return m;
  }, [agents]);

  // Map output_buffer (inventory field) per stage
  const outputByStageId = useMemo(() => {
    const m: Record<string, number> = {};
    for (const a of agents) {
      m[a.id] = a.inventory;
    }
    return m;
  }, [agents]);

  const plannerTrace = latestByAgent["planner_1"] ?? null;

  const inputBuffers: Record<string, number> = {
    raw_materials:     res.raw_input    ?? 0,
    intermediates:     res.inter_input  ?? 0,
    finished_product:  res.finished_output ?? 0,
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#0d1117] p-3 gap-3 overflow-hidden">

      {/* ── HUD strip ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-[#a371f7] animate-pulse shadow-[0_0_6px_#a371f7]" />
          <span className="text-xs font-semibold tracking-widest text-[#a371f7]">
            MANUFACTURING PIPELINE
          </span>
        </div>
        <div className="flex items-center gap-4 text-[10px] font-mono text-[#8b949e]">
          <span>Tick: <span className="text-[#00d9ff]">{gameState.tick}</span></span>
          <span>Score: <span className="text-[#7ee787]">{gameState.score.toFixed(3)}</span></span>
          <span>Approved: <span className="text-[#f59e0b]">{res.approved_finished ?? 0}</span></span>
          <span>Total WIP: <span className="text-[#e6edf3]">{
            (res.raw_input ?? 0) + (res.inter_input ?? 0) + (res.finished_output ?? 0)
          }</span></span>
        </div>
      </div>

      {/* ── Planner card ──────────────────────────────────────────── */}
      <div className="shrink-0">
        <PlannerCard lastTrace={plannerTrace} />
      </div>

      {/* ── Pipeline row ──────────────────────────────────────────── */}
      <div className="flex-1 flex items-stretch gap-0 min-h-0">
        {STAGE_CONFIG.map((stage, idx) => {
          const inputBuffer  = inputBuffers[stage.id] ?? 0;
          const outputBuffer = outputByStageId[stage.id] ?? 0;
          const workerState  = stateByStageId[stage.id] ?? "idle";
          const lastTrace    = latestByAgent[stage.agentId] ?? null;

          return (
            <div key={stage.id} className="flex items-stretch flex-1">
              <AgentCard
                emoji={stage.emoji}
                label={stage.label}
                color={stage.color}
                state={workerState}
                inputBuffer={inputBuffer}
                outputBuffer={outputBuffer}
                inputCap={stage.cap}
                outputCap={Math.floor(stage.cap * 0.6)}
                lastTrace={lastTrace}
              />
              {idx < STAGE_CONFIG.length - 1 && (
                <FlowArrow color={STAGE_CONFIG[idx + 1].color} />
              )}
            </div>
          );
        })}
      </div>

      {/* ── Bottom metrics strip ───────────────────────────────────── */}
      <div className="shrink-0 flex items-center gap-4 border-t border-[#21262d] pt-2">
        <div className="text-[10px] font-mono text-[#8b949e] flex items-center gap-4">
          <span>Processed: <span className="text-[#e6edf3]">{res.total_processed ?? 0}</span></span>
          <span>Approved: <span className="text-[#7ee787]">{res.approved_finished ?? 0}</span></span>
          {[
            { label: "Raw In",  val: res.raw_input    ?? 0, cap: 300,  color: "#f87171" },
            { label: "Int In",  val: res.inter_input  ?? 0, cap: 200,  color: "#f59e0b" },
            { label: "Fin Out", val: res.finished_output ?? 0, cap: 150, color: "#7ee787" },
          ].map(({ label, val, cap, color }) => (
            <div key={label} className="flex items-center gap-1.5">
              <span>{label}</span>
              <div className="w-16 h-[5px] rounded-full bg-[#21262d] overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.min((val / cap) * 100, 100)}%`, backgroundColor: color }}
                />
              </div>
              <span style={{ color }}>{val}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
