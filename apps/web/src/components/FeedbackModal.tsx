import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { submitFeedback } from "../lib/api";
import type { FeedbackRequest } from "../lib/types";

const FEEDBACK_OPTIONS: Array<{ value: FeedbackRequest["feedback_type"]; label: string }> = [
  { value: "error_in_article", label: "文章内容有误" },
  { value: "wrong_signal", label: "信号判断不对" },
  { value: "wrong_prediction", label: "预测结果偏差大" },
  { value: "missing_info", label: "缺少关键信息" },
  { value: "other", label: "其他" },
];

export function FeedbackModal({
  matchId,
  articleTitle,
  onClose,
}: {
  matchId?: string;
  articleTitle?: string | null;
  onClose: () => void;
}) {
  const [feedbackType, setFeedbackType] = useState<FeedbackRequest["feedback_type"]>("error_in_article");
  const [description, setDescription] = useState("");
  const [contact, setContact] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const mutation = useMutation({
    mutationFn: () =>
      submitFeedback({
        match_id: matchId,
        feedback_type: feedbackType,
        description,
        contact: contact || undefined,
      }),
    onSuccess: () => {
      setSubmitted(true);
      window.setTimeout(onClose, 900);
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="w-full max-w-lg rounded-[28px] border border-white/8 bg-bg-card/95 p-5 shadow-hero">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Feedback</div>
            <div className="mt-2 font-display text-2xl">提交纠错反馈</div>
            {articleTitle ? <div className="mt-2 text-sm text-text-secondary">{articleTitle}</div> : null}
          </div>
          <button className="text-sm text-text-secondary transition hover:text-white" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="mt-5 space-y-4">
          {submitted ? (
            <div className="rounded-2xl border border-accent-green/25 bg-accent-green/10 px-4 py-4 text-sm text-accent-green">
              感谢反馈，我们会认真处理。
            </div>
          ) : null}
          <label className="block space-y-2 text-sm">
            <span className="text-text-secondary">问题类型</span>
            <select
              className="w-full rounded-2xl border border-border bg-black/20 px-4 py-3 outline-none"
              value={feedbackType}
              onChange={(event) => setFeedbackType(event.target.value as FeedbackRequest["feedback_type"])}
            >
              {FEEDBACK_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block space-y-2 text-sm">
            <span className="text-text-secondary">描述问题</span>
            <textarea
              className="min-h-[140px] w-full rounded-2xl border border-border bg-black/20 px-4 py-3 outline-none"
              value={description}
              onChange={(event) => setDescription(event.target.value.slice(0, 500))}
              maxLength={500}
              placeholder="请尽量具体说明问题所在"
            />
            <div className="text-right text-xs text-text-muted">{description.length}/500</div>
          </label>

          <label className="block space-y-2 text-sm">
            <span className="text-text-secondary">联系方式（可选）</span>
            <input
              className="w-full rounded-2xl border border-border bg-black/20 px-4 py-3 outline-none"
              value={contact}
              onChange={(event) => setContact(event.target.value)}
              placeholder="邮箱或微信"
            />
          </label>
        </div>

        <div className="mt-5 flex gap-3">
          <button className="rounded-full border border-white/10 px-4 py-3 text-sm text-white" onClick={onClose}>
            取消
          </button>
          <button
            className="rounded-full bg-white px-4 py-3 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-50"
            disabled={submitted || mutation.isPending || description.trim().length === 0}
            onClick={() => mutation.mutate()}
          >
            {submitted ? "已提交" : mutation.isPending ? "提交中..." : "提交反馈"}
          </button>
        </div>
      </div>
    </div>
  );
}
