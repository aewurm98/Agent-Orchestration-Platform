import { useEffect, useRef } from "react";
import type { MfgGameState } from "@/context/SocketContext";

const CELL_COLORS: Record<string, string> = {
  floor:         "#0f1923",
  wall:          "#2d3540",
  conveyor:      "#0f2918",
  machine_slot:  "#14122a",
  loading_dock:  "#0f2318",
  shipping_dock: "#0f1a2a",
  storage_zone:  "#231f0f",
};

const CELL_BORDER: Record<string, string> = {
  floor:         "#1c2433",
  wall:          "#444c58",
  conveyor:      "#1a4228",
  machine_slot:  "#2a2550",
  loading_dock:  "#1f5c3a",
  shipping_dock: "#1a3a6b",
  storage_zone:  "#5c4e1a",
};

const MACHINE_EMOJI: Record<string, string> = {
  smelter:          "🔥",
  stamping_press:   "🔨",
  assembly_station: "⚙️",
  qc:               "🔍",
  packaging:        "📦",
  circuit_fab:      "💡",
};

const MACHINE_STATE_COLOR: Record<string, string> = {
  idle:         "#8b949e",
  loading:      "#f59e0b",
  processing:   "#00d9ff",
  output_ready: "#7ee787",
  broken:       "#f87171",
  offline:      "#4d5566",
};

const AGENT_EMOJI: Record<string, string> = {
  procurement: "🛒",
  operations:  "👷",
  engineering: "🔧",
  sales:       "💼",
  management:  "👔",
};

const AGENT_COLOR: Record<string, string> = {
  procurement: "#f59e0b",
  operations:  "#00d9ff",
  engineering: "#a371f7",
  sales:       "#7ee787",
  management:  "#f87171",
};

function drawCell(
  ctx: CanvasRenderingContext2D,
  cellType: string,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  const bg = CELL_COLORS[cellType] ?? CELL_COLORS.floor;
  const border = CELL_BORDER[cellType] ?? CELL_BORDER.floor;

  ctx.fillStyle = bg;
  ctx.fillRect(x, y, w, h);

  ctx.strokeStyle = border;
  ctx.lineWidth = 0.5;
  ctx.strokeRect(x + 0.25, y + 0.25, w - 0.5, h - 0.5);

  if (cellType === "loading_dock") {
    ctx.fillStyle = "#1f5c3a66";
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);
    ctx.fillStyle = "#2ecc7144";
    ctx.font = `${Math.min(w, h) * 0.35}px serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("IN", x + w / 2, y + h / 2);
  } else if (cellType === "shipping_dock") {
    ctx.fillStyle = "#1a3a6b66";
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);
    ctx.fillStyle = "#00d9ff44";
    ctx.font = `${Math.min(w, h) * 0.35}px serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("OUT", x + w / 2, y + h / 2);
  } else if (cellType === "storage_zone") {
    ctx.fillStyle = "#5c4e1a44";
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);
  } else if (cellType === "conveyor") {
    ctx.strokeStyle = "#1a4228";
    ctx.lineWidth = 1;
    const numArrows = 2;
    for (let i = 0; i < numArrows; i++) {
      const ax = x + (w / (numArrows + 1)) * (i + 1);
      const ay = y + h / 2;
      ctx.beginPath();
      ctx.moveTo(ax - 2, ay);
      ctx.lineTo(ax + 2, ay);
      ctx.lineTo(ax + 1, ay - 2);
      ctx.moveTo(ax + 2, ay);
      ctx.lineTo(ax + 1, ay + 2);
      ctx.stroke();
    }
  }
}

function drawMachine(
  ctx: CanvasRenderingContext2D,
  machine: {
    type: string;
    state: string;
    row: number;
    col: number;
    processing_ticks_remaining: number;
    health: number;
    total_produced: number;
    input_queue_len: number;
    output_queue_len: number;
  },
  x: number,
  y: number,
  w: number,
  h: number,
  tick: number,
) {
  const stateColor = MACHINE_STATE_COLOR[machine.state] ?? "#8b949e";
  const emoji = MACHINE_EMOJI[machine.type] ?? "🔩";

  const glowAmt = machine.state === "processing" ? Math.sin(tick * 0.3) * 0.4 + 0.6 :
                  machine.state === "output_ready" ? 1.0 :
                  machine.state === "broken" ? (Math.sin(tick * 0.5) * 0.5 + 0.5) : 0.3;

  if (machine.state !== "offline") {
    ctx.save();
    ctx.shadowColor = stateColor;
    ctx.shadowBlur = 8 * glowAmt;
    ctx.strokeStyle = stateColor + Math.round(glowAmt * 200).toString(16).padStart(2, "0");
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x + 2, y + 2, w - 4, h - 4);
    ctx.restore();
  }

  ctx.fillStyle = stateColor + "22";
  ctx.fillRect(x + 2, y + 2, w - 4, h - 4);

  ctx.font = `${Math.min(w, h) * 0.42}px serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(emoji, x + w / 2, y + h / 2 - 2);

  if (machine.state === "processing" && machine.processing_ticks_remaining > 0) {
    const barW = (w - 8);
    const barH = 3;
    const barX = x + 4;
    const barY = y + h - 6;
    ctx.fillStyle = "#30363d";
    ctx.fillRect(barX, barY, barW, barH);
    ctx.fillStyle = "#00d9ff";
    const pct = Math.max(0, 1 - machine.processing_ticks_remaining / 6);
    ctx.fillRect(barX, barY, barW * pct, barH);
  }

  if (machine.input_queue_len > 0 || machine.output_queue_len > 0) {
    ctx.fillStyle = "#f59e0b";
    ctx.font = `bold ${Math.min(w, h) * 0.22}px monospace`;
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(`${machine.input_queue_len}→`, x + 3, y + 3);
  }
  if (machine.output_queue_len > 0) {
    ctx.fillStyle = "#7ee787";
    ctx.font = `bold ${Math.min(w, h) * 0.22}px monospace`;
    ctx.textAlign = "right";
    ctx.textBaseline = "top";
    ctx.fillText(`→${machine.output_queue_len}`, x + w - 3, y + 3);
  }
}

function drawAgent(
  ctx: CanvasRenderingContext2D,
  agent: { role: string; row: number; col: number; state: string; inventory_count: number },
  x: number,
  y: number,
  w: number,
  h: number,
  tick: number,
) {
  const color = AGENT_COLOR[agent.role] ?? "#e6edf3";
  const emoji = AGENT_EMOJI[agent.role] ?? "👤";
  const r = Math.min(w, h) * 0.28;
  const cx = x + w / 2;
  const cy = y + h / 2;

  const isWorking = agent.state === "working";
  const glowPulse = isWorking ? Math.sin(tick * 0.4) * 0.4 + 0.8 : 0.6;

  ctx.save();
  ctx.shadowColor = color;
  ctx.shadowBlur = isWorking ? 12 * glowPulse : 4;
  ctx.fillStyle = color + "44";
  ctx.beginPath();
  ctx.arc(cx, cy, r + 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  ctx.fillStyle = color + "22";
  ctx.beginPath();
  ctx.arc(cx, cy, r + 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(cx, cy, r + 2, 0, Math.PI * 2);
  ctx.stroke();

  ctx.font = `${r * 1.3}px serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(emoji, cx, cy - 1);

  if (agent.inventory_count > 0) {
    ctx.fillStyle = color;
    ctx.font = `bold ${Math.min(w, h) * 0.2}px monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText(`${agent.inventory_count}`, cx, y + h - 1);
  }
}

function drawItem(
  ctx: CanvasRenderingContext2D,
  item: { type: string; row: number; col: number },
  x: number,
  y: number,
  w: number,
  h: number,
  offsetX: number,
  offsetY: number,
) {
  const ITEM_COLORS: Record<string, string> = {
    raw_ore:         "#f87171",
    raw_silicon:     "#a371f7",
    metal_ingot:     "#f59e0b",
    stamped_part:    "#fbbf24",
    circuit:         "#00d9ff",
    subassembly:     "#7ee787",
    inspected_unit:  "#86efac",
    finished_product: "#22d3ee",
    reject:          "#6b7280",
  };
  const color = ITEM_COLORS[item.type] ?? "#e6edf3";
  const dotR = Math.min(w, h) * 0.1;
  const dotX = x + w * 0.5 + offsetX * dotR * 2.5;
  const dotY = y + h * 0.5 + offsetY * dotR * 2.5;

  ctx.fillStyle = color + "cc";
  ctx.beginPath();
  ctx.arc(dotX, dotY, dotR, 0, Math.PI * 2);
  ctx.fill();
}

export default function GridCanvas({ state }: { state: MfgGameState }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const tickRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const render = () => {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      tickRef.current += 1;
      const t = tickRef.current;

      const W = canvas.clientWidth;
      const H = canvas.clientHeight;
      if (canvas.width !== W || canvas.height !== H) {
        canvas.width = W;
        canvas.height = H;
      }

      const rows = state.grid_rows ?? state.grid?.length ?? 10;
      const cols = state.grid_cols ?? (state.grid?.[0]?.length ?? 10);
      const cellW = W / cols;
      const cellH = H / rows;

      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = "#0a0e15";
      ctx.fillRect(0, 0, W, H);

      if (state.grid) {
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            const cellType = state.grid[r]?.[c] ?? "floor";
            drawCell(ctx, cellType, c * cellW, r * cellH, cellW, cellH);
          }
        }
      }

      if (state.machines) {
        for (const machine of Object.values(state.machines)) {
          const x = machine.col * cellW;
          const y = machine.row * cellH;
          drawMachine(ctx, machine, x, y, cellW, cellH, t);
        }
      }

      if (state.items) {
        const itemsByCell: Record<string, typeof state.items> = {};
        for (const item of state.items) {
          if (item.row == null || item.col == null) continue;
          const key = `${item.row},${item.col}`;
          if (!itemsByCell[key]) itemsByCell[key] = [];
          itemsByCell[key].push(item);
        }
        for (const [key, cellItems] of Object.entries(itemsByCell)) {
          const [r, c] = key.split(",").map(Number);
          const x = c * cellW;
          const y = r * cellH;
          const offsets = [[-1,-1],[1,-1],[-1,1],[1,1],[0,0]];
          cellItems.slice(0, 4).forEach((item, i) => {
            const [ox, oy] = offsets[i] ?? [0, 0];
            drawItem(ctx, item, x, y, cellW, cellH, ox, oy);
          });
        }
      }

      if (state.agents) {
        for (const agent of Object.values(state.agents)) {
          const x = agent.col * cellW;
          const y = agent.row * cellH;
          drawAgent(ctx, agent, x, y, cellW, cellH, t);
        }
      }

      ctx.fillStyle = "rgba(10,14,21,0.75)";
      ctx.fillRect(8, 8, 190, 42);
      ctx.strokeStyle = "#30363d";
      ctx.lineWidth = 1;
      ctx.strokeRect(8, 8, 190, 42);
      ctx.fillStyle = "#8b949e";
      ctx.font = "10px monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("MANUFACTURING GRID", 16, 16);
      ctx.fillStyle = "#00d9ff";
      ctx.font = "bold 11px monospace";
      ctx.fillText(
        `Tick: ${state.tick ?? 0}  Score: ${(state.fitness ?? 0).toFixed(3)}`,
        16,
        30,
      );

      animRef.current = requestAnimationFrame(render);
    };

    animRef.current = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animRef.current);
  }, [state]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-full block"
      data-testid="mfg-grid-canvas"
    />
  );
}
