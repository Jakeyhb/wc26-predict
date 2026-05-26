import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchScheduleGroups } from "../lib/api";

const FILTERS = [
  { key: "all", label: "全部", params: {} },
  { key: "wc", label: "世界杯", params: { competitionType: "national" as const, competition: "FIFA World Cup 2026" } },
  { key: "pl", label: "英超", params: { competitionType: "club" as const, competition: "Premier League" } },
  { key: "pd", label: "西甲", params: { competitionType: "club" as const, competition: "Primera Division" } },
  { key: "bl1", label: "德甲", params: { competitionType: "club" as const, competition: "Bundesliga" } },
  { key: "sa", label: "意甲", params: { competitionType: "club" as const, competition: "Serie A" } },
  { key: "fl1", label: "法甲", params: { competitionType: "club" as const, competition: "Ligue 1" } },
  { key: "cl", label: "欧冠", params: { competitionType: "cup" as const, competition: "Champions League" } },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

export function SchedulePage() {
  const [filter, setFilter] = useState<FilterKey>("all");
  const [daysAhead, setDaysAhead] = useState(7);
  const [pageSize, setPageSize] = useState(20);

  const activeFilter = FILTERS.find((item) => item.key === filter) ?? FILTERS[0];
  const query = useQuery({
    queryKey: ["matches", "schedule", filter, daysAhead, pageSize],
    queryFn: () =>
      fetchScheduleGroups({
        ...activeFilter.params,
        daysAhead,
        page: 1,
        pageSize,
      }),
  });

  const groups = query.data?.groups ?? [];
  const loadedCount = useMemo(() => groups.flatMap((group) => group.matches).length, [groups]);
  const canLoadMore = (query.data?.total ?? 0) > loadedCount || daysAhead < 60;

  return (
    <div className="space-y-6">
      <section className="rounded-[36px] border border-white/8 bg-bg-card/75 px-6 py-7 shadow-hero">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Schedule Map</div>
        <div className="mt-3 font-display text-[38px] leading-none">世界杯 + 联赛双线赛程</div>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-text-secondary">
          默认只加载最近 7 天赛程。可以按赛事筛选，并通过“加载更多”逐步扩展时间窗口和条目数量。
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              className={`rounded-full px-4 py-2 text-sm transition ${
                filter === item.key ? "bg-white text-black" : "border border-white/8 bg-black/10 text-white"
              }`}
              onClick={() => {
                setFilter(item.key);
                setDaysAhead(7);
                setPageSize(20);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <div className="space-y-6">
        {groups.map((group) => (
          <section key={group.date} className="rounded-[30px] border border-white/8 bg-bg-card/70 px-5 py-5">
            <div className="text-xs uppercase tracking-[0.24em] text-text-muted">{group.date_label}</div>
            <div className="mt-4 space-y-3">
              {group.matches.map((match) => (
                <Link
                  key={match.id}
                  to={`/match/${match.id}`}
                  className={`block rounded-[24px] border px-4 py-4 transition ${
                    match.latest_prediction
                      ? "border-white/10 bg-white/4 hover:bg-white/6"
                      : "border-white/6 bg-black/10 opacity-85 hover:opacity-100"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full px-3 py-1 text-[11px] uppercase tracking-[0.18em] ${tagTone(match.competition_code)}`}>
                          {match.competition_name_zh ?? match.competition}
                        </span>
                        <span className="text-xs text-text-muted">{match.stage ?? "赛阶段待定"}</span>
                      </div>
                      <div className="mt-2 font-medium">
                        {match.home_team.name_zh ?? match.home_team.name} vs {match.away_team.name_zh ?? match.away_team.name}
                      </div>
                      <div className="mt-1 text-sm text-text-secondary">
                        {formatBeijingTime(match.match_date)} · {match.venue ?? "场馆待定"}
                      </div>
                    </div>
                    <div className="text-right text-sm text-text-secondary">
                      {match.latest_prediction ? (
                        <div className="min-w-[180px]">
                          <div className="flex h-2 overflow-hidden rounded-full bg-white/8">
                            <div
                              className="bg-[var(--accent-blue)]"
                              style={{ width: `${Math.round((match.latest_prediction.home_win_prob ?? 0) * 100)}%` }}
                            />
                            <div
                              className="bg-white/45"
                              style={{ width: `${Math.round((match.latest_prediction.draw_prob ?? 0) * 100)}%` }}
                            />
                            <div
                              className="bg-[var(--accent-green)]"
                              style={{ width: `${Math.round((match.latest_prediction.away_win_prob ?? 0) * 100)}%` }}
                            />
                          </div>
                          <div className="mt-2 text-xs">
                            主胜 {Math.round((match.latest_prediction.home_win_prob ?? 0) * 100)}% · 平局{" "}
                            {Math.round((match.latest_prediction.draw_prob ?? 0) * 100)}% · 客胜{" "}
                            {Math.round((match.latest_prediction.away_win_prob ?? 0) * 100)}%
                          </div>
                        </div>
                      ) : (
                        <span className="rounded-full border border-white/8 bg-white/5 px-3 py-1 text-xs text-text-muted">待预测</span>
                      )}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        ))}

        {!query.isLoading && groups.length === 0 ? (
          <section className="rounded-[30px] border border-white/8 bg-bg-card/70 px-5 py-6 text-sm text-text-secondary">
            当前筛选条件下暂无比赛，可尝试“加载更多”扩展时间范围。
          </section>
        ) : null}
      </div>

      {canLoadMore ? (
        <div className="flex justify-center">
          <button
            className="rounded-full border border-white/10 bg-white/5 px-5 py-3 text-sm text-white transition hover:bg-white/10"
            onClick={() => {
              if ((query.data?.total ?? 0) > loadedCount) {
                setPageSize((value) => value + 20);
                return;
              }
              setDaysAhead((value) => Math.min(60, value + 7));
              setPageSize(20);
            }}
          >
            加载更多
          </button>
        </div>
      ) : null}
    </div>
  );
}

function formatBeijingTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function tagTone(code?: string | null) {
  const palette: Record<string, string> = {
    WC: "bg-sky-500/15 text-sky-300",
    PL: "bg-fuchsia-500/15 text-fuchsia-300",
    PD: "bg-rose-500/15 text-rose-300",
    BL1: "bg-amber-500/15 text-amber-300",
    SA: "bg-emerald-500/15 text-emerald-300",
    FL1: "bg-cyan-500/15 text-cyan-300",
    CL: "bg-indigo-500/15 text-indigo-300",
  };
  return palette[code ?? ""] ?? "bg-white/8 text-text-secondary";
}
