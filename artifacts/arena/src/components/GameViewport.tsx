import { useEffect, useRef } from "react";
import { useGameState } from "@/hooks/useGameState";

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

    // Clear background
    ctx.fillStyle = "#0d1117";
    ctx.fillRect(0, 0, width, height);

    if (!gameState) {
      ctx.fillStyle = "#8b949e";
      ctx.font = "16px var(--font-mono)";
      ctx.textAlign = "center";
      ctx.fillText("WAITING FOR SIMULATION", width / 2, height / 2);
      return;
    }

    // Draw Grid
    const gridSize = gameState.resources?.grid_size || 8;
    const cellWidth = width / gridSize;
    const cellHeight = height / gridSize;

    ctx.strokeStyle = "#30363d";
    ctx.lineWidth = 1;
    for (let x = 0; x <= width; x += cellWidth) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y <= height; y += cellHeight) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Draw Agents
    if (gameState.agents) {
      gameState.agents.forEach((agent) => {
        ctx.fillStyle = getRoleColor(agent.role);
        ctx.beginPath();
        const cx = agent.x * cellWidth + cellWidth / 2;
        const cy = agent.y * cellHeight + cellHeight / 2;
        ctx.arc(cx, cy, Math.min(cellWidth, cellHeight) * 0.3, 0, 2 * Math.PI);
        ctx.fill();
      });
    }

    // Draw scenario and score
    ctx.fillStyle = "#e6edf3";
    ctx.font = "14px var(--font-sans)";
    ctx.textAlign = "left";
    ctx.fillText(`Scenario: ${gameState.scenario}`, 16, 24);
    ctx.fillStyle = "#00d9ff";
    ctx.fillText(`Score: ${gameState.score}`, 16, 44);

  }, [gameState, getRoleColor]);

  return (
    <div className="w-full h-full relative">
      <canvas
        ref={canvasRef}
        className="w-full h-full bg-[#0d1117] border-b border-border block"
        data-testid="canvas-game-viewport"
      />
    </div>
  );
}
