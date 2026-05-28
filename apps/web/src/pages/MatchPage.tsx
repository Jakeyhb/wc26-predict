import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { useParams } from "react-router-dom";
import { ProbabilityArc } from "../components/ProbabilityArc";
import { SignalList } from "../components/SignalList";
import { TimelineRail } from "../components/TimelineRail";
import { EmptyState } from "../components/EmptyState";
import { FeedbackModal } from "../components/FeedbackModal";
import { Skeleton } from "../components/Skeleton";
import { fetchEvidence, fetchLatestPrediction, fetchMatch, fetchPredictionHistory, generateAnalysis } from "../lib/api";

export function MatchPage() {
  const { matchId = "" } = useParams();
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [articleExpanded, setArticleExpanded] = useState(true);
  const [analysisContext, setAnalysisContext] = useState("");
  const [analysisResult, setAnalysisResult] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [predictionTriggering, setPredictionTriggering] = useState(false);
  const [predictionJobId, setPredictionJobId] = useState<string | null>(null);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const matchQuery = useQuery({
    queryKey: ["match", matchId, "detail"],
    queryFn: () => fetchMatch(matchId),
  });
  const latestQuery = useQuery({
    queryKey: ["prediction", matchId, "latest"],
    queryFn: () => fetchLatestPrediction(matchId),
    refetchInterval: (query) => (query.state.data?.article_status === "generating" ? 30_000 : false),
  });
  const historyQuery = useQuery({
    queryKey: ["prediction", matchId, "history"],
    queryFn: () => fetchPredictionHistory(matchId),
  });
  const evidenceQuery = useQuery({
    queryKey: ["match", matchId, "evidence"],
    queryFn: () => fetchEvidence(matchId),
  });

  const match = matchQuery.data;
  const latest = latestQuery.data;
  const history = historyQuery.data ?? [];
  const snapshot = isRecord(latest?.input_feature_snapshot) ? latest.input_feature_snapshot : null;
  const calibrationStats = snapshot && isRecord(snapshot.calibration_stats) ? snapshot.calibration_stats : null;
  const enhancerSnapshot = snapshot && isRecord(snapshot.enhancer) ? snapshot.enhancer : null;
  const featureSnapshot = enhancerSnapshot && isRecord(enhancerSnapshot.feature_snapshot) ? enhancerSnapshot.feature_snapshot : null;
  const matchContext = snapshot && isRecord(snapshot.match_context) ? snapshot.match_context : null;
  const weather = matchContext && isRecord(matchContext.weather) ? matchContext.weather : null;
  const isClubMatch = match?.competition_type === "club";
  const factorCards = latest
    ? [
        {
          label: "模型版本",
          value: latest.model_version,
          tone: "text-white",
        },
        {
          label: "置信度",
          value: `${Math.round(latest.confidence_score * 100)}%`,
          tone: "text-accent-blue",
        },
        {
          label: "校准",
          value: snapshot?.calibration_applied ? "已启用" : "未启用",
          tone: snapshot?.calibration_applied ? "text-accent-green" : "text-text-secondary",
        },
        {
          label: "训练样本",
          value: typeof snapshot?.training_rows === "number" ? String(snapshot.training_rows) : "—",
          tone: "text-white",
        },
      ]
    : [];
  const driverRows = [
    {
      label: "近期 xG 优势",
      value: formatSignedMetric(readNumber(featureSnapshot, "recent_xg_gap"), 2),
    },
    {
      label: "近期积分优势",
      value: formatSignedMetric(readNumber(featureSnapshot, "recent_points_gap"), 2),
    },
    {
      label: "休息天差",
      value: formatSignedMetric(readNumber(featureSnapshot, "rest_day_diff"), 0, "天"),
    },
    {
      label: "天气",
      value: [
        typeof weather?.weather_description === "string" ? weather.weather_description : null,
        typeof weather?.temperature_c === "number" ? `${weather.temperature_c.toFixed(1)}°C` : null,
      ]
        .filter(Boolean)
        .join(" · ") || "—",
    },
  ];

  useEffect(() => {
    if (!match) return;
    const previousTitle = document.title;
    document.title = `${match.home_team.name_zh ?? match.home_team.name} vs ${match.away_team.name_zh ?? match.away_team.name} - WC26预测`;
    return () => {
      document.title = previousTitle;
    };
  }, [match]);

  useEffect(() => {
    setArticleExpanded(match?.competition_type !== "club");
  }, [match?.competition_type, matchId]);

  // Poll prediction status after triggering
  useEffect(() => {
    if (!predictionJobId || !predictionTriggering) return;
    const timer = setInterval(async () => {
      try {
        const resp = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? ""}/api/predictions/${matchId}/status`);
        const data = await resp.json();
        if (data.status === "completed") {
          setPredictionTriggering(false);
          latestQuery.refetch();
          matchQuery.refetch();
        } else if (data.status === "failed") {
          setPredictionTriggering(false);
          setPredictionError("预测生成失败，请重试");
        }
      } catch { /* keep polling */ }
    }, 5000);
    return () => clearInterval(timer);
  }, [predictionJobId, predictionTriggering, matchId]);

  const handleTriggerPrediction = async () => {
    setPredictionTriggering(true);
    setPredictionError(null);
    try {
      const resp = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? ""}/api/predictions/${matchId}/trigger-public`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_type: "t_minus_24h" }),
      });
      const data = await resp.json();
      setPredictionJobId(data.prediction_id);
    } catch (err) {
      setPredictionTriggering(false);
      setPredictionError(err instanceof Error ? err.message : "触发失败");
    }
  };

  if (matchQuery.isLoading || latestQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40 rounded-[32px]" />
        <Skeleton className="h-64 rounded-[32px]" />
        <Skeleton className="h-72 rounded-[32px]" />
      </div>
    );
  }

  if (!match) {
    return <EmptyState title="比赛未找到" description="该比赛不存在或已被移除。" />;
  }

  if (!latest) {
    return (
      <div className="mx-auto max-w-xl space-y-6 py-8">
        <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6 text-center">
          <div className="text-xs uppercase tracking-[0.24em] text-text-muted">{match.competition}</div>
          <div className="mt-3 font-display text-3xl text-white">
            {match.home_team.name} vs {match.away_team.name}
          </div>
          <div className="mt-2 text-sm text-text-secondary">
            {format(new Date(match.match_date), "MM/dd HH:mm")} · {match.stage}
          </div>
        </section>

        {predictionTriggering ? (
          <section className="rounded-[32px] border border-accent-blue/20 bg-accent-blue/5 px-5 py-10 text-center">
            <svg className="mx-auto h-16 w-16 animate-[spin_3s_linear_infinite]" viewBox="0 0 64 64">
              <circle cx="32" cy="32" r="28" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
              <circle cx="32" cy="32" r="28" fill="none" stroke="var(--accent-blue)" strokeWidth="4"
                strokeDasharray="60 200" strokeLinecap="round" />
            </svg>
            <div className="mt-5 font-display text-lg text-white">正在生成实时预测...</div>
            <div className="mt-2 text-sm text-text-secondary">
              系统正在基于最新赔率、天气和训练数据运行三层预测引擎
            </div>
            <div className="mt-1 text-xs text-text-muted">预计 30-90 秒</div>
          </section>
        ) : predictionError ? (
          <section className="rounded-[32px] border border-accent-red/30 bg-accent-red/5 px-5 py-10 text-center">
            <div className="text-sm text-accent-red">{predictionError}</div>
            <button onClick={handleTriggerPrediction} className="mt-4 rounded-full bg-accent-blue px-5 py-2 text-sm text-white hover:opacity-80">点击重试</button>
          </section>
        ) : (
          <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-10 text-center">
            <div className="font-display text-xl text-white">暂无预测数据</div>
            <div className="mt-3 text-sm text-text-secondary">
              点击下方按钮，系统将获取最新赔率、天气和赛事数据，<br />
              通过三层预测引擎实时生成预测。
            </div>
            <button
              onClick={handleTriggerPrediction}
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-accent-blue px-6 py-3 text-sm font-medium text-white transition hover:opacity-80"
            >
              🔄 触发实时预测
            </button>
            <div className="mt-2 text-xs text-text-muted">预计耗时 30-90 秒</div>
          </section>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">{match.competition}</div>
        <div className="mt-3 font-display text-[34px] leading-none">
          {match.home_team.name_zh ?? match.home_team.name} vs {match.away_team.name_zh ?? match.away_team.name}
        </div>
        <div className="mt-3 text-sm text-text-secondary">
          {format(new Date(match.match_date), "MM/dd HH:mm")} · {match.stage}
        </div>
        <div className="mt-4 flex flex-wrap gap-2 text-xs text-text-muted">
          <span className="rounded-full bg-white/5 px-3 py-2">更新于 {format(new Date(latest.created_at), "MM/dd HH:mm")}</span>
          <span className="rounded-full bg-white/5 px-3 py-2">{latest.model_version}</span>
        </div>
        <div className="mt-5">
          <TimelineRail history={history} active={latest.run_type} />
        </div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
          <ProbabilityArc value={latest.home_win_prob} color="var(--accent-blue)" label={match.home_team.fifa_code ?? "HOME"} />
          <ProbabilityArc value={latest.draw_prob} color="rgba(255,255,255,0.55)" label="DRAW" />
          <ProbabilityArc value={latest.away_win_prob} color="var(--accent-green)" label={match.away_team.fifa_code ?? "AWAY"} />
        </div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Top 3 Scores</div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {latest.top3_scores.map((item, index) => (
            <div
              key={item.score}
              className={`rounded-[28px] border px-4 py-5 ${index === 0 ? "border-amber-300/70 bg-amber-300/8" : "border-white/8 bg-white/4"}`}
            >
              <div className="font-display text-3xl">{item.score}</div>
              <div className="mt-2 text-sm text-text-secondary">{Math.round(item.prob * 100)}%</div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Expected Goals</div>
        <div className="mt-5 space-y-5">
          <XgBar label={match.home_team.name_zh ?? match.home_team.name} value={latest.home_xg} color="var(--accent-blue)" />
          <XgBar label={match.away_team.name_zh ?? match.away_team.name} value={latest.away_xg} color="var(--accent-green)" />
        </div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Signals</div>
        <div className="mt-4">
          <SignalList signals={latest.approved_signals} />
        </div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Risk Tags</div>
        <div className="mt-4 flex flex-wrap gap-2">
          {latest.risk_tags.map((tag) => (
            <span key={tag} className="rounded-full bg-accent-amber/15 px-3 py-2 text-sm text-accent-amber">
              {tag}
            </span>
          ))}
        </div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Model Snapshot</div>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          {factorCards.map((item) => (
            <div key={item.label} className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-text-muted">{item.label}</div>
              <div className={`mt-3 font-display text-2xl ${item.tone}`}>{item.value}</div>
            </div>
          ))}
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {driverRows.map((item) => (
            <div key={item.label} className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
              <div className="text-xs uppercase tracking-[0.18em] text-text-muted">{item.label}</div>
              <div className="mt-2 text-sm text-text-primary">{item.value}</div>
            </div>
          ))}
        </div>
        <div className="mt-5 rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-text-secondary">
          <div>校准样本：{typeof calibrationStats?.training_samples === "number" ? calibrationStats.training_samples : "—"}</div>
          <div className="mt-2">
            估算 ECE：
            {typeof calibrationStats?.expected_calibration_error === "number"
              ? ` ${calibrationStats.expected_calibration_error.toFixed(3)}`
              : " —"}
          </div>
          <div className="mt-2">
            关键输入：{typeof enhancerSnapshot?.algorithm === "string" ? enhancerSnapshot.algorithm : "Dixon-Coles baseline"}
          </div>
        </div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">证据来源</div>
        <div className="mt-4 space-y-3">
          {evidenceQuery.isLoading ? (
            <div className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-text-secondary">
              正在检索原始报道证据...
            </div>
          ) : null}
          {!evidenceQuery.isLoading && (evidenceQuery.data?.evidence_items ?? []).length === 0 ? (
            <div className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-text-secondary">
              暂无可展示的证据链条目
            </div>
          ) : null}
          {(evidenceQuery.data?.evidence_items ?? []).map((item) => (
            <a
              key={item.id}
              href={item.source_url}
              target="_blank"
              rel="noreferrer"
              className="block rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 hover:border-white/20"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-text-muted">{item.article_title}</div>
                  <div className="text-sm text-text-primary">{item.evidence_snippet}</div>
                  {item.signal_summary ? (
                    <div className="mt-2 text-xs text-accent-blue">关联信号：{item.signal_summary}</div>
                  ) : null}
                  <div className="mt-2 text-xs text-text-muted">
                    {item.source_name ?? "未知来源"} · {item.published_at ? format(new Date(item.published_at), "MM/dd HH:mm") : "时间未知"}
                  </div>
                </div>
                <div className="shrink-0 text-xs text-accent-green">{Math.round(item.relevance_score * 100)}%相关</div>
              </div>
            </a>
          ))}
        </div>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">AI 深度分析</div>
        <p className="mt-2 text-sm text-text-secondary">
          手动输入补充情报（伤停、新闻、阵容变动等），让 AI 结合模型预测与近期数据生成深度分析报告。
        </p>
        <textarea
          className="mt-3 w-full rounded-[20px] border border-white/8 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-text-muted focus:border-accent-blue focus:outline-none"
          rows={2}
          placeholder='例如：主队主力门将因伤缺席；客队刚刚经历了长途飞行...'
          value={analysisContext}
          onChange={(e) => setAnalysisContext(e.target.value)}
        />
        <button
          className="mt-3 inline-flex items-center gap-2 rounded-full bg-accent-blue px-5 py-2.5 text-sm font-medium text-white transition hover:opacity-80 disabled:opacity-50"
          disabled={analysisLoading}
          onClick={async () => {
            setAnalysisLoading(true);
            setAnalysisError(null);
            setAnalysisResult(null);
            try {
              const result = await generateAnalysis(matchId, analysisContext);
              setAnalysisResult(result.analysis);
            } catch (err) {
              setAnalysisError(err instanceof Error ? err.message : "生成分析失败");
            } finally {
              setAnalysisLoading(false);
            }
          }}
        >
          {analysisLoading ? "AI 正在分析中..." : "生成深度分析"}
        </button>
        {analysisLoading ? (
          <div className="mt-4 flex items-center gap-3 rounded-[24px] border border-accent-blue/30 bg-accent-blue/5 px-4 py-5">
            <span className="inline-flex h-3 w-3 animate-pulse rounded-full bg-accent-blue" />
            <span className="text-sm text-text-secondary">AI 正在分析比赛数据与情报，预计 10-30 秒...</span>
          </div>
        ) : null}
        {analysisError ? (
          <div className="mt-4 rounded-[24px] border border-accent-red/30 bg-accent-red/5 px-4 py-4 text-sm text-accent-red">
            {analysisError}
          </div>
        ) : null}
        {analysisResult ? (
          <div className="mt-4 rounded-[24px] border border-accent-green/20 bg-accent-green/5 px-5 py-5">
            <div className="text-xs uppercase tracking-[0.18em] text-accent-green">分析报告</div>
            <div className="mt-4 whitespace-pre-line text-sm leading-7 text-text-secondary">{analysisResult}</div>
          </div>
        ) : null}
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Supplementary Analysis</div>
          {isClubMatch ? (
            <button
              className="rounded-full border border-white/8 px-3 py-1 text-xs text-text-secondary transition hover:text-white"
              onClick={() => setArticleExpanded((value) => !value)}
            >
              {articleExpanded ? "折叠" : "展开"}
            </button>
          ) : null}
        </div>
        {isClubMatch && !articleExpanded ? (
          <p className="mt-4 text-sm leading-7 text-text-secondary">
            {latest.article_status === "unavailable" ? "联赛比赛分析文章暂不提供。" : "联赛比赛默认展示概率、因子解释和证据链，补充文章已折叠。"}
          </p>
        ) : null}
        {(!isClubMatch || articleExpanded) && latest.article_status === "ready" ? (
          <>
            <div className="mt-4 font-display text-2xl">{latest.article_title}</div>
            <p className="mt-4 whitespace-pre-line text-sm leading-7 text-text-secondary">{latest.article_body}</p>
          </>
        ) : null}
        {(!isClubMatch || articleExpanded) && latest.article_status === "generating" ? (
          <div className="mt-4 rounded-[24px] border border-white/8 bg-white/4 px-4 py-5">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-3 w-3 animate-pulse rounded-full bg-accent-blue" />
              <span className="text-sm text-text-secondary">AI 正在生成补充分析，通常需要 1-2 分钟...</span>
            </div>
          </div>
        ) : null}
        {(!isClubMatch || articleExpanded) && latest.article_status === "unavailable" ? (
          <p className="mt-4 text-sm leading-7 text-text-secondary">
            {isClubMatch ? "联赛比赛分析文章暂不提供。" : "当前版本以概率、证据链和因子解释为主，暂无补充分析正文。"}
          </p>
        ) : null}
        <button
          className="mt-4 text-sm text-text-secondary transition hover:text-white"
          onClick={() => setFeedbackOpen(true)}
        >
          发现错误或问题？点击反馈
        </button>
      </section>

      <section className="rounded-[32px] border border-white/8 bg-bg-card/75 px-5 py-6">
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">History</div>
        <div className="mt-4 space-y-3">
          {history.map((item) => (
            <div key={item.id} className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
              <div className="flex items-center justify-between gap-4">
                <div className="font-display text-xl">{item.run_type}</div>
                <div className="text-xs text-text-secondary">{format(new Date(item.created_at), "MM/dd HH:mm")}</div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3 text-sm text-text-secondary">
                <div>主胜 {Math.round(item.home_win_prob * 100)}%</div>
                <div>平局 {Math.round(item.draw_prob * 100)}%</div>
                <div>客胜 {Math.round(item.away_win_prob * 100)}%</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {feedbackOpen ? (
        <FeedbackModal
          matchId={match.id}
          articleTitle={latest.article_title}
          onClose={() => setFeedbackOpen(false)}
        />
      ) : null}
    </div>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function readNumber(record: Record<string, unknown> | null, key: string): number | null {
  if (!record) return null;
  const value = record[key];
  return typeof value === "number" ? value : null;
}

function formatSignedMetric(value: number | null, digits: number, suffix = ""): string {
  if (value === null || Number.isNaN(value)) return "—";
  const normalized = digits === 0 ? Math.round(value) : Number(value.toFixed(digits));
  const sign = normalized > 0 ? "+" : "";
  return `${sign}${normalized}${suffix}`;
}

function XgBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span>{label}</span>
        <span>{value.toFixed(2)}</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-white/6">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.min(100, value * 35)}%`,
            background: color,
            transition: "width 0.8s ease-out",
          }}
        />
      </div>
    </div>
  );
}
