import { useState } from "react";
import { Answer, History } from "./Results";
import { useInvestigation } from "./useInvestigation";
const samples = [
  ["単純検索", "SHP-DEMO-002の配送状態は？"],
  ["多段調査", "デモ青空商店の荷物が遅延している原因は？"],
  [
    "正本取得",
    "配達完了後の受領確認について、過去の問い合わせでの対応を調べて",
  ],
  ["回答不能", "SHP-NOT-FOUNDの配送状態は？"],
  ["曖昧性", "デモ双葉商会の荷物を調べて"],
];
const additionalSamples = [
  ["全体の件数", "どんな荷物があるの今"],
  ["所在不明一覧", "行方不明の荷物って今ある？"],
  ["同名の新規顧客", "デモ銀河資材の荷物を調べて"],
  ["営業所で特定", "架空拡充分第2営業所のデモ銀河資材の遅延荷物は？"],
  ["接触事故の原因", "SHP-EXPAND-003が遅延している原因は？"],
  ["通行規制の原因", "SHP-EXPAND-012が遅延している原因は？"],
  ["問い合わせなし", "SHP-EXPAND-053の配送状態は？"],
  ["発見予定は未確定", "SHP-EXPAND-021の所在と発見予定は？"],
  ["顧客内の該当なし", "デモ冬虹工芸の行方不明の荷物はある？"],
];
export default function App() {
  const [question, setQuestion] = useState("");
  const state = useInvestigation();
  const length = Array.from(question.trim()).length;
  const canSend = length > 0 && length <= 4000 && !state.pending;
  return (
    <>
      <header>
        <div className="brand">
          LogiScope <span>DEMO</span>
        </div>
        <p>物流業務の調査エージェント</p>
      </header>
      <main className="layout">
        <div>
          <section className="panel">
            <h1>業務データと文書から、状況を調べる</h1>
            <p className="muted">
              質問に応じてAgentが情報源を選び、根拠とともに回答します。架空データを使ったデモです。
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (canSend) void state.send(question);
              }}
            >
              <label htmlFor="question">質問</label>
              <textarea
                id="question"
                rows={4}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    (e.ctrlKey || e.metaKey) &&
                    !e.nativeEvent.isComposing &&
                    e.nativeEvent.keyCode !== 229
                  ) {
                    e.preventDefault();
                    if (canSend) void state.send(question);
                  }
                }}
                aria-describedby="input-help"
              />
              <div id="input-help" className="input-help">
                <span>Ctrl / Cmd + Enterで送信</span>
                <span>{length.toLocaleString()} / 4,000文字</span>
              </div>
              {length > 4000 && (
                <p className="failure">質問は4,000文字以内にしてください。</p>
              )}
              <div className="actions">
                <button className="primary" disabled={!canSend} type="submit">
                  {state.pending ? "調査中…" : "調査する"}
                </button>
                {state.pending && (
                  <button type="button" onClick={state.stop}>
                    待機を終了
                  </button>
                )}
              </div>
            </form>
            <p className="sample-label">サンプル質問 · 基本の5シナリオ</p>
            <div className="samples">
              {samples.map(([label, text]) => (
                <button
                  key={label}
                  disabled={state.pending}
                  onClick={() => setQuestion(text)}
                >
                  {label}
                </button>
              ))}
            </div>
            <details className="additional-samples">
              <summary>追加データで試す質問（9問）</summary>
              <p className="muted">選ぶと質問欄に入ります。「調査する」で送信してください。</p>
              <div className="samples">
                {additionalSamples.map(([label, text]) => (
                  <button key={label} type="button" disabled={state.pending}
                    onClick={() => setQuestion(text)}>
                    {label}
                  </button>
                ))}
              </div>
            </details>
            <p role="status" className="muted">
              {state.notice}
            </p>
            {state.pending && (
              <p>
                経過 {state.seconds}秒 ·
                ローカルLLMのため数分かかる場合があります。
              </p>
            )}
            {state.error && (
              <p role="alert" className="error">
                {state.error}
              </p>
            )}
          </section>
          {state.result ? (
            <Answer data={state.result} question={state.submitted} />
          ) : (
            <section className="panel empty">
              <h2>回答</h2>
              <p>
                {state.pending
                  ? "調査結果を待っています。"
                  : "質問を送信すると、ここに回答と根拠を表示します。"}
              </p>
            </section>
          )}
        </div>
        <aside>
          {state.result ? (
            <History data={state.result} />
          ) : (
            <section className="panel empty">
              <h2>実行履歴</h2>
              <p>Agentが実行したToolを、調査完了後に表示します。</p>
            </section>
          )}
        </aside>
      </main>
      <footer>読み取り専用のPoC · 内部推論は表示しません</footer>
    </>
  );
}
