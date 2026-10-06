import { useState, type ReactNode } from "react";
import type { AgentResponse, Source } from "./api";
const codes: Record<string, string> = {
  not_found: "対象が見つからない",
  insufficient_evidence: "情報不足・未確定",
  ambiguous_target: "対象の特定が必要",
  timeout: "時間超過",
  tool_error: "Tool実行失敗",
  invalid_tool_arguments: "引数の修正失敗",
  step_limit: "実行上限",
  no_progress: "調査が進展しない",
  llm_error: "回答生成の失敗",
};
const kinds: Record<string, string> = {
  customer: "顧客",
  shipment: "荷物",
  delivery_event: "配送イベント",
  inquiry: "問い合わせ",
};
export function Json({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}
export function Panel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(
    () => window.matchMedia("(min-width: 900px)").matches,
  );
  return (
    <details
      className="panel"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>{title}</summary>
      {children}
    </details>
  );
}
function SourceRow({ source }: { source: Source }) {
  const label =
    source.kind === "chunk"
      ? source.path
        ? "文書"
        : "問い合わせ本文"
      : (kinds[source.kind] ?? source.kind);
  const identifier =
    source.kind === "chunk"
      ? (source.path?.split("/").pop() ?? source.origin_id ?? source.id)
      : source.id;
  return (
    <li>
      <span className="tag">{label}</span>
      <code>{identifier}</code>
      <details>
        <summary>参照情報</summary>
        <Json value={source} />
      </details>
    </li>
  );
}
export function Answer({
  data,
  question,
}: {
  data: AgentResponse;
  question: string;
}) {
  return (
    <>
      <section className="panel">
        <h2>回答</h2>
        <p className="muted">質問：{question}</p>
        <p className="answer">{data.answer}</p>
      </section>
      {data.unresolved.length > 0 && (
        <section className="panel unresolved">
          <h2>
            未解決事項 <span>{data.unresolved.length}件</span>
          </h2>
          <ul>
            {data.unresolved.map((p, i) => (
              <li key={i}>
                <strong>{codes[p.code] ?? p.code}</strong>
                <code className="issue-code">{p.code}</code>
                <p>{p.message}</p>
                {p.details && Object.keys(p.details).length > 0 && (
                  <>
                    <Candidates details={p.details} />
                    <details>
                      <summary>詳細</summary>
                      <Json value={p.details} />
                    </details>
                  </>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      <Panel title={`根拠（${data.sources.length}件）`}>
        <ul className="sources">
          {data.sources.map((s) => (
            <SourceRow key={s.id} source={s} />
          ))}
        </ul>
        {!data.sources.length && <p>根拠はありません。</p>}
      </Panel>
    </>
  );
}
function Candidates({ details }: { details: Record<string, unknown> }) {
  if (!Array.isArray(details.candidates)) return null;
  return (
    <>
      <ul>
        {details.candidates.map((c, i) => (
          <li key={i}>
            {c && typeof c === "object" && (
              <>
                {String(c.name ?? "顧客")} / ID: {String(c.id ?? "")} / 営業所:{" "}
                {String(c.branch ?? "")}
              </>
            )}
          </li>
        ))}
      </ul>
      {details.truncated === true && <p>候補は一部のみ表示されています。</p>}
      <p>顧客IDまたは営業所を含めて、改めて質問してください。</p>
    </>
  );
}
export function History({ data }: { data: AgentResponse }) {
  return (
    <>
      <Panel title={`実行履歴（${data.steps.length}ステップ）`}>
        <ol className="steps">
          {data.steps.map((s, i) => (
            <li key={i}>
              <span className={s.ok ? "success" : "failure"}>
                {s.ok ? "成功" : "失敗"}
              </span>{" "}
              <code>{s.tool}</code>
              <details>
                <summary>引数{s.error ? "・エラー" : ""}</summary>
                <dl>
                  {Object.entries(s.args).map(([key, value]) => (
                    <div key={key}>
                      <dt>
                        <code>{key}</code>
                      </dt>
                      <dd className={value === null ? "muted" : ""}>
                        {value === null
                          ? "未指定"
                          : typeof value === "object"
                            ? JSON.stringify(value)
                            : String(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
                {s.error && (
                  <p>
                    エラー：<code>{s.error}</code>
                  </p>
                )}
              </details>
            </li>
          ))}
        </ol>
      </Panel>
      <details className="panel">
        <summary>APIレスポンスJSON</summary>
        <Json value={data} />
      </details>
    </>
  );
}
