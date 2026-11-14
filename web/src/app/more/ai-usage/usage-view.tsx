"use client";

import { useEffect, useState } from "react";

import { Card, Loading, Notice } from "@/components/ui";
import { ApiError, api } from "@/lib/api-client";
import { formatPeso } from "@/lib/format";
import type { AiUsage } from "@/lib/types";

function resetDate(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString("en-PH", { month: "long", day: "numeric" });
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-h-12 items-center justify-between gap-3 border-b border-border last:border-b-0">
      <span className="text-sm text-muted">{label}</span>
      <b className="text-base text-text tabular-nums">{value}</b>
    </div>
  );
}

export function UsageView() {
  const [usage, setUsage] = useState<AiUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<AiUsage>("insights/ai-usage").then(setUsage, (e: unknown) => {
      setError(e instanceof ApiError ? e.message : "Could not load AI usage.");
    });
  }, []);

  if (error) return <Notice title="Could not load AI usage">{error}</Notice>;
  if (!usage) return <Loading />;

  const percent =
    usage.budget_centavos > 0
      ? Math.min(100, Math.round((usage.spent_centavos / usage.budget_centavos) * 100))
      : 100;
  const filled = usage.spent_centavos > 0 ? Math.max(percent, 2) : 0;

  return (
    <div className="flex flex-col gap-4">
      {usage.reached && (
        <Notice icon="sukat" title="This month's limit is reached">
          Photo reading and the AI assistant will work again on {resetDate(usage.resets_on)}.
        </Notice>
      )}
      <Card>
        <p className="text-[13px] font-bold text-muted uppercase">{usage.month}</p>
        <p className="mt-2 text-[28px] leading-tight font-bold text-text tabular-nums">
          {formatPeso(usage.spent_centavos)}
        </p>
        <p className="mt-1 text-sm text-muted">of {formatPeso(usage.budget_centavos)} monthly limit</p>
        <div
          role="progressbar"
          aria-label="AI budget used"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="mt-4 h-3 overflow-hidden rounded-full bg-border"
        >
          <div
            className={`h-full rounded-full ${usage.reached ? "bg-red" : "bg-accent"}`}
            style={{ width: `${filled}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-[13px] text-muted tabular-nums">
          <span>{percent}% used</span>
          <span>Limit {formatPeso(usage.budget_centavos)}</span>
        </div>
      </Card>
      <Card padded={false} className="px-4">
        <Row label="Left this month" value={formatPeso(usage.remaining_centavos)} />
        <Row label="Photo reading" value={formatPeso(usage.scans_centavos)} />
        <Row label="AI assistant" value={formatPeso(usage.chat_centavos)} />
      </Card>
      <p className="text-sm text-muted">
        These are estimates. The count starts again on {resetDate(usage.resets_on)}.
      </p>
    </div>
  );
}
