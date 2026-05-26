import { Link } from "react-router-dom";
import { format } from "date-fns";
import type { MatchCard as MatchCardType } from "../lib/types";

function flagEmoji(code?: string | null) {
  if (!code || code.length !== 3) return "⚽";
  const twoLetter = code.slice(0, 2).toUpperCase();
  return String.fromCodePoint(...[...twoLetter].map((char) => 127397 + char.charCodeAt(0)));
}

export function MatchCard({ match }: { match: MatchCardType }) {
  const prediction = match.latest_prediction;
  const tag = competitionTag(match.competition_code, match.competition_name_zh ?? match.competition);
  return (
    <Link
      to={`/match/${match.id}`}
      className="group block rounded-[32px] border border-border bg-bg-card/75 p-5 transition hover:border-white/25 hover:bg-bg-elevated/80"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-[11px] uppercase tracking-[0.18em] ${tag.className}`}>{tag.label}</span>
            <span className="text-xs uppercase tracking-[0.24em] text-text-muted">{match.competition}</span>
          </div>
          <div className="mt-2 font-display text-xl text-text-primary">
            {flagEmoji(match.home_team.fifa_code)} {match.home_team.name_zh ?? match.home_team.name}
            <span className="mx-2 text-text-muted">vs</span>
            {flagEmoji(match.away_team.fifa_code)} {match.away_team.name_zh ?? match.away_team.name}
          </div>
          <div className="mt-2 text-sm text-text-secondary">
            {format(new Date(match.match_date), "MM/dd HH:mm")} · {match.stage ?? "待定"}
          </div>
        </div>
        <div className="rounded-full border border-white/10 px-3 py-1 text-xs text-text-secondary">
          {prediction ? `置信度 ${Math.round((prediction.confidence_score ?? 0) * 100)}` : "待预测"}
        </div>
      </div>
      <div className="mt-5 space-y-2">
        {prediction ? (
          <>
            <ProbabilityStrip label={match.home_team.fifa_code ?? "HOME"} value={prediction.home_win_prob ?? 0} color="var(--accent-blue)" />
            <ProbabilityStrip label="DRAW" value={prediction.draw_prob ?? 0} color="rgba(255,255,255,0.55)" />
            <ProbabilityStrip label={match.away_team.fifa_code ?? "AWAY"} value={prediction.away_win_prob ?? 0} color="var(--accent-green)" />
          </>
        ) : (
          <div className="text-sm text-text-muted">当前还没有预测快照，页面将显示空状态占位。</div>
        )}
      </div>
    </Link>
  );
}

function competitionTag(code?: string | null, fallback?: string) {
  const palette: Record<string, { label: string; className: string }> = {
    WC: { label: "世界杯", className: "bg-sky-500/15 text-sky-300" },
    PL: { label: "英超", className: "bg-fuchsia-500/15 text-fuchsia-300" },
    PD: { label: "西甲", className: "bg-rose-500/15 text-rose-300" },
    BL1: { label: "德甲", className: "bg-amber-500/15 text-amber-300" },
    SA: { label: "意甲", className: "bg-emerald-500/15 text-emerald-300" },
    FL1: { label: "法甲", className: "bg-cyan-500/15 text-cyan-300" },
    CL: { label: "欧冠", className: "bg-indigo-500/15 text-indigo-300" },
  };
  return palette[code ?? ""] ?? { label: fallback ?? "赛事", className: "bg-white/8 text-text-secondary" };
}

function ProbabilityStrip({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs uppercase tracking-[0.18em] text-text-secondary">
        <span>{label}</span>
        <span>{Math.round(value * 100)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/6">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.max(4, value * 100)}%`,
            background: color,
            transition: "width 0.8s ease-out",
          }}
        />
      </div>
    </div>
  );
}
