export type DeliveryStatus = "in_transit" | "delayed" | "missing" | "delivered";
export type DeliveryReport = {
  event_key: string;
  status: DeliveryStatus;
  occurred_at: string;
};
export type DeliveryReceipt = {
  shipment_id: string;
  event_id: number;
  status: DeliveryStatus;
  occurred_at: string;
  replayed: boolean;
};
export class ReportRejected extends Error {}
export async function reportDelivery(payload: DeliveryReport, signal: AbortSignal): Promise<DeliveryReceipt> {
  const response = await fetch("/updates-api/shipments/SHP-UPDATE-001/events", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload), signal,
  });
  if (!response.ok) {
    const messages: Record<number, string> = {
      403: "この荷物は更新対象ではありません。",
      404: "更新用の荷物がありません。デモデータを準備してください。",
      409: "配送状態や報告日時が登録内容と一致しません。配達完了後の変更はできません。",
      422: "配送状態と報告日時を確認してください。",
    };
    if (Object.hasOwn(messages, response.status))
      throw new ReportRejected(messages[response.status] ?? "報告を受け付けられませんでした。");
    throw new Error("報告の受付結果を確認できませんでした。同じ報告を再送して確認してください。");
  }
  const value: unknown = await response.json();
  if (typeof value !== "object" || value === null) throw new Error("受付結果を確認できませんでした。");
  const receipt = value as Partial<DeliveryReceipt>;
  if (receipt.shipment_id !== "SHP-UPDATE-001" || receipt.status !== payload.status
      || !Number.isInteger(receipt.event_id) || (receipt.event_id ?? 0) <= 0
      || typeof receipt.replayed !== "boolean" || typeof receipt.occurred_at !== "string"
      || Date.parse(receipt.occurred_at) !== Date.parse(payload.occurred_at))
    throw new Error("受付結果を確認できませんでした。同じ報告を再送して確認してください。");
  return receipt as DeliveryReceipt;
}
