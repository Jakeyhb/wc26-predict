import type { PredictionHistoryItem } from "../lib/types";

const labelMap = {
  t_minus_24h: "T-24h",
  t_minus_3h: "T-3h",
  lineup_confirmed: "首发后",
} as const;

export function TimelineRail({
  history,
  active,
}: {
  history: PredictionHistoryItem[];
  active?: string;
}) {
  return (
    <div className="flex items-center gap-3 overflow-x-auto">
      {(["t_minus_24h", "t_minus_3h", "lineup_confirmed"] as const).map((runType, index) => {
        const exists = history.find((item) => item.run_type === runType);
        const isActive = active === runType;
        return (
          <div key={runType} className="flex items-center gap-3">
            <div
              className={`rounded-full border px-3 py-2 text-xs uppercase tracking-[0.2em] ${
                exists
                  ? isActive
                    ? "border-accent-blue bg-accent-blue/15 text-text-primary"
                    : "border-white/20 bg-white/5 text-text-secondary"
                  : "border-dashed border-white/10 bg-transparent text-text-muted"
              }`}
            >
              {labelMap[runType]} {exists ? "✓" : "○"}
            </div>
            {index < 2 ? <div className="glass-line h-px w-7 shrink-0" /> : null}
          </div>
        );
      })}
    </div>
  );
}

