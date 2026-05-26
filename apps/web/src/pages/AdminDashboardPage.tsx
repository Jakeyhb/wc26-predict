import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDashboard, fetchHermesDigest } from "../lib/api";

export function AdminDashboardPage({ token }: { token: string }) {
  const { data } = useQuery({
    queryKey: ["admin", "dashboard", token],
    queryFn: () => fetchDashboard(token),
  });
  const hermesQuery = useQuery({
    queryKey: ["admin", "hermes-digest", token],
    queryFn: () => fetchHermesDigest(token),
  });

  if (!data) return null;

  const hermes = hermesQuery.data;

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Admin Dashboard</div>
        <div className="mt-2 font-display text-3xl">模型运营面板</div>
        <div className="mt-2 text-sm text-text-secondary">优先观察联赛/世界杯双线的回测、校准和任务运行状态。</div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="累计预测数" value={data.total_predictions_made} />
        <MetricCard label="今日预测运行" value={data.prediction_runs_today} />
        <MetricCard label="待审核信号" value={data.pending_signals} />
        <MetricCard label="今日新增文章" value={data.new_articles_today} />
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <MetricCard
          label="最近 5 场平均 Brier"
          value={data.recent_5_matches_avg_brier_score === null ? "—" : data.recent_5_matches_avg_brier_score.toFixed(3)}
        />
        <MetricCard
          label="最近 7 天平均 Brier"
          value={data.last_7_days_avg_brier_score === null ? "—" : data.last_7_days_avg_brier_score.toFixed(3)}
        />
        <MetricCard
          label="Top3 总体命中率"
          value={data.top3_hit_rate_overall === null ? "—" : `${Math.round(data.top3_hit_rate_overall * 100)}%`}
        />
      </div>

      <Panel title="Hermes 运营简报">
        {hermes ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/6 bg-black/10 px-4 py-3">
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-text-muted">关注级别</div>
                <div className="mt-2 text-lg text-white">{attentionLevelText(hermes.attention_level)}</div>
              </div>
              <div className={`rounded-full border px-3 py-2 text-sm ${attentionLevelToneClass(hermes.attention_level)}`}>
                {hermes.attention_level}
              </div>
            </div>

            <p className="text-sm leading-7 text-text-secondary">{hermes.summary}</p>

            <div className="grid gap-3 md:grid-cols-2">
              {hermes.focus_items.map((item) => (
                <div key={`${item.label}-${item.detail}`} className={`rounded-2xl border px-4 py-4 ${toneClass(item.tone)}`}>
                  <div className="text-xs uppercase tracking-[0.18em] text-text-muted">{item.label}</div>
                  <div className="mt-2 text-sm leading-6">{item.detail}</div>
                </div>
              ))}
            </div>

            {hermes.stale_tasks.length > 0 ? (
              <div className="space-y-2">
                <div className="text-xs uppercase tracking-[0.18em] text-text-muted">需要巡检的任务</div>
                <div className="grid gap-3 md:grid-cols-2">
                  {hermes.stale_tasks.map((task) => (
                    <div
                      key={task.name}
                      className={`rounded-2xl border px-4 py-4 ${task.stale ? "border-accent-red/20 bg-accent-red/10" : "border-white/6 bg-black/10"}`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm text-white">{task.name}</div>
                        <div className={`rounded-full px-2 py-1 text-xs ${task.stale ? "text-accent-red" : "text-text-secondary"}`}>
                          {task.stale ? "stale" : "ok"}
                        </div>
                      </div>
                      <div className="mt-2 text-xs text-text-secondary">
                        {task.last_run ? `上次运行 ${formatDate(task.last_run)}` : "尚未记录"}
                        {task.age_minutes !== null ? ` · ${task.age_minutes} 分钟前` : ""}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="rounded-2xl border border-white/6 bg-black/10 px-4 py-4 text-sm text-text-secondary">
            Hermes 正在整理今天的运营重点...
          </div>
        )}
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="赛事拆分">
          <div className="grid gap-3 sm:grid-cols-2">
            <MetricCard label="联赛比赛 / 预测" value={`${data.competition_breakdown.club?.match_count ?? 0} / ${data.competition_breakdown.club?.prediction_count ?? 0}`} compact />
            <MetricCard label="国家队比赛 / 预测" value={`${data.competition_breakdown.national?.match_count ?? 0} / ${data.competition_breakdown.national?.prediction_count ?? 0}`} compact />
            <MetricCard label="杯赛比赛 / 预测" value={`${data.competition_breakdown.cup?.match_count ?? 0} / ${data.competition_breakdown.cup?.prediction_count ?? 0}`} compact />
            <MetricCard
              label="校准器状态"
              value={data.calibrator_status.is_fitted ? `已训练 (${data.calibrator_status.training_samples})` : "未训练"}
              compact
            />
          </div>
        </Panel>

        <Panel title="最近 7 天预测量">
          <div className="space-y-3">
            {data.recent_prediction_counts_7d.map((item) => (
              <div key={item.competition} className="flex items-center justify-between rounded-2xl border border-white/6 bg-black/10 px-4 py-3">
                <div className="text-sm text-white">{item.competition_zh}</div>
                <div className="text-sm text-text-secondary">{item.prediction_count}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="最近 5 场准确率">
        <div className="space-y-3">
          {data.recent_accuracy.map((item) => (
            <div key={item.prediction_run_id} className="rounded-2xl border border-white/6 bg-black/10 px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm text-text-secondary">{item.match_id}</div>
                <div className="text-sm">{item.top3_hit ? "Top3 命中" : "Top3 未命中"}</div>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-[1fr_1fr_1fr]">
                <TrendBar label="Brier" value={item.brier_score} inverse />
                <TrendBar label="LogLoss" value={item.log_loss} inverse />
                <TrendBar label="Top3" value={item.top3_hit ? 1 : 0} percentage />
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Beat 任务最近运行时间">
        <div className="grid gap-3 md:grid-cols-2">
          {Object.entries(data.beat_tasks_last_run).map(([taskName, lastRun]) => (
            <div key={taskName} className="rounded-2xl border border-white/6 bg-black/10 px-4 py-3">
              <div className="text-xs uppercase tracking-[0.18em] text-text-muted">{taskName}</div>
              <div className="mt-2 text-sm text-white">{lastRun ? formatDate(lastRun) : "尚未记录"}</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-[28px] border border-border bg-bg-card/80 p-5">
      <div className="font-display text-xl">{title}</div>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: number | string;
  compact?: boolean;
}) {
  return (
    <div className="rounded-[28px] border border-border bg-bg-card/80 p-5">
      <div className="text-sm text-text-secondary">{label}</div>
      <div className={`mt-3 font-display ${compact ? "text-2xl" : "text-4xl"}`}>{value}</div>
    </div>
  );
}

function TrendBar({
  label,
  value,
  inverse = false,
  percentage = false,
}: {
  label: string;
  value: number;
  inverse?: boolean;
  percentage?: boolean;
}) {
  const normalized = percentage ? value : Math.min(1, value);
  const width = inverse ? Math.max(8, (1 - normalized) * 100) : Math.max(8, normalized * 100);
  const text = percentage ? `${Math.round(value * 100)}%` : value.toFixed(3);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-[0.18em] text-text-secondary">
        <span>{label}</span>
        <span>{text}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/6">
        <div className="h-full rounded-full bg-accent-blue" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function attentionLevelText(level: "normal" | "watch" | "urgent") {
  if (level === "urgent") return "需要立刻处理";
  if (level === "watch") return "建议优先关注";
  return "状态平稳";
}

function attentionLevelToneClass(level: "normal" | "watch" | "urgent") {
  if (level === "urgent") return "border-accent-red/20 bg-accent-red/10 text-accent-red";
  if (level === "watch") return "border-accent-amber/20 bg-accent-amber/10 text-accent-amber";
  return "border-accent-green/20 bg-accent-green/10 text-accent-green";
}

function toneClass(tone: "neutral" | "good" | "warning" | "urgent") {
  if (tone === "good") return "border-accent-green/20 bg-accent-green/10 text-accent-green";
  if (tone === "warning") return "border-accent-amber/20 bg-accent-amber/10 text-accent-amber";
  if (tone === "urgent") return "border-accent-red/20 bg-accent-red/10 text-accent-red";
  return "border-white/6 bg-black/10 text-text-secondary";
}
