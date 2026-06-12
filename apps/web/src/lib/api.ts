import {
  accuracyStatsSchema,
  adminDashboardSummarySchema,
  conflictSignalGroupItemSchema,
  evidenceResponseSchema,
  feedbackRequestSchema,
  feedbackResponseSchema,
  feedbackStatusUpdateSchema,
  hermesDigestSchema,
  manualMatchCreateRequestSchema,
  manualMatchCreateResponseSchema,
  manualSignalCreateRequestSchema,
  matchCardSchema,
  matchResultUpdateRequestSchema,
  paginatedFeedbackResponseSchema,
  paginatedPendingSignalResponseSchema,
  pendingArticleItemSchema,
  predictionHistoryItemSchema,
  predictionSnapshotSchema,
  recentPredictionsResponseSchema,
  reviewSummarySchema,
  scheduleResponseSchema,
  triggerPredictionResponseSchema,
} from "@wc26/shared";
import { z } from "zod";
import {
  mockAccuracyStats,
  mockDashboard,
  mockFeedback,
  mockHermesDigest,
  mockHistory,
  mockLatestPrediction,
  mockMatches,
  mockPendingArticles,
  mockPendingSignals,
  mockRecentPredictions,
  mockReview,
  mockScheduleResponse,
} from "./mock";
import type {
  AccuracyStats,
  AdminDashboardSummary,
  ConflictSignalGroupItem,
  EvidenceResponse,
  HermesDigestResponse,
  FeedbackRequest,
  FeedbackStatusUpdate,
  ManualMatchCreateRequest,
  ManualMatchCreateResponse,
  ManualSignalCreateRequest,
  MatchCard,
  MatchResultUpdateRequest,
  PaginatedFeedbackResponse,
  PaginatedResponse,
  PendingArticleItem,
  PendingSignalItem,
  PredictionHistoryItem,
  PredictionSnapshot,
  RecentPredictionItem,
  ReviewSummary,
  RunType,
  ScheduleResponse,
  TriggerPredictionResponse,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const USE_MOCK = import.meta.env.VITE_USE_MOCK_DATA === "true" || import.meta.env.VITE_USE_MOCK === "true";
const CAN_FALLBACK_TO_MOCK = import.meta.env.DEV && !USE_MOCK;

type RequestSchema<T> = z.ZodType<T>;

export interface ScheduleQuery {
  startDate?: string;
  endDate?: string;
  stage?: string;
  daysAhead?: number;
  competitionType?: "national" | "club" | "cup";
  competition?: string;
  page?: number;
  pageSize?: number;
}

export interface RecentPredictionsQuery {
  limit?: number;
  competition?: string;
}

async function request<T>(path: string, schema: RequestSchema<T>, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const message = await safeErrorMessage(response);
    throw new Error(message ? `Request failed: ${response.status} ${message}` : `Request failed: ${response.status}`);
  }
  return schema.parse(await response.json());
}

async function withMockFallback<T>(loader: () => Promise<T>, fallback: T | (() => T | Promise<T>)): Promise<T> {
  if (USE_MOCK) {
    return typeof fallback === "function" ? await (fallback as () => T | Promise<T>)() : fallback;
  }
  try {
    return await loader();
  } catch (error) {
    if (!CAN_FALLBACK_TO_MOCK) throw error;
    console.warn("API request failed, falling back to mock data.", error);
    return typeof fallback === "function" ? await (fallback as () => T | Promise<T>)() : fallback;
  }
}

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

function buildQuery(params: Record<string, string | undefined>) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) query.set(key, value);
  });
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

async function safeErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string; message?: string };
    return payload.detail ?? payload.message ?? "";
  } catch {
    return "";
  }
}

export async function fetchUpcomingMatches(params?: {
  competitionType?: "national" | "club" | "cup";
  competition?: string;
}): Promise<MatchCard[]> {
  const query = buildQuery({
    competition_type: params?.competitionType,
    competition: params?.competition,
  });
  return withMockFallback(() => request(`/api/matches/upcoming${query}`, z.array(matchCardSchema)), mockMatches);
}

export async function fetchScheduleGroups(params?: ScheduleQuery): Promise<ScheduleResponse> {
  const query = buildQuery({
    start_date: params?.startDate,
    end_date: params?.endDate,
    stage: params?.stage,
    days_ahead: params?.daysAhead ? String(params.daysAhead) : undefined,
    competition_type: params?.competitionType,
    competition: params?.competition,
    page: params?.page ? String(params.page) : undefined,
    page_size: params?.pageSize ? String(params.pageSize) : undefined,
  });
  return withMockFallback(() => request(`/api/matches/schedule${query}`, scheduleResponseSchema), mockScheduleResponse);
}

export async function fetchSchedule(params?: ScheduleQuery): Promise<MatchCard[]> {
  const response = await fetchScheduleGroups(params);
  return response.groups.flatMap((group) => group.matches);
}

export async function fetchMatch(matchId: string): Promise<MatchCard> {
  return withMockFallback(
    () => request(`/api/matches/${matchId}`, matchCardSchema),
    () => mockScheduleResponse.groups.flatMap((group) => group.matches).find((item) => item.id === matchId) ?? mockMatches[0],
  );
}

export async function fetchLatestPrediction(matchId: string): Promise<PredictionSnapshot> {
  return withMockFallback(
    () => request(`/api/predictions/${matchId}/latest`, predictionSnapshotSchema),
    () => mockLatestPrediction[matchId] ?? Object.values(mockLatestPrediction)[0],
  );
}

export async function fetchPredictionHistory(matchId: string): Promise<PredictionHistoryItem[]> {
  return withMockFallback(
    () => request(`/api/predictions/${matchId}/history`, z.array(predictionHistoryItemSchema)),
    () => mockHistory[matchId] ?? [],
  );
}

export async function fetchReview(matchId: string): Promise<ReviewSummary> {
  return withMockFallback(() => request(`/api/matches/${matchId}/review`, reviewSummarySchema), mockReview);
}

export async function fetchEvidence(matchId: string): Promise<EvidenceResponse> {
  return withMockFallback(
    () => request(`/api/matches/${matchId}/evidence`, evidenceResponseSchema),
    { match_id: matchId, evidence_items: [], total_articles_analyzed: 0, evidence_count: 0 },
  );
}

export async function fetchAccuracyStats(): Promise<AccuracyStats> {
  return withMockFallback(() => request("/api/stats/accuracy", accuracyStatsSchema), mockAccuracyStats);
}

export async function fetchRecentPredictions(params?: RecentPredictionsQuery): Promise<RecentPredictionItem[]> {
  const query = buildQuery({
    limit: params?.limit ? String(params.limit) : undefined,
    competition: params?.competition,
  });
  const response = await withMockFallback(
    () => request(`/api/stats/recent-predictions${query}`, recentPredictionsResponseSchema),
    { items: mockRecentPredictions },
  );
  return response.items;
}

export async function fetchDashboard(token: string): Promise<AdminDashboardSummary> {
  return withMockFallback(
    () =>
      request("/api/admin/dashboard", adminDashboardSummarySchema, {
        headers: authHeaders(token),
      }),
    mockDashboard,
  );
}

export async function fetchHermesDigest(token: string): Promise<HermesDigestResponse> {
  return withMockFallback(
    () =>
      request("/api/admin/hermes/digest", hermesDigestSchema, {
        headers: authHeaders(token),
      }),
    mockHermesDigest,
  );
}

export async function fetchPendingSignals(token: string): Promise<PaginatedResponse<PendingSignalItem>> {
  return withMockFallback(
    () =>
      request("/api/admin/signals/pending", paginatedPendingSignalResponseSchema, {
        headers: authHeaders(token),
      }),
    mockPendingSignals,
  );
}

export async function fetchPendingArticles(token: string): Promise<PendingArticleItem[]> {
  return withMockFallback(
    () =>
      request("/api/admin/articles/pending", z.array(pendingArticleItemSchema), {
        headers: authHeaders(token),
      }),
    mockPendingArticles,
  );
}

export async function reviewSignal(
  token: string,
  signalId: string,
  status: "approved" | "rejected",
  reviewedBy = "admin",
) {
  return withMockFallback(
    () =>
      request(`/api/admin/signals/${signalId}/review`, z.object({ status: z.string(), detail: z.string().optional() }), {
        method: "PATCH",
        headers: authHeaders(token),
        body: JSON.stringify({ status, enters_model: status === "approved", reviewed_by: reviewedBy }),
      }),
    { status: "ok" },
  );
}

export async function createManualSignal(token: string, payload: ManualSignalCreateRequest) {
  const normalizedPayload = {
    ...payload,
    match_id: payload.match_id || undefined,
    team_name: payload.team_name || undefined,
    review_notes: payload.review_notes || undefined,
  };
  return withMockFallback(
    () =>
      request("/api/admin/signals/manual", z.object({ status: z.string(), detail: z.string().nullable().optional() }), {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(manualSignalCreateRequestSchema.parse(normalizedPayload)),
      }),
    { status: "ok", detail: "Created signal manual-mock" },
  );
}

export async function rerunPrediction(
  token: string,
  matchId: string,
  runType: RunType = "lineup_confirmed",
): Promise<TriggerPredictionResponse> {
  return withMockFallback(
    () =>
      request(`/api/admin/predictions/${matchId}/trigger`, triggerPredictionResponseSchema, {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ run_type: runType }),
      }),
    { prediction_run_id: "run-mock", status: "ok" },
  );
}

export async function publishArticle(token: string, articleId: string) {
  return withMockFallback(
    () =>
      request(`/api/admin/articles/${articleId}/publish`, z.object({ status: z.string(), detail: z.string().optional() }), {
        method: "PATCH",
        headers: authHeaders(token),
        body: JSON.stringify({}),
      }),
    { status: "ok" },
  );
}

export async function submitFeedback(payload: FeedbackRequest): Promise<void> {
  await withMockFallback(
    () =>
      request("/api/feedback", feedbackResponseSchema, {
        method: "POST",
        body: JSON.stringify(feedbackRequestSchema.parse(payload)),
      }),
    { status: "received", message: "感谢反馈，我们会认真处理" },
  );
}

export async function fetchFeedback(token: string, page = 1, pageSize = 20): Promise<PaginatedFeedbackResponse> {
  const query = buildQuery({ page: String(page), page_size: String(pageSize), status: "open" });
  return withMockFallback(
    () =>
      request(`/api/admin/feedback${query}`, paginatedFeedbackResponseSchema, {
        headers: authHeaders(token),
      }),
    mockFeedback,
  );
}

export async function updateFeedbackStatus(
  token: string,
  feedbackId: string,
  payload: FeedbackStatusUpdate = { status: "resolved" },
): Promise<{ status: string; detail?: string }> {
  return withMockFallback(
    () =>
      request(`/api/admin/feedback/${feedbackId}`, z.object({ status: z.string(), detail: z.string().optional() }), {
        method: "PATCH",
        headers: authHeaders(token),
        body: JSON.stringify(feedbackStatusUpdateSchema.parse(payload)),
      }),
    { status: "ok", detail: "Feedback updated" },
  );
}

export async function fetchSignalConflicts(token: string, matchId?: string): Promise<ConflictSignalGroupItem[]> {
  const query = buildQuery({ match_id: matchId });
  return withMockFallback(
    () =>
      request(`/api/admin/signals/conflicts${query}`, z.array(conflictSignalGroupItemSchema), {
        headers: authHeaders(token),
      }),
    [],
  );
}

export async function createManualMatch(
  token: string,
  payload: ManualMatchCreateRequest,
): Promise<ManualMatchCreateResponse> {
  return withMockFallback(
    () =>
      request("/api/admin/matches", manualMatchCreateResponseSchema, {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(manualMatchCreateRequestSchema.parse(payload)),
      }),
    { match_id: "manual-match-mock", status: "created" },
  );
}

export async function updateMatchResult(
  token: string,
  matchId: string,
  payload: MatchResultUpdateRequest,
): Promise<{ status: string; detail?: string }> {
  return withMockFallback(
    () =>
      request(`/api/admin/matches/${matchId}/result`, z.object({ status: z.string(), detail: z.string().optional() }), {
        method: "PATCH",
        headers: authHeaders(token),
        body: JSON.stringify(matchResultUpdateRequestSchema.parse(payload)),
      }),
    { status: "updated", detail: "Match result saved" },
  );
}

export interface AnalysisResponse {
  match_id: string;
  analysis: string;
  generated_at: string;
}

export async function generateAnalysis(matchId: string, extraContext = ""): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE}/api/analysis/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ match_id: matchId, extra_context: extraContext }),
  });
  if (!response.ok) {
    const message = await safeErrorMessage(response);
    throw new Error(message || "生成分析失败");
  }
  return response.json();
}
