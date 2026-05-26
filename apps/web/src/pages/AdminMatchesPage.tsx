import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { createManualMatch, fetchSchedule, updateMatchResult } from "../lib/api";
import type { ManualMatchCreateRequest } from "../lib/types";

const TOURNAMENT_START = "2026-06-01T00:00:00Z";
const TOURNAMENT_END = "2026-07-31T23:59:59Z";

const initialForm: ManualMatchCreateRequest = {
  home_team_name: "",
  away_team_name: "",
  match_date: "2026-06-11T18:00:00Z",
  competition: "FIFA World Cup 2026",
  stage: "Group Stage",
  venue: "TBD",
  is_neutral_venue: true,
  competition_weight: 1.0,
};

export function AdminMatchesPage({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ManualMatchCreateRequest>(initialForm);
  const [scoreDrafts, setScoreDrafts] = useState<Record<string, { home: string; away: string }>>({});
  const [createdMatchId, setCreatedMatchId] = useState<string | null>(null);

  const scheduleQuery = useQuery({
    queryKey: ["admin", "matches", "schedule"],
    queryFn: () =>
      fetchSchedule({
        startDate: TOURNAMENT_START,
        endDate: TOURNAMENT_END,
        pageSize: 200,
      }),
  });

  const createMutation = useMutation({
    mutationFn: (payload: ManualMatchCreateRequest) => createManualMatch(token, payload),
    onSuccess: (result) => {
      setCreatedMatchId(result.match_id);
      setForm(initialForm);
      queryClient.invalidateQueries({ queryKey: ["admin", "matches", "schedule"] });
      queryClient.invalidateQueries({ queryKey: ["matches", "schedule"] });
    },
  });

  const resultMutation = useMutation({
    mutationFn: ({ matchId, home, away }: { matchId: string; home: number; away: number }) =>
      updateMatchResult(token, matchId, { home_goals: home, away_goals: away }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "matches", "schedule"] });
      queryClient.invalidateQueries({ queryKey: ["matches", "schedule"] });
    },
  });

  const schedule = useMemo(() => scheduleQuery.data ?? [], [scheduleQuery.data]);

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Match Desk</div>
        <div className="mt-2 font-display text-3xl">比赛维护</div>
      </div>

      <section className="rounded-[28px] border border-border bg-bg-card/80 p-5">
        <div className="font-display text-xl">手动新增比赛</div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <Field label="主队" value={form.home_team_name} onChange={(value) => setForm((current) => ({ ...current, home_team_name: value }))} />
          <Field label="客队" value={form.away_team_name} onChange={(value) => setForm((current) => ({ ...current, away_team_name: value }))} />
          <Field label="比赛时间 (ISO)" value={form.match_date} onChange={(value) => setForm((current) => ({ ...current, match_date: value }))} />
          <Field label="赛事" value={form.competition} onChange={(value) => setForm((current) => ({ ...current, competition: value }))} />
          <Field label="阶段" value={form.stage ?? ""} onChange={(value) => setForm((current) => ({ ...current, stage: value }))} />
          <Field label="场馆" value={form.venue ?? ""} onChange={(value) => setForm((current) => ({ ...current, venue: value }))} />
          <Field
            label="赛事权重"
            value={String(form.competition_weight)}
            onChange={(value) => setForm((current) => ({ ...current, competition_weight: Number(value || "1") }))}
          />
          <label className="space-y-2 text-sm">
            <span className="text-text-secondary">中立场</span>
            <select
              className="w-full rounded-2xl border border-border bg-black/20 px-4 py-3 outline-none"
              value={String(form.is_neutral_venue)}
              onChange={(event) =>
                setForm((current) => ({ ...current, is_neutral_venue: event.target.value === "true" }))
              }
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </label>
        </div>
        <button
          className="mt-4 rounded-full bg-white px-4 py-3 text-sm font-medium text-black disabled:opacity-50"
          disabled={createMutation.isPending || !form.home_team_name || !form.away_team_name}
          onClick={() => createMutation.mutate(form)}
        >
          {createMutation.isPending ? "创建中..." : "创建比赛"}
        </button>
        {createdMatchId ? (
          <div className="mt-4 rounded-2xl border border-accent-green/20 bg-accent-green/10 px-4 py-4 text-sm text-accent-green">
            已创建比赛：{createdMatchId}
          </div>
        ) : null}
      </section>

      <section className="space-y-3">
        {schedule.map((match) => {
          const draft = scoreDrafts[match.id] ?? { home: "", away: "" };
          return (
            <div key={match.id} className="rounded-[28px] border border-border bg-bg-card/80 p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="font-medium">
                    {match.home_team.name_zh ?? match.home_team.name} vs {match.away_team.name_zh ?? match.away_team.name}
                  </div>
                  <div className="mt-2 text-sm text-text-secondary">
                    {format(new Date(match.match_date), "MM/dd HH:mm")} · {match.stage ?? "—"} · {match.status}
                  </div>
                  <div className="mt-1 text-xs text-text-muted">{match.competition}</div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <ScoreInput
                    value={draft.home}
                    placeholder="主"
                    onChange={(value) =>
                      setScoreDrafts((current) => ({ ...current, [match.id]: { ...draft, home: value } }))
                    }
                  />
                  <span className="text-text-secondary">:</span>
                  <ScoreInput
                    value={draft.away}
                    placeholder="客"
                    onChange={(value) =>
                      setScoreDrafts((current) => ({ ...current, [match.id]: { ...draft, away: value } }))
                    }
                  />
                  <button
                    className="rounded-full bg-white/10 px-4 py-2 text-sm text-white disabled:opacity-50"
                    disabled={resultMutation.isPending || draft.home === "" || draft.away === ""}
                    onClick={() =>
                      resultMutation.mutate({
                        matchId: match.id,
                        home: Number(draft.home),
                        away: Number(draft.away),
                      })
                    }
                  >
                    {resultMutation.isPending ? "保存中..." : "录入比分"}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
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

function ScoreInput({
  value,
  placeholder,
  onChange,
}: {
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) {
  return (
    <input
      className="w-16 rounded-2xl border border-border bg-black/20 px-3 py-2 text-center outline-none"
      inputMode="numeric"
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value.replace(/[^\d]/g, "").slice(0, 2))}
    />
  );
}
