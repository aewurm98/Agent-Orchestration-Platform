import { useEffect, useRef, useState } from "react";
import { useSocket } from "@/hooks/useSocket";
import type { SCNode, SCTruck, SupplyChainV2State } from "@/context/SocketContext";

/**
 * Supply Chain — side-panel telemetry dashboard.
 *
 * The supply-chain scenario has no agent ↔ tool DAG to show (its "agents" are
 * programmatic trucks on a grid), so this replaces the DAG tab for that
 * scenario.  It surfaces the dynamic information that's hard to read off the
 * 20×20 grid on the left: a GLS trend strip, the live fleet roster, and a
 * per-node network breakdown.  Manufacturing keeps the DAG visualizer.
 */

const TRUCK_STATE_COLOR: Record<string, string> = {
  AUTOPILOT: "#15803d",
  THINKING: "#b45309",
  EXECUTING_OVERRIDE: "#1d4ed8",
};

// How many recent samples define the "trend" window. Mirrors the backend's
// 26-tick GLS trend window used for the director digest.
const TREND_WINDOW = 26;
const MAX_HISTORY = 240;

type GlsSample = { tick: number; gls: number };

export default function SupplyChainDashboard() {
  const { gameState } = useSocket();
  const sc = gameState?.sc;
  const tick = gameState?.tick ?? 0;

  // Accumulate a client-side GLS history — the socket only sends the current
  // value each tick. Reset when a new run rewinds the tick counter.
  const [history, setHistory] = useState<GlsSample[]>([]);
  const lastTick = useRef<number>(-1);

  useEffect(() => {
    if (!sc) return;
    if (tick === lastTick.current) return;
    if (tick < lastTick.current) {
      // New run / restart — start the history over.
      setHistory([{ tick, gls: sc.gls }]);
    } else {
      setHistory((prev) => [...prev, { tick, gls: sc.gls }].slice(-MAX_HISTORY));
    }
    lastTick.current = tick;
  }, [tick, sc]);

  if (!sc) {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 pointer-events-none" data-testid="supply-chain-dashboard">
        <div className="w-12 h-12 pixel-gradient blob opacity-60" />
        <p className="text-[12px] text-[#6b6359] font-mono">Start a run to see network telemetry</p>
      </div>
    );
  }

  const suppliers = sc.nodes.filter((n) => n.kind === "supplier");
  const demand = sc.nodes.filter((n) => n.kind === "demand");
  const warehouses = sc.nodes.filter((n) => n.kind === "warehouse");
  const totalServed = demand.reduce((s, n) => s + (n.served ?? 0), 0);
  const totalBacklog = demand.reduce((s, n) => s + (n.accumulated_demand ?? 0), 0);

  return (
    <div className="w-full h-full overflow-y-auto px-3 py-3 flex flex-col gap-3" data-testid="supply-chain-dashboard">
      {/* Summary strip */}
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Fleet" value={String(sc.fleet)} />
        <Stat label="Served" value={totalServed.toLocaleString()} accent="#15803d" />
        <Stat label="Backlog" value={totalBacklog.toLocaleString()} accent={totalBacklog > 0 ? "#b91c1c" : "#14120e"} />
      </div>

      <GlsTrend sc={sc} history={history} />

      {/* Fleet roster */}
      <Section title={`Fleet · ${sc.trucks.length}`}>
        {sc.trucks.length === 0 ? (
          <Empty label="No trucks deployed" />
        ) : (
          sc.trucks.map((t) => <TruckRow key={t.id} truck={t} />)
        )}
      </Section>

      {/* Network nodes */}
      <Section title={`Demand zones · ${demand.length}`}>
        {demand.map((n) => <DemandRow key={n.id} node={n} />)}
      </Section>

      {warehouses.length > 0 && (
        <Section title={`Warehouses · ${warehouses.length}`}>
          {warehouses.map((n) => <WarehouseRow key={n.id} node={n} />)}
        </Section>
      )}

      {suppliers.length > 0 && (
        <Section title={`Suppliers · ${suppliers.length}`}>
          {suppliers.map((n) => <SupplierRow key={n.id} node={n} />)}
        </Section>
      )}
    </div>
  );
}

// ── GLS trend strip ───────────────────────────────────────────────────────────

function GlsTrend({ sc, history }: { sc: SupplyChainV2State; history: GlsSample[] }) {
  const glsColor = sc.gls >= 0 ? "#15803d" : "#b91c1c";

  // Δ over the trend window (matches backend's 26-tick director digest window).
  let windowDelta: number | null = null;
  if (history.length >= 2) {
    const idx = Math.max(0, history.length - TREND_WINDOW);
    windowDelta = sc.gls - history[idx].gls;
  }

  // Components, normalized against the largest absolute magnitude for the bars.
  const components: Array<[string, number, string]> = [
    ["Revenue", sc.revenue, "#15803d"],
    ["OpEx", -sc.opex, "#b45309"],
    ["CapEx", -sc.capex, "#1d4ed8"],
    ["Penalties", -sc.penalties, "#b91c1c"],
  ];
  const maxMag = Math.max(1, ...components.map(([, v]) => Math.abs(v)));

  return (
    <div className="rounded-xl border border-[#ebe5d6] bg-white px-3 py-2.5 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[9px] uppercase tracking-[0.18em] text-[#6b6359] font-semibold">GLS Trend</span>
        <div className="flex items-baseline gap-2">
          <span className="text-[14px] font-mono font-bold tabular-nums" style={{ color: glsColor }}>
            ${Math.round(sc.gls).toLocaleString()}
          </span>
          {windowDelta !== null && windowDelta !== 0 && (
            <span
              className="text-[10px] font-mono font-semibold"
              style={{ color: windowDelta > 0 ? "#15803d" : "#b91c1c" }}
            >
              {windowDelta > 0 ? "▲" : "▼"} {Math.abs(Math.round(windowDelta)).toLocaleString()}
            </span>
          )}
        </div>
      </div>

      <Sparkline points={history.map((h) => h.gls)} />

      <div className="flex flex-col gap-1 pt-0.5">
        {components.map(([label, value, color]) => (
          <div key={label} className="flex items-center gap-2">
            <span className="text-[9px] text-[#6b6359] w-[58px] shrink-0">{label}</span>
            <div className="flex-1 h-2 rounded-full bg-[#efe9d9] overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{ width: `${(Math.abs(value) / maxMag) * 100}%`, backgroundColor: color }}
              />
            </div>
            <span className="text-[10px] font-mono tabular-nums w-[64px] text-right" style={{ color }}>
              ${Math.round(value).toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) {
    return <div className="h-10 flex items-center text-[10px] text-[#a89e8e] italic">Collecting trend…</div>;
  }
  const W = 100;
  const H = 28;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = W / (points.length - 1);
  const path = points
    .map((v, i) => {
      const x = i * step;
      const y = H - ((v - min) / range) * H;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const last = points[points.length - 1];
  const stroke = last >= 0 ? "#15803d" : "#b91c1c";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="w-full h-10">
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

// ── Rows ──────────────────────────────────────────────────────────────────────

function TruckRow({ truck }: { truck: SCTruck }) {
  const color = TRUCK_STATE_COLOR[truck.state] ?? "#15803d";
  const cargoPct = truck.capacity > 0 ? (truck.cargo / truck.capacity) * 100 : 0;
  return (
    <div className="flex flex-col gap-1 py-1.5 border-b border-[#f0ebdf] last:border-b-0" title={truck.last_event}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className="w-1.5 h-1.5 rounded-full shrink-0"
            style={{ backgroundColor: color, animation: truck.state === "THINKING" ? "packet-flow 1.2s ease-in-out infinite" : undefined }}
          />
          <span className="text-[11px] font-mono text-[#14120e] truncate">{truck.id}</span>
          <span className="text-[8px] uppercase tracking-wide font-semibold" style={{ color }}>{truck.state}</span>
        </div>
        <span className="text-[9px] font-mono text-[#6b6359] shrink-0">→ {truck.target ?? "—"}</span>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-[#efe9d9] overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${cargoPct}%`, backgroundColor: color }} />
        </div>
        <span className="text-[9px] font-mono text-[#6b6359] tabular-nums shrink-0">
          {truck.cargo}/{truck.capacity} · {Math.round(truck.cargo_health)}%
        </span>
      </div>
    </div>
  );
}

function DemandRow({ node }: { node: SCNode }) {
  const backlog = node.accumulated_demand ?? 0;
  const hot = backlog > 50;
  return (
    <div className="flex items-center justify-between gap-2 py-1 border-b border-[#f0ebdf] last:border-b-0">
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="text-[10px]">{node.shocked ? "📈" : "🏬"}</span>
        <span className="text-[11px] font-mono text-[#14120e] truncate">{node.id}</span>
      </div>
      <div className="flex items-center gap-3 shrink-0 text-[9px] font-mono tabular-nums">
        <span style={{ color: hot ? "#b91c1c" : "#6b6359" }}>backlog {backlog}</span>
        <span className="text-[#15803d]">served {node.served ?? 0}</span>
        <span className="text-[#6b6359]">${Math.round(node.price ?? 0)}/u</span>
      </div>
    </div>
  );
}

function WarehouseRow({ node }: { node: SCNode }) {
  const inv = node.inventory ?? 0;
  const cap = node.capacity ?? 0;
  const pct = cap > 0 ? (inv / cap) * 100 : 0;
  return (
    <div className="flex items-center gap-2 py-1 border-b border-[#f0ebdf] last:border-b-0">
      <span className="text-[10px]">{node.full ? "🟥" : "🏢"}</span>
      <span className="text-[11px] font-mono text-[#14120e] w-[64px] truncate shrink-0">{node.id}</span>
      <div className="flex-1 h-1.5 rounded-full bg-[#efe9d9] overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: pct >= 100 ? "#b91c1c" : "#14120e" }} />
      </div>
      <span className="text-[9px] font-mono text-[#6b6359] tabular-nums shrink-0">{inv}/{cap}</span>
    </div>
  );
}

function SupplierRow({ node }: { node: SCNode }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1 border-b border-[#f0ebdf] last:border-b-0">
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="text-[10px]">🏭</span>
        <span className="text-[11px] font-mono text-[#14120e] truncate">{node.id}</span>
      </div>
      <span className="text-[9px] font-mono text-[#6b6359] tabular-nums shrink-0">stock {node.stock ?? 0}</span>
    </div>
  );
}

// ── Layout primitives ─────────────────────────────────────────────────────────

function Stat({ label, value, accent = "#14120e" }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-xl border border-[#ebe5d6] bg-white px-3 py-2">
      <span className="text-[9px] uppercase tracking-[0.16em] text-[#6b6359] font-semibold block">{label}</span>
      <span className="text-[15px] font-mono font-bold tabular-nums" style={{ color: accent }}>{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[#ebe5d6] bg-white px-3 py-2">
      <div className="text-[9px] uppercase tracking-[0.18em] text-[#6b6359] font-semibold mb-1">{title}</div>
      <div className="flex flex-col">{children}</div>
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="text-[10px] text-[#a89e8e] italic py-1">{label}</div>;
}
