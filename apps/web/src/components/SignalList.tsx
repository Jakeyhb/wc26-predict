import { useState } from "react";
import { AlertTriangle, Plane, ShieldAlert, Users } from "lucide-react";
import type { ApprovedSignalItem } from "../lib/types";

function iconForSignal(type: string) {
  if (type === "travel") return Plane;
  if (type === "injury") return ShieldAlert;
  if (type === "lineup_hint") return Users;
  return AlertTriangle;
}

function colorForImpact(direction: string) {
  if (direction === "positive") return "text-accent-green";
  if (direction === "negative") return "text-accent-red";
  return "text-accent-amber";
}

function availabilityTone(value?: string | null) {
  if (value === "out" || value === "suspended") return "bg-accent-red/15 text-accent-red";
  if (value === "doubtful" || value === "likely_bench") return "bg-accent-amber/15 text-accent-amber";
  if (value === "available" || value === "likely_start") return "bg-accent-green/15 text-accent-green";
  return "bg-white/8 text-text-secondary";
}

export function SignalList({ signals }: { signals: ApprovedSignalItem[] }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? signals : signals.slice(0, 5);

  return (
    <div className="space-y-3">
      <div className={`signal-collapse ${expanded ? "max-h-[520px]" : "max-h-[280px]"}`}>
        <div className="space-y-3">
          {shown.map((signal) => {
            const Icon = iconForSignal(signal.signal_type);
            return (
              <div
                key={signal.id}
                className="flex items-start gap-3 rounded-3xl border border-white/8 bg-white/4 px-4 py-3"
              >
                <div className="mt-1 rounded-full border border-white/10 p-2">
                  <Icon className="h-4 w-4 text-text-secondary" />
                </div>
                <div className="flex-1">
                  <div className="text-sm leading-6 text-text-primary">{signal.summary_zh}</div>
                  <div className="mt-2 flex items-center gap-3 text-xs text-text-secondary">
                    <span className={colorForImpact(signal.impact_direction)}>{signal.impact_direction}</span>
                    {signal.normalized_availability ? (
                      <span className={`rounded-full px-2 py-1 ${availabilityTone(signal.normalized_availability)}`}>
                        {signal.normalized_availability}
                      </span>
                    ) : null}
                    {signal.contradiction_risk === "high" ? <span className="text-accent-amber">⚠️ 高冲突</span> : null}
                    <span className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: `rgba(79, 142, 247, ${Math.max(0.25, signal.source_reliability)})` }}
                      />
                      来源可信度 {Math.round(signal.source_reliability * 100)}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {signals.length > 5 ? (
        <button
          className="text-sm text-accent-blue transition hover:text-white"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "收起信号" : `展开全部 ${signals.length} 条信号`}
        </button>
      ) : null}
    </div>
  );
}
