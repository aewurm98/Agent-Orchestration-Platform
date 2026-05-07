import { useSocket } from "@/hooks/useSocket";
import { useState, useEffect, useCallback } from "react";
import type { MfgGameState, MfgMetrics } from "@/context/SocketContext";

const MACHINE_STATE_COLOR: Record<string, string> = {
  idle:         "#8b949e",
  loading:      "#f59e0b",
  processing:   "#00d9ff",
  output_ready: "#7ee787",
  broken:       "#f87171",
  offline:      "#4d5566",
};

const ROLE_COLOR: Record<string, string> = {
  procurement: "#f59e0b",
  operations:  "#00d9ff",
  engineering: "#a371f7",
  sales:       "#7ee787",
  management:  "#f87171",
};

function MetricBadge({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="flex flex-col items-center px-2 py-1 rounded bg-[#161b22] border border-[#30363d] min-w-[60px]">
      <span className="text-[9px] font-mono text-[#8b949e] uppercase tracking-wide">{label}</span>
      <span className="text-[12px] font-bold font-mono" style={{ color: color ?? "#e6edf3" }}>
        {value}
      </span>
    </div>
  );
}

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.min((value / Math.max(max, 1)) * 100, 100);
  return (
    <div className="flex-1 h-[4px] rounded-full bg-[#21262d] overflow-hidden">
      <div className="h-full rounded-full transition-all duration-300" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

function BudgetPanel({ budget, startingBudget, metrics }: { budget: number; startingBudget: number; metrics: MfgMetrics | null }) {
  const base = startingBudget > 0 ? startingBudget : 8000;
  const pct = Math.min((budget / base) * 100, 100);
  const budgetColor = budget > base * 0.5 ? "#7ee787" : budget > base * 0.25 ? "#f59e0b" : "#f87171";

  return (
    <div className="flex flex-col gap-1 p-2 rounded-lg border border-[#30363d] bg-[#0d1117]">
      <div className="flex items-center justify-between">
        <span className="text-[9px] font-mono text-[#8b949e] uppercase">Budget</span>
        <span className="text-[12px] font-bold font-mono" style={{ color: budgetColor }}>
          ${budget.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </span>
      </div>
      <Bar value={budget} max={base} color={budgetColor} />
      {metrics && (
        <div className="flex gap-2 text-[9px] font-mono text-[#8b949e]">
          <span>Profit: <span style={{ color: metrics.current_profit >= 0 ? "#7ee787" : "#f87171" }}>
            ${metrics.current_profit.toFixed(0)}
          </span></span>
          <span>Rev: <span className="text-[#00d9ff]">${metrics.total_revenue.toFixed(0)}</span></span>
        </div>
      )}
    </div>
  );
}

function OrdersPanel({ orders }: { orders: MfgGameState["active_orders"] }) {
  if (!orders || orders.length === 0) {
    return (
      <div className="p-2 rounded-lg border border-[#30363d] bg-[#0d1117]">
        <span className="text-[9px] font-mono text-[#4d5566]">No active orders</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1 p-2 rounded-lg border border-[#30363d] bg-[#0d1117]">
      <span className="text-[9px] font-mono text-[#8b949e] uppercase">Orders ({orders.length})</span>
      <div className="flex flex-col gap-0.5 max-h-[80px] overflow-y-auto">
        {orders.slice(0, 4).map((order) => (
          <div key={order.id} className="flex items-center gap-1 text-[9px] font-mono">
            <span className={order.is_rush ? "text-[#f87171]" : "text-[#8b949e]"}>
              {order.is_rush ? "⚡" : "📋"}
            </span>
            <span className="text-[#e6edf3]">{order.id}</span>
            <span className="text-[#f59e0b]">${order.effective_price}</span>
            <span className="text-[#6e7681]">→ T{order.deadline_tick}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MachineStatusRow({ machines }: { machines: MfgGameState["machines"] }) {
  if (!machines) return null;
  const machineList = Object.values(machines);
  const states: Record<string, number> = {};
  for (const m of machineList) {
    states[m.state] = (states[m.state] ?? 0) + 1;
  }
  const brokenCount = states["broken"] ?? 0;

  return (
    <div className="flex flex-wrap gap-1 p-2 rounded-lg border border-[#30363d] bg-[#0d1117]">
      <span className="w-full text-[9px] font-mono text-[#8b949e] uppercase">Machines ({machineList.length})</span>
      {machineList.map((m) => (
        <div
          key={m.id}
          className="w-2 h-2 rounded-sm"
          title={`${m.id}: ${m.state}`}
          style={{ backgroundColor: MACHINE_STATE_COLOR[m.state] ?? "#8b949e" }}
        />
      ))}
      {brokenCount > 0 && (
        <span className="text-[9px] font-mono text-[#f87171] animate-pulse">
          ⚠ {brokenCount} broken
        </span>
      )}
    </div>
  );
}

function AgentStatusRow({ agents }: { agents: MfgGameState["agents"] }) {
  if (!agents) return null;
  const agentList = Object.values(agents);

  return (
    <div className="flex flex-wrap gap-1 p-2 rounded-lg border border-[#30363d] bg-[#0d1117]">
      <span className="w-full text-[9px] font-mono text-[#8b949e] uppercase">Agents ({agentList.length})</span>
      {agentList.map((a) => (
        <div
          key={a.id}
          className="px-1 py-0.5 rounded text-[9px] font-mono"
          title={`${a.id}: ${a.state}`}
          style={{
            backgroundColor: (ROLE_COLOR[a.role] ?? "#8b949e") + "22",
            color: ROLE_COLOR[a.role] ?? "#8b949e",
            border: `1px solid ${(ROLE_COLOR[a.role] ?? "#8b949e")}44`,
          }}
        >
          {a.role.slice(0, 3).toUpperCase()}
        </div>
      ))}
    </div>
  );
}

const SPEED_PRESETS: Array<{ label: string; mult: number }> = [
  { label: "1x",  mult: 1 },
  { label: "5x",  mult: 5 },
  { label: "10x", mult: 10 },
  { label: "Max", mult: 50 },
];

function SpeedControl() {
  const { socket } = useSocket();

  const setSpeed = (mult: number) => {
    socket?.emit("set_speed", { multiplier: mult });
  };

  const doPause = () => {
    socket?.emit("pause", {});
  };

  const doResume = () => {
    socket?.emit("resume", {});
  };

  return (
    <div className="flex flex-wrap items-center gap-1 p-2 rounded-lg border border-[#30363d] bg-[#0d1117]">
      <span className="text-[9px] font-mono text-[#8b949e] uppercase mr-1">Speed</span>
      {SPEED_PRESETS.map(({ label, mult }) => (
        <button
          key={label}
          onClick={() => setSpeed(mult)}
          className="px-2 py-0.5 rounded text-[10px] font-mono font-bold border border-[#30363d] text-[#8b949e] hover:text-[#00d9ff] hover:border-[#00d9ff] transition-colors"
        >
          {label}
        </button>
      ))}
      <button
        onClick={doPause}
        className="px-2 py-0.5 rounded text-[10px] font-mono border border-[#30363d] text-[#8b949e] hover:text-[#f87171] hover:border-[#f87171] transition-colors"
        title="Pause simulation"
      >
        ⏸
      </button>
      <button
        onClick={doResume}
        className="px-2 py-0.5 rounded text-[10px] font-mono border border-[#30363d] text-[#8b949e] hover:text-[#7ee787] hover:border-[#7ee787] transition-colors"
        title="Resume simulation"
      >
        ▶
      </button>
    </div>
  );
}

interface AlertItem {
  id: string;
  type: string;
  event?: string;
  message?: string;
}

function ToastAlerts({ alerts }: { alerts: AlertItem[] }) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const dismiss = useCallback((id: string) => {
    setDismissed((prev) => new Set([...prev, id]));
  }, []);

  const visible = alerts.filter((a) => !dismissed.has(a.id)).slice(-5).reverse();
  if (visible.length === 0) return null;

  return (
    <div className="flex flex-col gap-1">
      {visible.map((alert) => (
        <div
          key={alert.id}
          className="flex items-start justify-between gap-1 px-2 py-1 rounded border border-[#f8717144] bg-[#f8717110] animate-in fade-in"
        >
          <span className="text-[9px] font-mono text-[#f87171] leading-tight">
            ⚠ {alert.event ? alert.event.replace(/_/g, " ") : (alert.message ?? JSON.stringify(alert))}
          </span>
          <button
            onClick={() => dismiss(alert.id)}
            className="text-[8px] font-mono text-[#f8717188] hover:text-[#f87171] shrink-0 leading-none pt-0.5"
            title="Dismiss"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

export default function ManufacturingHUD({ state }: { state: MfgGameState }) {
  const { mfgMetrics, mfgAlerts } = useSocket();
  const metrics = mfgMetrics;

  // Assign stable IDs to alerts so toast dismissal works correctly
  const [alertsWithIds, setAlertsWithIds] = useState<AlertItem[]>([]);
  useEffect(() => {
    if (!mfgAlerts) return;
    setAlertsWithIds(
      mfgAlerts.map((a, i) => ({
        ...a,
        id: `${i}-${a.event ?? a.message ?? ""}`,
      }))
    );
  }, [mfgAlerts]);

  const simProgress = state.simulation_length
    ? Math.min((state.tick / state.simulation_length) * 100, 100)
    : 0;

  return (
    <div className="w-full h-full flex flex-col gap-2 p-2 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ backgroundColor: "#a371f7", boxShadow: "0 0 6px #a371f7" }}
          />
          <span className="text-[11px] font-bold tracking-widest text-[#a371f7] font-mono">
            MFG v2
          </span>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono">
          <MetricBadge label="Tick" value={state.tick ?? 0} color="#00d9ff" />
          <MetricBadge
            label="Fitness"
            value={(state.fitness ?? 0).toFixed(2)}
            color={state.fitness > 0 ? "#7ee787" : "#f87171"}
          />
        </div>
      </div>

      {/* Simulation progress */}
      <div className="shrink-0 flex items-center gap-2 text-[9px] font-mono text-[#8b949e]">
        <span>Progress</span>
        <div className="flex-1 h-[3px] rounded-full bg-[#21262d] overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${simProgress}%`, backgroundColor: "#a371f7" }}
          />
        </div>
        <span>{state.simulation_length ? `${state.tick}/${state.simulation_length}` : state.tick}</span>
      </div>

      {/* Budget */}
      <div className="shrink-0">
        <BudgetPanel budget={state.budget ?? 0} startingBudget={state.starting_budget ?? 8000} metrics={metrics} />
      </div>

      {/* Metrics row */}
      {metrics && (
        <div className="shrink-0 flex flex-wrap gap-1">
          <MetricBadge label="Thru" value={metrics.throughput} color="#00d9ff" />
          <MetricBadge label="Fulfilled" value={metrics.orders_fulfilled} color="#7ee787" />
          <MetricBadge label="Missed" value={metrics.orders_missed} color="#f87171" />
          <MetricBadge label="M.Util" value={`${(metrics.machine_utilization * 100).toFixed(0)}%`} color="#f59e0b" />
        </div>
      )}

      {/* Orders */}
      <div className="shrink-0">
        <OrdersPanel orders={state.active_orders} />
      </div>

      {/* Machines */}
      <div className="shrink-0">
        <MachineStatusRow machines={state.machines} />
      </div>

      {/* Agents */}
      <div className="shrink-0">
        <AgentStatusRow agents={state.agents} />
      </div>

      {/* Speed Control */}
      <div className="shrink-0">
        <SpeedControl />
      </div>

      {/* Dismissible toast alerts */}
      {alertsWithIds.length > 0 && (
        <div className="shrink-0">
          <ToastAlerts alerts={alertsWithIds} />
        </div>
      )}

      {state.done && (
        <div className="shrink-0 p-2 rounded-lg border border-[#7ee787] bg-[#7ee78708] text-center">
          <p className="text-[11px] font-bold font-mono text-[#7ee787]">✓ SIMULATION COMPLETE</p>
          <p className="text-[9px] font-mono text-[#8b949e]">
            Profit: ${(metrics?.current_profit ?? 0).toFixed(0)} | Fitness: {(state.fitness ?? 0).toFixed(3)}
          </p>
        </div>
      )}
    </div>
  );
}
