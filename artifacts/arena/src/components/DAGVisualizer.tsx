import { useMemo, useState } from "react";
import ReactFlow, { Background, Controls, Node, Edge, Position, MarkerType, Handle } from "reactflow";
import "reactflow/dist/style.css";
import { useSocket } from "@/hooks/useSocket";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const CustomNode = ({ data }: any) => {
  const getBorderColor = (status: string) => {
    switch (status) {
      case "active": return "#00d9ff";
      case "failed": return "#f87171";
      case "evolved": return "#f59e0b";
      default: return "#30363d";
    }
  };

  const size = 60 + (data.ctx_util || 0) * 30;

  return (
    <div 
      className={`rounded-full flex items-center justify-center bg-[#161b22] border-[3px] text-xs font-mono text-center overflow-hidden transition-all duration-300 ${data.status === 'active' ? 'node-active-pulse' : ''}`}
      style={{ 
        width: `${size}px`, 
        height: `${size}px`, 
        borderColor: getBorderColor(data.status),
        boxShadow: data.status === 'active' ? '0 0 12px 4px rgba(0, 217, 255, 0.2)' : 'none'
      }}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <span className="max-w-full truncate px-2 text-[#e6edf3]">{data.label}</span>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
};

const nodeTypes = {
  custom: CustomNode,
};

export default function DAGVisualizer() {
  const { dagData } = useSocket();
  const [selectedNode, setSelectedNode] = useState<any>(null);

  const { nodes, edges } = useMemo(() => {
    if (!dagData) return { nodes: [], edges: [] };

    const totalNodes = dagData.nodes.length;
    const radius = 150;
    const center = { x: 250, y: 250 };

    const flowNodes: Node[] = dagData.nodes.map((n, i) => {
      const angle = (i / totalNodes) * 2 * Math.PI - Math.PI / 2;
      return {
        id: n.id,
        type: "custom",
        position: {
          x: center.x + radius * Math.cos(angle) - 30,
          y: center.y + radius * Math.sin(angle) - 30,
        },
        data: { ...n },
      };
    });

    const flowEdges: Edge[] = dagData.edges.map((e, i) => ({
      id: `e-${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
      animated: true,
      style: {
        strokeWidth: Math.max(1, (e.payload_size || 100) / 100),
        stroke: e.grpo_score < 0 ? "#f87171" : "#00d9ff",
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: e.grpo_score < 0 ? "#f87171" : "#00d9ff",
      }
    }));

    return { nodes: flowNodes, edges: flowEdges };
  }, [dagData]);

  return (
    <div className="w-full h-full relative bg-[#0d1117]" data-testid="dag-visualizer">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        onNodeClick={(_, node) => setSelectedNode(node.data)}
      >
        <Background color="#30363d" gap={16} />
        <Controls className="fill-[#e6edf3] bg-[#161b22] border-[#30363d]" />
      </ReactFlow>

      {selectedNode && (
        <Card className="absolute top-4 right-4 w-64 bg-[#161b22]/95 backdrop-blur border-[#30363d] p-4 flex flex-col gap-3 shadow-xl">
          <div className="flex justify-between items-center border-b border-[#30363d] pb-2">
            <h3 className="font-mono text-sm text-[#00d9ff]">{selectedNode.label}</h3>
            <button onClick={() => setSelectedNode(null)} className="text-muted-foreground hover:text-foreground text-xs" data-testid="btn-close-node-details">✕</button>
          </div>
          
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-muted-foreground uppercase">Status</span>
            <Badge variant="outline" className={`w-fit text-xs ${selectedNode.status === 'active' ? 'border-[#00d9ff] text-[#00d9ff]' : 'border-[#30363d]'}`}>
              {selectedNode.status}
            </Badge>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-muted-foreground uppercase">Context Utility</span>
            <div className="text-xs font-mono">{(selectedNode.ctx_util * 100).toFixed(1)}%</div>
          </div>
          
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-muted-foreground uppercase">System Prompt snippet</span>
            <div className="text-[10px] font-mono bg-[#0d1117] p-2 rounded border border-[#30363d] text-[#8b949e] h-20 overflow-hidden text-ellipsis">
              You are an autonomous {selectedNode.label} agent operating in a highly volatile environment. Optimize for efficiency and minimal latency while strictly adhering to network constraints.
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
