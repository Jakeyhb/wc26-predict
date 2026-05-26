import { Info } from "lucide-react";

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-[28px] border border-border bg-bg-card/70 p-6 text-center text-text-secondary">
      <Info className="mx-auto mb-3 h-6 w-6 text-text-muted" />
      <div className="font-display text-lg text-text-primary">{title}</div>
      <p className="mt-2 text-sm leading-6">{description}</p>
    </div>
  );
}

