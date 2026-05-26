import type { GameState, SCNode, SCTruck, SupplyChainV2State } from "@/context/SocketContext";

/**
 * Supply Chain v2 — real-time truck logistics on a 20×20 terrain grid.
 *
 * Programmatic truck "edge agents" haul cargo from Suppliers (🏭) to Demand
 * Zones (🏬), routing around obstacles on highways/off-road.  A global
 * Meta-Optimizer reshapes the network every 25 ticks.  The headline metric is
 * the Global Liquidity Score (GLS = Revenue − CapEx − OpEx − Penalties).
 */

type Props = { gameState: GameState };

const TERRAIN_BG: Record<string, string> = {
  highway: "#e9e4d6",
  off_road: "#f7f3ea",
  obstacle: "#3a352c",
};

const TRUCK_STATE_COLOR: Record<string, string> = {
  AUTOPILOT: "#15803d",
  THINKING: "#b45309",
  EXECUTING_OVERRIDE: "#1d4ed8",
};

export default function SupplyChainView({ gameState }: Props) {
  const sc = gameState.sc;
  if (!sc) {
    return (
      <div className="w-full h-full flex items-center justify-center text-[#6b6359] text-sm" data-testid="supply-chain-view">
        Waiting for supply-chain telemetry…
      </div>
    );
  }
  return (
    <div className="w-full h-full flex flex-col" data-testid="supply-chain-view">
      <Header sc={sc} tick={gameState.tick} />
      <div className="flex-1 min-h-0 grid grid-cols-[1fr_240px] gap-3 px-3 py-3 overflow-hidden">
        <GridBoard sc={sc} />
        <SidePanel sc={sc} />
      </div>
      <Ledger sc={sc} />
    </div>
  );
}

// ── Header ──────────────────────────────────────────────────────────────────

function Header({ sc, tick }: { sc: SupplyChainV2State; tick: number }) {
  const glsColor = sc.gls >= 0 ? "#15803d" : "#b91c1c";
  return (
    <div className="shrink-0 px-4 py-2.5 flex items-center justify-between border-b border-[#ebe5d6]">
      <div className="flex items-center gap-2.5">
        <span className="text-[15px]">🚚</span>
        <div className="flex flex-col leading-tight">
          <span className="text-[10px] uppercase tracking-[0.18em] text-[#6b6359] font-semibold">
            Supply Chain · 20×20 grid
          </span>
          <span className="text-[13px] font-semibold text-[#14120e] tabular-nums">
            Tick {tick} / {sc.episode_ticks} · Fleet {sc.fleet}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2 px-3 py-1 rounded-full border border-[#ebe5d6] bg-white">
        <span className="text-[9px] uppercase tracking-widest text-[#6b6359] font-semibold">GLS</span>
        <span className="text-[14px] font-mono font-bold tabular-nums" style={{ color: glsColor }}>
          ${sc.gls.toLocaleString()}
        </span>
      </div>
    </div>
  );
}

// ── 20×20 board ──────────────────────────────────────────────────────────────

function GridBoard({ sc }: { sc: SupplyChainV2State }) {
  const size = sc.grid.length || 20;
  // Index nodes and trucks by cell for O(1) overlay lookup.
  const nodeAt = new Map<string, SCNode>();
  sc.nodes.forEach((n) => nodeAt.set(`${n.x},${n.y}`, n));
  const trucksAt = new Map<string, SCTruck[]>();
  sc.trucks.forEach((t) => {
    const k = `${t.x},${t.y}`;
    (trucksAt.get(k) ?? trucksAt.set(k, []).get(k)!).push(t);
  });

  return (
    <div className="rounded-2xl border border-[#ebe5d6] bg-white p-2 min-h-0 overflow-hidden flex items-center justify-center">
      <div
        className="grid gap-px aspect-square w-full max-h-full"
        style={{ gridTemplateColumns: `repeat(${size}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: size }).map((_, y) =>
          Array.from({ length: size }).map((__, x) => {
            const terrain = sc.grid[y]?.[x] ?? "off_road";
            const key = `${x},${y}`;
            const node = nodeAt.get(key);
            const trucks = trucksAt.get(key) ?? [];
            return (
              <Cell key={key} terrain={terrain} node={node} trucks={trucks} />
            );
          })
        )}
      </div>
    </div>
  );
}

function Cell({ terrain, node, trucks }: { terrain: string; node?: SCNode; trucks: SCTruck[] }) {
  let content: string | null = null;
  let title = "";
  let ring = "";

  if (node) {
    if (node.kind === "supplier") { content = "🏭"; title = `${node.id} · stock ${node.stock}`; }
    else if (node.kind === "demand") {
      content = node.shocked ? "📈" : "🏬";
      title = `${node.id} · backlog ${node.accumulated_demand} · $${node.price}/u`;
      if ((node.accumulated_demand ?? 0) > 50) ring = "#b91c1c";
    } else { content = node.full ? "🟥" : "🏢"; title = `${node.id} · ${node.inventory}/${node.capacity}`; }
  }
  // Truck overlay takes visual priority.
  const truck = trucks[0];
  if (truck) {
    content = "🚚";
    title = `${truck.id} · ${truck.state} · cargo ${truck.cargo} (${truck.cargo_health}%) → ${truck.target ?? "—"}`;
    ring = TRUCK_STATE_COLOR[truck.state] ?? "#15803d";
  }

  return (
    <div
      className="relative flex items-center justify-center"
      style={{
        backgroundColor: TERRAIN_BG[terrain] ?? "#f7f3ea",
        boxShadow: ring ? `inset 0 0 0 1.5px ${ring}` : undefined,
        borderRadius: 2,
      }}
      title={title}
    >
      {content && (
        <span
          className="leading-none"
          style={{
            fontSize: "clamp(6px, 0.9vw, 12px)",
            animation: truck?.state === "THINKING" ? "packet-flow 1.2s ease-in-out infinite" : undefined,
          }}
        >
          {content}
        </span>
      )}
      {trucks.length > 1 && (
        <span className="absolute -top-0.5 -right-0.5 text-[7px] font-bold text-[#14120e] bg-white rounded-full px-0.5 leading-none">
          {trucks.length}
        </span>
      )}
    </div>
  );
}

// ── Side panel: alerts + director log + legend ───────────────────────────────

function SidePanel({ sc }: { sc: SupplyChainV2State }) {
  return (
    <div className="flex flex-col gap-2 min-h-0 overflow-hidden">
      <Legend />
      <Panel title="Bottlenecks & shocks" flex>
        {sc.alerts.length === 0 ? (
          <Empty label="Network nominal" />
        ) : (
          sc.alerts.slice(0, 8).map((a, i) => (
            <div key={i} className="text-[10px] text-[#7a1818] leading-snug">• {a}</div>
          ))
        )}
      </Panel>
      <Panel title="Director interventions" flex>
        {sc.director_log.length === 0 ? (
          <Empty label="No interventions yet" />
        ) : (
          sc.director_log.slice().reverse().map((d, i) => (
            <div key={i} className="text-[10px] text-[#14120e] leading-snug">
              <span className="text-[#6b6359] font-mono">t{d.tick}</span> {d.note}
            </div>
          ))
        )}
      </Panel>
    </div>
  );
}

function Legend() {
  const items: Array<[string, string]> = [
    ["🏭", "Supplier"], ["🏬", "Demand"], ["🏢", "Warehouse"], ["🚚", "Truck"],
  ];
  return (
    <div className="rounded-xl border border-[#ebe5d6] bg-white px-2.5 py-2 flex flex-wrap gap-x-3 gap-y-1">
      {items.map(([g, l]) => (
        <span key={l} className="text-[9px] text-[#6b6359] flex items-center gap-1">
          <span className="text-[11px]">{g}</span>{l}
        </span>
      ))}
    </div>
  );
}

function Panel({ title, children, flex }: { title: string; children: React.ReactNode; flex?: boolean }) {
  return (
    <div className={`rounded-xl border border-[#ebe5d6] bg-white px-2.5 py-2 ${flex ? "flex-1 min-h-0 overflow-y-auto" : ""}`}>
      <div className="text-[9px] uppercase tracking-[0.18em] text-[#6b6359] font-semibold mb-1.5">{title}</div>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="text-[10px] text-[#a89e8e] italic">{label}</div>;
}

// ── Bottom ledger: GLS breakdown ──────────────────────────────────────────────

function Ledger({ sc }: { sc: SupplyChainV2State }) {
  return (
    <div className="shrink-0 border-t border-[#ebe5d6] px-3 py-2.5 grid grid-cols-5 gap-2">
      <LedgerTile label="Revenue" value={sc.revenue} accent="#15803d" />
      <LedgerTile label="OpEx" value={-sc.opex} accent="#b45309" />
      <LedgerTile label="CapEx" value={-sc.capex} accent="#1d4ed8" />
      <LedgerTile label="Penalties" value={-sc.penalties} accent="#b91c1c" />
      <LedgerTile label="Capital" value={sc.capital} accent="#14120e" />
    </div>
  );
}

function LedgerTile({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-xl border border-[#ebe5d6] bg-white px-3 py-2">
      <span className="text-[9px] uppercase tracking-[0.16em] text-[#6b6359] font-semibold block">{label}</span>
      <span className="text-[13px] font-mono font-bold tabular-nums" style={{ color: accent }}>
        ${Math.round(value).toLocaleString()}
      </span>
    </div>
  );
}
