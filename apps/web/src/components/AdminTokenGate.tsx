import { useState } from "react";

import type { ReactNode } from "react";

export function AdminTokenGate({
  children,
}: {
  children: (token: string) => ReactNode;
}) {
  const [token, setToken] = useState(() => sessionStorage.getItem("admin_token") ?? "");
  const [draft, setDraft] = useState(token);

  if (!token) {
    return (
      <div className="rounded-[28px] border border-border bg-bg-card/80 p-6">
        <div className="font-display text-xl">Admin Token</div>
        <p className="mt-2 text-sm text-text-secondary">输入 `ADMIN_TOKEN` 后进入审核后台。Token 仅保存在当前浏览器会话。</p>
        <div className="mt-4 flex gap-3">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="flex-1 rounded-2xl border border-border bg-black/20 px-4 py-3 text-sm outline-none ring-0"
            placeholder="Bearer token"
          />
          <button
            onClick={() => {
              sessionStorage.setItem("admin_token", draft);
              setToken(draft);
            }}
            className="rounded-2xl bg-accent-blue px-4 py-3 text-sm font-medium"
          >
            进入
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          className="text-sm text-text-secondary transition hover:text-white"
          onClick={() => {
            sessionStorage.removeItem("admin_token");
            setToken("");
            setDraft("");
          }}
        >
          清除 Token
        </button>
      </div>
      {children(token)}
    </div>
  );
}
