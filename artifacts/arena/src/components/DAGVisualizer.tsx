import { useMemo, useState } from "react";
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
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type NodeStatus = DagNode["status"];

// Design plan §10.4 — node state color system
const NODE_STATUS_COLORS: Record<NodeStatus, { border: string; bg: string; text: string; shadow: string }> = {
  active:  { border: "#4F7CFF", bg: "#EEF3FF", text: "#1D3FA8", shadow: "rgba(79,124,255,0.30)" },
  evolved: { border: "#10B981", bg: "#ECFDF5", text: "#065F46", shadow: "rgba(16,185,129,0.25)" },
  failed:  { border: "#F43F5E", bg: "#FFF1F3", text: "#9F1239", shadow: "rgba(244,63,94,0.25)" },
  idle:    { border: "#D8DFEA", bg: "#FFFFFF", text: "#5E667A", shadow: "none" },
};

function getBorderColor(status: NodeStatus): string {
  return NODE_STATUS_COLORS[status]?.border ?? "#D8DFEA";
}

function CustomNode({ data }: NodeProps<DagNode>) {
  const size = 60 + (data.ctx_util || 0) * 30;
  const isActive = data.status === "active";
  const colors = NODE_STATUS_COLORS[data.status] ?? NODE_STATUS_COLORS.idle;

  return (
    <div
      className={`rounded-full flex items-center justify-center border-[2.5px] text-xs font-mono text-center overflow-hidden transition-all duration-300 ${isActive ? "node-active-pulse" : ""}`}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        borderColor: colors.border,
        backgroundColor: colors.bg,
        color: colors.text,
        boxShadow: isActive ? `0 0 14px 4px ${colors.shadow}` : "none",
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <span className="max-w-full truncate px-2">{data.label}</span>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}

const nodeTypes = { custom: CustomNode };

export default function DAGVisualizer() {
  const { dagData } = useSocket();
  const [selectedNode, setSelectedNode] = useState<DagNode | null>(null);

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
        fitView
        onNodeClick={(_, node) => setSelectedNode(node.data as DagNode)}
      >
        <Background color="rgba(20, 18, 14, 0.10)" gap={20} />
        <Controls className="fill-[#14120e] bg-[#ffffff] border-[#ebe5d6]" />
      </ReactFlow>

      {/* Empty state — shown before first run */}
      {isEmpty && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 pointer-events-none">
          <div className="w-12 h-12 rounded-2xl pixel-gradient opacity-60" />
          <p className="text-[12px] text-[#6b6359] font-mono">Start a run to see the agent graph</p>
        </div>
      )}

      {/* Node inspector panel */}
      {selectedNode && (
        <Card className="absolute top-4 right-4 w-72 bg-[#ffffff]/96 backdrop-blur border-[#ebe5d6] p-4 flex flex-col gap-3 shadow-xl overflow-y-auto max-h-[calc(100%-2rem)] animate-in slide-in-from-right-2 duration-200">
          <div className="flex justify-between items-center border-b border-[#ebe5d6] pb-2">
            <div className="flex items-center gap-2">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: NODE_STATUS_COLORS[selectedNode.status]?.border ?? "#D8DFEA" }}
              />
              <h3 className="font-mono text-sm text-[#14120e]">{selectedNode.label}</h3>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-muted-foreground hover:text-foreground text-xs w-5 h-5 flex items-center justify-center rounded hover:bg-[#efe9d9] transition-colors"
              data-testid="btn-close-node-details"
            >
              ✕
            </button>
          </div>

          {/* Status + Context Utility */}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Status</span>
              <Badge
                variant="outline"
                className="w-fit text-xs"
                style={{
                  borderColor: NODE_STATUS_COLORS[selectedNode.status]?.border,
                  color: NODE_STATUS_COLORS[selectedNode.status]?.text,
                  backgroundColor: NODE_STATUS_COLORS[selectedNode.status]?.bg,
                }}
              >
                {selectedNode.status}
              </Badge>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Ctx Util</span>
              <span className="text-xs font-mono text-[#14120e]">
                {(selectedNode.ctx_util * 100).toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Tools */}
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Tools</span>
            <div className="flex flex-wrap gap-1">
              {selectedNode.tools.length > 0 ? (
                selectedNode.tools.map((tool) => (
                  <Badge
                    key={tool}
                    variant="outline"
                    className="text-[9px] font-mono border-[#ebe5d6] text-[#6b6359] px-1.5 py-0.5"
                  >
                    {tool}
                  </Badge>
                ))
              ) : (
                <span className="text-[10px] text-muted-foreground italic">none assigned</span>
              )}
            </div>
          </div>

          {/* Last 3 Actions */}
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Recent Actions</span>
            <div className="flex flex-col gap-1">
              {selectedNode.last_actions.length > 0 ? (
                selectedNode.last_actions.map((action, idx) => (
                  <div
                    key={idx}
                    className="text-[10px] font-mono bg-[#f4f0e7] px-2 py-1 rounded border border-[#ebe5d6] text-[#6b6359] truncate"
                    title={action}
                  >
                    {action}
                  </div>
                ))
              ) : (
                <span className="text-[10px] text-muted-foreground italic">No actions yet</span>
              )}
            </div>
          </div>

          {/* System Prompt */}
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">System Prompt</span>
            <div className="text-[10px] font-mono bg-[#f4f0e7] p-2 rounded border border-[#ebe5d6] text-[#6b6359] leading-relaxed max-h-24 overflow-y-auto">
              {selectedNode.system_prompt || "—"}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
