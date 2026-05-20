import { useEffect, useRef } from "react";
import { useGameState } from "@/hooks/useGameState";
import { useSocket } from "@/hooks/useSocket";
import ManufacturingView from "@/components/ManufacturingView";
import SupplyChainView from "@/components/SupplyChainView";
import type { GameAgent } from "@/context/SocketContext";

const ROLE_EMOJI: Record<string, string> = {
  supplier:    "🏭",
  warehouse:   "🏪",
  distributor: "🚚",
  retailer:    "🛒",
};

const ROLE_COLOR: Record<string, string> = {
  supplier:    "#b91c1c",
  warehouse:   "#14120e",
  distributor: "#b45309",
  retailer:    "#15803d",
};

const ROLE_TINT: Record<string, string> = {
  supplier:    "#fbeaea",
  warehouse:   "#efe9d9",
  distributor: "#fdf2dd",
  retailer:    "#e6f4ea",
};

const FLOW_ROUTES: Array<[string, string]> = [
  ["supplier",    "warehouse"],
  ["warehouse",   "distributor"],
  ["distributor", "retailer"],
];

function roleColor(role: string): string {
  return ROLE_COLOR[role.toLowerCase()] ?? "#14120e";
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number, r: number,
) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y,     x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x,     y + h, radius);
  ctx.arcTo(x,     y + h, x,     y,     radius);
  ctx.arcTo(x,     y,     x + w, y,     radius);
  ctx.closePath();
}

function drawFlowLines(
  ctx: CanvasRenderingContext2D,
  agents: GameAgent[],
  cellW: number,
  cellH: number,
) {
  const byRole = (role: string) => agents.filter((a) => a.role === role);
  for (const [srcRole, tgtRole] of FLOW_ROUTES) {
    for (const src of byRole(srcRole)) {
      for (const tgt of byRole(tgtRole)) {
        const x1 = src.x * cellW + cellW / 2;
        const y1 = src.y * cellH + cellH / 2;
        const x2 = tgt.x * cellW + cellW / 2;
        const y2 = tgt.y * cellH + cellH / 2;
        // Gentle curved bow between source and target
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2 - Math.abs(x2 - x1) * 0.08;

        ctx.save();
        ctx.strokeStyle = "rgba(20, 18, 14, 0.18)";
        ctx.lineWidth = 1.25;
        ctx.setLineDash([3, 5]);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.quadraticCurveTo(mx, my, x2, y2);
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
  // Slightly larger card — easier to see than before
  const cardW = Math.min(cellW * 1.5, 78);
  const cardH = Math.min(cellH * 1.5, 78);
  const x = cx - cardW / 2;
  const y = cy - cardH / 2;
  const color = roleColor(agent.role);
  const tint = ROLE_TINT[agent.role.toLowerCase()] ?? "#efe9d9";
  const emoji = ROLE_EMOJI[agent.role.toLowerCase()] ?? "?";
  const isActive =
    agent.state === "delivering" ||
    agent.state === "fetching" ||
    agent.state === "generating";

  // Active glow ring
  if (isActive) {
    ctx.save();
    ctx.shadowColor = color;
    ctx.shadowBlur = 14;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    roundRect(ctx, x - 2, y - 2, cardW + 4, cardH + 4, 12);
    ctx.stroke();
    ctx.restore();
  }

  // Card body
  ctx.fillStyle = "#ffffff";
  roundRect(ctx, x, y, cardW, cardH, 10);
  ctx.fill();

  // Tinted top stripe (role accent)
  ctx.save();
  ctx.fillStyle = tint;
  roundRect(ctx, x, y, cardW, cardH * 0.42, 10);
  ctx.fill();
  // Re-clip bottom of top-stripe so only the rounded top tints
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(x, y + cardH * 0.42 - 1, cardW, 2);
  ctx.restore();

  // Card border
  ctx.strokeStyle = color;
  ctx.lineWidth = isActive ? 1.5 : 1;
  roundRect(ctx, x, y, cardW, cardH, 10);
  ctx.stroke();

  // Emoji — larger than before
  ctx.font = `${Math.max(20, cardW * 0.36)}px "Apple Color Emoji", "Segoe UI Emoji", serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(emoji, cx, y + cardH * 0.30);

  // Value (inventory or delivered for retailers)
  const displayCount =
    agent.role === "retailer" && (agent as any).delivered != null
      ? (agent as any).delivered
      : agent.inventory;
  ctx.fillStyle = color;
  ctx.font = `bold ${Math.max(11, cardW * 0.18)}px 'JetBrains Mono', monospace`;
  ctx.textBaseline = "middle";
  ctx.fillText(String(displayCount), cx, y + cardH * 0.68);

  // Role label (very small, under value)
  ctx.fillStyle = "#6b6359";
  ctx.font = `${Math.max(8, cardW * 0.11)}px 'JetBrains Mono', monospace`;
  ctx.fillText(
    agent.role.toUpperCase(),
    cx,
    y + cardH * 0.86,
  );
}

function drawHudCard(
  ctx: CanvasRenderingContext2D,
  scenario: string,
  score: number,
  tick: number,
) {
  const x = 10, y = 10, w = 200, h = 50;
  ctx.save();
  // Card body — white with warm border
  ctx.fillStyle = "#ffffff";
  roundRect(ctx, x, y, w, h, 10);
  ctx.fill();
  ctx.strokeStyle = "#ebe5d6";
  ctx.lineWidth = 1;
  roundRect(ctx, x, y, w, h, 10);
  ctx.stroke();

  // Scenario label
  ctx.fillStyle = "#6b6359";
  ctx.font = "600 9px 'Inter', system-ui, sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText(scenario.replace(/_/g, " ").toUpperCase(), x + 12, y + 8);

  // Score + tick
  ctx.fillStyle = "#14120e";
  ctx.font = "bold 14px 'JetBrains Mono', monospace";
  ctx.fillText(`Tick ${tick}`, x + 12, y + 22);
  ctx.fillStyle = "#b45309";
  ctx.fillText(`Score ${score.toFixed(2)}`, x + 92, y + 22);
  ctx.restore();
}

function drawLegend(
  ctx: CanvasRenderingContext2D,
  width: number,
) {
  const entries: [string, string, string][] = [
    ["🏭", "Supplier",    "#b91c1c"],
    ["🏪", "Warehouse",   "#14120e"],
    ["🚚", "Distributor", "#b45309"],
    ["🛒", "Retailer",    "#15803d"],
  ];
  const w = 116, lineH = 18, pad = 8;
  const h = entries.length * lineH + pad * 2;
  const x = width - w - 10;
  const y = 10;

  ctx.save();
  ctx.fillStyle = "#ffffff";
  roundRect(ctx, x, y, w, h, 10);
  ctx.fill();
  ctx.strokeStyle = "#ebe5d6";
  ctx.lineWidth = 1;
  roundRect(ctx, x, y, w, h, 10);
  ctx.stroke();

  entries.forEach(([icon, label, color], i) => {
    const ly = y + pad + i * lineH + lineH / 2;
    // colored dot
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x + pad + 3, ly, 3, 0, Math.PI * 2);
    ctx.fill();
    // emoji
    ctx.font = "12px 'Apple Color Emoji', 'Segoe UI Emoji', serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(icon, x + pad + 12, ly);
    // label
    ctx.fillStyle = "#14120e";
    ctx.font = "11px 'Inter', system-ui, sans-serif";
    ctx.fillText(label, x + pad + 30, ly);
  });
  ctx.restore();
}

function drawResourcePanel(
  ctx: CanvasRenderingContext2D,
  resources: Record<string, number>,
  width: number,
  height: number,
  panelH: number,
) {
  const panelY = height - panelH;
  const pad = 8;
  // Outer cream strip with top divider
  ctx.fillStyle = "#faf6ed";
  ctx.fillRect(0, panelY, width, panelH);
  ctx.strokeStyle = "#ebe5d6";
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, panelY); ctx.lineTo(width, panelY); ctx.stroke();

  const metrics: [string, number, number, string][] = [
    ["STOCK",     resources.stock_level      ?? 0, 2000, "#14120e"],
    ["DEMAND",    resources.demand_queue     ?? 0, 500,  "#b45309"],
    ["BACKLOG",   resources.backlog          ?? 0, 500,  "#b91c1c"],
    ["DELIVERED", resources.total_delivered  ?? 0, 2000, "#15803d"],
  ];

  const tileW = (width - pad * (metrics.length + 1)) / metrics.length;
  const tileH = panelH - pad * 2;
  metrics.forEach(([label, value, max, color], i) => {
    const tx = pad + i * (tileW + pad);
    const ty = panelY + pad;

    // Tile card
    ctx.fillStyle = "#ffffff";
    roundRect(ctx, tx, ty, tileW, tileH, 8);
    ctx.fill();
    ctx.strokeStyle = "#ebe5d6";
    ctx.lineWidth = 1;
    roundRect(ctx, tx, ty, tileW, tileH, 8);
    ctx.stroke();

    // Label
    ctx.fillStyle = "#6b6359";
    ctx.font = "600 9px 'Inter', system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(label, tx + 10, ty + 8);

    // Value
    ctx.fillStyle = color;
    ctx.font = "bold 16px 'JetBrains Mono', monospace";
    ctx.textAlign = "right";
    ctx.fillText(String(value), tx + tileW - 10, ty + 6);

    // Capacity bar
    const pct = Math.min(value / max, 1);
    const barX = tx + 10;
    const barY = ty + tileH - 8;
    const barW = tileW - 20;
    ctx.fillStyle = "#efe9d9";
    roundRect(ctx, barX, barY, barW, 3, 2);
    ctx.fill();
    ctx.fillStyle = color;
    roundRect(ctx, barX, barY, barW * pct, 3, 2);
    ctx.fill();
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

    // High-DPI scaling for crisp text + shapes
    const dpr = window.devicePixelRatio || 1;
    const width  = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width  = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Cream backdrop
    ctx.fillStyle = "#f4f0e7";
    ctx.fillRect(0, 0, width, height);

    if (!gameState) {
      ctx.fillStyle = "#6b6359";
      ctx.font = "13px 'Inter', system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("Waiting for simulation…", width / 2, height / 2);
      return;
    }

    const gridSize = gameState.resources?.grid_size ?? 10;
    const panelH   = 64;
    const gridH    = height - panelH;
    const cellW    = width  / gridSize;
    const cellH    = gridH  / gridSize;

    // Subtle grid lines — barely visible warm beige
    ctx.strokeStyle = "rgba(20, 18, 14, 0.04)";
    ctx.lineWidth   = 1;
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

    drawHudCard(ctx, gameState.scenario, gameState.score, gameState.tick);
    drawLegend(ctx, width);
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
  const { mfgState } = useSocket();

  const isManufacturing =
    mfgState?.grid != null || gameState?.scenario === "manufacturing";

  if (isManufacturing) {
    const legacyGameState = gameState ?? {
      scenario: "manufacturing",
      agents: [],
      resources: {},
      score: 0,
      tick: mfgState?.tick ?? 0,
    };
    return (
      <div className="w-full h-full bg-transparent" data-testid="manufacturing-view">
        <ManufacturingView gameState={legacyGameState as import("@/context/SocketContext").GameState} />
      </div>
    );
  }

  if (gameState && gameState.scenario === "supply_chain") {
    return (
      <div className="w-full h-full bg-transparent" data-testid="supply-chain-viewport">
        <SupplyChainView gameState={gameState} />
      </div>
    );
  }

  return (
    <div className="w-full h-full relative bg-transparent">
      <GridCanvas />
    </div>
  );
}
