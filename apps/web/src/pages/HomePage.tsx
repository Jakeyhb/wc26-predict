import { useCallback, useEffect, useRef, useState } from "react";
import { TeamSelector } from "../components/TeamSelector";
import { PredictionProgress } from "../components/PredictionProgress";
import { PredictionResult } from "../components/PredictionResult";
import { UsageTracker } from "../components/UsageTracker";
import { submitCustomPrediction, fetchPredictionStatus } from "../lib/api";
import { hasReachedLimit, incrementUsage } from "../lib/usage";
import type { TeamItem, PredictionStatusResponse } from "../lib/types";

type PageState = "select" | "predicting" | "result" | "error" | "limit";

export function HomePage() {
  const [homeTeam, setHomeTeam] = useState<TeamItem | null>(null);
  const [awayTeam, setAwayTeam] = useState<TeamItem | null>(null);
  const [neutral, setNeutral] = useState(true);
  const [state, setState] = useState<PageState>("select");
  const [predictionId, setPredictionId] = useState<string | null>(null);
  const [matchId, setMatchId] = useState<string | null>(null);
  const [result, setResult] = useState<PredictionStatusResponse["result"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<Date | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const canPredict = homeTeam && awayTeam && !hasReachedLimit();

  const handlePredict = useCallback(async () => {
    if (!homeTeam || !awayTeam) return;
    if (hasReachedLimit()) { setState("limit"); return; }

    setState("predicting");
    setError(null);
    setResult(null);
    setStartedAt(new Date());

    try {
      const resp = await submitCustomPrediction({
        home_team: homeTeam.name,
        away_team: awayTeam.name,
        competition: "Custom Match",
        is_neutral_venue: neutral,
      });
      setPredictionId(resp.prediction_id);
      setMatchId(resp.match_id);
      incrementUsage(resp.prediction_id, homeTeam.name, awayTeam.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交预测失败");
      setState("error");
    }
  }, [homeTeam, awayTeam, neutral]);

  // Poll for prediction status
  useEffect(() => {
    if (!predictionId || state !== "predicting") return;

    let attempts = 0;
    const poll = async () => {
      attempts++;
      try {
        const status = await fetchPredictionStatus(predictionId);
        if (status.status === "completed" && status.result) {
          setResult(status.result);
          setState("result");
          if (pollRef.current) clearInterval(pollRef.current);
        } else if (status.status === "failed") {
          setError(status.error ?? "预测失败");
          setState("error");
          if (pollRef.current) clearInterval(pollRef.current);
        }
        // Timeout after 180s
        if (attempts > 36) {
          setError("预测超时，请重试");
          setState("error");
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {
        // Keep polling on network errors
      }
    };

    poll(); // immediate first poll
    pollRef.current = setInterval(poll, 5000); // then every 5s

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [predictionId, state]);

  const handleReset = () => {
    setState("select");
    setHomeTeam(null);
    setAwayTeam(null);
    setPredictionId(null);
    setResult(null);
    setError(null);
  };

  // Check limit on mount
  useEffect(() => {
    if (hasReachedLimit()) setState("limit");
  }, []);

  return (
    <div className="mx-auto max-w-xl space-y-6 py-6">
      {/* Hero */}
      <section className="text-center">
        <div className="text-xs uppercase tracking-[0.3em] text-text-muted">2026 World Cup Prediction Desk</div>
        <h1 className="mt-3 font-display text-[36px] leading-tight text-white">WC26 Predict</h1>
        <p className="mt-2 text-sm leading-relaxed text-text-secondary">
          选择两支球队，让 AI 预测引擎为你生成深度分析报告。
        </p>
      </section>

      {/* Limit reached */}
      {state === "limit" ? (
        <section className="rounded-[32px] border border-accent-amber/20 bg-accent-amber/5 px-5 py-8 text-center">
          <div className="font-display text-2xl text-accent-amber">内测次数已用完</div>
          <p className="mt-3 text-sm text-text-secondary">
            每位用户限 3 次免费预测。感谢参与内测！正式版即将上线，届时将支持无限次数。
          </p>
        </section>
      ) : null}

      {/* Team selection */}
      {state === "select" || state === "error" ? (
        <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6 space-y-4">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-text-muted mb-2">主队</div>
            <TeamSelector value={homeTeam} onChange={setHomeTeam} placeholder="选择主队..." disabledTeam={awayTeam} />
          </div>
          <div className="flex items-center justify-center">
            <div className="font-display text-sm text-text-muted">VS</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-text-muted mb-2">客队</div>
            <TeamSelector value={awayTeam} onChange={setAwayTeam} placeholder="选择客队..." disabledTeam={homeTeam} />
          </div>

          {/* Neutral venue toggle */}
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={neutral}
              onChange={(e) => setNeutral(e.target.checked)}
              className="h-4 w-4 rounded border-white/20 bg-white/5 text-accent-blue focus:ring-accent-blue"
            />
            <span className="text-sm text-text-secondary">中立场地</span>
          </label>

          {/* Error */}
          {error ? (
            <div className="rounded-[20px] border border-accent-red/30 bg-accent-red/5 px-4 py-3 text-sm text-accent-red">
              {error}
            </div>
          ) : null}

          {/* Predict button */}
          <button
            disabled={!canPredict}
            onClick={handlePredict}
            className={`w-full rounded-[28px] px-6 py-4 text-center text-sm font-medium transition ${
              canPredict
                ? "bg-accent-blue text-white hover:opacity-80"
                : "cursor-not-allowed bg-white/5 text-text-muted"
            }`}
          >
            {!homeTeam || !awayTeam ? "请选择两支球队" : hasReachedLimit() ? "次数已用完" : "开始预测"}
          </button>

          <UsageTracker />
        </section>
      ) : null}

      {/* Predicting */}
      {state === "predicting" && startedAt ? (
        <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
          <PredictionProgress startedAt={startedAt} status="running" />
          <button
            onClick={() => { setState("error"); setError("用户取消了预测"); }}
            className="mx-auto mt-4 block text-sm text-text-muted hover:text-text-secondary transition"
          >
            取消
          </button>
        </section>
      ) : null}

      {/* Result */}
      {state === "result" && result ? (
        <PredictionResult result={result as any} onNewPrediction={handleReset} />
      ) : null}
    </div>
  );
}
