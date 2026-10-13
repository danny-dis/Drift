export type CaptureStatus = "captured" | "queued" | "processed" | "needs_review";
export type Capture = {
  id: string;
  text: string;
  created_at: string;
  status: CaptureStatus;
  idea_id: string | null;
  task_id: string | null;
  report_path: string | null;
};
export type CapturePage = { captures: Capture[]; total: number; has_more: boolean };
export type Draft = { text: string; client_id: string };
export const CAPTURE_URL = "/api/ui/captures";
export const MAX_CAPTURE_LENGTH = 1_000_000;
export const STATUS_COPY: Record<CaptureStatus, { label: string; explanation: string }> = {
  captured: { label: "Saved", explanation: "Your original is saved. Processing has not started." },
  queued: { label: "Waiting to process", explanation: "Your original is saved. Processing is waiting to start." },
  processed: { label: "Processed", explanation: "Processing finished. Your original remains unchanged." },
  needs_review: { label: "Needs your review", explanation: "Your original is safe. Drift needs your input before it can continue; you can return to this later." },
};

export function isCapture(value: unknown): value is Capture {
  if (!value || typeof value !== "object") return false;
  const item = value as Capture;
  return typeof item.id === "string" && typeof item.text === "string" &&
    typeof item.created_at === "string" && Object.hasOwnProperty.call(STATUS_COPY, item.status);
}

export function isDraft(value: unknown): value is Draft {
  if (!value || typeof value !== "object") return false;
  const item = value as Draft;
  return typeof item.text === "string" && typeof item.client_id === "string" &&
    (item.text === "" || item.client_id.length > 0);
}
