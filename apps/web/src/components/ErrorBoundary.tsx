export function ErrorBoundaryFallback({
  error,
  resetError,
}: {
  error: unknown;
  resetError: () => void;
}) {
  const message = error instanceof Error ? error.message : "页面出错了，请刷新重试";

  return (
    <div className="mx-auto mt-16 max-w-xl rounded-[32px] border border-white/8 bg-bg-card/90 px-6 py-8 text-center shadow-hero">
      <div className="text-xs uppercase tracking-[0.24em] text-text-muted">Runtime Error</div>
      <div className="mt-3 font-display text-3xl">页面出错了，请刷新重试</div>
      <p className="mt-4 text-sm leading-7 text-text-secondary">{message}</p>
      <button className="mt-6 rounded-full bg-white px-4 py-3 text-sm font-medium text-black" onClick={resetError}>
        重新加载
      </button>
    </div>
  );
}
