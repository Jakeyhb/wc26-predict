import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchPendingArticles, publishArticle } from "../lib/api";

export function AdminArticlesPage({ token }: { token: string }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["admin", "articles", token],
    queryFn: () => fetchPendingArticles(token),
  });

  const mutation = useMutation({
    mutationFn: (articleId: string) => publishArticle(token, articleId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "articles", token] });
    },
  });

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Article Review</div>
        <div className="mt-2 font-display text-3xl">文章发布</div>
      </div>
      <div className="space-y-3">
        {data?.map((article) => (
          <div key={article.id} className="rounded-[28px] border border-border bg-bg-card/80 p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="font-display text-xl">{article.title}</div>
                <p className="mt-3 whitespace-pre-line text-sm leading-7 text-text-secondary">{article.body}</p>
              </div>
              <button
                className="rounded-full bg-accent-blue/20 px-4 py-2 text-sm text-accent-blue"
                onClick={() => mutation.mutate(article.id)}
              >
                发布
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

