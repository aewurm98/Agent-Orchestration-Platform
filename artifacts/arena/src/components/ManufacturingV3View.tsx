import type {
  GameState,
  MfgV3Node,
  MfgV3Edge,
  MfgV3Economics,
  MfgV3Orders,
} from "@/context/SocketContext";

/**
 * Manufacturing v3 — Topological Flow Graph.
 *
 * A 3-stage factory DAG: Inbound Docks feed Molding + Wire Drawing, which feed
 * Assembly, then QA & Packaging, then the Outbound Docks (sink). Machines carry
 * input/output queues and a per-batch state (IDLE / PROCESSING / DOWN); edges
 * are conveyors whose live throughput is the `flow` value. The headline metric
 * is Fitness = Revenue − (OpEx + Material) − Penalties.
 */

type Props = { gameState: GameState };

// Fixed layout coordinates (percent of the board) for every node in the DAG,
// including the synthetic Inbound/Outbound docks that edges reference.
const LAYOUT: Record<string, { x: number; y: number }> = {
  inbound: { x: 7, y: 50 },
  molding: { x: 31, y: 27 },
  wire_drawing: { x: 31, y: 73 },
  assembly: { x: 55, y: 50 },
  packaging: { x: 78, y: 50 },
  __sink__: { x: 95, y: 50 },
};

const STATE_COLOR: Record<string, string> = {
  IDLE: "#6b6359",
  PROCESSING: "#15803d",
  DOWN: "#b91c1c",
};

const money = (v: number) =>
  `${v < 0 ? "−" : ""}$${Math.abs(Math.round(v)).toLocaleString()}`;

export default function ManufacturingV3View({ gameState }: Props) {
  const nodes = gameState.nodes;
  const edges = gameState.edges;
  if (!nodes || !edges) {
    return (
      <div
        className="w-full h-full flex items-center justify-center text-[#6b6359] text-sm"
        data-testid="manufacturing-v3-view"
      >
        Waiting for flow-graph telemetry…
      </div>
    );
  }

  const orders: MfgV3Orders = gameState.orders ?? { received: 0, fulfilled: 0, missed: 0 };
  const econ: MfgV3Economics =
    gameState.economics ?? { revenue: 0, opex: 0, material_cost: 0, penalties: 0, fitness: 0 };
  const total = gameState.simulation_length ?? 500;

  return (
    <div className="w-full h-full flex flex-col" data-testid="manufacturing-v3-view">
      <style>{`
        @keyframes mfg-belt { to { stroke-dashoffset: -12; } }
        @keyframes mfg-process-pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(21,128,61,0.0); }
          50%      { box-shadow: 0 0 0 4px rgba(21,128,61,0.18); }
        }
        @keyframes mfg-down-pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(185,28,28,0.0); }
          50%      { box-shadow: 0 0 0 4px rgba(185,28,28,0.20); }
        }
        .mfg-belt { animation: mfg-belt 0.6s linear infinite; }
        .mfg-card-processing { animation: mfg-process-pulse 1.1s ease-in-out infinite; }
        .mfg-card-down { animation: mfg-down-pulse 1.1s ease-in-out infinite; }
      `}</style>
      <Header tick={gameState.tick} total={total} orders={orders} fitness={econ.fitness} />
      <div className="flex-1 min-h-0 relative px-4 py-3">
        <FlowBoard nodes={nodes} edges={edges} />
      </div>
      <Ledger econ={econ} orders={orders} />
    </div>
  );
}

// ── Header ────────────────────────────────────────────────────────────────────

function Header({
  tick,
  total,
  orders,
  fitness,
}: {
  tick: number;
  total: number;
  orders: MfgV3Orders;
  fitness: number;
}) {
  const fitColor = fitness >= 0 ? "#15803d" : "#b91c1c";
  return (
    <div className="shrink-0 px-4 py-2.5 flex items-center justify-between border-b border-[#ebe5d6]">
      <div className="flex items-center gap-2.5">
        <span className="text-[15px]">🏭</span>
        <div className="flex flex-col leading-tight">
          <span className="text-[10px] uppercase tracking-[0.18em] text-[#6b6359] font-semibold">
            Manufacturing · Flow Graph
          </span>
          <span className="text-[13px] font-semibold text-[#14120e] tabular-nums">
            Tick {tick} / {total} · Orders {orders.fulfilled}/{orders.received} fulfilled
          </span>
        </div>
      </div>
      <div className="flex flex-col items-end leading-tight">
        <span className="text-[10px] uppercase tracking-[0.18em] text-[#6b6359] font-semibold">
          Fitness
        </span>
        <span className="text-[15px] font-semibold tabular-nums" style={{ color: fitColor }}>
          {money(fitness)}
        </span>
      </div>
    </div>
  );
}

// ── Flow board (edges + node cards) ─────────────────────────────────────────────

function FlowBoard({ nodes, edges }: { nodes: MfgV3Node[]; edges: MfgV3Edge[] }) {
  return (
    <div className="absolute inset-0 px-4 py-3">
      {/* Edge layer */}
      <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="none">
        {edges.map((e) => {
          const a = LAYOUT[e.source];
          const b = LAYOUT[e.target];
          if (!a || !b) return null;
          const active = e.flow > 0;
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          // One traveling "part" per unit of flow this tick (capped so the belt
          // doesn't get crowded), staggered along the conveyor.
          const parts = active ? Math.min(e.flow, 4) : 0;
          return (
            <g key={e.id}>
              {/* Static rail */}
              <line
                x1={`${a.x}%`}
                y1={`${a.y}%`}
                x2={`${b.x}%`}
                y2={`${b.y}%`}
                stroke={active ? "#15803d" : "#d8d0c0"}
                strokeWidth={active ? 2.5 : 1.5}
                strokeOpacity={active ? 0.35 : 1}
                strokeDasharray={active ? "0" : "4 4"}
              />
              {/* Animated belt overlay — moving dashes read as a running conveyor */}
              {active && (
                <line
                  className="mfg-belt"
                  x1={`${a.x}%`}
                  y1={`${a.y}%`}
                  x2={`${b.x}%`}
                  y2={`${b.y}%`}
                  stroke="#15803d"
                  strokeWidth={2.5}
                  strokeDasharray="3 9"
                  strokeLinecap="round"
                />
              )}
              {/* Traveling parts */}
              {Array.from({ length: parts }).map((_, i) => (
                <circle key={i} r={3.5} fill="#15803d">
                  <animate
                    attributeName="cx"
                    values={`${a.x}%;${b.x}%`}
                    dur="1.2s"
                    begin={`${(i * 1.2) / Math.max(1, parts)}s`}
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="cy"
                    values={`${a.y}%;${b.y}%`}
                    dur="1.2s"
                    begin={`${(i * 1.2) / Math.max(1, parts)}s`}
                    repeatCount="indefinite"
                  />
                </circle>
              ))}
              <foreignObject x={`${mx - 4}%`} y={`${my - 3}%`} width="8%" height="6%">
                <div className="flex items-center justify-center">
                  <span
                    className="px-1.5 py-0.5 rounded-full text-[9px] font-mono font-semibold tabular-nums border bg-white"
                    style={{
                      borderColor: active ? "#15803d" : "#ebe5d6",
                      color: active ? "#15803d" : "#a89e8e",
                    }}
                  >
                    {e.flow}/{e.bandwidth}
                  </span>
                </div>
              </foreignObject>
            </g>
          );
        })}
      </svg>

      {/* Dock chips (source + sink) */}
      <DockChip pos={LAYOUT.inbound} label="Inbound" icon="📦" />
      <DockChip pos={LAYOUT.__sink__} label="Outbound" icon="✅" />

      {/* Machine node cards */}
      {nodes.map((n) => {
        const pos = LAYOUT[n.id];
        if (!pos) return null;
        return <MachineCard key={n.id} node={n} pos={pos} />;
      })}
    </div>
  );
}

function DockChip({ pos, label, icon }: { pos: { x: number; y: number }; label: string; icon: string }) {
  return (
    <div
      className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center gap-1"
      style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
    >
      <div className="w-11 h-11 rounded-xl bg-[#efe9d9] border border-[#ebe5d6] flex items-center justify-center text-[18px]">
        {icon}
      </div>
      <span className="text-[9px] uppercase tracking-wider text-[#6b6359] font-semibold">{label}</span>
    </div>
  );
}

function MachineCard({ node, pos }: { node: MfgV3Node; pos: { x: number; y: number } }) {
  const color = STATE_COLOR[node.state] ?? "#6b6359";
  const util = Math.round(node.utilization * 100);
  const pulseClass =
    node.state === "PROCESSING" ? "mfg-card-processing" : node.state === "DOWN" ? "mfg-card-down" : "";
  return (
    <div
      className={`absolute -translate-x-1/2 -translate-y-1/2 w-[148px] rounded-xl border bg-white shadow-sm ${pulseClass}`}
      style={{ left: `${pos.x}%`, top: `${pos.y}%`, borderColor: color }}
      data-testid={`mfg-v3-node-${node.id}`}
    >
      <div className="flex items-center justify-between px-2.5 pt-2">
        <span className="text-[11px] font-semibold text-[#14120e]">{node.label}</span>
        <span
          className="px-1.5 py-0.5 rounded-full text-[8px] font-mono font-semibold uppercase tracking-wide text-white"
          style={{ backgroundColor: color }}
        >
          {node.state}
        </span>
      </div>
      <div className="px-2.5 py-1.5 flex items-center justify-between text-[10px] text-[#6b6359] tabular-nums">
        <span>in {node.input_queue}</span>
        <span className="text-[#a89e8e]">cap {node.capacity}</span>
        <span>out {node.output_queue}</span>
      </div>
      <div className="px-2.5 pb-2">
        <div className="h-1.5 rounded-full bg-[#efe9d9] overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${util}%`, backgroundColor: color }} />
        </div>
        <span className="text-[8px] text-[#a89e8e] font-mono">util {util}%</span>
      </div>
    </div>
  );
}

// ── Ledger ──────────────────────────────────────────────────────────────────────

function Ledger({ econ, orders }: { econ: MfgV3Economics; orders: MfgV3Orders }) {
  const items: Array<{ label: string; value: string; color?: string }> = [
    { label: "Revenue", value: money(econ.revenue), color: "#15803d" },
    { label: "OpEx", value: `−${money(econ.opex).replace(/^−/, "")}`, color: "#b45309" },
    { label: "Material", value: `−${money(econ.material_cost).replace(/^−/, "")}`, color: "#b45309" },
    { label: "Penalties", value: `−${money(econ.penalties).replace(/^−/, "")}`, color: "#b91c1c" },
    { label: "Missed", value: `${orders.missed}`, color: orders.missed > 0 ? "#b91c1c" : "#6b6359" },
  ];
  return (
    <div className="shrink-0 border-t border-[#ebe5d6] px-4 py-2 grid grid-cols-5 gap-2">
      {items.map((it) => (
        <div key={it.label} className="flex flex-col items-center leading-tight">
          <span className="text-[9px] uppercase tracking-wider text-[#6b6359]">{it.label}</span>
          <span className="text-[12px] font-semibold tabular-nums" style={{ color: it.color ?? "#14120e" }}>
            {it.value}
          </span>
        </div>
      ))}
    </div>
  );
}
