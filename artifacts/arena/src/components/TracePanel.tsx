import { useState, useRef, useEffect } from "react";
import { useSocket } from "@/hooks/useSocket";
import { Button } from "@/components/ui/button";

const ROLE_COLORS: Record<string, string> = {
  orchestrator:           "#14120e",
  evaluator:              "#b45309",
  supply_agent:           "#15803d",
  demand_agent:           "#15803d",
  worker_1:               "#15803d",
  worker_2:               "#15803d",
  rescuer:                "#15803d",
  coordinator:            "#15803d",
  worker:                 "#15803d",
  planner:                "#9333ea",
  system:                 "#6b6359",
};

const STAGE_BADGE_COLORS: Record<string, string> = {
  raw_materials:    "#b45309",
  intermediates:    "#10b981",
  finished_product: "#1d4ed8",
};

type FilterKey = "All" | "Orchestrator" | "Evaluator" | "Game Agents" | "System";

const FILTERS: FilterKey[] = ["All", "Orchestrator", "Evaluator", "Game Agents", "System"];

function matchesFilter(role: string, filter: FilterKey): boolean {
  if (filter === "All") return true;
  const r = role.toLowerCase();
  switch (filter) {
    case "Orchestrator": return r === "orchestrator";
    case "Evaluator":    return r === "evaluator";
    case "System":       return r === "system";
    case "Game Agents":
      return !["orchestrator", "evaluator", "system"].includes(r);
  }
}

export default function TracePanel() {
  const { traces } = useSocket();
  const [filter, setFilter] = useState<FilterKey>("All");
  const scrollRef = useRef<HTMLDivElement>(null);
  const [expandedIndices, setExpandedIndices] = useState<Set<number>>(new Set());

  const filteredTraces = traces.filter((t) => matchesFilter(t.role, filter));

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredTraces]);

  const toggleExpand = (index: number) => {
    setExpandedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  return (
    <div className="w-full h-full flex flex-col bg-transparent" data-testid="trace-panel">
      <div className="flex p-2 gap-1 border-b border-[#ebe5d6] bg-[#efe9d9] overflow-x-auto shrink-0">
        {FILTERS.map((f) => (
          <Button
            key={f}
            variant="ghost"
            size="sm"
            onClick={() => setFilter(f)}
            className={`text-xs h-7 rounded-full whitespace-nowrap ${
              filter === f
                ? "bg-[#14120e] text-white hover:bg-[#2a2620]"
                : "text-[#6b6359] hover:bg-[#faf6ed]"
            }`}
            data-testid={`filter-trace-${f.toLowerCase().replace(/\s+/g, "-")}`}
          >
            {f}
          </Button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3" ref={scrollRef}>
        {filteredTraces.map((trace, i) => {
          const isLast = i === filteredTraces.length - 1;
          const isExpanded = expandedIndices.has(i);
          const color = ROLE_COLORS[trace.role] ?? "#14120e";
          const stageColor = trace.stage ? STAGE_BADGE_COLORS[trace.stage] ?? "#6b6359" : null;

          return (
            <div
              key={`${trace.timestamp}-${i}`}
              className="text-sm font-mono border-l-2 pl-3 py-1 cursor-pointer transition-colors hover:bg-[#faf6ed] rounded-r-md"
              style={{ borderLeftColor: color }}
              onClick={() => toggleExpand(i)}
            >
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded bg-[#ffffff] border border-[#ebe5d6] uppercase"
                  style={{ color }}
                >
                  {trace.agent_role ?? trace.role}
                </span>
                {trace.agent_name && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#ffffff] border border-[#ebe5d6] text-[#6b6359]">
                    {trace.agent_name}
                  </span>
                )}
                {trace.stage && stageColor && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded border border-[#ebe5d6]"
                    style={{ color: stageColor, backgroundColor: "#ffffff" }}
                  >
                    {trace.stage.replace(/_/g, " ")}
                  </span>
                )}
                {trace.action && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#15803d]/15 text-[#15803d] border border-[#15803d]/30">
                    {trace.action}
                  </span>
                )}
                <span className="text-[10px] text-[#6b6359]">
                  {new Date(trace.timestamp * 1000).toLocaleTimeString()}
                </span>
              </div>

              {trace.reasoning && (
                <div className="text-[11px] text-[#6b6359] italic mb-1 truncate">
                  {trace.reasoning}
                </div>
              )}

              <div
                className={`text-[#14120e] ${isExpanded ? "whitespace-pre-wrap" : "truncate"} ${
                  isLast ? "cursor-blink" : ""
                }`}
              >
                {trace.content}
              </div>

              {isExpanded && trace.parameters && Object.keys(trace.parameters).length > 0 && (
                <div className="mt-1 text-[10px] text-[#6b6359] bg-[#faf6ed] border border-[#ebe5d6] rounded p-1.5">
                  <span className="text-[#8b8378]">params: </span>
                  {JSON.stringify(trace.parameters)}
                </div>
              )}
            </div>
          );
        })}
        {filteredTraces.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-3 pt-12">
            <div className="w-9 h-9 rounded-xl bg-[#efe9d9] flex items-center justify-center text-[16px]">💬</div>
            <p className="text-[12px] text-[#6b6359] font-mono">
              {filter === "All" ? "No agent traces yet" : `No ${filter} traces`}
            </p>
            <p className="text-[11px] text-[#a89e8e]">Traces appear here as agents act</p>
          </div>
        )}
      </div>
    </div>
  );
}
