export type Source = {
  id: string;
  kind: string;
  record_id?: number | string;
  path?: string;
  chunk_id?: string;
  origin_id?: string;
  source_revision?: string;
};
export type Step = {
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
  error?: string;
};
export type Unresolved = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};
export type AgentResponse = {
  answer: string;
  sources: Source[];
  steps: Step[];
  unresolved: Unresolved[];
};
const object = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
export function parseResponse(v: unknown): AgentResponse {
  if (
    !object(v) ||
    typeof v.answer !== "string" ||
    !Array.isArray(v.sources) ||
    !Array.isArray(v.steps) ||
    !Array.isArray(v.unresolved) ||
    !v.sources.every(
      (s) =>
        object(s) &&
        typeof s.id === "string" &&
        typeof s.kind === "string" &&
        ["path", "chunk_id", "origin_id", "source_revision"].every(
          (k) => s[k] === undefined || typeof s[k] === "string",
        ),
    ) ||
    !v.steps.every(
      (s) =>
        object(s) &&
        typeof s.tool === "string" &&
        object(s.args) &&
        typeof s.ok === "boolean" &&
        (s.error === undefined || typeof s.error === "string"),
    ) ||
    !v.unresolved.every(
      (s) =>
        object(s) &&
        typeof s.code === "string" &&
        typeof s.message === "string" &&
        (s.details === undefined || object(s.details)),
    )
  )
    throw new Error("APIの応答形式を確認できませんでした。");
  return v as AgentResponse;
}
export async function investigate(
  question: string,
  signal: AbortSignal,
): Promise<AgentResponse> {
  const response = await fetch("/api/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok) {
    const messages: Record<number, string> = {
      422: "質問の入力内容を確認してください。",
      502: "LLMから回答を取得できませんでした。",
      504: "LLMへの要求が時間超過しました。",
    };
    let message = messages[response.status] ?? "APIへの接続に失敗しました。";
    const data: unknown = await response.json().catch(() => null);
    if (response.status === 503 && object(data) && object(data.detail))
      message =
        data.detail.code === "agent_busy"
          ? "別の調査を実行中です。しばらく待って再送信してください。"
          : "Agentの準備ができていません。";
    throw new Error(message);
  }
  return parseResponse(await response.json());
}
