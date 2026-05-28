import { ProbabilityArc } from "./ProbabilityArc";
import { SignalList } from "./SignalList";

interface PredictionResultData {
  prediction_run_id: string;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  home_xg: number;
  away_xg: number;
  top3_scores: Array<{ score: string; prob: number }>;
  confidence_score: number;
  risk_tags: string[];
  model_version: string;
  home_team: string;
  away_team: string;
  competition: string;
  created_at: string | null;
}

interface PredictionResultProps {
  result: PredictionResultData;
  onNewPrediction: () => void;
}

export function PredictionResult({ result, onNewPrediction }: PredictionResultProps) {
  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6 text-center">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">{result.competition}</div>
        <div className="mt-3 font-display text-[32px] leading-none text-white">
          {result.home_team} vs {result.away_team}
        </div>
        <div className="mt-3 text-sm text-text-secondary">
          模型版本 {result.model_version} · 置信度 {Math.round(result.confidence_score * 100)}%
        </div>
      </div>

      {/* Probabilities */}
      <div className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="grid grid-cols-3 gap-4">
          <ProbabilityArc value={result.home_win_prob} color="var(--accent-blue)" label="主胜" />
          <ProbabilityArc value={result.draw_prob} color="rgba(255,255,255,0.55)" label="平局" />
          <ProbabilityArc value={result.away_win_prob} color="var(--accent-green)" label="客胜" />
        </div>
      </div>

      {/* Top 3 Scores */}
      {result.top3_scores && result.top3_scores.length > 0 ? (
        <div className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
          <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Top 3 Expected Scores</div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {result.top3_scores.map((item, index) => (
              <div
                key={item.score}
                className={`rounded-[28px] border px-4 py-5 text-center ${
                  index === 0 ? "border-amber-300/70 bg-amber-300/8" : "border-white/8 bg-white/4"
                }`}
              >
                <div className="font-display text-3xl text-white">{item.score}</div>
                <div className="mt-2 text-sm text-text-secondary">{Math.round(item.prob * 100)}%</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* xG */}
      <div className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Expected Goals (xG)</div>
        <div className="mt-5 space-y-5">
          <XgBar label={result.home_team} value={result.home_xg} color="var(--accent-blue)" />
          <XgBar label={result.away_team} value={result.away_xg} color="var(--accent-green)" />
        </div>
      </div>

      {/* Risk Tags */}
      {result.risk_tags && result.risk_tags.length > 0 ? (
        <div className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
          <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Risk Factors</div>
          <div className="mt-4 flex flex-wrap gap-2">
            {result.risk_tags.map((tag) => (
              <span key={tag} className="rounded-full bg-accent-amber/15 px-3 py-2 text-sm text-accent-amber">
                {tag}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {/* Confidence card */}
      <div className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Model Details</div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
            <div className="text-xs text-text-muted">模型版本</div>
            <div className="mt-2 font-display text-xl text-white">{result.model_version}</div>
          </div>
          <div className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
            <div className="text-xs text-text-muted">置信度</div>
            <div className="mt-2 font-display text-xl text-accent-blue">{Math.round(result.confidence_score * 100)}%</div>
          </div>
          <div className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
            <div className="text-xs text-text-muted">预测引擎</div>
            <div className="mt-2 font-display text-xl text-white">DC+HGB</div>
          </div>
        </div>
      </div>

      {/* New prediction button */}
      <button
        onClick={onNewPrediction}
        className="w-full rounded-[28px] bg-accent-blue px-6 py-4 text-center text-sm font-medium text-white transition hover:opacity-80"
      >
        ← 预测另一场比赛
      </button>
    </div>
  );
}

function XgBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="text-text-secondary">{label}</span>
        <span className="text-white">{value.toFixed(2)}</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-white/6">
        <div
          className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{ width: `${Math.min(100, value * 35)}%`, background: color }}
        />
      </div>
    </div>
  );
}
