import { useEffect, useRef } from "react";
import { useGameState } from "@/hooks/useGameState";

const ROLE_ICONS: Record<string, string> = {
  warehouse:   "W",
  distributor: "D",
  retailer:    "R",
  supplier:    "S",
  worker:      "A",
  orchestrator: "O",
  evaluator:   "E",
  rescuer:     "X",
  coordinator: "C",
};

function drawResourcePanel(
  ctx: CanvasRenderingContext2D,
  resources: Record<string, number>,
  width: number,
  height: number,
) {
  const panelH = 56;
  const panelY = height - panelH;

  // Semi-transparent background strip
  ctx.fillStyle = "rgba(22, 27, 34, 0.88)";
  ctx.fillRect(0, panelY, width, panelH);
  ctx.strokeStyle = "#30363d";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, panelY);
  ctx.lineTo(width, panelY);
  ctx.stroke();

  const metrics: [string, string, string][] = [
    ["STOCK",  String(resources.stock_level  ?? 0), "#00d9ff"],
    ["DEMAND", String(resources.demand_queue ?? 0), "#f59e0b"],
    ["BACKLOG",String(resources.backlog      ?? 0), "#f87171"],
    ["COST",   String(resources.carrying_cost ?? 0), "#7ee787"],
  ];

  const colW = width / metrics.length;
  metrics.forEach(([label, value, color], i) => {
    const cx = i * colW + colW / 2;
    // Label
    ctx.fillStyle = "#8b949e";
    ctx.font = "10px var(--font-mono, monospace)";
    ctx.textAlign = "center";
    ctx.fillText(label, cx, panelY + 16);
    // Value bar (normalized to max 1000)
    const maxVal = label === "COST" ? 1 : 1000;
    const pct = Math.min(Number(value) / maxVal, 1);
    const barW = colW * 0.7;
    const barH = 5;
    const barX = cx - barW / 2;
    ctx.fillStyle = "#30363d";
    ctx.fillRect(barX, panelY + 22, barW, barH);
    ctx.fillStyle = color;
    ctx.fillRect(barX, panelY + 22, barW * pct, barH);
    // Numeric
    ctx.fillStyle = color;
    ctx.font = "bold 11px var(--font-mono, monospace)";
    ctx.fillText(value, cx, panelY + 44);
  });
}

function drawResourceNodes(
  ctx: CanvasRenderingContext2D,
  resources: Record<string, number>,
  cellWidth: number,
  cellHeight: number,
  gridSize: number,
) {
  // Draw fixed resource depot icons at grid corners/midpoints
  const depots: [number, number, string, string][] = [
    [0, 0, "STOCK", "#00d9ff"],
    [gridSize - 1, 0, "DEM", "#f59e0b"],
    [0, gridSize - 1, "SUP", "#7ee787"],
    [gridSize - 1, gridSize - 1, "LOG", "#f87171"],
  ];
  depots.forEach(([gx, gy, label, color]) => {
    const px = gx * cellWidth + cellWidth / 2;
    const py = gy * cellHeight + cellHeight / 2;
    const r = Math.min(cellWidth, cellHeight) * 0.22;

    // Depot square icon
    ctx.fillStyle = color + "22";
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.rect(px - r, py - r, r * 2, r * 2);
    ctx.fill();
    ctx.stroke();

    // Label inside
    ctx.fillStyle = color;
    ctx.font = `bold ${Math.max(8, r * 0.9)}px var(--font-mono, monospace)`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, px, py);
    ctx.textBaseline = "alphabetic";
  });
}

export default function GameViewport() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { gameState, getRoleColor } = useGameState();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width;
    canvas.height = height;

    // Background
    ctx.fillStyle = "#0d1117";
    ctx.fillRect(0, 0, width, height);

    if (!gameState) {
      ctx.fillStyle = "#8b949e";
      ctx.font = "16px var(--font-mono, monospace)";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("WAITING FOR SIMULATION", width / 2, height / 2);
      ctx.textBaseline = "alphabetic";
      return;
    }

    const gridSize = gameState.resources?.grid_size ?? 8;
    const cellWidth = width / gridSize;
    const resourcePanelH = 56;
    const gridHeight = height - resourcePanelH;
    const cellHeight = gridHeight / gridSize;

    // Grid lines
    ctx.strokeStyle = "#30363d";
    ctx.lineWidth = 0.5;
    for (let x = 0; x <= width; x += cellWidth) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, gridHeight); ctx.stroke();
    }
    for (let y = 0; y <= gridHeight; y += cellHeight) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
    }

    // Resource depot icons at grid corners
    drawResourceNodes(ctx, gameState.resources as Record<string, number>, cellWidth, cellHeight, gridSize);

    // Agents as filled circles with role letter
    if (gameState.agents) {
      gameState.agents.forEach((agent) => {
        const cx = agent.x * cellWidth + cellWidth / 2;
        const cy = agent.y * cellHeight + cellHeight / 2;
        const r = Math.min(cellWidth, cellHeight) * 0.3;
        const color = getRoleColor(agent.role);

        // Glow ring
        ctx.strokeStyle = color + "55";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(cx, cy, r + 3, 0, 2 * Math.PI);
        ctx.stroke();

        // Filled circle
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, 2 * Math.PI);
        ctx.fill();

        // Role initial inside
        const icon = ROLE_ICONS[agent.role.toLowerCase()] ?? agent.role[0]?.toUpperCase() ?? "?";
        ctx.fillStyle = "#0d1117";
        ctx.font = `bold ${Math.max(9, r * 0.85)}px var(--font-mono, monospace)`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(icon, cx, cy);
        ctx.textBaseline = "alphabetic";
      });
    }

    // HUD overlay — scenario + tick
    ctx.fillStyle = "rgba(22, 27, 34, 0.75)";
    ctx.fillRect(8, 8, 200, 40);
    ctx.fillStyle = "#e6edf3";
    ctx.font = "12px var(--font-sans, sans-serif)";
    ctx.textAlign = "left";
    ctx.fillText(`Scenario: ${gameState.scenario}`, 16, 24);
    ctx.fillStyle = "#00d9ff";
    ctx.fillText(`Score: ${gameState.score.toFixed(4)}  Tick: ${gameState.tick}`, 16, 40);

    // Resource panel at the bottom
    drawResourcePanel(ctx, gameState.resources as Record<string, number>, width, height);

  }, [gameState, getRoleColor]);

  return (
    <div className="w-full h-full relative">
      <canvas
        ref={canvasRef}
        className="w-full h-full bg-[#0d1117] block"
        data-testid="canvas-game-viewport"
      />
    </div>
  );
}
