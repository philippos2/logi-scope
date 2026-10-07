# LogiScope

[![CI](https://github.com/philippos2/logi-scope/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/philippos2/logi-scope/actions/workflows/ci.yml)

**業務データとRAGを横断調査する Tool-calling Agent Loop のデモ。**

物流会社の架空データを題材に、自然言語の質問からLLMがToolを選び、結果を観測して次の調査を進め、根拠と未解決事項を返します。案件獲得用ポートフォリオとして、Agentの設計・実装・検証を示すPoCです。

**[紹介文：概要・技術と設計の説明](docs/introduction.md)**

## デモ動画（約4分）

https://github.com/user-attachments/assets/063796d0-f901-40da-b438-677618746aa8

多段調査、同名顧客の曖昧性、配送報告後の再調査を、実際の画面で紹介します。日本語字幕・音声付き（3分51秒）。応答待ちの一部は短縮しています。

> **Reactの調査画面とAgent APIを実装しています。** `POST /agent`からローカルLLM・業務DB・RAGを使って調査できます。`frontend/`のReact画面から質問し、回答・根拠・Tool履歴・未解決事項を確認できます。任意起動の配送更新デモでは、同じ画面から更新用荷物の状態を報告できます。

## 示すこと

- 顧客・荷物・配送イベントの構造化検索と、日本語文書・過去問い合わせのRAG検索。
- 配送状態による一覧・有無の検索。所在不明と遅延を区別します。
- 前段の検索結果を次のToolへ利用する複数段階の調査。
- 根拠付き回答とTool実行履歴。情報不足・曖昧性の明示。
- 引数検証、重複防止、例外処理、上限によるAgent Loopの制御。
- 有料クラウドLLMに依存しないローカル再現性。

問い合わせ別の固定処理フローを作るデモではありません。LLMが次の操作を選びます。モデル内部のChain-of-Thoughtは記録・公開しません。

通常の架空データは顧客30件・荷物90件・配送イベント177件・問い合わせ20件・文書13本。配送更新デモを初期化すると専用顧客・荷物が1件ずつ加わり、荷物の全体件数は91件になります。[追加の質問例と期待する事実](docs/demo-data.md)を参照してください。

## 構成と正本

LLMはホスト上で実行し、OpenAI互換APIで接続します。Tool実行結果を観測して次の操作を選びます。

```mermaid
flowchart LR
    Curl[curl] --> API[FastAPI]
    Browser[ブラウザ] --> Frontend[React / 開発用プロキシ]
    Frontend --> API
    Frontend -->|任意起動の報告欄| Updates[配送更新API / 専用ロール]
    Updates -->|更新用荷物の状態・イベント| DB
    API --> Loop[Agent Loop]
    Loop <--> LLM[ホスト上のローカルLLM]
    Loop <--> Tools[読み取り専用Tools]
    Tools --> DB[PostgreSQL + pgvector]
    Tools --> RAG[RAG / CPU埋め込み]
    RAG --> DB
    Docs[文書の正本] --> Ingest[手動ingest]
    DB -->|問い合わせ正本| Ingest
    Ingest -->|派生索引| DB
```

業務テーブルが顧客・荷物・配送イベント・問い合わせの正本、`seed/docs`のMarkdownが文書の正本です。チャンクと埋め込みは再生成可能な派生データです。過去問い合わせの検索結果から、IDで正本を取得します。

ORMはSQLAlchemy、マイグレーションはAlembic、テストはpytestを採用します。構成の詳細と検証範囲は[設計書](docs/design.md)に記載しています。

## 実装済みのTool

| Tool | 動作 |
|---|---|
| `search_customers` | `customer_name`・`branch`の部分一致で候補を返し、営業所を絞り込める |
| `search_shipments` | `customer_id`・`shipment_id`・`status`で条件検索。`scope=all`で全体の概要・内訳を取得 |
| `get_shipment_details` | 荷物IDで状態と配送イベントを取得。関連する障害IDを返す |
| `get_inquiry` | `inquiry_id`から問い合わせの正本と対応内容を取得 |
| `search_knowledge` | 文書・問い合わせの派生チャンクをベクトル検索。種類と荷物・障害IDで絞り込める |

登録済みToolのみを呼び出し、Pydanticで未知フィールド・不正な型・空の条件を拒否します。数値文字列やboolをIDへ自動変換しません。顧客名の`%`・`_`はワイルドカードではなく文字として検索します。同名候補を任意に選ぶ処理はありません。

結果は`records`、取得済みレコードを識別する`sources`、省略を示す`truncated`を持ちます。`search_shipments`は検索条件に一致するDB上の総件数`total_count`も返し、取得した例の件数と区別します。`scope=all`では状態別の総件数`status_counts`も返します。検索件数は既定10・最大20、配送イベントは既定20・最大20、本文は各項目2,000文字に制限します。空の検索結果は正常結果です。DB例外は公開用コードに置き換え、各Toolに15秒のタイムアウトを設けます。DBセッションはToolの処理内で閉じます。

Toolを個別のHTTP APIとして公開せず、Agent Loopから呼び出します。`search_knowledge`にはロード済みの埋め込みモデルを渡します。業務Toolだけを使う場合はモデルをロードする必要はありません。

## Agent Loop

`src/logi_scope/agent.py`でLLM応答・Tool実行・最終応答を分離しています。LLMが操作を選び、呼び出しIDに対応する結果を次のLLM要求へ戻します。問い合わせ別の固定フローはありません。

- LLM呼び出しとTool試行数を別々に制限。不正・重複も予算を消費します。
- 質問・取得結果にない荷物ID・顧客IDでの検索を拒否し、対象未指定では追加情報を求めます。
- 引数修正は1回。同じ操作は正規化した引数で検出し、成功結果を再利用します。
- 無進展の反復・例外・時間超過では停止し、履歴と未解決事項を返します。
- 顧客検索が複数候補または省略ありの場合は停止し、特定に必要な情報を求めます。
- `steps`は実行側で生成し、根拠は取得済みIDへ照合。問い合わせチャンクの引用には正本の取得・引用も必要です。

打ち切り後の回答専用LLM呼び出しは最大1回で、全体の時間制限内に収めます。最終化も失敗した場合は制御された応答を返します。初期値と詳細は[設計書](docs/design.md#6-agent-loop)を参照してください。偽LLMの制御テストと、実モデルによるA〜Eの受入確認を分離しています。

## 画面から試す

[セットアップガイド](docs/getting-started.md)に従って起動し、ブラウザで `http://localhost:5173` を開きます。サンプル質問を選び、「調査する」を押すと、回答・根拠・Tool履歴・未解決事項を確認できます。質問は直接入力でき、Ctrl/Cmd+Enterでも送信できます。

配送更新を試す場合は[更新デモの準備](docs/delivery-updates.md#実行手順)を行い、「配送状況の報告（デモ）」から専用荷物の状態を報告します。その後「更新用荷物を調べる」→「調査する」で、更新が回答へ反映されることを確認できます。

## APIを直接呼ぶ

React画面と同じ調査APIを、curlからも利用できます。

```bash
curl -X POST http://localhost:8000/agent \
  -H 'Content-Type: application/json' \
  -d '{"question":"デモ青空商店の荷物が遅延している原因は？"}'
```

応答は`answer`（回答）、`sources`（照合済み根拠）、`steps`（実行操作）、`unresolved`（未解決事項）。Toolを何回・どの順で使うかは利用者が指定しません。入力不正は422、LLM接続障害は502、初回LLM時間超過は504、未準備・実行中は503です。回答不能・曖昧性・制御された部分回答は200で未解決事項を返します。

## デモシナリオ

| シナリオ | 確認する振る舞い |
|---|---|
| A: 単純検索 | 業務データによる回答、根拠、実行履歴 |
| B: 複数段階の調査 | 前段の結果を利用し、業務データと報告文書を統合 |
| C: 非構造化検索 → 正本取得 | 類似問い合わせの検索後、対応する正本を追加取得 |
| D: 回答不能 | 存在しない荷物を捏造せず、未解決事項を返す |
| E: 曖昧性 | 同名顧客を勝手に選ばず、追加情報を求める |

架空データは`seed/business.json`と`seed/docs/*.md`にあります。質問例は[セットアップガイド](docs/getting-started.md#db準備)に記載しています。実接続の確認には下記の検証スクリプトを使用します。[受入条件](docs/requirements.md#9-デモシナリオと受入条件)

## セットアップ・データ準備・起動

Docker Engine・Composeと、ホスト上のOllamaが必要です。[セットアップガイド](docs/getting-started.md)で検証環境、モデル取得、WSLの待ち受け設定、UID/GID、DB権限を説明しています。先にホスト上のモデルを準備してください。

```bash
git clone https://github.com/philippos2/logi-scope.git
cd logi-scope
cp .env.example .env
mkdir -p artifacts
# .envの4つのパスワードとLOCAL_UID/LOCAL_GIDを編集
docker compose up -d --build
docker compose run --build --rm manage init
docker compose run --rm manage seed
docker compose run --build --rm ingest
docker compose exec app bash
```

コンテナ内の作業場所は`/home/developer/work/logi-scope`。ホストのソースをマウントし、非rootユーザーと`/opt/venv`で作業できます。続けてコンテナ内でAPIを起動します。

```bash
uv run --locked uvicorn logi_scope.api:app --host 0.0.0.0 --port 8000 --reload
```

API起動完了後、[React画面の起動手順](docs/getting-started.md#フロントエンド開発基盤)に従い、ブラウザから調査します。APIを直接確認する場合は、ホスト側の別のターミナルから上記のcurlを実行できます。`GET /health`は生存確認のみ。モデルはGitやアプリイメージに含めず、LLMはOllama側、CPU埋め込みモデルはDockerのキャッシュへ置きます。業務DB・文書が正本で、ingestは問い合わせと文書から索引を再生成します。画面・更新サービスを含む全体停止は`docker compose --profile frontend --profile updates down`、`-v`を付けるとDBと埋め込みキャッシュを削除します。

配送イベントの更新を試す場合は[更新デモ手順](docs/delivery-updates.md#実行手順)を参照してください。通常の90件のデータとは別に、更新用荷物を1件作成します。

React画面の起動方法は[フロントエンド開発基盤](docs/getting-started.md#フロントエンド開発基盤)を参照してください。

## テスト

[単体テスト分類表](docs/test-catalog.md)と[要件と単体テストの対応表](docs/requirements-test-matrix.md)で、確認対象・依存・検証範囲を整理しています。

```bash
docker compose exec app uv run --locked pytest
```

通常のテストは外部サービスなしで実行します。実DBテストは既定でスキップし、DB準備後に管理サービスで明示的に実行します。

```bash
docker compose run --rm --entrypoint uv -e LOGISCOPE_DB_TESTS=1 manage run --locked pytest
docker compose run --rm --entrypoint uv manage run --locked alembic check
```

DBテストは実PostgreSQLで、ORMの関連取得・同名候補・不存在・seed再実行・FK・pgvector拡張・読み取り専用ロールを確認します。書き込み拒否はトランザクションのread-only設定を解除してもDB権限で拒否されることを検証します。テスト用の更新はロールバックします。管理認証情報はアプリサービスに渡しません。

実埋め込みモデル単独の検証は[ガイド](docs/getting-started.md#ragの準備と事前検証)のスクリプトで分離します。自動テストと実接続の実測結果は[検証記録一覧](docs/history/README.md)を参照してください。

実モデル・API・DB・RAGを通したA〜Eの確認は、API起動後に実行します。

```bash
docker compose exec app uv run --locked python scripts/verify_demo.py --repeat 2
```

自動判定は根拠ID・Tool依存・期待語句と、既知の否定・矛盾表現を確認する補助チェックであり、回答の意味の正しさを保証しません。`passed`は自動チェックの成功を表し、受入合格の確定ではありません。各結果の`manual_review_required`と`manual_review_check`に従って公開回答を正本と照合し、人による確認結果も記録してください。特にBは対象荷物の原因がセンサー故障による安全停止と一致すること、Cは問い合わせ501の配達完了時刻11:15（日本時間）と確認方法を反映し、受領確認の実施を断定していないことを確認します。

公開応答とケース別判定はGit対象外の`artifacts/demo-verification.json`へ保存します。内部推論・生LLM応答は保存しません。実測結果と修正経緯は[検証記録一覧](docs/history/README.md)にまとめています。

Pythonの静的検査（src・tests・scripts・migrations）:

```bash
docker compose exec app uv run --locked ruff check .
```

フロントエンドの静的検査・テスト・型チェック・ビルド:

```bash
docker compose exec frontend npm run lint
docker compose exec frontend npm test
docker compose exec frontend npm run build
```

偽APIを使い、重複送信・エラー・待機終了後の古い応答の扱いを確認します。CSSやレイアウトのスナップショットテストは作成しません。

## CI

[GitHub Actions設定](.github/workflows/ci.yml)で、main向けPR・mainへのpush・手動実行時にDockerビルド、RuffによるPython静的検査、空のDBへのマイグレーション、架空seed、全自動テスト、`alembic check`を実行します。標準Ubuntu runnerと使い捨てDBを使用し、GitHub Secretsの登録は不要です。

RAG統合テストには`tests/prepare_database.py`で決定論的なベクトルを準備します。実LLM・実埋め込みモデルの品質検証はCIに含めず、上記のローカル実接続検証で行います。テスト用索引の準備は実デモDBに対して実行しないでください。mainはGitHubのブランチ保護で、`Tests and migrations`と`Frontend tests and build`の成功を必須にしています。管理者にも適用し、PRブランチを最新のmainへ追従させてからマージします。PRは必要ですが、他人の承認は要求しません。ジョブ名の変更時は必須チェックの設定も更新してください。

フロントエンドは別ジョブでDockerイメージをビルドし、ESLintによるReact・TypeScript静的検査、TypeScriptの型チェックとViteのビルドを実行します。重要な送信・エラー・待機終了の振る舞いをVitestとReact Testing Libraryで検証します。見た目はブラウザで別途確認します。

## Known Limitations

- 検証対象は小規模な架空データ、5つの受入シナリオと追加の状態別検索・個別調査。任意の質問に対する品質保証ではありません。
- Agentの同時調査は1件。実行中の追加調査リクエストは503で返します。
- LLMは不要な追加検索を行う場合があります。回数・時間の上限で制御します。
- 実行速度・Tool Calling品質・日本語検索品質は採用モデルとホスト性能に依存します。
- 架空データのみを対象とする、単一利用者向けPoCです。Agentは読み取り専用で、任意起動の更新APIは更新用荷物だけを対象にします。
- ブラウザの「待機を終了」は通信の中断であり、サーバ側の調査停止を保証しません。
- 更新APIは認証なしのローカル実演専用です。報告後の回答は自動更新せず、再調査が必要です。結果不明時の再送用データはページの再読み込みで失われます。[更新デモの制限](docs/delivery-updates.md#画面から報告する)を参照してください。
- 認証、マルチテナント、ストリーミング、高度な検索改善、本番デプロイは対象外です。
- 参照元の検証だけで回答の事実性を完全保証するものではありません。
- 数値顧客IDの出所は検証しますが、すべてのID・回答の意味を完全に検証するものではありません。追加ケースの結果と修正は[検証履歴](docs/history/demo-data-expansion.md)を参照してください。

## 本番化する場合

利用者・組織ごとの認証と参照権限、個人情報保護、運用監視、負荷・信頼性評価、秘密管理、データ更新運用、モデル変更時の評価などが別途必要です。本PoCの実装範囲には含めません。

## 文書と開発用skills

- [セットアップ・実行ガイド](docs/getting-started.md)
- [要件・制約・受入条件](docs/requirements.md)
- [設計・技術選定・検証範囲](docs/design.md)
- [設計FAQ](docs/design-faq.md)
- [DBスキーマ・ER図](docs/database-schema.md)
- [配送イベント更新デモ](docs/delivery-updates.md)
- [フロントエンドUI設計](docs/frontend-design.md)
- [技術選定・検証の履歴一覧](docs/history/README.md)
- [最終確認チェックリスト](docs/final-verification.md)
- [AGENTS.md](AGENTS.md)
- [ローカルTool Calling検証skill](.agents/skills/verify-local-tool-calling/SKILL.md)
- [デモシナリオ検証skill](.agents/skills/verify-demo-scenarios/SKILL.md)

skillsは開発支援用の手順です。実行時Agentの機能ではありません。
