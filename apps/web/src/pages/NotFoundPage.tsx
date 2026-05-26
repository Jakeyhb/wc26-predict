import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="rounded-[36px] border border-white/8 bg-bg-card/85 px-6 py-10 text-center shadow-hero">
      <div className="text-xs uppercase tracking-[0.24em] text-text-muted">404</div>
      <div className="mt-3 font-display text-[42px] leading-none">页面不存在</div>
      <p className="mx-auto mt-4 max-w-md text-sm leading-7 text-text-secondary">
        这个页面可能已经被移除，或者链接地址本身就不正确。
      </p>
      <Link to="/" className="mt-6 inline-flex rounded-full bg-white px-4 py-3 text-sm font-medium text-black">
        返回首页
      </Link>
    </div>
  );
}
