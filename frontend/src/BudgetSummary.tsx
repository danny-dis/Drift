import type { ReactNode } from "react";

type Props = { value: Record<string, unknown> };

export default function BudgetSummary({ value }: Props) {
  const raw = value.calls;
  const calls = raw && typeof raw === "object" ? raw as Record<string, unknown> : null;
  const row = (label: string, content: unknown): ReactNode => <li key={label}>{label}: {String(content ?? "Unavailable")}</li>;
  if (!calls) return <p>Model-call allowance is unavailable. Saved thoughts are separate from model work.</p>;
  return <section aria-label="Model-call allowance">
    {Boolean(value.waiting_reason) && <p role="status"><strong>Model work is waiting.</strong> {String(value.waiting_reason)}. You can still capture and search thoughts.</p>}
    <ul>
      {row("Daily calls used", `${calls.daily_calls ?? "?"} / ${calls.daily_limit ?? "?"}`)}
      {row("Weekly calls used", `${calls.weekly_calls ?? "?"} / ${calls.weekly_limit ?? "?"}`)}
      {row("Calls remaining this week", calls.weekly_remaining)}
      {row("Provider failures recorded", calls.failures)}
      {Boolean(calls.next_admission_at) && row("Allowance resumes", new Date(String(calls.next_admission_at)).toLocaleString())}
    </ul>
    <details><summary>Estimated monetary budget</summary>
      <p>Free calls and failed attempts still consume the call allowance. These numbers are not billing receipts.</p>
      <ul>{["daily_budget", "daily_remaining", "weekly_budget", "weekly_remaining", "total_spend"].map(key => row(key.replace(/_/g, " "), value[key]))}</ul>
    </details>
  </section>;
}
