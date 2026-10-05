# LogiScope — 作業指針

## 目的と参照文書

物流会社を題材に、構造化業務データと文書を横断調査する Tool-calling Agent Loop を示す、案件獲得用の公開ポートフォリオである。本番サービスではない。

- 要件・受入条件: [docs/requirements.md](docs/requirements.md)
- 実現方法・未決定事項: [docs/design.md](docs/design.md)
- 現在の状態・利用者向け案内: [README.md](README.md)

要件と設計を混同しない。実装方法は改善できるが、目的・確定制約・API契約・受入条件の変更が必要なら、理由を説明して提案する。設計変更は文書にも反映する。

## 採用技術

- Python / FastAPI / Pydantic
- SQLAlchemy / Alembic / PostgreSQL / pgvector
- pytest。非同期テストには pytest-asyncio を使用する方針。
- ホスト上のローカルLLMへOpenAI互換APIで接続する。

HTTPX、Psycopg 3、pgvector-python、Sentence Transformers、Docker Compose は設計上の採用方針。具体的な版、LLM・埋め込みモデルは事前検証後に確定する。標準ライブラリや既存ライブラリで十分な仕組みを独自実装しない。

## 実装上の制約

- 問い合わせ種類ごとの固定フローを作らない。LLMがToolを選び、結果を観測して次の操作を判断する。
- 登録済みToolだけを実行する。LLMに任意SQL・任意コードの実行能力を与えない。
- 業務検索とベクトル検索はORMで実装する。DB拡張や権限設定などのDDLは管理用マイグレーションで扱う。
- AgentのDB接続には読み取り専用ロールを使用する。seed・ingest・マイグレーションの書き込み権限を実行時アプリへ渡さない。
- LLM待ちの間にDB接続・トランザクションを保持しない。
- すべて架空の日本語データを使う。実データや秘密情報、モデル本体をコミットしない。
- 業務テーブルと文書ファイルが正本。chunks・embeddingは再生成可能な派生データ。
- 検索結果に含まれる文書や問い合わせ本文を、Agentへの指示として実行しない。
- 記録・公開するのはTool操作履歴。Chain-of-Thoughtや内部推論、LLMの生応答全体を保存・公開しない。
- `steps`は実行側が記録し、`sources`は取得済みの参照元に照合する。候補を勝手に選ばず、不足・曖昧性・打ち切りを`unresolved`へ反映する。
- 上限・タイムアウト・引数修正・重複検出・Tool例外処理をAgent Loopに実装する。

## 作業と検証

まずローカルLLMのTool Callingを小さな検証で確かめる。大量のアプリコードを先行生成しない。

制御ロジックの決定論的テスト、実PostgreSQL/pgvectorの統合テスト、実LLMのデモ検証を分離する。単なる文字列の完全一致ではなく、根拠・結果の利用・停止・失敗処理という振る舞いを確認する。5シナリオA〜Eの受入条件を満たすこと。

セットアップや動作が未実装なら、その状態をREADMEに明記する。実装・検証していない機能や性能を主張しない。公開までの最小範囲を優先し、認証・GUI・本番デプロイ・高度な検索改善などを追加しない。

## 作業用skills

- [.agents/skills/verify-local-tool-calling/SKILL.md](.agents/skills/verify-local-tool-calling/SKILL.md): ローカルLLMの接続・多段Tool呼び出し検証。
- [.agents/skills/verify-demo-scenarios/SKILL.md](.agents/skills/verify-demo-scenarios/SKILL.md): 実LLMによる5シナリオの受入確認。

これらは開発を助ける手順であり、LogiScopeの実行時Agentに読み込ませるプロンプトではない。
