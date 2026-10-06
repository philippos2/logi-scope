import { useEffect, useRef, useState } from "react";
import { ReportRejected, reportDelivery, type DeliveryReport, type DeliveryStatus } from "./deliveryApi";
const labels: Record<DeliveryStatus, string> = {
  in_transit: "配送中", delayed: "遅延", missing: "所在不明", delivered: "配達完了",
};
function localTime() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 19);
}
export default function DeliveryUpdate({ investigating, onBusy, onQuestion }: {
  investigating: boolean;
  onBusy: (busy: boolean) => void;
  onQuestion: (question: string) => void;
}) {
  const [status, setStatus] = useState<DeliveryStatus>("delivered");
  const [occurred, setOccurred] = useState(localTime);
  const [pending, setPending] = useState(false);
  const [retry, setRetry] = useState<DeliveryReport | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const active = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    sequence.current++;
    active.current?.abort();
    if (timer.current !== null) clearTimeout(timer.current);
  }, []);
  async function send() {
    if (active.current || investigating || !occurred) return;
    const date = new Date(occurred);
    if (Number.isNaN(date.getTime())) {
      setError("報告日時を確認してください。");
      return;
    }
    const payload = retry ?? { event_key: crypto.randomUUID(), status, occurred_at: date.toISOString() };
    setRetry(payload);
    setPending(true);
    setError("");
    setNotice("");
    onBusy(true);
    const controller = new AbortController();
    active.current = controller;
    const id = ++sequence.current;
    const timeout = setTimeout(() => {
      if (id !== sequence.current) return;
      sequence.current++;
      active.current = null;
      controller.abort();
      setPending(false);
      onBusy(false);
      setError("報告の応答待ちが時間超過しました。登録済みの場合があります。同じ報告を再送して確認してください。");
    }, 30_000);
    timer.current = timeout;
    try {
      const receipt = await reportDelivery(payload, controller.signal);
      if (id !== sequence.current) return;
      setRetry(null);
      setOccurred(localTime());
      setNotice(`${labels[receipt.status]}の報告を受け付けました。${receipt.replayed ? "再送した報告の受付を確認しました。" : ""}もう一度調査して現在の状態を確認してください。`);
    } catch (e) {
      if (id !== sequence.current) return;
      if (e instanceof ReportRejected) setRetry(null);
      setError(e instanceof ReportRejected ? e.message : "報告の受付結果を確認できませんでした。同じ報告を再送して確認してください。");
    } finally {
      clearTimeout(timeout);
      if (id === sequence.current) {
        active.current = null;
        setPending(false);
        onBusy(false);
      }
    }
  }
  const locked = pending || investigating || retry !== null;
  return (
    <section className="panel">
      <details>
        <summary>配送状況の報告（デモ）</summary>
        <p>更新用荷物 <code>SHP-UPDATE-001</code> の配送状況を報告します。</p>
        <p className="muted">表示済みの回答は自動更新されません。報告後は再度調査してください。</p>
        <form onSubmit={(e) => { e.preventDefault(); void send(); }}>
          <label htmlFor="delivery-status">報告する配送状態</label>
          <select id="delivery-status" value={status} disabled={locked}
            onChange={(e) => setStatus(e.target.value as DeliveryStatus)}>
            {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <label htmlFor="delivery-time">報告日時（端末の現地時刻）</label>
          <input id="delivery-time" type="datetime-local" step="1" required value={occurred} disabled={locked}
            onChange={(e) => setOccurred(e.target.value)} />
          <div className="actions update-actions">
            <button type="submit" disabled={pending || investigating || !occurred}>
              {pending ? "報告中…" : retry ? "同じ報告を再送" : "配送状況を報告"}
            </button>
            <button type="button" disabled={pending || investigating}
              onClick={() => onQuestion("SHP-UPDATE-001の配送状態は？")}>更新用荷物を調べる</button>
          </div>
        </form>
        {notice && <p role="status">{notice}</p>}
        {error && <p role="alert" className="error">{error}</p>}
      </details>
    </section>
  );
}
