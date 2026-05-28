import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { format } from "date-fns";
import { MatchCard } from "../components/MatchCard";
import { Skeleton } from "../components/Skeleton";
import { fetchScheduleGroups } from "../lib/api";
import type { MatchCard as MatchCardType } from "../lib/types";

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "FIFA World Cup 2026", label: "世界杯" },
  { key: "Champions League", label: "欧冠" },
  { key: "club", label: "联赛" },
] as const;

export function HomePage() {
  const [filter, setFilter] = useState<string>("all");

  const matchesQuery = useQuery({
    queryKey: ["matches", "schedule", filter],
    queryFn: () =>
      fetchScheduleGroups({
        competition: filter === "club" ? undefined : filter === "all" ? undefined : filter,
        competitionType: filter === "club" ? "club" : filter === "all" ? undefined : "national",
        daysAhead: 30,
        page: 1,
        pageSize: 50,
      }),
  });

  const allMatches = (matchesQuery.data?.groups ?? []).flatMap((g) => g.matches);

  const filtered = allMatches.filter((m) => {
    if (filter === "all") return true;
    if (filter === "club") return m.competition_type === "club";
    return m.competition === filter;
  });

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-4">
      {/* Hero */}
      <section className="text-center">
        <div className="text-xs uppercase tracking-[0.3em] text-text-muted">2026 World Cup Prediction Desk</div>
        <h1 className="mt-3 font-display text-[34px] leading-tight text-white">WC26 Predict</h1>
        <p className="mt-2 text-sm text-text-secondary">
          基于 Dixon-Coles + Elo 预测引擎，选择一场比赛获取深度分析报告。
        </p>
      </section>

      {/* Filter tabs */}
      <div className="flex gap-2 overflow-x-auto pb-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`shrink-0 rounded-full px-4 py-2 text-sm transition ${
              filter === f.key
                ? "bg-white text-black font-medium"
                : "bg-white/5 text-text-secondary hover:bg-white/10 hover:text-white"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Match list */}
      <div className="space-y-4">
        {matchesQuery.isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-[32px]" />
          ))
        ) : filtered.length === 0 ? (
          <div className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-10 text-center text-sm text-text-secondary">
            暂无符合条件的比赛
          </div>
        ) : (
          filtered.map((match) => (
            <Link key={match.id} to={`/match/${match.id}`} className="block">
              <div className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-5 transition hover:border-white/20 hover:bg-bg-card">
                {/* Match info */}
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-[0.18em] text-text-muted">
                      {match.competition} · {match.stage || ""}
                    </div>
                    <div className="mt-2 font-display text-2xl text-white">
                      {match.home_team.name} vs {match.away_team.name}
                    </div>
                    <div className="mt-1 text-sm text-text-secondary">
                      {format(new Date(match.match_date), "MM/dd HH:mm")}
                    </div>
                  </div>
                  {match.latest_prediction ? (
                    <div className="shrink-0 text-right">
                      <div className="flex items-center gap-3">
                        <ProbBadge value={match.latest_prediction.home_win_prob} color="var(--accent-blue)" />
                        <ProbBadge value={match.latest_prediction.draw_prob} color="rgba(255,255,255,0.55)" />
                        <ProbBadge value={match.latest_prediction.away_win_prob} color="var(--accent-green)" />
                      </div>
                      <div className="mt-2 text-xs text-text-muted">
                        置信度 {Math.round((match.latest_prediction.confidence_score ?? 0) * 100)}%
                      </div>
                    </div>
                  ) : (
                    <span className="shrink-0 text-xs text-text-muted">待预测</span>
                  )}
                </div>
                {/* Probability bar */}
                {match.latest_prediction ? (
                  <div className="mt-4 flex h-1.5 overflow-hidden rounded-full bg-white/8">
                    <div
                      className="h-full bg-accent-blue transition-all"
                      style={{ width: `${(match.latest_prediction.home_win_prob ?? 0) * 100}%` }}
                    />
                    <div
                      className="h-full bg-white/20 transition-all"
                      style={{ width: `${(match.latest_prediction.draw_prob ?? 0) * 100}%` }}
                    />
                    <div
                      className="h-full bg-accent-green transition-all"
                      style={{ width: `${(match.latest_prediction.away_win_prob ?? 0) * 100}%` }}
                    />
                  </div>
                ) : null}
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

function ProbBadge({ value, color }: { value: number | null | undefined; color: string }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div className="text-center">
      <div className="font-display text-lg" style={{ color }}>
        {pct}%
      </div>
    </div>
  );
}
