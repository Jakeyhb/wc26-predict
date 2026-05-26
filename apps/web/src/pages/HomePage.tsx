import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { MatchCard } from "../components/MatchCard";
import { Skeleton } from "../components/Skeleton";
import { fetchScheduleGroups, fetchUpcomingMatches } from "../lib/api";
import type { MatchCard as MatchCardType } from "../lib/types";

const WORLD_CUP_START = new Date("2026-06-11T00:00:00Z");

export function HomePage() {
  const now = new Date();
  const worldCupStarted = now >= WORLD_CUP_START;
  const countdownDays = Math.max(0, Math.ceil((WORLD_CUP_START.getTime() - now.getTime()) / (24 * 60 * 60 * 1000)));

  const clubHighlightsQuery = useQuery({
    queryKey: ["matches", "upcoming", "club"],
    queryFn: () => fetchUpcomingMatches({ competitionType: "club" }),
    enabled: !worldCupStarted,
  });
  const worldCupPreviewQuery = useQuery({
    queryKey: ["matches", "world-cup-preview"],
    queryFn: () =>
      fetchScheduleGroups({
        competition: "FIFA World Cup 2026",
        competitionType: "national",
        startDate: "2026-06-11T00:00:00Z",
        endDate: "2026-06-18T23:59:59Z",
        page: 1,
        pageSize: 6,
      }),
    enabled: !worldCupStarted,
  });
  const worldCupLiveQuery = useQuery({
    queryKey: ["matches", "upcoming", "world-cup"],
    queryFn: () => fetchUpcomingMatches({ competition: "FIFA World Cup 2026", competitionType: "national" }),
    enabled: worldCupStarted,
  });

  const clubHighlights = (clubHighlightsQuery.data ?? []).filter((item) => item.latest_prediction).slice(0, 6);
  const worldCupPreviewMatches = (worldCupPreviewQuery.data?.groups ?? []).flatMap((group) => group.matches).slice(0, 6);
  const liveWorldCupMatches = worldCupLiveQuery.data ?? [];

  return (
    <div className="space-y-8">
      <section className="rounded-[36px] border border-white/8 bg-aurora px-6 py-8 shadow-hero">
        <div className="max-w-2xl">
          <div className="text-xs uppercase tracking-[0.3em] text-text-secondary">2026 World Cup Desk</div>
          <h1 className="mt-3 font-display text-[42px] leading-none text-white">预测准确率优先，文章降级处理</h1>
          <p className="mt-4 text-sm leading-7 text-text-secondary">
            当前主线聚焦概率可信度、xG、证据链和赛后复盘。世界杯开赛前，先用五大联赛和欧冠持续验证模型。
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link to="/schedule" className="rounded-full bg-white px-4 py-3 text-sm font-medium text-black">
              查看赛程
            </Link>
            <Link to="/stats" className="rounded-full border border-white/10 px-4 py-3 text-sm text-white">
              查看准确率
            </Link>
          </div>
        </div>
      </section>

      {!worldCupStarted ? (
        <section className="rounded-[32px] border border-sky-300/20 bg-sky-300/8 px-5 py-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Countdown</div>
              <div className="mt-2 font-display text-3xl">距 2026 世界杯开幕还有 {countdownDays} 天</div>
              <div className="mt-2 text-sm text-text-secondary">现在预测五大联赛比赛，验证模型准确性。</div>
            </div>
            <Link to="/stats" className="rounded-full bg-white px-4 py-3 text-sm font-medium text-black">
              查看准确率
            </Link>
          </div>
        </section>
      ) : null}

      {worldCupStarted ? (
        <MatchesSection
          title="世界杯进行中"
          eyebrow="World Cup Now"
          matches={liveWorldCupMatches}
          isLoading={worldCupLiveQuery.isLoading}
        />
      ) : (
        <>
          <MatchesSection
            title="今日联赛焦点"
            eyebrow="League Highlights"
            matches={clubHighlights}
            isLoading={clubHighlightsQuery.isLoading}
            emptyMessage="最近 14 天内暂无已生成预测的联赛比赛。"
          />
          <MatchesSection
            title="世界杯分组赛预告"
            eyebrow="World Cup Preview"
            matches={worldCupPreviewMatches}
            isLoading={worldCupPreviewQuery.isLoading}
            emptyMessage="暂未加载到世界杯赛程预告。"
          />
        </>
      )}
    </div>
  );
}

function MatchesSection({
  title,
  eyebrow,
  matches,
  isLoading,
  emptyMessage,
}: {
  title: string;
  eyebrow: string;
  matches: MatchCardType[];
  isLoading: boolean;
  emptyMessage?: string;
}) {
  return (
    <section className="space-y-4">
      <div>
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">{eyebrow}</div>
        <div className="mt-2 font-display text-2xl">{title}</div>
      </div>
      <div className="space-y-4">
        {isLoading ? Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-40 rounded-[32px]" />) : null}
        {!isLoading && matches.length === 0 ? (
          <div className="rounded-[28px] border border-white/8 bg-bg-card/75 px-5 py-5 text-sm text-text-secondary">{emptyMessage ?? "暂无比赛数据。"}</div>
        ) : null}
        {!isLoading ? matches.map((match) => <MatchCard key={match.id} match={match} />) : null}
      </div>
    </section>
  );
}
