import { getRemainingPredictions, hasReachedLimit, FREE_LIMIT } from "../lib/usage";

interface UsageTrackerProps {
  onRefresh?: () => void;
}

export function UsageTracker({ onRefresh: _onRefresh }: UsageTrackerProps) {
  const remaining = getRemainingPredictions();
  const reached = hasReachedLimit();
  const used = FREE_LIMIT - remaining;

  return (
    <div className={`rounded-[24px] border px-4 py-3 ${reached ? "border-accent-amber/30 bg-accent-amber/5" : "border-white/8 bg-white/4"}`}>
      {reached ? (
        <div className="text-center">
          <div className="text-sm font-medium text-accent-amber">免费次数已用完</div>
          <div className="mt-1 text-xs text-text-muted">内测阶段，每位用户限 {FREE_LIMIT} 次免费预测。正式版即将上线。</div>
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-text-secondary">
              剩余 <span className="font-medium text-white">{remaining}</span> 次免费预测
            </span>
            <span className="text-text-muted text-xs">
              {used}/{FREE_LIMIT}
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/8">
            <div
              className="h-full rounded-full bg-accent-blue transition-all duration-500"
              style={{ width: `${(used / FREE_LIMIT) * 100}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export { FREE_LIMIT };
