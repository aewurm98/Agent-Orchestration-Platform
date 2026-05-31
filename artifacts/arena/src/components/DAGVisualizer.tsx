import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  Node,
  Edge,
  NodeProps,
  Position,
  MarkerType,
  Handle,
} from "reactflow";
import "reactflow/dist/style.css";
import { useSocket } from "@/hooks/useSocket";
import { DagNode } from "@/context/SocketContext";

type NodeStatus = DagNode["status"];

// Design plan §10.4 — node state color system
const NODE_STATUS_COLORS: Record<NodeStatus, { border: string; bg: string; text: string; shadow: string }> = {
  active:  { border: "#4F7CFF", bg: "#EEF3FF", text: "#1D3FA8", shadow: "rgba(79,124,255,0.30)" },
  evolved: { border: "#10B981", bg: "#ECFDF5", text: "#065F46", shadow: "rgba(16,185,129,0.25)" },
  failed:  { border: "#F43F5E", bg: "#FFF1F3", text: "#9F1239", shadow: "rgba(244,63,94,0.25)" },
  idle:    { border: "#D8DFEA", bg: "#FFFFFF", text: "#5E667A", shadow: "none" },
};

function CustomNode({ data }: NodeProps<DagNode>) {
  const status = data?.status ?? "idle";
  const isActive = status === "active";
  const colors = NODE_STATUS_COLORS[status] ?? NODE_STATUS_COLORS.idle;
  const size = 60;

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className={`relative rounded-full border-[2.5px] transition-all duration-300 ${isActive ? "node-active-pulse" : ""}`}
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderColor: colors.border,
          backgroundColor: colors.bg,
          boxShadow: isActive ? `0 0 14px 4px ${colors.shadow}` : "none",
        }}
      >
        <Handle type="target" position={Position.Top} className="opacity-0" />
        <Handle type="source" position={Position.Bottom} className="opacity-0" />
      </div>
      <div
        className="text-[10px] font-medium text-center leading-tight px-2 py-0.5 rounded-md bg-white/95 border border-[#ebe5d6] max-w-[130px] break-words shadow-sm"
        style={{ color: colors.text }}
      >
        {data?.label ?? "—"}
      </div>
    </div>
  );
}

const nodeTypes = { custom: CustomNode };

export default function DAGVisualizer() {
  const { dagData } = useSocket();

  const { nodes, edges } = useMemo(() => {
    if (!dagData) return { nodes: [] as Node[], edges: [] as Edge[] };

    const totalNodes = dagData.nodes.length;
    const radius = 150;
    const center = { x: 250, y: 250 };

    const flowNodes: Node<DagNode>[] = dagData.nodes.map((n, i) => {
      const angle = (i / totalNodes) * 2 * Math.PI - Math.PI / 2;
      return {
        id: n.id,
        type: "custom",
        position: {
          x: center.x + radius * Math.cos(angle) - 30,
          y: center.y + radius * Math.sin(angle) - 30,
        },
        data: n,
      };
    });

    const flowEdges: Edge[] = dagData.edges.map((e, i) => ({
      id: `e-${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
      animated: true,
      style: {
        strokeWidth: Math.max(1, (e.payload_size || 100) / 100),
        stroke: e.grpo_score < 0 ? "#b91c1c" : "#14120e",
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: e.grpo_score < 0 ? "#b91c1c" : "#14120e",
      },
    }));

    return { nodes: flowNodes, edges: flowEdges };
  }, [dagData]);

  const isEmpty = nodes.length === 0;

  return (
    <div className="w-full h-full relative bg-transparent" data-testid="dag-visualizer">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
      >
        <Background color="rgba(20, 18, 14, 0.10)" gap={20} />
        <Controls className="fill-[#14120e] bg-[#ffffff] border-[#ebe5d6]" />
      </ReactFlow>

      {/* Empty state — shown before first run */}
      {isEmpty && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 pointer-events-none">
          <div className="w-12 h-12 pixel-gradient blob opacity-60" />
          <p className="text-[12px] text-[#6b6359] font-mono">Start a run to see the agent graph</p>
        </div>
      )}
    </div>
  );
}
