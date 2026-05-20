import { useEffect, useRef, useState } from "react";
import type { MfgGameState } from "@/context/SocketContext";
import { useSocket } from "@/hooks/useSocket";

// ── Particle system ───────────────────────────────────────────────────────────

type Particle = {
  x: number; y: number; vx: number; vy: number;
  color: string; radius: number; life: number; maxLife: number;
};

function spawnParticles(cx: number, cy: number, color: string, count: number, buf: Particle[]) {
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 0.5 + Math.random() * 1.4;
    buf.push({
      x: cx + (Math.random() - 0.5) * 8,
      y: cy + (Math.random() - 0.5) * 8,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 0.3,
      color, radius: 1.5 + Math.random() * 2,
      life: 24 + Math.floor(Math.random() * 18), maxLife: 42,
    });
  }
}

function drawParticle(ctx: CanvasRenderingContext2D, p: Particle) {
  const alpha = p.life / p.maxLife;
  ctx.save();
  ctx.globalAlpha = alpha * 0.85;
  ctx.fillStyle = p.color;
  ctx.beginPath();
  ctx.arc(p.x, p.y, p.radius * alpha, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

// ── Color maps ────────────────────────────────────────────────────────────────

const ITEM_PARTICLE_COLOR: Record<string, string> = {
  raw_ore: "#b91c1c", raw_silicon: "#7c3aed", metal_ingot: "#d97706",
  stamped_part: "#b45309", circuit: "#4338ca", subassembly: "#15803d",
  inspected_unit: "#16a34a", finished_product: "#4f46e5", reject: "#64748b",
};

const CELL_BG: Record<string, string> = {
  floor: "#f1f5f9", wall: "#94a3b8", conveyor: "#dcfce7",
  machine_slot: "#ede9fe", loading_dock: "#d1fae5",
  shipping_dock: "#dbeafe", storage_zone: "#fef3c7",
};

const CELL_BORDER: Record<string, string> = {
  floor: "#e2e8f0", wall: "#64748b", conveyor: "#86efac",
  machine_slot: "#c4b5fd", loading_dock: "#6ee7b7",
  shipping_dock: "#93c5fd", storage_zone: "#fcd34d",
};

const MACHINE_STATE_COLOR: Record<string, string> = {
  idle: "#94a3b8", loading: "#f59e0b", processing: "#4338ca",
  output_ready: "#16a34a", broken: "#dc2626", offline: "#64748b",
};

const AGENT_COLOR: Record<string, string> = {
  procurement: "#d97706", operations: "#4338ca",
  engineering: "#7c3aed", sales: "#15803d", management: "#dc2626",
};

// ── Cell rendering ────────────────────────────────────────────────────────────

function drawCell(ctx: CanvasRenderingContext2D, cellType: string, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = CELL_BG[cellType] ?? CELL_BG.floor;
  ctx.fillRect(x, y, w, h);
  ctx.strokeStyle = CELL_BORDER[cellType] ?? CELL_BORDER.floor;
  ctx.lineWidth = 0.5;
  ctx.strokeRect(x + 0.25, y + 0.25, w - 0.5, h - 0.5);

  if (cellType === "conveyor") {
    ctx.strokeStyle = "#4ade80";
    ctx.lineWidth = 1;
    for (let i = 0; i < 2; i++) {
      const ax = x + (w / 3) * (i + 1);
      const ay = y + h / 2;
      ctx.beginPath();
      ctx.moveTo(ax - 3, ay - 2); ctx.lineTo(ax + 1, ay); ctx.lineTo(ax - 3, ay + 2);
      ctx.stroke();
    }
  } else if (cellType === "loading_dock") {
    ctx.fillStyle = "#10b98133";
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);
    ctx.fillStyle = "#047857";
    ctx.font = `bold ${Math.min(w, h) * 0.28}px monospace`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("IN", x + w / 2, y + h / 2);
  } else if (cellType === "shipping_dock") {
    ctx.fillStyle = "#3b82f633";
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);
    ctx.fillStyle = "#1d4ed8";
    ctx.font = `bold ${Math.min(w, h) * 0.25}px monospace`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("OUT", x + w / 2, y + h / 2);
  } else if (cellType === "storage_zone") {
    ctx.fillStyle = "#fcd34d44";
    ctx.fillRect(x + 3, y + 3, w - 6, h - 6);
    for (let i = 0; i < 3; i++) {
      const bx = x + 4 + i * (w / 4);
      ctx.fillStyle = "#92400e44";
      ctx.fillRect(bx, y + h * 0.3, w / 6, h * 0.45);
    }
  }
}

// ── Machine rendering ─────────────────────────────────────────────────────────

function drawMachine(
  ctx: CanvasRenderingContext2D,
  machine: { type: string; state: string; processing_ticks_remaining: number; health: number; total_produced: number; input_queue_len: number; output_queue_len: number },
  x: number, y: number, w: number, h: number, tick: number,
) {
  const sc = MACHINE_STATE_COLOR[machine.state] ?? "#94a3b8";
  const pad = Math.max(2, w * 0.06);
  const ix = x + pad; const iy = y + pad;
  const iw = w - pad * 2; const ih = h - pad * 2;

  const glowAmt = machine.state === "processing" ? Math.sin(tick * 0.25) * 0.5 + 0.6
    : machine.state === "output_ready" ? 1.0
    : machine.state === "broken" ? Math.sin(tick * 0.5) * 0.4 + 0.4 : 0;
  if (glowAmt > 0) {
    ctx.save();
    ctx.shadowColor = sc; ctx.shadowBlur = 10 * glowAmt;
    ctx.strokeStyle = sc + Math.round(glowAmt * 180).toString(16).padStart(2, "0");
    ctx.lineWidth = 1.5;
    ctx.strokeRect(ix, iy, iw, ih);
    ctx.restore();
  }

  ctx.fillStyle = sc + "18";
  ctx.fillRect(ix, iy, iw, ih);

  drawMachineShape(ctx, machine.type, machine.state, ix, iy, iw, ih, tick, sc);

  if (machine.state === "processing" && machine.processing_ticks_remaining > 0) {
    const pct = Math.max(0, 1 - machine.processing_ticks_remaining / 8);
    ctx.fillStyle = "#e2e8f0"; ctx.fillRect(ix, y + h - pad - 3, iw, 3);
    ctx.fillStyle = sc; ctx.fillRect(ix, y + h - pad - 3, iw * pct, 3);
  }

  if (machine.health < 1.0) {
    const barH = ih * machine.health;
    ctx.fillStyle = "#f1f5f9"; ctx.fillRect(x + w - pad - 2, iy, 2, ih);
    const hColor = machine.health > 0.6 ? "#16a34a" : machine.health > 0.3 ? "#f59e0b" : "#dc2626";
    ctx.fillStyle = hColor; ctx.fillRect(x + w - pad - 2, iy + ih - barH, 2, barH);
  }

  const badgeSize = Math.max(7, Math.min(w, h) * 0.2);
  if (machine.input_queue_len > 0) {
    ctx.fillStyle = "#f59e0b";
    ctx.font = `bold ${badgeSize}px monospace`;
    ctx.textAlign = "left"; ctx.textBaseline = "top";
    ctx.fillText(`${machine.input_queue_len}`, ix + 1, iy + 1);
  }
  if (machine.output_queue_len > 0) {
    ctx.fillStyle = "#16a34a";
    ctx.font = `bold ${badgeSize}px monospace`;
    ctx.textAlign = "right"; ctx.textBaseline = "top";
    ctx.fillText(`${machine.output_queue_len}`, ix + iw - 1, iy + 1);
  }
}

function drawMachineShape(
  ctx: CanvasRenderingContext2D,
  type: string, state: string,
  x: number, y: number, w: number, h: number,
  tick: number, color: string,
) {
  const cx = x + w / 2; const cy = y + h / 2;
  ctx.save();

  switch (type) {
    case "smelter": {
      const bw = w * 0.65; const bh = h * 0.55;
      const bx = cx - bw / 2; const by = cy - bh * 0.2;
      ctx.fillStyle = "#78350f";
      ctx.beginPath();
      ctx.moveTo(bx + bw * 0.1, by + bh);
      ctx.lineTo(bx + bw * 0.9, by + bh);
      ctx.lineTo(bx + bw * 0.75, by);
      ctx.lineTo(bx + bw * 0.25, by);
      ctx.closePath(); ctx.fill();
      ctx.fillStyle = "#000000aa";
      ctx.fillRect(cx - bw * 0.18, by + bh * 0.35, bw * 0.36, bh * 0.45);
      if (state === "processing" || state === "loading") {
        const flicker = Math.sin(tick * 0.6 + Math.PI * 0.3) * 0.15;
        ctx.fillStyle = `rgba(251,146,60,${0.9 + flicker})`;
        ctx.beginPath();
        ctx.ellipse(cx, by - h * 0.08, w * 0.12, h * 0.18 + h * 0.04 * flicker, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = `rgba(253,224,71,${0.8 + flicker})`;
        ctx.beginPath();
        ctx.ellipse(cx, by - h * 0.1, w * 0.07, h * 0.1, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = "#44403c";
      ctx.fillRect(cx + bw * 0.25, by - h * 0.22, w * 0.08, h * 0.22);
      break;
    }
    case "stamping_press": {
      const baseH = h * 0.18; const ramW = w * 0.45; const ramH = h * 0.25;
      ctx.fillStyle = "#475569";
      ctx.fillRect(cx - w * 0.32, y + h * 0.05, w * 0.07, h * 0.72);
      ctx.fillRect(cx + w * 0.25, y + h * 0.05, w * 0.07, h * 0.72);
      ctx.fillStyle = "#334155";
      ctx.fillRect(x + w * 0.08, y + h - baseH - h * 0.06, w * 0.84, baseH);
      ctx.fillStyle = "#fbbf24aa";
      ctx.fillRect(cx - ramW * 0.35, y + h - baseH - h * 0.14, ramW * 0.7, h * 0.08);
      const ramOffset = state === "processing" ? Math.abs(Math.sin(tick * 0.4)) * h * 0.22 : 0;
      ctx.fillStyle = "#64748b";
      ctx.fillRect(cx - ramW / 2, y + h * 0.05 + ramOffset, ramW, ramH);
      ctx.fillStyle = "#94a3b8";
      ctx.fillRect(cx - ramW / 2, y + h * 0.05 + ramOffset + ramH - h * 0.05, ramW, h * 0.05);
      break;
    }
    case "assembly_station": {
      const tableH = h * 0.14;
      const tableY = y + h * 0.72;
      ctx.fillStyle = "#92400e";
      ctx.fillRect(x + w * 0.08, tableY, w * 0.84, tableH);
      ctx.fillRect(x + w * 0.12, tableY + tableH, w * 0.08, h * 0.16);
      ctx.fillRect(x + w * 0.80, tableY + tableH, w * 0.08, h * 0.16);
      ctx.strokeStyle = "#64748b"; ctx.lineWidth = w * 0.06; ctx.lineCap = "round";
      const armAngle = state === "processing" ? Math.sin(tick * 0.35) * 0.4 : -0.2;
      ctx.beginPath();
      ctx.moveTo(cx, tableY);
      ctx.lineTo(cx + Math.cos(armAngle - Math.PI / 2) * h * 0.28, tableY - Math.sin(armAngle + Math.PI / 2) * h * 0.28);
      ctx.stroke();
      ctx.fillStyle = "#4338ca88";
      ctx.fillRect(cx - w * 0.28, tableY - h * 0.1, w * 0.18, h * 0.08);
      ctx.fillStyle = "#15803d88";
      ctx.fillRect(cx + w * 0.1, tableY - h * 0.1, w * 0.18, h * 0.08);
      break;
    }
    case "qc": {
      const lensR = Math.min(w, h) * 0.2;
      const lensX = cx - w * 0.1; const lensY = cy - h * 0.05;
      if (state === "processing" || state === "output_ready") {
        const alpha = state === "output_ready" ? 0.35 : (0.18 + Math.sin(tick * 0.3) * 0.08);
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = "#fef08a";
        ctx.beginPath();
        ctx.moveTo(lensX, lensY);
        ctx.lineTo(lensX - w * 0.25, cy + h * 0.35);
        ctx.lineTo(lensX + w * 0.25, cy + h * 0.35);
        ctx.closePath(); ctx.fill();
        ctx.restore();
      }
      ctx.strokeStyle = "#475569"; ctx.lineWidth = w * 0.07; ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(lensX + lensR * 0.7, lensY + lensR * 0.7);
      ctx.lineTo(cx + w * 0.3, cy + h * 0.3);
      ctx.stroke();
      ctx.strokeStyle = "#334155"; ctx.lineWidth = w * 0.06;
      ctx.beginPath(); ctx.arc(lensX, lensY, lensR, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = state === "output_ready" ? "#bbf7d088" : "#bfdbfe66";
      ctx.beginPath(); ctx.arc(lensX, lensY, lensR - w * 0.03, 0, Math.PI * 2); ctx.fill();
      if (state === "output_ready") {
        ctx.strokeStyle = "#16a34a"; ctx.lineWidth = w * 0.06;
        ctx.beginPath();
        ctx.moveTo(lensX - lensR * 0.45, lensY);
        ctx.lineTo(lensX - lensR * 0.1, lensY + lensR * 0.4);
        ctx.lineTo(lensX + lensR * 0.45, lensY - lensR * 0.35);
        ctx.stroke();
      }
      break;
    }
    case "packaging": {
      const bw = w * 0.62; const bh = h * 0.45;
      const bx = cx - bw / 2; const by = cy - bh * 0.1;
      ctx.strokeStyle = "#334155"; ctx.lineWidth = w * 0.05; ctx.fillStyle = "#f8fafc";
      ctx.beginPath();
      ctx.moveTo(bx, by + bh * 0.25);
      ctx.lineTo(bx, by + bh);
      ctx.lineTo(bx + bw, by + bh);
      ctx.lineTo(bx + bw, by + bh * 0.25);
      ctx.fill(); ctx.stroke();
      const lidAngle = state === "output_ready" ? -0.7
        : state === "processing" ? -0.35 - Math.sin(tick * 0.3) * 0.2 : -0.1;
      ctx.strokeStyle = "#334155"; ctx.lineWidth = w * 0.04;
      ctx.save();
      ctx.translate(bx, by + bh * 0.25);
      ctx.rotate(lidAngle);
      ctx.fillStyle = "#e2e8f0";
      ctx.fillRect(0, -bh * 0.3, bw * 0.48, bh * 0.3);
      ctx.strokeRect(0, -bh * 0.3, bw * 0.48, bh * 0.3);
      ctx.restore();
      ctx.save();
      ctx.translate(bx + bw, by + bh * 0.25);
      ctx.rotate(Math.PI - lidAngle);
      ctx.fillStyle = "#e2e8f0";
      ctx.fillRect(-bw * 0.48, -bh * 0.3, bw * 0.48, bh * 0.3);
      ctx.strokeRect(-bw * 0.48, -bh * 0.3, bw * 0.48, bh * 0.3);
      ctx.restore();
      ctx.strokeStyle = "#7c3aed88"; ctx.lineWidth = w * 0.04;
      ctx.beginPath(); ctx.moveTo(cx, by + bh * 0.25); ctx.lineTo(cx, by + bh); ctx.stroke();
      break;
    }
    case "circuit_fab": {
      const bw = w * 0.75; const bh = h * 0.62;
      const bx = cx - bw / 2; const by = cy - bh / 2;
      ctx.fillStyle = "#064e3b"; ctx.fillRect(bx, by, bw, bh);
      ctx.strokeStyle = "#065f46"; ctx.lineWidth = 0.5; ctx.strokeRect(bx, by, bw, bh);
      ctx.strokeStyle = "#fbbf2466"; ctx.lineWidth = w * 0.025;
      const traces = [[0.2, 0.2, 0.8, 0.2], [0.2, 0.5, 0.8, 0.5], [0.2, 0.8, 0.8, 0.8],
                      [0.2, 0.2, 0.2, 0.8], [0.5, 0.2, 0.5, 0.8], [0.8, 0.2, 0.8, 0.8]];
      for (const [x1, y1, x2, y2] of traces) {
        ctx.beginPath();
        ctx.moveTo(bx + bw * x1, by + bh * y1);
        ctx.lineTo(bx + bw * x2, by + bh * y2);
        ctx.stroke();
      }
      const pads = [[0.2,0.2],[0.5,0.2],[0.8,0.2],[0.2,0.5],[0.8,0.5],[0.2,0.8],[0.5,0.8],[0.8,0.8]];
      for (const [px, py] of pads) {
        const active = state === "processing" && Math.sin(tick * 0.3 + px * 5) > 0;
        ctx.fillStyle = active ? "#fbbf24" : "#92400e";
        ctx.beginPath();
        ctx.arc(bx + bw * px, by + bh * py, w * 0.04, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = "#1e293b"; ctx.fillRect(bx + bw * 0.35, by + bh * 0.3, bw * 0.3, bh * 0.4);
      ctx.strokeStyle = "#fbbf2444"; ctx.lineWidth = 0.5; ctx.strokeRect(bx + bw * 0.35, by + bh * 0.3, bw * 0.3, bh * 0.4);
      break;
    }
    default: {
      ctx.fillStyle = color + "33";
      ctx.fillRect(x + w * 0.15, y + h * 0.15, w * 0.7, h * 0.7);
      ctx.fillStyle = color;
      ctx.font = `bold ${Math.min(w, h) * 0.28}px monospace`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(type.slice(0, 3).toUpperCase(), cx, cy);
    }
  }
  ctx.restore();
}

// ── Agent rendering (pixel people) ───────────────────────────────────────────

function drawAgent(
  ctx: CanvasRenderingContext2D,
  agent: { role: string; row: number; col: number; state: string; inventory_count: number; path?: Array<[number, number]> },
  x: number, y: number, w: number, h: number, tick: number,
) {
  const color = AGENT_COLOR[agent.role] ?? "#0f172a";
  const cx = x + w / 2;

  const scale = Math.min(w, h) * 0.038;
  const headR = scale * 2.2;
  const bodyH = scale * 3.5;
  const bodyW = scale * 2.4;
  const legH  = scale * 3.0;
  const armH  = scale * 2.2;

  const topY = y + h * 0.12;
  const headCY = topY + headR;
  const shoulderY = headCY + headR + scale * 0.4;
  const hipY = shoulderY + bodyH;
  const footY = hipY + legH;

  const isWorking = agent.state === "working";
  const isMoving  = agent.state === "moving";

  // Ground shadow when working
  if (isWorking) {
    ctx.save();
    ctx.shadowColor = color; ctx.shadowBlur = 8 + Math.sin(tick * 0.4) * 4;
    ctx.fillStyle = color + "22";
    ctx.beginPath();
    ctx.ellipse(cx, footY + scale, scale * 4, scale * 1.2, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  // Legs (animate when moving)
  const legSwing = isMoving ? Math.sin(tick * 0.5) * scale * 1.2 : 0;
  ctx.strokeStyle = color; ctx.lineWidth = scale * 1.1; ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(cx - bodyW * 0.25, hipY);
  ctx.lineTo(cx - bodyW * 0.25 - legSwing, footY);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(cx + bodyW * 0.25, hipY);
  ctx.lineTo(cx + bodyW * 0.25 + legSwing, footY);
  ctx.stroke();

  // Body
  ctx.fillStyle = color + "cc";
  ctx.beginPath();
  ctx.roundRect(cx - bodyW / 2, shoulderY, bodyW, bodyH, scale * 0.6);
  ctx.fill();

  // Arms
  ctx.strokeStyle = color; ctx.lineWidth = scale * 0.9;
  const armSwing = isMoving ? -legSwing * 0.7 : 0;
  ctx.beginPath();
  ctx.moveTo(cx - bodyW / 2, shoulderY + bodyH * 0.2);
  ctx.lineTo(cx - bodyW / 2 - scale * 1.0 + armSwing, shoulderY + bodyH * 0.2 + armH);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(cx + bodyW / 2, shoulderY + bodyH * 0.2);
  ctx.lineTo(cx + bodyW / 2 + scale * 1.0 - armSwing, shoulderY + bodyH * 0.2 + armH);
  ctx.stroke();

  // Head
  ctx.fillStyle = "#fde68a";
  ctx.beginPath(); ctx.arc(cx, headCY, headR, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = color; ctx.lineWidth = scale * 0.5;
  ctx.beginPath(); ctx.arc(cx, headCY, headR, 0, Math.PI * 2); ctx.stroke();

  // Eyes
  ctx.fillStyle = "#0f172a";
  ctx.beginPath(); ctx.arc(cx - headR * 0.32, headCY - headR * 0.1, scale * 0.35, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(cx + headR * 0.32, headCY - headR * 0.1, scale * 0.35, 0, Math.PI * 2); ctx.fill();

  // Role hat
  drawRoleHat(ctx, agent.role, cx, headCY, headR, color, scale);

  // Inventory badge
  if (agent.inventory_count > 0) {
    const badgeR = scale * 1.5;
    const badgeX = cx + headR + scale * 0.2;
    const badgeY = headCY - headR;
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(badgeX, badgeY, badgeR, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.font = `bold ${scale * 1.4}px monospace`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(`${agent.inventory_count}`, badgeX, badgeY);
  }

  // Direction nub when has a path
  if (agent.path && agent.path.length > 0) {
    const [nextR, nextC] = agent.path[0];
    const dr = nextR - agent.row; const dc = nextC - agent.col;
    if (dr !== 0 || dc !== 0) {
      const angle = Math.atan2(dr, dc);
      ctx.save();
      ctx.globalAlpha = 0.6;
      ctx.strokeStyle = color; ctx.lineWidth = scale * 0.7; ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(cx, footY + scale * 1.4);
      ctx.lineTo(cx + Math.cos(angle) * scale * 2.2, footY + scale * 1.4 + Math.sin(angle) * scale * 2.2);
      ctx.stroke();
      ctx.restore();
    }
  }
}

function drawRoleHat(
  ctx: CanvasRenderingContext2D,
  role: string, cx: number, headCY: number, headR: number, color: string, scale: number,
) {
  const hatY = headCY - headR;
  ctx.save();
  ctx.fillStyle = color;
  switch (role) {
    case "management": {
      ctx.fillRect(cx - headR * 0.9, hatY - scale * 2.2, headR * 1.8, scale * 2.2);
      ctx.fillRect(cx - headR * 1.2, hatY - scale * 0.4, headR * 2.4, scale * 0.4);
      break;
    }
    case "engineering": {
      ctx.beginPath();
      ctx.ellipse(cx, hatY, headR * 1.25, scale * 1.4, 0, Math.PI, 0);
      ctx.fill();
      ctx.fillStyle = "#fef9c3";
      ctx.fillRect(cx - headR * 1.25, hatY - scale * 0.1, headR * 2.5, scale * 0.35);
      break;
    }
    case "sales": {
      ctx.beginPath();
      ctx.ellipse(cx, hatY, headR * 1.5, scale * 0.5, 0, Math.PI, 0);
      ctx.fill();
      ctx.fillStyle = color + "dd";
      ctx.beginPath();
      ctx.ellipse(cx, hatY - scale * 0.3, headR * 0.85, scale * 1.1, 0, Math.PI, 0);
      ctx.fill();
      break;
    }
    case "procurement": {
      ctx.fillRect(cx - headR * 0.9, hatY - scale * 0.8, headR * 1.8, scale * 0.8);
      ctx.fillRect(cx - headR * 1.2, hatY, headR * 2.2, scale * 0.3);
      break;
    }
    case "operations": {
      ctx.fillStyle = "#fbbf24";
      ctx.beginPath();
      ctx.ellipse(cx, hatY, headR * 1.2, scale * 1.3, 0, Math.PI, 0);
      ctx.fill();
      ctx.fillStyle = "#f59e0b";
      ctx.fillRect(cx - headR * 1.2, hatY - scale * 0.1, headR * 2.4, scale * 0.3);
      break;
    }
    default: break;
  }
  ctx.restore();
}

// ── Item rendering ────────────────────────────────────────────────────────────

function drawItem(ctx: CanvasRenderingContext2D, item: { type: string }, cx: number, cy: number, r: number) {
  ctx.save();
  switch (item.type) {
    case "raw_ore": {
      ctx.fillStyle = "#b91c1c";
      ctx.beginPath();
      const pts = 7; const jitter = r * 0.4;
      for (let i = 0; i < pts; i++) {
        const a = (i / pts) * Math.PI * 2;
        const rr = r + (i % 2 === 0 ? jitter : -jitter * 0.5);
        i === 0 ? ctx.moveTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr)
                : ctx.lineTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr);
      }
      ctx.closePath(); ctx.fill();
      break;
    }
    case "raw_silicon": {
      ctx.fillStyle = "#7c3aed";
      ctx.beginPath();
      ctx.moveTo(cx, cy - r * 1.2); ctx.lineTo(cx + r * 0.85, cy);
      ctx.lineTo(cx, cy + r * 0.8); ctx.lineTo(cx - r * 0.85, cy);
      ctx.closePath(); ctx.fill();
      ctx.fillStyle = "#a78bfa66";
      ctx.beginPath();
      ctx.moveTo(cx, cy - r * 1.2); ctx.lineTo(cx + r * 0.85, cy); ctx.lineTo(cx, cy - r * 0.1);
      ctx.closePath(); ctx.fill();
      break;
    }
    case "metal_ingot": {
      ctx.fillStyle = "#d97706";
      ctx.beginPath();
      ctx.roundRect(cx - r * 1.4, cy - r * 0.55, r * 2.8, r * 1.1, r * 0.2);
      ctx.fill();
      ctx.fillStyle = "#fbbf2466";
      ctx.fillRect(cx - r * 1.1, cy - r * 0.35, r * 1.8, r * 0.3);
      break;
    }
    case "stamped_part": {
      ctx.fillStyle = "#b45309";
      ctx.beginPath();
      for (let i = 0; i < 8; i++) {
        const a = (i / 8) * Math.PI * 2 - Math.PI / 8;
        const rr = i % 2 === 0 ? r : r * 0.7;
        i === 0 ? ctx.moveTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr)
                : ctx.lineTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr);
      }
      ctx.closePath(); ctx.fill();
      ctx.fillStyle = "#78350f";
      ctx.beginPath(); ctx.arc(cx, cy, r * 0.35, 0, Math.PI * 2); ctx.fill();
      break;
    }
    case "circuit": {
      ctx.fillStyle = "#1e3a5f"; ctx.fillRect(cx - r * 0.85, cy - r * 0.85, r * 1.7, r * 1.7);
      ctx.fillStyle = "#4338ca"; ctx.fillRect(cx - r * 0.6, cy - r * 0.6, r * 1.2, r * 1.2);
      ctx.fillStyle = "#fbbf24";
      for (let i = -1; i <= 1; i++) {
        ctx.fillRect(cx + i * r * 0.45 - r * 0.07, cy - r * 1.05, r * 0.14, r * 0.25);
        ctx.fillRect(cx + i * r * 0.45 - r * 0.07, cy + r * 0.8,  r * 0.14, r * 0.25);
      }
      break;
    }
    case "subassembly": {
      ctx.strokeStyle = "#15803d"; ctx.lineWidth = r * 0.22; ctx.fillStyle = "#dcfce7";
      ctx.fillRect(cx - r * 0.9, cy - r * 0.6, r * 1.8, r * 1.3);
      ctx.strokeRect(cx - r * 0.9, cy - r * 0.6, r * 1.8, r * 1.3);
      ctx.beginPath();
      ctx.moveTo(cx - r * 0.9, cy - r * 0.6);
      ctx.lineTo(cx, cy - r * 1.0);
      ctx.lineTo(cx + r * 0.9, cy - r * 0.6);
      ctx.stroke();
      break;
    }
    case "inspected_unit": {
      ctx.fillStyle = "#16a34a"; ctx.strokeStyle = "#166534"; ctx.lineWidth = r * 0.18;
      ctx.fillRect(cx - r * 0.9, cy - r * 0.7, r * 1.8, r * 1.4);
      ctx.strokeRect(cx - r * 0.9, cy - r * 0.7, r * 1.8, r * 1.4);
      ctx.strokeStyle = "#ffffff"; ctx.lineWidth = r * 0.28; ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(cx - r * 0.4, cy + r * 0.05);
      ctx.lineTo(cx - r * 0.05, cy + r * 0.45);
      ctx.lineTo(cx + r * 0.5, cy - r * 0.3);
      ctx.stroke();
      break;
    }
    case "finished_product": {
      ctx.fillStyle = "#4f46e5"; ctx.strokeStyle = "#3730a3"; ctx.lineWidth = r * 0.15;
      ctx.beginPath(); ctx.roundRect(cx - r, cy - r * 0.8, r * 2, r * 1.6, r * 0.2); ctx.fill(); ctx.stroke();
      ctx.strokeStyle = "#fbbf24"; ctx.lineWidth = r * 0.22;
      ctx.beginPath(); ctx.moveTo(cx, cy - r * 0.8); ctx.lineTo(cx, cy + r * 0.8); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx - r, cy); ctx.lineTo(cx + r, cy); ctx.stroke();
      ctx.fillStyle = "#fef08a";
      ctx.beginPath(); ctx.ellipse(cx - r * 0.3, cy - r * 0.8, r * 0.3, r * 0.18, -0.4, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.ellipse(cx + r * 0.3, cy - r * 0.8, r * 0.3, r * 0.18,  0.4, 0, Math.PI * 2); ctx.fill();
      break;
    }
    case "reject": {
      ctx.fillStyle = "#64748b";
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "#dc2626"; ctx.lineWidth = r * 0.4; ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(cx - r * 0.5, cy - r * 0.5); ctx.lineTo(cx + r * 0.5, cy + r * 0.5); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx + r * 0.5, cy - r * 0.5); ctx.lineTo(cx - r * 0.5, cy + r * 0.5); ctx.stroke();
      break;
    }
    default: {
      ctx.fillStyle = "#94a3b8";
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
    }
  }
  ctx.restore();
}

// ── Agent path trail ──────────────────────────────────────────────────────────

function drawAgentPath(
  ctx: CanvasRenderingContext2D,
  path: Array<[number, number]>,
  agentRow: number, agentCol: number,
  cellW: number, cellH: number, color: string,
) {
  if (!path || path.length === 0) return;
  ctx.save();
  ctx.globalAlpha = 0.28;
  ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.setLineDash([3, 4]);
  ctx.beginPath();
  ctx.moveTo(agentCol * cellW + cellW / 2, agentRow * cellH + cellH / 2);
  for (const [pr, pc] of path.slice(0, 6)) {
    ctx.lineTo(pc * cellW + cellW / 2, pr * cellH + cellH / 2);
  }
  ctx.stroke();
  const [destR, destC] = path[Math.min(5, path.length - 1)];
  ctx.globalAlpha = 0.45; ctx.setLineDash([]);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(destC * cellW + cellW / 2, destR * cellH + cellH / 2, 2.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

// ── Zone label strip ──────────────────────────────────────────────────────────

function drawColumnLabels(
  ctx: CanvasRenderingContext2D,
  cols: number, rows: number, cellW: number, cellH: number,
) {
  const stripH = cellH * 0.5;
  const stripY = rows * cellH - stripH;

  const zones = [
    { label: "INPUT",          fromCol: 0,       toCol: 1,         color: "#047857" },
    { label: "RAW PROCESSING", fromCol: 2,       toCol: 4,         color: "#b91c1c" },
    { label: "MID PROCESSING", fromCol: 5,       toCol: 9,         color: "#4338ca" },
    { label: "FINISHING",      fromCol: 10,      toCol: cols - 2,  color: "#7c3aed" },
    { label: "OUTPUT",         fromCol: cols - 1, toCol: cols - 1, color: "#1d4ed8" },
  ];

  ctx.save();
  ctx.font = `bold ${Math.max(7, cellH * 0.22)}px monospace`;
  ctx.textBaseline = "middle";

  for (const z of zones) {
    if (z.fromCol >= cols || z.toCol >= cols) continue;
    const lx = z.fromCol * cellW + 2;
    const rx = (z.toCol + 1) * cellW - 2;
    ctx.fillStyle = z.color + "1a";
    ctx.fillRect(lx, stripY, rx - lx, stripH);
    ctx.fillStyle = z.color;
    ctx.textAlign = "center";
    ctx.fillText(z.label, lx + (rx - lx) / 2, stripY + stripH / 2);
  }
  ctx.restore();
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function GridCanvas({ state }: { state: MfgGameState }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef   = useRef<number>(0);
  const tickRef   = useRef(0);
  const { evolutionData } = useSocket();

  const particlesRef  = useRef<Particle[]>([]);
  const prevOutputRef = useRef<Record<string, number>>({});

  const [genFlash, setGenFlash] = useState<{ gen: number; label: string; improved: boolean } | null>(null);
  const lastGenRef = useRef(0);

  useEffect(() => {
    if (evolutionData.length === 0) return;
    const latest = evolutionData[evolutionData.length - 1];
    if (latest.generation > lastGenRef.current) {
      lastGenRef.current = latest.generation;
      setGenFlash({ gen: latest.generation, label: latest.mutation_type ?? "genome", improved: latest.improved ?? true });
      const t = setTimeout(() => setGenFlash(null), 1800);
      return () => clearTimeout(t);
    }
  }, [evolutionData]);

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
      if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }

      const rows = state.grid_rows ?? state.grid?.length ?? 10;
      const cols = state.grid_cols ?? (state.grid?.[0]?.length ?? 10);

      // Reserve bottom strip for zone labels
      const labelH = Math.max(14, H * 0.042);
      const gridH  = H - labelH;
      const cellW  = W / cols;
      const cellH  = gridH / rows;

      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = "#f8fafc";
      ctx.fillRect(0, 0, W, H);

      // Grid cells
      if (state.grid) {
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            drawCell(ctx, state.grid[r]?.[c] ?? "floor", c * cellW, r * cellH, cellW, cellH);
          }
        }
      }

      // Machines + particles
      if (state.machines) {
        for (const machine of Object.values(state.machines)) {
          const mx = machine.col * cellW; const my = machine.row * cellH;
          drawMachine(ctx, machine, mx, my, cellW, cellH, t);
          const prevOut = prevOutputRef.current[machine.id] ?? 0;
          const curOut  = machine.output_queue_len ?? 0;
          if (curOut > prevOut) {
            const outItem = machine.output_queue?.[0];
            const pColor  = (outItem ? ITEM_PARTICLE_COLOR[outItem.type] : null)
              ?? MACHINE_STATE_COLOR[machine.state] ?? "#4338ca";
            spawnParticles(mx + cellW / 2, my + cellH / 2, pColor, 4, particlesRef.current);
          }
          prevOutputRef.current[machine.id] = curOut;
        }
      }

      // Particle step
      const alive: Particle[] = [];
      for (const p of particlesRef.current) {
        p.x += p.vx; p.y += p.vy; p.vy += 0.035; p.life -= 1;
        if (p.life > 0) { drawParticle(ctx, p); alive.push(p); }
      }
      particlesRef.current = alive;

      // Floor items (not carried)
      if (state.items) {
        const byCell: Record<string, typeof state.items> = {};
        for (const item of state.items) {
          if (item.row == null || item.col == null || item.carrier_id != null) continue;
          const key = `${item.row},${item.col}`;
          if (!byCell[key]) byCell[key] = [];
          byCell[key].push(item);
        }
        const offsets = [[-1,-1],[1,-1],[-1,1],[1,1],[0,0]];
        for (const [key, cellItems] of Object.entries(byCell)) {
          const [r, c] = key.split(",").map(Number);
          const baseX = c * cellW + cellW / 2;
          const baseY = r * cellH + cellH / 2;
          const itemR = Math.min(cellW, cellH) * 0.13;
          cellItems.slice(0, 4).forEach((item, i) => {
            const [ox, oy] = offsets[i] ?? [0, 0];
            drawItem(ctx, item as { type: string }, baseX + ox * itemR * 2.2, baseY + oy * itemR * 2.2, itemR);
          });
        }
      }

      // Agent paths then agents
      if (state.agents) {
        for (const agent of Object.values(state.agents)) {
          if (agent.path && agent.path.length > 0) {
            drawAgentPath(ctx, agent.path, agent.row, agent.col, cellW, cellH, AGENT_COLOR[agent.role] ?? "#0f172a");
          }
        }
        for (const agent of Object.values(state.agents)) {
          drawAgent(ctx, agent, agent.col * cellW, agent.row * cellH, cellW, cellH, t);
        }
      }

      // Zone label strip
      drawColumnLabels(ctx, cols, rows, cellW, cellH);

      // Minimal HUD overlay (tick + fitness only — rest is in the sidebar)
      ctx.fillStyle = "rgba(15,23,42,0.70)";
      ctx.beginPath(); ctx.roundRect(8, 8, 172, 38, 6); ctx.fill();
      ctx.fillStyle = "#94a3b8";
      ctx.font = "9px monospace"; ctx.textAlign = "left"; ctx.textBaseline = "top";
      ctx.fillText("MANUFACTURING", 16, 14);
      ctx.fillStyle = "#818cf8";
      ctx.font = "bold 11px monospace";
      ctx.fillText(`Tick ${state.tick ?? 0}  ·  Fitness ${(state.fitness ?? 0).toFixed(2)}`, 16, 26);

      animRef.current = requestAnimationFrame(render);
    };

    animRef.current = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animRef.current);
  }, [state]);

  return (
    <div className="w-full h-full relative">
      <canvas ref={canvasRef} className="w-full h-full block" data-testid="mfg-grid-canvas" />
      {genFlash && (
        <div
          className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none"
          style={{ animation: "fadeOut 1.8s ease-out forwards" }}
        >
          <div
            className="px-8 py-4 rounded-xl border text-center"
            style={{
              backgroundColor: "rgba(10,14,21,0.90)",
              borderColor: genFlash.improved ? "#4338ca" : "#b45309",
              boxShadow: `0 0 40px ${genFlash.improved ? "#4338ca44" : "#b4530944"}`,
            }}
          >
            <div className="text-3xl font-mono font-bold tracking-widest"
              style={{ color: genFlash.improved ? "#818cf8" : "#fbbf24" }}>
              GEN {String(genFlash.gen).padStart(4, "0")}
            </div>
            <div className="text-xs font-mono mt-1"
              style={{ color: genFlash.improved ? "#4ade80" : "#f87171" }}>
              {genFlash.improved ? "▲ FITNESS IMPROVED" : "▼ PARENT RETAINED"} · {genFlash.label}
            </div>
          </div>
        </div>
      )}
      <style>{`@keyframes fadeOut{0%,60%{opacity:1}100%{opacity:0}}`}</style>
    </div>
  );
}
