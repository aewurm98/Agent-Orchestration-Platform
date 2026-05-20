import { useEffect, useState } from "react";
import { useSocket } from "@/hooks/useSocket";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Check, XSquare } from "lucide-react";

export default function HITLModal() {
  const { hitlRequest, emitHitlResponse, clearHitlRequest } = useSocket();
  const [timeLeft, setTimeLeft] = useState(30);
  const [constraint, setConstraint] = useState("");
  const [mode, setMode] = useState<"view" | "override">("view");

  useEffect(() => {
    if (hitlRequest) {
      setTimeLeft(30);
      setMode("view");
      setConstraint("");
    }
  }, [hitlRequest]);

  useEffect(() => {
    if (!hitlRequest) return;

    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          // Auto approve when time is up
          emitHitlResponse("approve");
          clearHitlRequest();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [hitlRequest, emitHitlResponse, clearHitlRequest]);

  if (!hitlRequest) return null;

  const handleApprove = () => {
    emitHitlResponse("approve");
    clearHitlRequest();
  };

  const handleStop = () => {
    emitHitlResponse("stop");
    clearHitlRequest();
  };

  const handleOverrideSubmit = () => {
    emitHitlResponse("override", constraint);
    clearHitlRequest();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#ffffff] border border-[#ebe5d6] w-[500px] rounded-lg shadow-2xl flex flex-col overflow-hidden">
        
        <div className="p-4 border-b border-[#ebe5d6] flex justify-between items-center bg-[#b45309]/10">
          <div className="flex items-center gap-2 text-[#b45309]">
            <AlertTriangle size={18} />
            <h2 className="font-semibold uppercase tracking-wider text-sm">Human Override Required</h2>
          </div>
          
          <div className="relative w-8 h-8 flex items-center justify-center">
            <svg className="w-8 h-8 transform -rotate-90">
              <circle cx="16" cy="16" r="14" fill="none" stroke="#ebe5d6" strokeWidth="2" />
              <circle 
                cx="16" cy="16" r="14" fill="none" stroke="#b45309" strokeWidth="2"
                strokeDasharray="88"
                strokeDashoffset={88 - (88 * timeLeft) / 30}
                className="transition-all duration-1000 ease-linear"
              />
            </svg>
            <span className="absolute text-[10px] font-mono text-[#b45309]">{timeLeft}</span>
          </div>
        </div>

        <div className="p-6 flex flex-col gap-4">
          <div className="flex justify-between items-start">
            <div className="text-xs text-muted-foreground uppercase">Gen: {hitlRequest.generation} | Run: {hitlRequest.run_id.slice(0, 8)}</div>
            <Badge variant="outline" className="border-[#14120e] text-[#14120e] bg-[#14120e]/10">
              Confidence: {Math.round(hitlRequest.confidence * 100)}%
            </Badge>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Proposed Action:</span>
            <div className="font-mono text-sm bg-[#f4f0e7] p-2 border border-[#ebe5d6] rounded text-[#14120e]">
              {hitlRequest.proposed_action}
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Plan Justification:</span>
            <div className="text-sm text-[#6b6359] italic border-l-2 border-[#ebe5d6] pl-3 py-1">
              "{hitlRequest.plan}"
            </div>
          </div>

          {mode === "override" && (
            <div className="mt-2 animate-in slide-in-from-top-2">
              <Input 
                autoFocus
                placeholder="Enter constraint or new directive..." 
                value={constraint}
                onChange={e => setConstraint(e.target.value)}
                className="bg-[#f4f0e7] border-[#b45309] focus-visible:ring-[#b45309]"
                data-testid="input-override-constraint"
              />
            </div>
          )}
        </div>

        <div className="p-4 bg-[#f4f0e7] border-t border-[#ebe5d6] flex justify-end gap-3">
          {mode === "view" ? (
            <>
              <Button variant="destructive" onClick={handleStop} data-testid="btn-hitl-stop">
                <XSquare size={16} className="mr-2" /> Stop
              </Button>
              <Button variant="outline" className="border-[#b45309] text-[#b45309] hover:bg-[#b45309]/10 hover:text-[#b45309]" onClick={() => setMode("override")} data-testid="btn-hitl-override">
                Override
              </Button>
              <Button className="bg-[#15803d] text-black hover:bg-[#15803d]/80" onClick={handleApprove} data-testid="btn-hitl-approve">
                <Check size={16} className="mr-2" /> Approve
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={() => setMode("view")} data-testid="btn-hitl-cancel-override">Cancel</Button>
              <Button className="bg-[#b45309] text-black hover:bg-[#b45309]/80" onClick={handleOverrideSubmit} disabled={!constraint} data-testid="btn-hitl-submit-override">
                Submit Override
              </Button>
            </>
          )}
        </div>

      </div>
    </div>
  );
}
