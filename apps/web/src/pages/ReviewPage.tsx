import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { fetchReview } from "../lib/api";
import { Skeleton } from "../components/Skeleton";

export function ReviewPage() {
  const { matchId = "" } = useParams();
  const { data, isLoading } = useQuery({
    queryKey: ["review", matchId],
    queryFn: () => fetchReview(matchId),
  });

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 rounded-[32px]" />
        <Skeleton className="h-72 rounded-[32px]" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Postmatch Review</div>
        <div className="mt-3 font-display text-[34px]">实际比分 {data.actual_score}</div>
        <div className="mt-2 text-sm text-text-secondary">赛果标签：{data.actual_result}</div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Prediction Runs</div>
        <div className="mt-4 space-y-3">
          {data.runs.map((run) => (
            <div key={run.prediction_run_id} className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-display text-2xl">{run.run_type}</div>
                  <div className="mt-1 text-sm text-text-secondary">{new Date(run.created_at).toLocaleString()}</div>
                </div>
                <div className="rounded-full border border-white/10 px-3 py-2 text-sm text-text-secondary">
                  实际比分 {run.actual_score}
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-4">
                <StatBox label="预测比分" value={run.predicted_top_score} />
                <StatBox label="Brier Score" value={run.brier_score.toFixed(3)} />
                <StatBox label="Log Loss" value={run.log_loss.toFixed(3)} />
                <StatBox label="Top3 命中" value={run.top3_hit ? "是" : "否"} />
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className={`rounded-full px-3 py-2 text-sm ${run.exact_score_hit ? "bg-accent-green/15 text-accent-green" : "bg-white/6 text-text-secondary"}`}>
                  {run.exact_score_hit ? "Exact Score 命中" : "Exact Score 未命中"}
                </span>
                <span className={`rounded-full px-3 py-2 text-sm ${run.top3_hit ? "bg-accent-blue/15 text-accent-blue" : "bg-white/6 text-text-secondary"}`}>
                  {run.top3_hit ? "Top3 命中" : "Top3 未命中"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Signal Audit</div>
        <div className="mt-4 space-y-3">
          {data.signal_reviews.map((signal) => (
            <div key={signal.signal_id} className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
              <div className="font-medium">{signal.summary_zh}</div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                <span className="text-text-secondary">{signal.signal_type}</span>
                <span
                  className={`rounded-full px-3 py-1 ${
                    signal.verdict === "accurate"
                      ? "bg-accent-green/15 text-accent-green"
                      : signal.verdict === "misleading"
                        ? "bg-accent-red/15 text-accent-red"
                        : "bg-white/6 text-text-secondary"
                  }`}
                >
                  {signal.verdict === "accurate" ? "方向正确" : signal.verdict === "misleading" ? "方向错误" : signal.verdict}
                </span>
              </div>
              {signal.notes ? <div className="mt-2 text-sm text-text-secondary">{signal.notes}</div> : null}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-black/10 px-4 py-4">
      <div className="text-xs uppercase tracking-[0.18em] text-text-muted">{label}</div>
      <div className="mt-2 font-display text-2xl">{value}</div>
    </div>
  );
}
