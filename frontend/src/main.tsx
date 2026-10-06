import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

function App() {
  return (
    <main>
      <p>物流業務の調査エージェント（デモ）</p>
      <h1>LogiScope</h1>
      <p>Reactの開発基盤を準備しました。質問入力・調査結果の画面は次の工程で実装します。</p>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
