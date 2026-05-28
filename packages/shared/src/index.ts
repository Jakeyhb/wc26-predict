import { z } from "zod";

export const runTypeSchema = z.enum(["t_minus_24h", "t_minus_3h", "lineup_confirmed"]);
export const signalTypeSchema = z.enum([
  "injury",
  "return",
  "travel",
  "weather",
  "lineup_hint",
  "coach_statement",
  "training",
  "other",
]);
export const impactDirectionSchema = z.enum(["positive", "negative", "neutral", "uncertain"]);
export const reviewStatusSchema = z.enum(["pending", "approved", "rejected"]);
export const jobStatusSchema = z.enum(["queued", "running", "completed", "failed", "cancelled"]);
export const matchStatusSchema = z.enum(["scheduled", "live", "finished", "postponed", "cancelled"]);
export const articleStatusSchema = z.enum(["ready", "generating", "unavailable"]);
export const competitionTypeSchema = z.enum(["national", "club", "cup"]);
export const feedbackTypeSchema = z.enum([
  "error_in_article",
  "wrong_signal",
  "wrong_prediction",
  "missing_info",
  "other",
]);

export const teamRefSchema = z.object({
  id: z.string(),
  name: z.string(),
  name_zh: z.string().nullable().optional(),
  fifa_code: z.string().nullable().optional(),
});

export const matchCardPredictionSchema = z.object({
  latest_run_id: z.string().nullable().optional(),
  home_win_prob: z.number().nullable().optional(),
  draw_prob: z.number().nullable().optional(),
  away_win_prob: z.number().nullable().optional(),
  confidence_score: z.number().nullable().optional(),
  run_type: runTypeSchema.nullable().optional(),
});

export const matchCardSchema = z.object({
  id: z.string(),
  match_date: z.string(),
  competition: z.string(),
  competition_type: competitionTypeSchema,
  competition_code: z.string().nullable().optional(),
  competition_name_zh: z.string().nullable().optional(),
  stage: z.string().nullable().optional(),
  venue: z.string().nullable().optional(),
  status: matchStatusSchema,
  home_team: teamRefSchema,
  away_team: teamRefSchema,
  latest_prediction: matchCardPredictionSchema.nullable().optional(),
});

export const scoreProbabilitySchema = z.object({
  score: z.string(),
  prob: z.number(),
});

export const approvedSignalItemSchema = z.object({
  id: z.string(),
  signal_type: signalTypeSchema,
  impact_direction: impactDirectionSchema,
  summary_zh: z.string(),
  source_reliability: z.number(),
  confidence: z.number(),
  key_players: z.array(z.string()),
  player_name: z.string().nullable().optional(),
  claim: z.string().nullable().optional(),
  evidence_snippet: z.string().nullable().optional(),
  normalized_availability: z.string().nullable().optional(),
  expected_minutes_delta: z.number().nullable().optional(),
  effective_until: z.string().nullable().optional(),
  contradiction_risk: z.string().nullable().optional(),
  conflict_group_id: z.string().nullable().optional(),
  reviewed_at: z.string().nullable().optional(),
});

export const predictionSnapshotSchema = z.object({
  id: z.string(),
  match_id: z.string(),
  run_type: runTypeSchema,
  model_version: z.string(),
  as_of_time: z.string(),
  created_at: z.string(),
  home_win_prob: z.number(),
  draw_prob: z.number(),
  away_win_prob: z.number(),
  home_xg: z.number(),
  away_xg: z.number(),
  score_matrix: z.array(z.array(z.number())),
  top3_scores: z.array(scoreProbabilitySchema),
  confidence_score: z.number(),
  risk_tags: z.array(z.string()),
  approved_signals: z.array(approvedSignalItemSchema),
  input_feature_snapshot: z.record(z.string(), z.unknown()),
  article_title: z.string().nullable().optional(),
  article_body: z.string().nullable().optional(),
  article_status: articleStatusSchema,
});

export const predictionHistoryItemSchema = z.object({
  id: z.string(),
  run_type: runTypeSchema,
  as_of_time: z.string(),
  created_at: z.string(),
  home_win_prob: z.number(),
  draw_prob: z.number(),
  away_win_prob: z.number(),
  home_xg: z.number(),
  away_xg: z.number(),
  confidence_score: z.number(),
  risk_tags: z.array(z.string()),
});

export const reviewRunSummarySchema = z.object({
  prediction_run_id: z.string(),
  run_type: runTypeSchema,
  created_at: z.string(),
  predicted_top_score: z.string(),
  actual_score: z.string(),
  brier_score: z.number(),
  log_loss: z.number(),
  exact_score_hit: z.boolean(),
  top3_hit: z.boolean(),
});

export const reviewSignalSummarySchema = z.object({
  signal_id: z.string(),
  summary_zh: z.string(),
  signal_type: signalTypeSchema,
  verdict: z.string(),
  notes: z.string().nullable().optional(),
});

export const reviewSummarySchema = z.object({
  match_id: z.string(),
  actual_score: z.string(),
  actual_result: z.string(),
  runs: z.array(reviewRunSummarySchema),
  signal_reviews: z.array(reviewSignalSummarySchema),
});

export const pendingSignalItemSchema = z.object({
  id: z.string(),
  article_id: z.string(),
  match_id: z.string().nullable().optional(),
  team_id: z.string().nullable().optional(),
  signal_type: signalTypeSchema,
  impact_direction: impactDirectionSchema,
  confidence: z.number(),
  summary_zh: z.string(),
  source_reliability: z.number(),
  key_players: z.array(z.string()),
  player_name: z.string().nullable().optional(),
  claim: z.string().nullable().optional(),
  evidence_snippet: z.string().nullable().optional(),
  normalized_availability: z.string().nullable().optional(),
  expected_minutes_delta: z.number().nullable().optional(),
  effective_until: z.string().nullable().optional(),
  contradiction_risk: z.string().nullable().optional(),
  conflict_group_id: z.string().nullable().optional(),
  created_at: z.string(),
  article_title: z.string(),
  source_name: z.string().nullable().optional(),
});

export const conflictSignalGroupItemSchema = z.object({
  conflict_group_id: z.string(),
  signals: z.array(pendingSignalItemSchema),
});

export const pendingArticleItemSchema = z.object({
  id: z.string(),
  match_id: z.string(),
  prediction_run_id: z.string(),
  title: z.string(),
  body: z.string(),
  article_version: z.number(),
  created_at: z.string(),
});

export const adminAccuracyItemSchema = z.object({
  prediction_run_id: z.string(),
  match_id: z.string(),
  brier_score: z.number(),
  log_loss: z.number(),
  top3_hit: z.boolean(),
});

export const adminDashboardSummarySchema = z.object({
  new_articles_today: z.number(),
  pending_signals: z.number(),
  prediction_runs_today: z.number(),
  recent_accuracy: z.array(adminAccuracyItemSchema),
  recent_5_matches_avg_brier_score: z.number().nullable(),
  last_7_days_avg_brier_score: z.number().nullable(),
  total_predictions_made: z.number(),
  top3_hit_rate_overall: z.number().nullable(),
  competition_breakdown: z.record(
    z.string(),
    z.object({
      match_count: z.number(),
      prediction_count: z.number(),
    }),
  ),
  calibrator_status: z.object({
    is_fitted: z.boolean(),
    training_samples: z.number(),
    fitted_at: z.string().nullable().optional(),
    expected_calibration_error: z.number().nullable().optional(),
  }),
  beat_tasks_last_run: z.record(z.string(), z.string().nullable()),
  recent_prediction_counts_7d: z.array(
    z.object({
      competition: z.string(),
      competition_zh: z.string(),
      prediction_count: z.number(),
    }),
  ),
});

export const hermesDigestItemSchema = z.object({
  label: z.string(),
  detail: z.string(),
  tone: z.enum(["neutral", "good", "warning", "urgent"]),
});

export const hermesTaskSnapshotSchema = z.object({
  name: z.string(),
  last_run: z.string().nullable(),
  age_minutes: z.number().nullable(),
  stale: z.boolean(),
});

export const hermesDigestSchema = z.object({
  generated_at: z.string(),
  attention_level: z.enum(["normal", "watch", "urgent"]),
  summary: z.string(),
  counts: z.object({
    pending_signals: z.number(),
    conflict_groups: z.number(),
    pending_articles: z.number(),
    upcoming_matches_24h: z.number(),
    prediction_runs_today: z.number(),
  }),
  focus_items: z.array(hermesDigestItemSchema),
  watch_items: z.array(hermesDigestItemSchema),
  stale_tasks: z.array(hermesTaskSnapshotSchema),
  calibrator_status: z.object({
    is_fitted: z.boolean(),
    training_samples: z.number(),
    fitted_at: z.string().nullable().optional(),
    expected_calibration_error: z.number().nullable().optional(),
  }),
});

export const paginationSchema = z.object({
  page: z.number(),
  page_size: z.number(),
  total: z.number(),
});

export const paginatedPendingSignalResponseSchema = z.object({
  items: z.array(pendingSignalItemSchema),
  pagination: paginationSchema,
});

export const manualSignalCreateRequestSchema = z.object({
  source_name: z.string().min(1),
  source_url: z.string().url(),
  article_title: z.string().min(1),
  article_content: z.string().optional(),
  language: z.string().default("zh"),
  team_name: z.string().optional(),
  match_id: z.string().optional(),
  signal_type: signalTypeSchema,
  impact_direction: impactDirectionSchema,
  confidence: z.number().min(0).max(1),
  key_players: z.array(z.string()).default([]),
  summary_zh: z.string().min(1),
  source_reliability: z.number().min(0).max(1),
  review_notes: z.string().optional(),
  reviewed_by: z.string().optional(),
  enters_model: z.boolean().default(true),
});

export const signalReviewRequestSchema = z.object({
  status: z.enum(["approved", "rejected"]),
  enters_model: z.boolean().optional(),
  notes: z.string().optional(),
  reviewed_by: z.string().optional(),
});

export const triggerPredictionResponseSchema = z.object({
  prediction_run_id: z.string(),
  status: z.string(),
});

export const jobStatusResponseSchema = z.object({
  id: z.string(),
  job_type: z.string(),
  match_id: z.string().nullable().optional(),
  workflow_instance_id: z.string().nullable().optional(),
  queue_name: z.string().nullable().optional(),
  status: jobStatusSchema,
  attempt: z.number(),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  error_message: z.string().nullable().optional(),
  result: z.record(z.string(), z.unknown()).nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const feedbackRequestSchema = z.object({
  match_id: z.string().optional(),
  article_id: z.string().optional(),
  feedback_type: feedbackTypeSchema,
  description: z.string().min(1).max(500),
  contact: z.string().max(200).optional(),
});

export const feedbackResponseSchema = z.object({
  status: z.string(),
  message: z.string(),
});

export const feedbackItemSchema = z.object({
  id: z.string(),
  match_id: z.string().nullable().optional(),
  article_id: z.string().nullable().optional(),
  feedback_type: feedbackTypeSchema,
  description: z.string(),
  contact: z.string().nullable().optional(),
  status: z.string(),
  created_at: z.string(),
});

export const paginatedFeedbackResponseSchema = z.object({
  items: z.array(feedbackItemSchema),
  pagination: paginationSchema,
});

export const evidenceItemSchema = z.object({
  id: z.string(),
  article_title: z.string(),
  source_name: z.string().nullable().optional(),
  source_url: z.string(),
  evidence_snippet: z.string(),
  published_at: z.string().nullable().optional(),
  relevance_score: z.number(),
  signal_summary: z.string().nullable().optional(),
  used_in_article: z.boolean(),
});

export const evidenceResponseSchema = z.object({
  match_id: z.string(),
  evidence_items: z.array(evidenceItemSchema),
  total_articles_analyzed: z.number(),
  evidence_count: z.number(),
});

export const scheduleGroupSchema = z.object({
  date: z.string(),
  date_label: z.string(),
  matches: z.array(matchCardSchema),
});

export const scheduleResponseSchema = z.object({
  groups: z.array(scheduleGroupSchema),
  total: z.number(),
  total_pages: z.number(),
  current_page: z.number(),
});

export const accuracyByCompetitionItemSchema = z.object({
  competition: z.string(),
  competition_zh: z.string(),
  total: z.number(),
  brier_score: z.number().nullable(),
  top3_hit_rate: z.number().nullable(),
});

export const accuracyStatsSchema = z.object({
  overall: z.object({
    total_predictions: z.number(),
    brier_score_avg: z.number().nullable(),
    top3_hit_rate: z.number().nullable(),
    log_loss_avg: z.number().nullable(),
    last_updated: z.string().nullable().optional(),
  }),
  by_competition: z.array(accuracyByCompetitionItemSchema),
  recent_30: z.object({
    brier_score: z.number().nullable(),
    top3_hit_rate: z.number().nullable(),
    trend: z.enum(["improving", "stable", "declining"]),
  }),
  calibration_applied: z.boolean(),
  model_version: z.string(),
});

export const recentPredictionItemSchema = z.object({
  match_id: z.string(),
  match_date: z.string(),
  home_team_zh: z.string(),
  away_team_zh: z.string(),
  competition: z.string(),
  competition_zh: z.string(),
  predicted_home_win: z.number(),
  predicted_draw: z.number(),
  predicted_away_win: z.number(),
  top1_score: z.string(),
  actual_home_goals: z.number(),
  actual_away_goals: z.number(),
  result: z.enum(["home_win", "draw", "away_win"]),
  prediction_correct: z.boolean(),
  top3_hit: z.boolean(),
  brier_score: z.number(),
});

export const recentPredictionsResponseSchema = z.object({
  items: z.array(recentPredictionItemSchema),
});

export const feedbackStatusUpdateSchema = z.object({
  status: z.string(),
});

export const manualMatchCreateRequestSchema = z.object({
  home_team_name: z.string().min(1),
  away_team_name: z.string().min(1),
  match_date: z.string(),
  competition: z.string().min(1),
  stage: z.string().optional(),
  venue: z.string().optional(),
  is_neutral_venue: z.boolean().default(true),
  competition_weight: z.number().default(1),
});

export const manualMatchCreateResponseSchema = z.object({
  match_id: z.string(),
  status: z.string(),
});

export const matchResultUpdateRequestSchema = z.object({
  home_goals: z.number().int().min(0),
  away_goals: z.number().int().min(0),
});

export type RunType = z.infer<typeof runTypeSchema>;
export type SignalType = z.infer<typeof signalTypeSchema>;
export type ImpactDirection = z.infer<typeof impactDirectionSchema>;
export type ReviewStatus = z.infer<typeof reviewStatusSchema>;
export type JobStatus = z.infer<typeof jobStatusSchema>;
export type MatchStatus = z.infer<typeof matchStatusSchema>;
export type ArticleStatus = z.infer<typeof articleStatusSchema>;
export type CompetitionType = z.infer<typeof competitionTypeSchema>;
export type FeedbackType = z.infer<typeof feedbackTypeSchema>;
export type TeamRef = z.infer<typeof teamRefSchema>;
export type MatchCard = z.infer<typeof matchCardSchema>;
export type ScoreProbability = z.infer<typeof scoreProbabilitySchema>;
export type ApprovedSignalItem = z.infer<typeof approvedSignalItemSchema>;
export type PredictionSnapshot = z.infer<typeof predictionSnapshotSchema>;
export type PredictionHistoryItem = z.infer<typeof predictionHistoryItemSchema>;
export type ReviewSummary = z.infer<typeof reviewSummarySchema>;
export type PendingSignalItem = z.infer<typeof pendingSignalItemSchema>;
export type ConflictSignalGroupItem = z.infer<typeof conflictSignalGroupItemSchema>;
export type PendingArticleItem = z.infer<typeof pendingArticleItemSchema>;
export type AdminDashboardSummary = z.infer<typeof adminDashboardSummarySchema>;
export type HermesDigestItem = z.infer<typeof hermesDigestItemSchema>;
export type HermesTaskSnapshot = z.infer<typeof hermesTaskSnapshotSchema>;
export type HermesDigestResponse = z.infer<typeof hermesDigestSchema>;
export type PaginatedPendingSignals = z.infer<typeof paginatedPendingSignalResponseSchema>;
export type ManualSignalCreateRequest = z.infer<typeof manualSignalCreateRequestSchema>;
export type SignalReviewRequest = z.infer<typeof signalReviewRequestSchema>;
export type TriggerPredictionResponse = z.infer<typeof triggerPredictionResponseSchema>;
export type JobStatusResponse = z.infer<typeof jobStatusResponseSchema>;
export type FeedbackRequest = z.infer<typeof feedbackRequestSchema>;
export type FeedbackResponse = z.infer<typeof feedbackResponseSchema>;
export type FeedbackItem = z.infer<typeof feedbackItemSchema>;
export type PaginatedFeedbackResponse = z.infer<typeof paginatedFeedbackResponseSchema>;
export type EvidenceItem = z.infer<typeof evidenceItemSchema>;
export type EvidenceResponse = z.infer<typeof evidenceResponseSchema>;
export type ScheduleGroup = z.infer<typeof scheduleGroupSchema>;
export type ScheduleResponse = z.infer<typeof scheduleResponseSchema>;
export type AccuracyStats = z.infer<typeof accuracyStatsSchema>;
export type RecentPredictionItem = z.infer<typeof recentPredictionItemSchema>;
export type RecentPredictionsResponse = z.infer<typeof recentPredictionsResponseSchema>;
export type FeedbackStatusUpdate = z.infer<typeof feedbackStatusUpdateSchema>;
export type ManualMatchCreateRequest = z.infer<typeof manualMatchCreateRequestSchema>;
export type ManualMatchCreateResponse = z.infer<typeof manualMatchCreateResponseSchema>;
export type MatchResultUpdateRequest = z.infer<typeof matchResultUpdateRequestSchema>;

// ── Custom Prediction API ────────────────────────────────

export const teamItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  name_zh: z.string().nullable().optional(),
  fifa_code: z.string().nullable().optional(),
  team_type: z.string(),
});

export const customPredictionRequestSchema = z.object({
  home_team: z.string().min(1),
  away_team: z.string().min(1),
  competition: z.string().default("Custom Match"),
  is_neutral_venue: z.boolean().default(false),
});

export const customPredictionResponseSchema = z.object({
  prediction_id: z.string(),
  match_id: z.string(),
  status: z.string(),
});

export const predictionStatusResponseSchema = z.object({
  prediction_id: z.string(),
  status: z.string(),
  match_id: z.string().nullable().optional(),
  result: z.record(z.string(), z.unknown()).nullable().optional(),
  error: z.string().nullable().optional(),
});

export type TeamItem = z.infer<typeof teamItemSchema>;
export type CustomPredictionRequest = z.infer<typeof customPredictionRequestSchema>;
export type CustomPredictionResponse = z.infer<typeof customPredictionResponseSchema>;
export type PredictionStatusResponse = z.infer<typeof predictionStatusResponseSchema>;

export function parseJsonArray<T>(value: string | null | undefined, fallback: T): T {
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}
