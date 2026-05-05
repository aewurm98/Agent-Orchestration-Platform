import { useState, useRef, useEffect } from "react";
import { useSocket } from "@/hooks/useSocket";
import { Button } from "@/components/ui/button";

const ROLE_COLORS: Record<string, string> = {
  orchestrator: "#00d9ff", // cyan
  evaluator: "#f59e0b",    // amber
  supply_agent: "#7ee787", // green
  demand_agent: "#a371f7", // purple
  system: "#8b949e",       // gray
};

export default function TracePanel() {
  const { traces } = useSocket();
  const [filter, setFilter] = useState("All");
  const scrollRef = useRef<HTMLDivElement>(null);

  const filteredTraces = traces.filter(t => filter === "All" || t.role.toLowerCase().includes(filter.toLowerCase()));

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredTraces]);

  const [expandedIndices, setExpandedIndices] = useState<Set<number>>(new Set());

  const toggleExpand = (index: number) => {
    const newSet = new Set(expandedIndices);
    if (newSet.has(index)) newSet.delete(index);
    else newSet.add(index);
    setExpandedIndices(newSet);
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#0d1117]" data-testid="trace-panel">
      <div className="flex p-2 gap-2 border-b border-[#30363d] bg-[#161b22] overflow-x-auto">
        {["All", "Orchestrator", "Evaluator", "Supply", "Demand", "System"].map(f => (
          <Button 
            key={f}
            variant="ghost" 
            size="sm"
            onClick={() => setFilter(f)}
            className={`text-xs h-7 rounded-full ${filter === f ? 'bg-[#30363d] text-white' : 'text-muted-foreground hover:bg-[#30363d]/50'}`}
          >
            {f}
          </Button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3" ref={scrollRef}>
        {filteredTraces.map((trace, i) => {
          const isLast = i === filteredTraces.length - 1;
          const isExpanded = expandedIndices.has(i);
          const color = ROLE_COLORS[trace.role] || "#e6edf3";

          return (
            <div 
              key={`${trace.timestamp}-${i}`}
              className={`text-sm font-mono border-l-2 pl-3 py-1 cursor-pointer transition-colors hover:bg-[#161b22]`}
              style={{ borderLeftColor: color }}
              onClick={() => toggleExpand(i)}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#161b22] border border-[#30363d] uppercase" style={{ color }}>
                  {trace.role}
                </span>
                <span className="text-[10px] text-[#8b949e]">
                  {new Date(trace.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div className={`text-[#e6edf3] ${isExpanded ? 'whitespace-pre-wrap' : 'truncate'} ${isLast ? 'cursor-blink' : ''}`}>
                {trace.content}
              </div>
            </div>
          );
        })}
        {filteredTraces.length === 0 && (
          <div className="text-center text-muted-foreground text-sm font-mono pt-8">
            No traces captured yet...
          </div>
        )}
      </div>
    </div>
  );
}
