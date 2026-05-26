import { startTransition, useDeferredValue, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ManualSignalCreateRequest, RunType } from "../lib/types";
import {
  createManualSignal,
  fetchSignalConflicts,
  fetchPendingSignals,
  fetchUpcomingMatches,
  rerunPrediction,
  reviewSignal,
} from "../lib/api";

const SIGNAL_TYPE_OPTIONS = [
  "injury",
  "return",
  "travel",
  "weather",
  "lineup_hint",
  "coach_statement",
  "training",
  "other",
] as const;

const initialForm: ManualSignalCreateRequest = {
  source_name: "Manual Desk",
  source_url: "https://example.com/manual-signal",
  article_title: "人工录入信号",
  article_content: "",
  language: "zh",
  team_name: "",
  match_id: "",
  signal_type: "lineup_hint",
  impact_direction: "uncertain",
  confidence: 0.68,
  key_players: [],
  summary_zh: "",
  source_reliability: 0.8,
  review_notes: "",
  reviewed_by: "admin",
  enters_model: true,
};

export function AdminSignalsPage({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const [lastTriggeredRunId, setLastTriggeredRunId] = useState<string | null>(null);
  const [manualSignal, setManualSignal] = useState<ManualSignalCreateRequest>(initialForm);
  const deferredFilter = useDeferredValue(filter);

  const pendingSignalsQuery = useQuery({
    queryKey: ["admin", "signals", token],
    queryFn: () => fetchPendingSignals(token),
  });
  const conflictsQuery = useQuery({
    queryKey: ["admin", "signals", "conflicts", token],
    queryFn: () => fetchSignalConflicts(token),
  });
  const upcomingMatchesQuery = useQuery({
    queryKey: ["matches", "upcoming", "admin"],
    queryFn: () => fetchUpcomingMatches(),
  });
  const reviewMutation = useMutation({
    mutationFn: ({ signalId, status }: { signalId: string; status: "approved" | "rejected" }) =>
      reviewSignal(token, signalId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "signals", token] });
      queryClient.invalidateQueries({ queryKey: ["admin", "signals", "conflicts", token] });
    },
  });

  const manualSignalMutation = useMutation({
    mutationFn: (payload: ManualSignalCreateRequest) => createManualSignal(token, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "signals", token] });
      queryClient.invalidateQueries({ queryKey: ["admin", "signals", "conflicts", token] });
      startTransition(() => setManualSignal(initialForm));
    },
  });

  const rerunMutation = useMutation({
    mutationFn: ({ matchId, runType }: { matchId: string; runType: RunType }) => rerunPrediction(token, matchId, runType),
    onSuccess: (result) => {
      setLastTriggeredRunId(result.prediction_run_id);
      queryClient.invalidateQueries({ queryKey: ["matches", "upcoming"] });
    },
  });

  const filtered = (pendingSignalsQuery.data?.items ?? []).filter((item) => {
    const keyword = deferredFilter.trim().toLowerCase();
    if (!keyword) return true;
    return item.summary_zh.toLowerCase().includes(keyword) || item.signal_type.toLowerCase().includes(keyword);
  });
  const upcomingMatches = upcomingMatchesQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Signal Review</div>
        <div className="mt-2 font-display text-3xl">信号审核与人工 rerun</div>
      </div>

      <section className="rounded-[28px] border border-border bg-bg-card/80 p-5">
        <div className="font-display text-xl">人工新增信号</div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <Field
            label="摘要"
            value={manualSignal.summary_zh}
            onChange={(value) => setManualSignal((current) => ({ ...current, summary_zh: value }))}
          />
          <Field
            label="球队"
            value={manualSignal.team_name ?? ""}
            onChange={(value) => setManualSignal((current) => ({ ...current, team_name: value }))}
          />
          <Field
            label="来源名称"
            value={manualSignal.source_name}
            onChange={(value) => setManualSignal((current) => ({ ...current, source_name: value }))}
          />
          <Field
            label="来源链接"
            value={manualSignal.source_url}
            onChange={(value) => setManualSignal((current) => ({ ...current, source_url: value }))}
          />
          <Field
            label="文章标题"
            value={manualSignal.article_title}
            onChange={(value) => setManualSignal((current) => ({ ...current, article_title: value }))}
          />
          <label className="space-y-2 text-sm">
            <span className="text-text-secondary">关联比赛</span>
            <select
              className="w-full rounded-2xl border border-border bg-black/20 px-4 py-3 outline-none"
              value={manualSignal.match_id ?? ""}
              onChange={(event) => setManualSignal((current) => ({ ...current, match_id: event.target.value }))}
            >
              <option value="">不指定</option>
              {upcomingMatches.map((match) => (
                <option key={match.id} value={match.id}>
                  {match.home_team.name_zh ?? match.home_team.name} vs {match.away_team.name_zh ?? match.away_team.name}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2 text-sm">
            <span className="text-text-secondary">信号类型</span>
            <select
              className="w-full rounded-2xl border border-border bg-black/20 px-4 py-3 outline-none"
              value={manualSignal.signal_type}
              onChange={(event) =>
                setManualSignal((current) => ({ ...current, signal_type: event.target.value as ManualSignalCreateRequest["signal_type"] }))
              }
            >
              {SIGNAL_TYPE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2 text-sm">
            <span className="text-text-secondary">影响方向</span>
            <select
              className="w-full rounded-2xl border border-border bg-black/20 px-4 py-3 outline-none"
              value={manualSignal.impact_direction}
              onChange={(event) =>
                setManualSignal((current) => ({
                  ...current,
                  impact_direction: event.target.value as ManualSignalCreateRequest["impact_direction"],
                }))
              }
            >
              <option value="positive">positive</option>
              <option value="negative">negative</option>
              <option value="neutral">neutral</option>
              <option value="uncertain">uncertain</option>
            </select>
          </label>
          <Field
            label="置信度"
            value={String(manualSignal.confidence)}
            onChange={(value) =>
              setManualSignal((current) => ({ ...current, confidence: Number(value || "0.6"), source_reliability: current.source_reliability }))
            }
          />
          <Field
            label="来源可靠度"
            value={String(manualSignal.source_reliability)}
            onChange={(value) => setManualSignal((current) => ({ ...current, source_reliability: Number(value || "0.8") }))}
          />
        </div>
        <button
          className="mt-4 rounded-full bg-white/10 px-4 py-3 text-sm text-white"
          disabled={manualSignalMutation.isPending || !manualSignal.summary_zh}
          onClick={() => manualSignalMutation.mutate(manualSignal)}
        >
          {manualSignalMutation.isPending ? "提交中..." : "创建并进入审核流"}
        </button>
      </section>

      <section className="rounded-[28px] border border-border bg-bg-card/80 p-5">
        <div className="font-display text-xl">手动重新预测</div>
        <div className="mt-4 space-y-3">
          {upcomingMatches.map((match) => (
            <div key={match.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/6 bg-black/10 px-4 py-4">
              <div>
                <div className="font-medium">
                  {match.home_team.name_zh ?? match.home_team.name} vs {match.away_team.name_zh ?? match.away_team.name}
                </div>
                <div className="mt-1 text-sm text-text-secondary">{new Date(match.match_date).toLocaleString()}</div>
              </div>
              <div className="flex gap-2">
                <RunButton
                  label="T-24h"
                  pending={rerunMutation.isPending}
                  onClick={() => rerunMutation.mutate({ matchId: match.id, runType: "t_minus_24h" })}
                />
                <RunButton
                  label="T-3h"
                  pending={rerunMutation.isPending}
                  onClick={() => rerunMutation.mutate({ matchId: match.id, runType: "t_minus_3h" })}
                />
                <RunButton
                  label="首发后"
                  pending={rerunMutation.isPending}
                  onClick={() => rerunMutation.mutate({ matchId: match.id, runType: "lineup_confirmed" })}
                />
              </div>
            </div>
          ))}
        </div>
        {lastTriggeredRunId ? (
          <div className="mt-4 rounded-2xl border border-accent-blue/20 bg-accent-blue/10 px-4 py-4 text-sm">
            最新触发的预测 Run：{lastTriggeredRunId}
          </div>
        ) : null}
      </section>

      <section className="space-y-4">
        <input
          className="w-full rounded-2xl border border-border bg-bg-card/70 px-4 py-3 text-sm outline-none"
          placeholder="按摘要或类型过滤"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        {(conflictsQuery.data ?? []).length > 0 ? (
          <div className="rounded-[28px] border border-accent-amber/20 bg-accent-amber/8 p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs uppercase tracking-[0.24em] text-accent-amber">Conflict Groups</div>
                <div className="mt-2 font-display text-2xl">待仲裁冲突情报</div>
              </div>
              <div className="rounded-full border border-accent-amber/30 px-3 py-2 text-sm text-accent-amber">
                {(conflictsQuery.data ?? []).length} 组
              </div>
            </div>
            <div className="mt-4 space-y-3">
              {(conflictsQuery.data ?? []).map((group) => (
                <div key={group.conflict_group_id} className="rounded-[24px] border border-accent-amber/20 bg-black/10 px-4 py-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-text-muted">{group.conflict_group_id}</div>
                  <div className="mt-3 space-y-2">
                    {group.signals.map((signal) => (
                      <div key={signal.id} className="rounded-2xl border border-white/8 bg-white/4 px-3 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm text-white">{signal.summary_zh}</div>
                          <div className="text-xs text-accent-amber">
                            {signal.impact_direction} · {signal.normalized_availability ?? "unknown"}
                          </div>
                        </div>
                        <div className="mt-2 text-xs text-text-secondary">
                          {signal.source_name ?? "未知来源"}
                          {signal.player_name ? ` · ${signal.player_name}` : ""}
                          {signal.evidence_snippet ? ` · ${signal.evidence_snippet}` : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
        <div className="space-y-3">
          {filtered.map((signal) => (
            <div key={signal.id} className="rounded-[28px] border border-border bg-bg-card/80 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-medium">{signal.summary_zh}</div>
                  <div className="mt-2 text-sm text-text-secondary">
                    {signal.signal_type} · {signal.impact_direction} · 来源 {signal.source_name}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    {signal.normalized_availability ? (
                      <span className="rounded-full bg-white/8 px-2 py-1 text-text-secondary">{signal.normalized_availability}</span>
                    ) : null}
                    {signal.expected_minutes_delta !== null && signal.expected_minutes_delta !== undefined ? (
                      <span className="rounded-full bg-white/8 px-2 py-1 text-text-secondary">
                        分钟变化 {signal.expected_minutes_delta > 0 ? "+" : ""}
                        {signal.expected_minutes_delta}
                      </span>
                    ) : null}
                    {signal.contradiction_risk === "high" ? (
                      <span className="rounded-full bg-accent-amber/15 px-2 py-1 text-accent-amber">⚠️ 高冲突</span>
                    ) : null}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    className="rounded-full bg-accent-green/20 px-3 py-2 text-sm text-accent-green"
                    onClick={() => reviewMutation.mutate({ signalId: signal.id, status: "approved" })}
                  >
                    通过
                  </button>
                  <button
                    className="rounded-full bg-accent-red/20 px-3 py-2 text-sm text-accent-red"
                    onClick={() => reviewMutation.mutate({ signalId: signal.id, status: "rejected" })}
                  >
                    拒绝
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="space-y-2 text-sm">
      <span className="text-text-secondary">{label}</span>
      <input
        className="w-full rounded-2xl border border-border bg-black/20 px-4 py-3 outline-none"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function RunButton({ label, pending, onClick }: { label: string; pending: boolean; onClick: () => void }) {
  return (
    <button className="rounded-full bg-white/10 px-4 py-2 text-sm text-white" disabled={pending} onClick={onClick}>
      {pending ? "处理中..." : label}
    </button>
  );
}
