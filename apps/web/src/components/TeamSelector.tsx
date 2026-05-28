import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { fetchTeams } from "../lib/api";
import type { TeamItem } from "../lib/types";

interface TeamSelectorProps {
  value: TeamItem | null;
  onChange: (team: TeamItem | null) => void;
  placeholder?: string;
  disabledTeam?: TeamItem | null;
}

export function TeamSelector({ value, onChange, placeholder, disabledTeam }: TeamSelectorProps) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<"all" | "national" | "club">("national");

  const teamsQuery = useQuery({
    queryKey: ["teams"],
    queryFn: fetchTeams,
    staleTime: 10 * 60_000,
  });

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    let list = teamsQuery.data ?? [];
    if (filter === "national") list = list.filter((t) => t.team_type === "national");
    if (filter === "club") list = list.filter((t) => t.team_type === "club");
    if (q) list = list.filter((t) => t.name.toLowerCase().includes(q) || (t.name_zh ?? "").includes(q));
    // Exclude already-selected opponent
    if (disabledTeam) list = list.filter((t) => t.id !== disabledTeam.id);
    return list.slice(0, 30);
  }, [teamsQuery.data, search, filter, disabledTeam]);

  // Close on blur
  useEffect(() => {
    if (!open) setSearch("");
  }, [open]);

  return (
    <div className="relative">
      {value ? (
        <div className="flex items-center justify-between rounded-[20px] border border-accent-blue/40 bg-accent-blue/10 px-4 py-3">
          <div>
            <div className="text-sm font-medium text-white">{value.name}</div>
            <div className="text-xs text-text-muted">{value.name_zh ?? (value.team_type === "national" ? "国家队" : "俱乐部")}</div>
          </div>
          <button
            onClick={() => onChange(null)}
            className="ml-2 rounded-full p-1 text-text-muted transition hover:bg-white/10 hover:text-white"
          >
            <X size={16} />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex w-full items-center gap-2 rounded-[20px] border border-white/8 bg-bg-card/75 px-4 py-3 text-left text-sm text-text-muted transition hover:border-white/20 hover:text-text-secondary"
        >
          <Search size={16} />
          {placeholder ?? "搜索球队..."}
        </button>
      )}

      {open && !value ? (
        <div className="absolute z-50 mt-2 w-full rounded-[24px] border border-white/12 bg-bg-elevated p-3 shadow-2xl">
          {/* Search input + filter tabs */}
          <input
            autoFocus
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="输入队名搜索..."
            className="mb-2 w-full rounded-[14px] border border-white/8 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-text-muted focus:border-accent-blue focus:outline-none"
          />
          <div className="mb-2 flex gap-1">
            {(["national", "club", "all"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-full px-3 py-1 text-xs transition ${
                  filter === f ? "bg-accent-blue text-white" : "bg-white/5 text-text-secondary hover:bg-white/10"
                }`}
              >
                {f === "national" ? "国家队" : f === "club" ? "俱乐部" : "全部"}
              </button>
            ))}
          </div>

          {/* Team list */}
          <div className="max-h-64 space-y-0.5 overflow-y-auto">
            {teamsQuery.isLoading ? (
              <div className="px-3 py-4 text-center text-sm text-text-muted">加载中...</div>
            ) : filtered.length === 0 ? (
              <div className="px-3 py-4 text-center text-sm text-text-muted">无匹配球队</div>
            ) : (
              filtered.map((team) => (
                <button
                  key={team.id}
                  type="button"
                  onClick={() => { onChange(team); setOpen(false); }}
                  className="flex w-full items-center gap-3 rounded-[14px] px-3 py-2 text-left transition hover:bg-white/8"
                >
                  <span className="text-lg">
                    {team.fifa_code ? getFlagEmoji(team.fifa_code) : "⚽"}
                  </span>
                  <div>
                    <div className="text-sm text-white">{team.name}</div>
                    <div className="text-xs text-text-muted">
                      {team.name_zh ?? team.team_type === "national" ? "国家队" : "俱乐部"}
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>

          {/* Close button */}
          <button
            onClick={() => setOpen(false)}
            className="mt-2 w-full rounded-[14px] py-1.5 text-xs text-text-muted transition hover:bg-white/5"
          >
            关闭
          </button>
        </div>
      ) : null}
    </div>
  );
}

function getFlagEmoji(fifaCode: string): string {
  if (fifaCode.length !== 3) return "⚽";
  const code = fifaCode.toUpperCase();
  // Regional indicator letters: 🇦 = U+1F1E6 (A), 🇿 = U+1F1FF (Z)
  const a = 0x1F1E6 + code.charCodeAt(0) - 65;
  const b = 0x1F1E6 + code.charCodeAt(1) - 65;
  return String.fromCodePoint(a, b);
}
