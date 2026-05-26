import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchAccuracyStats, fetchRecentPredictions } from "../lib/api";
import { EmptyState } from "../components/EmptyState";
import type { RecentPredictionItem } from "../lib/types";

export function StatsPage() {
  const statsQuery = useQuery({
    queryKey: ["stats", "accuracy"],
    queryFn: fetchAccuracyStats,
  });
  const recentQuery = useQuery({
    queryKey: ["stats", "recent-predictions"],
    queryFn: () => fetchRecentPredictions({ limit: 30 }),
  });

  if (statsQuery.isLoading) {
    return null;
  }

  const stats = statsQuery.data;
  const recent = recentQuery.data ?? [];
  if (!stats) {
    return <EmptyState title="统计暂不可用" description="请稍后再试，或检查后端统计接口是否正常启动。" />;
  }

  const totalPredictions = stats.overall.total_predictions;
  const sampleWarning =
    totalPredictions === 0
      ? "系统刚启动，正在累积预测数据。首批联赛比赛结束后将自动更新。"
      : totalPredictions < 5
      ? `当前样本量较少（${totalPredictions}场），统计数据供参考。`
      : null;

  return (
    <div className="space-y-6">
      <section className="rounded-[36px] border border-white/8 bg-bg-card/75 px-6 py-7 shadow-hero">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Accuracy Board</div>
        <div className="mt-3 font-display text-[38px] leading-none">公开准确率看板</div>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-text-secondary">
          赛后结果统一以 Brier、LogLoss、Top3 命中率回测。世界杯开赛前，先用五大联赛和欧冠比赛持续验证模型表现。
        </p>
      </section>

      {sampleWarning ? (
        <section className="rounded-[28px] border border-amber-300/30 bg-amber-300/8 px-5 py-4 text-sm text-amber-200">
          {sampleWarning}
        </section>
      ) : null}

      {totalPredictions === 0 ? (
        <EmptyState title="系统刚启动，正在累积预测数据" description="首批联赛比赛结束后，这里会自动展示准确率和最近预测记录。" />
      ) : (
        <>
          <section className="grid gap-3 md:grid-cols-3">
            <MetricCard label="已预测场次" value={String(totalPredictions)} helper="已完成赛后评估的预测条目" />
            <MetricCard
              label="Top3 命中率"
              value={stats.overall.top3_hit_rate === null ? "—" : `${Math.round(stats.overall.top3_hit_rate * 100)}%`}
              helper="预测前三比分之一命中"
            />
            <MetricCard
              label="Brier Score"
              value={stats.overall.brier_score_avg === null ? "—" : stats.overall.brier_score_avg.toFixed(3)}
              helper="↓ 越低越准"
            />
          </section>

          <section className="rounded-[30px] border border-white/8 bg-bg-card/75 px-5 py-5">
            <div className="font-display text-2xl">按赛事准确率</div>
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-text-muted">
                  <tr>
                    <th className="pb-3 font-medium">赛事</th>
                    <th className="pb-3 font-medium">预测场次</th>
                    <th className="pb-3 font-medium">Top3 命中率</th>
                    <th className="pb-3 font-medium">Brier Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/6">
                  {stats.by_competition.map((item) => (
                    <tr key={item.competition}>
                      <td className="py-3">{item.competition_zh}</td>
                      <td className="py-3 text-text-secondary">{item.total}</td>
                      <td className="py-3">
                        <span className={rateTone(item.top3_hit_rate)}>
                          {item.top3_hit_rate === null ? "—" : `${Math.round(item.top3_hit_rate * 100)}%`}
                        </span>
                      </td>
                      <td className="py-3 text-text-secondary">{item.brier_score === null ? "—" : item.brier_score.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-[30px] border border-white/8 bg-bg-card/75 px-5 py-5">
            <div className="flex items-end justify-between gap-4">
              <div>
                <div className="font-display text-2xl">最近 30 场预测记录</div>
                <div className="mt-1 text-sm text-text-secondary">
                  最近 30 场平均 Brier {stats.recent_30.brier_score === null ? "—" : stats.recent_30.brier_score.toFixed(3)} ·
                  趋势 {trendLabel(stats.recent_30.trend)}
                </div>
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {recent.map((item) => (
                <Link
                  key={`${item.match_id}-${item.match_date}`}
                  to={`/match/${item.match_id}/review`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 transition hover:border-white/20"
                >
                  <div>
                    <div className="text-sm text-text-primary">
                      {formatDate(item.match_date)} · {item.home_team_zh} vs {item.away_team_zh}
                    </div>
                    <div className="mt-1 text-xs text-text-muted">
                      {item.competition_zh} · 预测 {predictionLabel(item)} · 实际 {item.actual_home_goals}:{item.actual_away_goals}
                    </div>
                  </div>
                  <div className={`text-sm ${item.prediction_correct ? "text-emerald-300" : "text-rose-300"}`}>
                    {item.prediction_correct ? "✓ 命中" : "✗ 偏离"}
                  </div>
                </Link>
              ))}
            </div>
          </section>
        </>
      )}

      <section className="rounded-[30px] border border-white/8 bg-bg-card/75 px-5 py-5">
        <div className="font-display text-2xl">关于我们的预测方法</div>
        <div className="mt-4 space-y-3 text-sm leading-7 text-text-secondary">
          <p>核心基线来自 Dixon-Coles 比分分布模型，用于稳定输出胜平负概率和 Top3 比分。</p>
          <p>赛前会叠加 xG、天气、休息日、结构化情报和冲突风险，再做概率校准，确保“60%”尽量接近真实发生率。</p>
          <p>整套系统不依赖博彩赔率，所有公开准确率都来自赛后回测。</p>
        </div>
      </section>
    </div>
  );
}

function MetricCard({ label, value, helper }: { label: string; value: string; helper: string }) {
  return (
    <div className="rounded-[28px] border border-white/8 bg-bg-card/75 px-5 py-5">
      <div className="text-sm text-text-secondary">{label}</div>
      <div className="mt-3 font-display text-4xl">{value}</div>
      <div className="mt-2 text-xs text-text-muted">{helper}</div>
    </div>
  );
}

function rateTone(value: number | null) {
  if (value === null) return "text-text-secondary";
  if (value > 0.4) return "text-emerald-300";
  if (value >= 0.2) return "text-amber-300";
  return "text-rose-300";
}

function trendLabel(value: "improving" | "stable" | "declining") {
  if (value === "improving") return "改善中";
  if (value === "declining") return "走弱";
  return "稳定";
}

function predictionLabel(item: RecentPredictionItem) {
  const probabilities = [
    { label: "主胜", value: item.predicted_home_win },
    { label: "平局", value: item.predicted_draw },
    { label: "客胜", value: item.predicted_away_win },
  ];
  return probabilities.sort((left, right) => right.value - left.value)[0]?.label ?? "未知";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}
