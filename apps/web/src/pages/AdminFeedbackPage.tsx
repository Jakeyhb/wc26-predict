import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { fetchFeedback, updateFeedbackStatus } from "../lib/api";

export function AdminFeedbackPage({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["admin", "feedback", token],
    queryFn: () => fetchFeedback(token),
  });
  const mutation = useMutation({
    mutationFn: (feedbackId: string) => updateFeedbackStatus(token, feedbackId, { status: "resolved" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "feedback", token] });
    },
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Feedback Queue</div>
        <div className="mt-2 font-display text-3xl">用户反馈</div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="总反馈数" value={data?.pagination.total ?? 0} />
        <MetricCard label="当前页" value={data?.pagination.page ?? 1} />
        <MetricCard label="每页条数" value={data?.pagination.page_size ?? 20} />
      </div>

      <div className="space-y-3">
        {items.length === 0 ? (
          <div className="rounded-[28px] border border-border bg-bg-card/80 p-5 text-sm text-text-secondary">
            暂无用户反馈。
          </div>
        ) : null}
        {items.map((item) => (
          <div key={item.id} className="rounded-[28px] border border-border bg-bg-card/80 p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.18em] text-text-muted">
                  <span>{item.feedback_type}</span>
                  <span>·</span>
                  <span>{item.status}</span>
                </div>
                <div className="text-sm leading-7 text-white">{item.description}</div>
              </div>
              <div className="text-right text-xs text-text-secondary">
                <div>{format(new Date(item.created_at), "MM/dd HH:mm")}</div>
                <div className="mt-1">match: {item.match_id ?? "—"}</div>
                <div className="mt-1">article: {item.article_id ?? "—"}</div>
                <div className="mt-1">contact: {item.contact ?? "—"}</div>
                <button
                  className="mt-3 rounded-full bg-white/10 px-3 py-2 text-xs text-white disabled:opacity-50"
                  disabled={mutation.isPending}
                  onClick={() => mutation.mutate(item.id)}
                >
                  标记已处理
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-[28px] border border-border bg-bg-card/80 p-5">
      <div className="text-sm text-text-secondary">{label}</div>
      <div className="mt-3 font-display text-4xl">{value}</div>
    </div>
  );
}
