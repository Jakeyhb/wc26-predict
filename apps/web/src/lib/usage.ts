const STORAGE_KEY = "wc26_prediction_usage";
export const FREE_LIMIT = 3;

export interface UsageRecord {
  count: number;
  predictions: Array<{
    id: string;
    homeTeam: string;
    awayTeam: string;
    timestamp: number;
  }>;
}

function read(): UsageRecord {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as UsageRecord;
  } catch { /* localStorage unavailable */ }
  return { count: 0, predictions: [] };
}

function write(record: UsageRecord): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch { /* localStorage full or unavailable */ }
}

export function getUsage(): UsageRecord {
  return read();
}

export function getRemainingPredictions(): number {
  return Math.max(0, FREE_LIMIT - read().count);
}

export function hasReachedLimit(): boolean {
  return read().count >= FREE_LIMIT;
}

export function incrementUsage(
  predictionId: string,
  homeTeam: string,
  awayTeam: string,
): UsageRecord {
  const record = read();
  record.count += 1;
  record.predictions.unshift({
    id: predictionId,
    homeTeam,
    awayTeam,
    timestamp: Date.now(),
  });
  write(record);
  return record;
}
