# LogiScope — 作業指針

## 目的と参照文書

物流会社を題材に、構造化業務データと文書を横断調査する Tool-calling Agent Loop を示す、案件獲得用の公開ポートフォリオである。本番サービスではない。

- 要件・受入条件: [docs/requirements.md](docs/requirements.md)
- 実現方法・検証範囲: [docs/design.md](docs/design.md)
- 現在の状態・利用者向け案内: [README.md](README.md)

要件と設計を混同しない。実装方法は改善できるが、目的・確定制約・API契約・受入条件の変更が必要なら、理由を説明して提案する。設計変更は文書にも反映する。

## 採用技術

- Python 3 / FastAPI / Pydantic
- SQLAlchemy / Alembic / PostgreSQL / pgvector
- pytest / pytest-asyncio。
- ホスト上のローカルLLMへOpenAI互換APIで接続する。

HTTPX、Psycopg 3、pgvector-python、Sentence Transformers、Docker Compose を使用する。採用モデルと検証環境は設計書・セットアップガイド、依存の版は実行設定を参照する。標準ライブラリや既存ライブラリで十分な仕組みを独自実装しない。

## バージョンとコンテナ

- Python 3の比較的新しい安定版を使い、FastAPI・SQLAlchemy・Sentence Transformers/PyTorchとの互換性を確認して選ぶ。Python 2への対応は行わない。
- アプリのベースは公式PythonイメージのDebian slim系とする。Python版とDebianのコードネームを明示したタグを選び、`latest`やOS版を省いた可変タグに依存しない。
- DBはPostgreSQL＋pgvectorの専用イメージを使い、アプリと分離する。LLMはホスト側で実行する。
- Python・ライブラリ・PostgreSQL・pgvectorの具体的な版は互換性を確認して固定し、更新時にも確認する。Python要件は`pyproject.toml`、依存の解決済み版はロックファイル、コンテナ版はDockerfile/Composeに記録する。
- 正確な版の唯一の管理元は上記の実行設定とし、AGENTS.mdに重複した版一覧を維持しない。選定理由は設計書、検証済み環境はセットアップガイド、実測結果は履歴に記載する。
- バージョン更新は必要性と互換性を確認し、関連するテスト・起動確認と文書更新を伴わせる。

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

LLMモデルや実行サーバーを変更するときは、まず小さなTool Calling検証で互換性を確かめる。

制御ロジックの決定論的テスト、実PostgreSQL/pgvectorの統合テスト、実LLMのデモ検証を分離する。単なる文字列の完全一致ではなく、根拠・結果の利用・停止・失敗処理という振る舞いを確認する。5シナリオA〜Eの受入条件を満たすこと。

セットアップや動作が未実装なら、その状態をREADMEに明記する。実装・検証していない機能や性能を主張しない。公開までの最小範囲を優先し、認証・本番デプロイ・高度な検索改善などを追加しない。

## 文書とフロントエンド

READMEは現在の機能・起動方法・制限への入口とする。試行錯誤、日時付きの実測結果、修正経緯は`docs/history/`へ置く。AGENTS.mdは共通の作業指針、SKILL.mdは特定の検証手順を扱い、実行時Agentの指示と混同しない。

Reactのデモ画面は同じリポジトリの`frontend/`に実装済み。既存の`POST /agent`を利用し、質問・回答・根拠・Tool履歴・未解決事項を表示する。Agentの判断や検索処理を画面へ移さない。フロントエンドの依存管理・ビルド・テストはPython側と分離し、起動手順は共通のガイドで説明する。

作業単位ごとに`feature/`ブランチを作る。コミット・プッシュ、PR作成・マージは利用者の指示に従う。

## 作業用skills

- [.agents/skills/verify-local-tool-calling/SKILL.md](.agents/skills/verify-local-tool-calling/SKILL.md): ローカルLLMの接続・多段Tool呼び出し検証。
- [.agents/skills/verify-demo-scenarios/SKILL.md](.agents/skills/verify-demo-scenarios/SKILL.md): 実LLMによる5シナリオの受入確認。

これらは開発を助ける手順であり、LogiScopeの実行時Agentに読み込ませるプロンプトではない。
