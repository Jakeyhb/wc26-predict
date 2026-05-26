import { useEffect, useState } from "react";

export function ProbabilityArc({
  value,
  color,
  label,
}: {
  value: number;
  color: string;
  label: string;
}) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    const id = requestAnimationFrame(() => setDisplayValue(value));
    return () => cancelAnimationFrame(id);
  }, [value]);

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        className="relative grid h-28 w-28 place-items-center rounded-full border border-white/10"
        style={{
          background: `conic-gradient(${color} ${displayValue * 360}deg, rgba(255,255,255,0.05) 0deg)`,
          transition: "background 0.8s ease-out",
        }}
      >
        <div className="grid h-[84px] w-[84px] place-items-center rounded-full bg-bg-card text-center shadow-hero">
          <div className="font-display text-2xl font-bold">{Math.round(displayValue * 100)}%</div>
        </div>
      </div>
      <div className="text-sm uppercase tracking-[0.2em] text-text-secondary">{label}</div>
    </div>
  );
}

