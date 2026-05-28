import { useEffect, useState } from "react";

interface PredictionProgressProps {
  startedAt: Date;
  status: string;
}

export function PredictionProgress({ startedAt, status }: PredictionProgressProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt.getTime()) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

  const phase = elapsed < 15 ? "loading" : elapsed < 45 ? "training" : elapsed < 80 ? "predicting" : "finishing";

  const messages: Record<string, string> = {
    loading: "正在加载训练数据...",
    training: "正在训练预测模型 (Dixon-Coles + Enhancer + Elo)...",
    predicting: "正在生成预测结果...",
    finishing: "正在完成最后的计算...",
  };

  const phaseIndex = Object.keys(messages).indexOf(phase);

  return (
    <div className="flex flex-col items-center justify-center py-12">
      {/* Animated ring */}
      <div className="relative mb-8">
        <svg className="h-24 w-24 animate-[spin_3s_linear_infinite]" viewBox="0 0 96 96">
          <circle cx="48" cy="48" r="40" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="6" />
          <circle
            cx="48" cy="48" r="40" fill="none"
            stroke="var(--accent-blue)" strokeWidth="6"
            strokeDasharray={`${30 + phaseIndex * 20} 252`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-display text-xl text-white">{Math.min(elapsed, 99)}s</span>
        </div>
      </div>

      <div className="mb-3 font-display text-lg text-white">{status === "queued" ? "等待中..." : messages[phase]}</div>
      <div className="mb-6 text-sm text-text-secondary">完整预测通常需要 30-90 秒</div>

      {/* Progress steps */}
      <div className="flex gap-2">
        {["数据加载", "模型训练", "预测生成", "完成"].map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-xs transition ${
                i < phaseIndex
                  ? "bg-accent-green text-black"
                  : i === phaseIndex
                    ? "bg-accent-blue text-white"
                    : "bg-white/5 text-text-muted"
              }`}
            >
              {i < phaseIndex ? "✓" : i + 1}
            </div>
            <span className={`hidden text-xs sm:inline ${i <= phaseIndex ? "text-text-secondary" : "text-text-muted"}`}>
              {label}
            </span>
            {i < 3 ? <div className="mx-0.5 h-px w-4 bg-white/10" /> : null}
          </div>
        ))}
      </div>

      {elapsed > 60 ? (
        <div className="mt-6 text-sm text-amber-400/80">预测时间比预期长，请耐心等待...</div>
      ) : null}
    </div>
  );
}
