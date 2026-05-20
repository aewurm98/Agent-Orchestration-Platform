import type { ReactElement } from "react";

/**
 * Pastel pixel-block gradient decoration — inspired by the MindFlow hero.
 * Renders a 16x6 grid of squares with random-but-stable per-cell opacity,
 * coloured by a pink → lavender horizontal gradient.
 */

type Props = {
  className?: string;
  cols?: number;
  rows?: number;
  cell?: number;
  gap?: number;
};

const PALETTE = [
  "#f7a8b8", // pink
  "#f6b8c5",
  "#e9b3d4",
  "#d9b3e3",
  "#c7b5ea",
  "#b8b8eb",
  "#adb6e8", // lavender
];

// Deterministic pseudo-random (so render is stable across reloads).
function rand(seed: number): number {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

export default function PixelGradient({
  className = "",
  cols = 22,
  rows = 6,
  cell = 14,
  gap = 2,
}: Props) {
  const width = cols * cell + (cols - 1) * gap;
  const height = rows * cell + (rows - 1) * gap;
  const blocks: ReactElement[] = [];

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const seed = r * cols + c + 1;
      const noise = rand(seed);
      // Soft falloff at edges so the shape feels organic
      const colT = c / (cols - 1);
      const rowT = Math.abs(r - (rows - 1) / 2) / ((rows - 1) / 2);
      const edgeFade = 1 - rowT * 0.85;
      const visible = noise > 0.18 && noise * edgeFade > 0.22;
      if (!visible) continue;

      const paletteIdx = Math.min(
        PALETTE.length - 1,
        Math.floor(colT * PALETTE.length + noise * 0.6),
      );
      blocks.push(
        <rect
          key={`${r}-${c}`}
          x={c * (cell + gap)}
          y={r * (cell + gap)}
          width={cell}
          height={cell}
          rx={2}
          fill={PALETTE[paletteIdx]}
          opacity={0.65 + edgeFade * 0.35}
        />,
      );
    }
  }

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height="100%"
      preserveAspectRatio="xMidYMid meet"
      className={className}
      aria-hidden="true"
    >
      {blocks}
    </svg>
  );
}
