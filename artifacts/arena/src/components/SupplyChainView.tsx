import { useEffect, useRef, useState } from "react";
import { ArrowRight, Sliders } from "lucide-react";
import type { GameAgent, GameState } from "@/context/SocketContext";
import { useSocket } from "@/hooks/useSocket";

/**
 * Supply chain view — four-column chain:
 *
 *   ┌───────────────────────────────────────────────────────────────┐
 *   │ FACTORY  →  BULK WAREHOUSES  →  EXPRESS DISTRIBUTOR  →  STORES │
 *   └───────────────────────────────────────────────────────────────┘
 *
 * Each column shows the agents at that tier. Animated arrows between
 * columns indicate flow; arrows pulse when at least one upstream agent
 * is `delivering` and the downstream tier is accepting.
 *
 * Retail shelves on the right are the visual hook — slot icons fill on
 * delivery and empty as customer demand consumes them. Red slot = lost sale.
 */

type Props = { gameState: GameState };

const ROLE_TINT: Record<string, string> = {
  supplier:    "#b91c1c",
  warehouse:   "#14120e",
  distributor: "#b45309",
  retailer:    "#15803d",
};

export default function SupplyChainView({ gameState }: Props) {
  const res = gameState.resources ?? {};
  const agents = gameState.agents ?? [];

  const supplier     = agents.find((a) => a.role === "supplier") ?? null;
  const warehouses   = agents.filter((a) => a.role === "warehouse");
  const distributors = agents.filter((a) => a.role === "distributor");
  const retailers    = agents.filter((a) => a.role === "retailer");

  // Activity flags for inter-column arrows
  const supplierActive   = supplier?.state === "generating" || (supplier?.inventory ?? 0) > 0;
  const whDelivering     = warehouses.some((w) => w.state === "delivering");
  const distDelivering   = distributors.some((d) => d.state === "delivering");
  const whFetching       = warehouses.some((w) => w.state === "fetching");
  const distFetching     = distributors.some((d) => d.state === "fetching");

  return (
    <div className="w-full h-full flex flex-col" data-testid="supply-chain-view">
      {/* Status strip */}
      <div className="shrink-0 px-4 py-2.5 flex items-center justify-between border-b border-[#ebe5d6]">
        <div className="flex items-center gap-2.5">
          <span className="text-[15px]">🌐</span>
          <div className="flex flex-col leading-tight">
            <span className="text-[10px] uppercase tracking-[0.18em] text-[#6b6359] font-semibold">
              Supply Chain
            </span>
            <span className="text-[13px] font-semibold text-[#14120e] tabular-nums">
              Tick {gameState.tick} · Score {gameState.score.toFixed(2)}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <ServiceLevel value={res.service_level ?? 0} />
          <StockoutsBadge ticks={res.stockout_ticks ?? 0} />
        </div>
      </div>

      {/* Four-column chain */}
      <div className="flex-1 min-h-0 grid grid-cols-[180px_18px_180px_18px_180px_18px_1fr] gap-2 px-3 py-3 items-stretch overflow-hidden">
        {/* COL 1 — Factory */}
        <div className="flex flex-col gap-2 min-h-0">
          <ColumnHeader label="Factory" />
          <FactoryCard supplier={supplier} supplyRate={res.supply_rate ?? 0} />
        </div>

        {/* Connector 1 → 2 */}
        <Connector active={whFetching || (supplierActive && (supplier?.inventory ?? 0) > 0)} />

        {/* COL 2 — Bulk warehouses */}
        <div className="flex flex-col gap-2 min-h-0">
          <ColumnHeader label="Bulk Warehouses" sub="🚛" />
          <div className="flex flex-col gap-2 flex-1 min-h-0 overflow-y-auto pr-1">
            {warehouses.map((w) => (
              <CarrierCard key={w.id} agent={w} capacity={200} archetype="TRUCK" />
            ))}
            {warehouses.length === 0 && <EmptyCol label="No warehouses" />}
          </div>
        </div>

        {/* Connector 2 → 3 */}
        <Connector active={distFetching || whDelivering} />

        {/* COL 3 — Express distributor */}
        <div className="flex flex-col gap-2 min-h-0">
          <ColumnHeader label="Express Dispatch" sub="✈️" />
          <div className="flex flex-col gap-2 flex-1 min-h-0 overflow-y-auto pr-1">
            {distributors.map((d) => (
              <CarrierCard key={d.id} agent={d} capacity={150} archetype="AIR" />
            ))}
            {distributors.length === 0 && <EmptyCol label="No distributors" />}
          </div>
        </div>

        {/* Connector 3 → 4 */}
        <Connector active={distDelivering} />

        {/* COL 4 — Retail shelves */}
        <div className="flex flex-col gap-2 min-h-0">
          <ColumnHeader label="Retail Shelves" />
          <div className="flex flex-col gap-2 flex-1 min-h-0 overflow-y-auto pr-1">
            {retailers.map((r) => (
              <RetailShelf key={r.id} retailer={r} />
            ))}
          </div>
        </div>
      </div>

      {/* Sliders + bottom metric tiles */}
      <div className="shrink-0 border-t border-[#ebe5d6]">
        <ControlPanel
          currentSupplyRate={res.supply_rate ?? 0}
          currentDemandBase={res.demand_base ?? 8}
          supplyOverride={!!res.supply_override}
          demandOverride={!!res.demand_override}
        />
        <div className="px-3 pb-3 grid grid-cols-4 gap-2">
          <MetricTile label="Stock" value={res.stock_level ?? 0} max={2000} accent="#14120e" />
          <MetricTile label="Backlog" value={res.backlog ?? 0} max={500} accent="#b91c1c" />
          <MetricTile label="Delivered" value={res.total_delivered ?? 0} max={2000} accent="#15803d" />
          <MetricTile label="Customers served" value={res.customers_served ?? 0} max={2000} accent="#b45309" />
        </div>
      </div>
    </div>
  );
}

// ── Column header ────────────────────────────────────────────────────────────

function ColumnHeader({ label, sub }: { label: string; sub?: string }) {
  return (
    <div className="flex items-center justify-between px-1">
      <span className="text-[9px] uppercase tracking-[0.2em] text-[#6b6359] font-semibold">
        {label}
      </span>
      {sub && <span className="text-[11px] leading-none">{sub}</span>}
    </div>
  );
}

function EmptyCol({ label }: { label: string }) {
  return (
    <div className="rounded-xl border border-dashed border-[#ebe5d6] bg-[#faf6ed] flex items-center justify-center text-[10px] text-[#6b6359] py-6">
      {label}
    </div>
  );
}

// ── Connector arrow between columns ─────────────────────────────────────────

function Connector({ active }: { active: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center relative">
      {/* dashed line */}
      <div
        className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-px"
        style={{
          backgroundImage: active
            ? "linear-gradient(to bottom, #14120e 0 4px, transparent 4px 9px)"
            : "linear-gradient(to bottom, rgba(20,18,14,0.15) 0 4px, transparent 4px 9px)",
          backgroundSize: "1px 9px",
          backgroundRepeat: "repeat-y",
        }}
      />
      {/* arrow head */}
      <div
        className={`rounded-full p-1 flex items-center justify-center transition-colors ${
          active ? "bg-[#14120e] text-white" : "bg-[#efe9d9] text-[#a89e8e]"
        }`}
      >
        <ArrowRight className="w-2.5 h-2.5" />
      </div>
      {/* moving packet — only when active */}
      {active && (
        <span
          className="absolute left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-[#14120e]"
          style={{ animation: "packet-flow 1.6s ease-in-out infinite" }}
        />
      )}
    </div>
  );
}

// ── Service level + stockouts badges ────────────────────────────────────────

function ServiceLevel({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 95 ? "#15803d" : pct >= 80 ? "#b45309" : "#b91c1c";
  return (
    <div className="flex items-center gap-2 px-2.5 py-1 rounded-full border border-[#ebe5d6] bg-white">
      <span className="text-[9px] uppercase tracking-widest text-[#6b6359] font-semibold">Fill</span>
      <span className="text-[12px] font-mono font-bold tabular-nums" style={{ color }}>
        {pct}%
      </span>
    </div>
  );
}

function StockoutsBadge({ ticks }: { ticks: number }) {
  return (
    <div
      className="flex items-center gap-2 px-2.5 py-1 rounded-full border bg-[#fbeaea]"
      style={{ borderColor: "#fadcdc" }}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-[#b91c1c]" />
      <span className="text-[9px] uppercase tracking-widest text-[#7a1818] font-semibold">Stockouts</span>
      <span className="text-[12px] font-mono font-bold text-[#b91c1c] tabular-nums">{ticks}</span>
    </div>
  );
}

// ── Factory card ────────────────────────────────────────────────────────────

function FactoryCard({ supplier, supplyRate }: { supplier: GameAgent | null; supplyRate: number }) {
  const inv = supplier?.inventory ?? 0;
  const queueDepth = Math.min(1, inv / 800);
  const active = supplier?.state === "generating";
  return (
    <div className="rounded-2xl border border-[#ebe5d6] bg-white shadow-sm flex flex-col p-3 relative overflow-hidden flex-1 min-h-0">
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5"
        style={{ backgroundColor: ROLE_TINT.supplier }}
      />
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[22px]">🏭</span>
          <div className="flex flex-col leading-tight">
            <span className="text-[9px] uppercase tracking-widest text-[#6b6359] font-semibold">Supplier</span>
          </div>
        </div>
        <span
          className="text-[8px] font-mono font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider"
          style={{
            backgroundColor: active ? "#b91c1c" : "#fbeaea",
            color: active ? "#ffffff" : "#b91c1c",
          }}
        >
          {active ? "Producing" : "Idle"}
        </span>
      </div>

      <div className="flex flex-col gap-1 mb-2">
        <span className="text-[9px] uppercase tracking-widest text-[#6b6359]">Production</span>
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-semibold tabular-nums text-[#14120e]">{supplyRate}</span>
          <span className="text-[10px] font-mono text-[#6b6359]">u/tick</span>
        </div>
      </div>

      <div className="flex flex-col gap-1.5 mt-auto">
        <div className="flex items-center justify-between">
          <span className="text-[9px] uppercase tracking-widest text-[#6b6359]">Output queue</span>
          <span className="text-[10px] font-mono font-bold text-[#14120e] tabular-nums">{inv}</span>
        </div>
        <div className="h-2 rounded-full bg-[#efe9d9] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{ width: `${queueDepth * 100}%`, backgroundColor: ROLE_TINT.supplier }}
          />
        </div>
        <div className="grid grid-cols-8 gap-0.5">
          {Array.from({ length: 16 }, (_, i) => {
            const filled = i < Math.round(queueDepth * 16);
            return (
              <div
                key={i}
                className="aspect-square rounded-sm"
                style={{ backgroundColor: filled ? ROLE_TINT.supplier : "#efe9d9", opacity: filled ? 0.85 : 1 }}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Carrier card (warehouse / distributor) ──────────────────────────────────

function CarrierCard({
  agent, capacity, archetype,
}: { agent: GameAgent; capacity: number; archetype: "TRUCK" | "AIR" }) {
  const tint = ROLE_TINT[agent.role] ?? "#14120e";
  const icon = archetype === "TRUCK" ? "🚛" : "✈️";
  const inv = agent.inventory ?? 0;
  const fill = Math.min(1, inv / capacity);
  const isActive =
    agent.state === "delivering" ||
    agent.state === "fetching";
  const stateLabel =
    agent.state === "delivering" ? "Delivering" :
    agent.state === "fetching"   ? "Fetching"   :
    "Idle";

  return (
    <div
      className="rounded-xl bg-white border shadow-sm p-2.5 flex flex-col gap-1.5 relative overflow-hidden"
      style={{ borderColor: tint, borderWidth: isActive ? 1.5 : 1 }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-[15px] leading-none">{icon}</span>
          <span className="text-[10px] font-semibold text-[#14120e]">
            {agent.id.replace(/_/g, " ").replace("warehouse", "WH").replace("distributor", "Dist").trim()}
          </span>
        </div>
        <span
          className="text-[8px] font-mono font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider"
          style={{
            backgroundColor: isActive ? tint : "transparent",
            color: isActive ? "#ffffff" : tint,
            border: isActive ? "none" : `1px solid ${tint}`,
          }}
        >
          {stateLabel}
        </span>
      </div>
      <div className="flex items-baseline justify-between">
        <span className="text-lg font-semibold tabular-nums text-[#14120e]">{inv}</span>
        <span className="text-[9px] font-mono text-[#6b6359]">{inv}/{capacity}</span>
      </div>
      <div className="h-1 rounded-full bg-[#efe9d9] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${fill * 100}%`, backgroundColor: tint }}
        />
      </div>
      <span
        className="text-[8px] font-mono font-semibold uppercase tracking-wider"
        style={{ color: tint }}
      >
        {archetype}
      </span>
    </div>
  );
}

// ── Retail shelf ────────────────────────────────────────────────────────────

const SHELF_SLOTS_PER_ROW = 8;
const SHELF_ROWS = 2;
const UNITS_PER_SLOT = 25;

function RetailShelf({ retailer }: { retailer: GameAgent }) {
  const inv = retailer.inventory ?? 0;
  const demand = retailer.demand ?? 0;
  const lastDemand = retailer.last_demand ?? 0;
  const lastSold = retailer.last_sold ?? 0;
  const delivered = retailer.delivered ?? 0;
  const stockout = !!retailer.stockout;

  const filledSlots = Math.min(SHELF_SLOTS_PER_ROW * SHELF_ROWS, Math.floor(inv / UNITS_PER_SLOT));
  const lostSlots = stockout
    ? Math.min(SHELF_SLOTS_PER_ROW * SHELF_ROWS - filledSlots, Math.max(1, Math.ceil(demand / UNITS_PER_SLOT)))
    : 0;

  return (
    <div
      className="rounded-xl border bg-white shadow-sm p-2.5 relative overflow-hidden"
      style={{ borderColor: stockout ? "#b91c1c" : "#ebe5d6", borderWidth: stockout ? 1.5 : 1 }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-[15px]">🏬</span>
          <span className="text-[11px] font-semibold text-[#14120e]">
            {retailer.id.replace(/_/g, " ").replace("retailer", "Store").trim()}
          </span>
        </div>
        {stockout ? (
          <span className="text-[8px] font-mono font-bold px-1.5 py-0.5 rounded uppercase tracking-wider bg-[#b91c1c] text-white">
            Out
          </span>
        ) : (
          <span className="text-[8px] font-mono font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider bg-[#e6f4ea] text-[#15803d]">
            Stocked
          </span>
        )}
      </div>

      <div className="flex flex-col gap-0.5 mb-1.5 bg-[#faf6ed] rounded-md p-1 border border-[#ebe5d6]">
        {Array.from({ length: SHELF_ROWS }, (_, row) => (
          <div key={row} className="flex gap-0.5">
            {Array.from({ length: SHELF_SLOTS_PER_ROW }, (_, col) => {
              const i = row * SHELF_SLOTS_PER_ROW + col;
              const isFilled = i < filledSlots;
              const isLost = !isFilled && i < filledSlots + lostSlots;
              return (
                <div
                  key={col}
                  className="flex-1 aspect-square rounded-sm flex items-center justify-center text-[9px] leading-none transition-colors duration-300"
                  style={{
                    backgroundColor: isFilled ? "#e6f4ea" : isLost ? "#fbeaea" : "#ffffff",
                    border: `1px solid ${
                      isFilled ? "#bcdcc6" : isLost ? "#f3c4c4" : "#ebe5d6"
                    }`,
                  }}
                  title={
                    isFilled ? `${UNITS_PER_SLOT} units`
                      : isLost ? "Lost sale"
                      : "Empty slot"
                  }
                >
                  {isFilled ? "📦" : isLost ? "✕" : ""}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between text-[10px] font-mono text-[#6b6359]">
        <span>
          Shelf <span className="text-[#14120e] font-bold">{inv}</span>
        </span>
        <span>
          Sold <span className="text-[#15803d] font-bold">{delivered}</span>
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[10px] font-mono text-[#6b6359]">
        <DemandSpark label="Demand" value={lastDemand} accent="#b45309" />
        <DemandSpark label="Sold" value={lastSold} accent="#15803d" />
        {demand > 0 && (
          <span className="ml-auto text-[#b91c1c] font-bold">Backlog {demand}</span>
        )}
      </div>
    </div>
  );
}

function DemandSpark({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="text-[8px] uppercase tracking-widest text-[#6b6359]">{label}</span>
      <span className="text-[10px] font-bold tabular-nums" style={{ color: accent }}>
        {value}
      </span>
    </span>
  );
}

// ── Control panel ───────────────────────────────────────────────────────────

function ControlPanel({
  currentSupplyRate, currentDemandBase,
  supplyOverride, demandOverride,
}: {
  currentSupplyRate: number; currentDemandBase: number;
  supplyOverride: boolean; demandOverride: boolean;
}) {
  const [open, setOpen] = useState(true);
  const { emitSupplyChainKnobs } = useSocket();

  const [supplyDraft, setSupplyDraft] = useState<number>(currentSupplyRate);
  const [demandDraft, setDemandDraft] = useState<number>(currentDemandBase);

  useEffect(() => {
    if (!supplyOverride) setSupplyDraft(currentSupplyRate);
  }, [currentSupplyRate, supplyOverride]);
  useEffect(() => {
    if (!demandOverride) setDemandDraft(currentDemandBase);
  }, [currentDemandBase, demandOverride]);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queue = (knobs: { supply_rate?: number | null; retail_demand_base?: number | null }) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => emitSupplyChainKnobs(knobs), 120);
  };

  const handleSupplyChange = (v: number) => {
    setSupplyDraft(v);
    queue({ supply_rate: v });
  };
  const handleDemandChange = (v: number) => {
    setDemandDraft(v);
    queue({ retail_demand_base: v });
  };
  const clearOverrides = () => {
    emitSupplyChainKnobs({ supply_rate: null, retail_demand_base: null });
  };

  return (
    <div className="px-3 pt-2.5">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between text-[10px] uppercase tracking-widest text-[#6b6359] font-semibold py-1 hover:text-[#14120e] transition-colors"
        data-testid="btn-toggle-controls"
      >
        <span className="flex items-center gap-1.5">
          <Sliders className="w-3 h-3" />
          Manual controls
        </span>
        <span className="flex items-center gap-2">
          {(supplyOverride || demandOverride) && (
            <span
              className="text-[9px] font-mono px-1.5 py-0.5 rounded uppercase tracking-wider"
              style={{ backgroundColor: "#14120e", color: "#ffffff" }}
            >
              Override active
            </span>
          )}
          <span className="text-[#a89e8e]">{open ? "▾" : "▸"}</span>
        </span>
      </button>
      {open && (
        <div className="grid grid-cols-2 gap-3 py-2.5">
          <SliderRow
            label="Supply rate"
            unit="u/tick"
            min={0} max={80}
            value={supplyDraft}
            onChange={handleSupplyChange}
            accent="#b91c1c"
            active={supplyOverride}
          />
          <SliderRow
            label="Customer demand"
            unit="u/tick"
            min={0} max={30} step={0.5}
            value={demandDraft}
            onChange={handleDemandChange}
            accent="#15803d"
            active={demandOverride}
          />
          {(supplyOverride || demandOverride) && (
            <button
              onClick={clearOverrides}
              className="col-span-2 self-start text-[10px] font-medium text-[#6b6359] hover:text-[#14120e] underline underline-offset-2"
              data-testid="btn-clear-overrides"
            >
              Hand back to EA
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function SliderRow({
  label, unit, min, max, step = 1, value, onChange, accent, active,
}: {
  label: string; unit: string;
  min: number; max: number; step?: number;
  value: number; onChange: (v: number) => void;
  accent: string; active: boolean;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] uppercase tracking-wider text-[#6b6359] font-semibold flex items-center gap-1.5">
          {label}
          {active && <span className="w-1 h-1 rounded-full" style={{ backgroundColor: accent }} />}
        </span>
        <span className="text-[12px] font-bold tabular-nums" style={{ color: accent }}>
          {Number.isInteger(value) ? value : value.toFixed(1)}
          <span className="text-[9px] font-mono text-[#6b6359] font-normal ml-1">{unit}</span>
        </span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
        style={{
          background: `linear-gradient(to right, ${accent} 0%, ${accent} ${pct}%, #efe9d9 ${pct}%, #efe9d9 100%)`,
        }}
      />
    </div>
  );
}

// ── Metric tile ─────────────────────────────────────────────────────────────

function MetricTile({
  label, value, max, accent,
}: { label: string; value: number; max: number; accent: string }) {
  const pct = Math.min(1, value / Math.max(1, max));
  return (
    <div className="rounded-xl border border-[#ebe5d6] bg-white px-3 py-2 relative">
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] uppercase tracking-[0.18em] text-[#6b6359] font-semibold">
          {label}
        </span>
        <span className="text-[14px] font-semibold tabular-nums" style={{ color: accent }}>
          {value}
        </span>
      </div>
      <div className="mt-1.5 h-1 rounded-full bg-[#efe9d9] overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${pct * 100}%`, backgroundColor: accent }}
        />
      </div>
    </div>
  );
}
