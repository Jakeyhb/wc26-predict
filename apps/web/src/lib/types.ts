export type {
  AccuracyStats,
  AdminDashboardSummary,
  ApprovedSignalItem,
  ConflictSignalGroupItem,
  CompetitionType,
  EvidenceResponse,
  FeedbackRequest,
  FeedbackItem,
  FeedbackResponse,
  FeedbackStatusUpdate,
  HermesDigestItem,
  HermesDigestResponse,
  HermesTaskSnapshot,
  ManualMatchCreateRequest,
  ManualMatchCreateResponse,
  ManualSignalCreateRequest,
  MatchCard,
  MatchResultUpdateRequest,
  PaginatedFeedbackResponse,
  PendingArticleItem,
  PendingSignalItem,
  PredictionHistoryItem,
  PredictionSnapshot,
  RecentPredictionItem,
  RecentPredictionsResponse,
  ReviewSummary,
  RunType,
  ScheduleResponse,
  TriggerPredictionResponse,
  TeamItem,
  CustomPredictionRequest,
  CustomPredictionResponse,
  PredictionStatusResponse,
} from "@wc26/shared";

export interface PaginatedResponse<T> {
  items: T[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
  };
}
