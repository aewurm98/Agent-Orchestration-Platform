import { useEffect, useRef } from "react";
import { useGameState } from "@/hooks/useGameState";
import ManufacturingView from "@/components/ManufacturingView";
import type { GameAgent } from "@/context/SocketContext";

const ROLE_EMOJI: Record<string, string> = {
  supplier:    "🏭",
  warehouse:   "🏪",
  distributor: "🚚",
  retailer:    "🛒",
};

const ROLE_COLOR: Record<string, string> = {
  supplier:    "#ff6b6b",
  warehouse:   "#00d9ff",
  distributor: "#f59e0b",
  retailer:    "#7ee787",
};

const FLOW_ROUTES: Array<[string, string, string]> = [
  ["supplier",    "warehouse",   "#ff6b6b"],
  ["warehouse",   "distributor", "#00d9ff"],
  ["distributor", "retailer",    "#f59e0b"],
];

function roleColor(role: string): string {
  return ROLE_COLOR[role.toLowerCase()] ?? "#e6edf3";
}

function drawFlowLines(
  ctx: CanvasRenderingContext2D,
  agents: GameAgent[],
  cellW: number,
  cellH: number,
) {
  const byRole = (role: string) => agents.filter((a) => a.role === role);
  for (const [srcRole, tgtRole, color] of FLOW_ROUTES) {
    for (const src of byRole(srcRole)) {
      for (const tgt of byRole(tgtRole)) {
        ctx.save();
        ctx.strokeStyle = color + "33";
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 6]);
        ctx.beginPath();
        ctx.moveTo(src.x * cellW + cellW / 2, src.y * cellH + cellH / 2);
        ctx.lineTo(tgt.x * cellW + cellW / 2, tgt.y * cellH + cellH / 2);
        ctx.stroke();
        ctx.restore();
      }
    }
  }
}

function drawAgent(
  ctx: CanvasRenderingContext2D,
  agent: GameAgent,
  cellW: number,
  cellH: number,
) {
  const cx   = agent.x * cellW + cellW / 2;
  const cy   = agent.y * cellH + cellH / 2;
  const half = Math.min(cellW, cellH) * 0.38;
  const color = roleColor(agent.role);
  const emoji = ROLE_EMOJI[agent.role.toLowerCase()] ?? "?";
  const isActive = agent.state === "delivering" || agent.state === "generating";

  if (isActive) {
    ctx.save();
    ctx.shadowColor = color;
    ctx.shadowBlur = 10;
    ctx.strokeStyle = color + "88";
    ctx.lineWidth = 2;
    ctx.strokeRect(cx - half - 3, cy - half - 3, (half + 3) * 2, (half + 3) * 2);
    ctx.restore();
  }

  ctx.fillStyle = color + "22";
  ctx.fillRect(cx - half, cy - half, half * 2, half * 2);
  ctx.strokeStyle = color;
  ctx.lineWidth = isActive ? 2 : 1;
  ctx.strokeRect(cx - half, cy - half, half * 2, half * 2);

  ctx.font = `${Math.max(12, half * 0.85)}px serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(emoji, cx, cy - half * 0.12);

  ctx.fillStyle = color;
  ctx.font = `bold ${Math.max(7, half * 0.42)}px monospace`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(agent.inventory), cx, cy + half * 0.52);
}

function drawResourcePanel(
  ctx: CanvasRenderingContext2D,
  resources: Record<string, number>,
  width: number,
  height: number,
  panelH: number,
) {
  const panelY = height - panelH;
  ctx.fillStyle = "rgba(13, 17, 23, 0.92)";
  ctx.fillRect(0, panelY, width, panelH);
  ctx.strokeStyle = "#30363d";
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, panelY); ctx.lineTo(width, panelY); ctx.stroke();

  const metrics: [string, number, number, string][] = [
    ["STOCK",     resources.stock_level      ?? 0, 2000,  "#00d9ff"],
    ["DEMAND",    resources.demand_queue     ?? 0, 500,   "#f59e0b"],
    ["BACKLOG",   resources.backlog          ?? 0, 500,   "#f87171"],
    ["DELIVERED", resources.total_delivered  ?? 0, 2000,  "#7ee787"],
  ];

  const colW = width / metrics.length;
  metrics.forEach(([label, value, max, color], i) => {
    const cx = i * colW + colW / 2;
    ctx.fillStyle = "#8b949e";
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText(label, cx, panelY + 6);

    const pct = Math.min(value / max, 1);
    const barW = colW * 0.72;
    const barX = cx - barW / 2;
    ctx.fillStyle = "#30363d";
    ctx.fillRect(barX, panelY + 22, barW, 5);
    ctx.fillStyle = color;
    ctx.fillRect(barX, panelY + 22, barW * pct, 5);

    ctx.fillStyle = color;
    ctx.font = "bold 11px monospace";
    ctx.textBaseline = "top";
    ctx.fillText(String(value), cx, panelY + 32);
  });
}

// ── Canvas renderer for supply chain / other grid-based scenarios ─────────────

function GridCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { gameState } = useGameState();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width  = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width  = width;
    canvas.height = height;

    ctx.fillStyle = "#0d1117";
    ctx.fillRect(0, 0, width, height);

    if (!gameState) {
      ctx.fillStyle = "#8b949e";
      ctx.font = "16px monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("WAITING FOR SIMULATION", width / 2, height / 2);
      return;
    }

    const gridSize = gameState.resources?.grid_size ?? 10;
    const panelH   = 54;
    const gridH    = height - panelH;
    const cellW    = width  / gridSize;
    const cellH    = gridH  / gridSize;

    // Grid lines
    ctx.strokeStyle = "#21262d";
    ctx.lineWidth   = 0.5;
    for (let c = 0; c <= gridSize; c++) {
      ctx.beginPath(); ctx.moveTo(c * cellW, 0); ctx.lineTo(c * cellW, gridH); ctx.stroke();
    }
    for (let r = 0; r <= gridSize; r++) {
      ctx.beginPath(); ctx.moveTo(0, r * cellH); ctx.lineTo(width, r * cellH); ctx.stroke();
    }

    if (gameState.agents?.length) {
      drawFlowLines(ctx, gameState.agents, cellW, cellH);
      for (const agent of gameState.agents) drawAgent(ctx, agent, cellW, cellH);
    }

    // HUD
    ctx.fillStyle = "rgba(22,27,34,0.82)";
    ctx.fillRect(8, 8, 210, 46);
    ctx.strokeStyle = "#30363d"; ctx.lineWidth = 1;
    ctx.strokeRect(8, 8, 210, 46);
    ctx.fillStyle = "#8b949e"; ctx.font = "11px monospace";
    ctx.textAlign = "left"; ctx.textBaseline = "top";
    ctx.fillText(`Scenario: ${gameState.scenario.replace(/_/g, " ")}`, 16, 16);
    ctx.fillStyle = "#00d9ff"; ctx.font = "bold 12px monospace";
    ctx.fillText(`Score: ${gameState.score.toFixed(2)}  Tick: ${gameState.tick}`, 16, 33);

    // Legend
    const legendEntries: [string, string][] = [
      ["🏭 Supplier", "#ff6b6b"], ["🏪 Warehouse", "#00d9ff"],
      ["🚚 Distributor", "#f59e0b"], ["🛒 Retailer", "#7ee787"],
    ];
    const legendW = 110;
    const legendPad = 6;
    const legendLineH = 14;
    const legendH = legendEntries.length * legendLineH + legendPad * 2;
    const legendX = width - legendW - 8;
    ctx.fillStyle = "rgba(22,27,34,0.82)";
    ctx.fillRect(legendX, 8, legendW, legendH);
    ctx.strokeStyle = "#30363d"; ctx.strokeRect(legendX, 8, legendW, legendH);
    legendEntries.forEach(([label, color], i) => {
      ctx.fillStyle = color;
      ctx.font = "11px monospace"; ctx.textAlign = "left"; ctx.textBaseline = "top";
      ctx.fillText(label, legendX + legendPad, 8 + legendPad + i * legendLineH);
    });

    drawResourcePanel(ctx, gameState.resources as Record<string, number>, width, height, panelH);
  }, [gameState]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-full block"
      data-testid="canvas-game-viewport"
    />
  );
}

// ── Top-level component — routes between views by scenario ────────────────────

export default function GameViewport() {
  const { gameState } = useGameState();

  if (gameState?.scenario === "manufacturing") {
    return (
      <div className="w-full h-full bg-[#0d1117]" data-testid="manufacturing-view">
        <ManufacturingView gameState={gameState} />
      </div>
    );
  }

  return (
    <div className="w-full h-full relative bg-[#0d1117]">
      <GridCanvas />
    </div>
  );
}
