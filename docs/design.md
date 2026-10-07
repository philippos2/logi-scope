# LogiScope — 設計

状態: Agent API、Reactの調査・報告画面、専用APIによる配送更新デモは実装済み。選定・実測・修正経緯は[履歴一覧](history/README.md)を参照。決定論的テスト・実DB統合・実モデル評価を分離する。

## 1. 設計方針

[要件](requirements.md)に基づき、FastAPI・SQLAlchemy・Alembic・pytestを使用する。業務検索と文書・過去問い合わせの検索をToolとして提供し、取得結果から必要に応じて正本を取得する。

検索結果の統合と、存在しない事実の生成を区別する。類似事故報告だけで遅延原因を断定しない。5シナリオは必要な振る舞いを検証し、固定Tool順序を実装しない。

## 2. 構成

```mermaid
flowchart TD
    Curl["curl: POST /agent"] --> API[FastAPI]
    Browser[ブラウザ] --> Frontend["React / 開発用プロキシ"]
    Frontend --> API
    Frontend -->|報告 / updates-api| Updates[専用配送更新API]
    Updates -->|専用更新ロール / 状態・イベント| DB
    API --> Loop[Agent Loop]
    Loop <--> Client[LLMクライアント]
    Client <--> LLM["ホスト上のローカルLLM / OpenAI互換API"]
    Loop --> Tools["Tool登録・引数検証・実行"]
    Tools --> ORM[SQLAlchemy]
    Tools --> Retrieve["RAG retrieve / CPU埋め込み"]
    Retrieve --> ORM
    ORM -->|Agentは読み取りロール| DB["PostgreSQL + pgvector"]
    Docs["seed/docs のMarkdown正本"] --> Ingest["手動ingest CLI / CPU埋め込み"]
    DB -->|問い合わせ正本を読む| Ingest
    Ingest -->|派生データを書き込む| DB
    Seed[架空業務データ投入CLI] --> DB
    Loop --> Response["参照元検証 / answer, sources, steps, unresolved"]
    Response --> API
```

業務テーブルと文書が正本。DB内のchunksは派生インデックス。ingestはAPIとは別プロセスで手動実行する。バックグラウンドジョブ基盤は導入しない。

## 3. 技術と選定理由

| 役割 | 採用方針 | 理由 |
|---|---|---|
| API | FastAPI | 入出力検証とHTTP APIを簡潔に構成できる |
| 検証 | Pydantic | API・Tool引数・応答契約を型で定義する |
| ORM | SQLAlchemy | 関連・トランザクション・pgvector検索を一貫して扱う |
| DB変更 | Alembic | 再現可能なマイグレーション |
| DBドライバー | Psycopg 3 | PostgreSQL接続と非同期処理 |
| ベクトル連携 | pgvector-python | SQLAlchemyのベクトル型・距離式 |
| LLM通信 | HTTPX | OpenAI互換HTTP APIを薄いアダプターで扱う |
| 埋め込み | Sentence Transformers | CPUで日本語対応モデルを実行する |
| テスト | pytest / pytest-asyncio | fixture・パラメーター化・非同期の振る舞い検証 |
| 静的検査 | Ruff / ESLint | PythonとReact・TypeScriptの問題をテスト前に検出する |
| 起動 | Docker Compose | アプリとDBの再現性。LLMはホスト側 |

依存管理はuvを採用する。`pyproject.toml`で依存範囲を定義し、`uv.lock`で解決済み版を固定する。Docker内の`/opt/venv`に`uv sync --locked`で導入し、ホストへのPythonパッケージ導入を必須としない。ORM・埋め込みを含む依存は導入済み。更新時にも互換性を確認する。

Agentフレームワークは本デモでは導入しない。狭いLoopだけを実装し、通信・ORM・検証・埋め込み等はライブラリを使う。依存関係は互換性を確認して固定し、更新時にも検証する。

アプリは公式PythonイメージのDebian slim系を使用する。Python 3の比較的新しい安定版を採用し、埋め込み関連を含む互換性を依存導入時に確認する。タグにPython版とDebianコードネームを明示する。DBはPostgreSQL＋pgvectorの専用イメージに分ける。Python要件・依存ロック・Dockerfile/Composeを実行設定の管理元とする。

開発コンテナはPython 3.13のbookworm slim系をdigestで固定し、DBもpgvector入りのイメージをdigestで固定する。実際の指定はDockerfileとdocker-compose.ymlを参照する。Python 3.13でCPU版PyTorch・Sentence Transformersの依存導入と実モデル動作を確認済み。`app`は非rootのシェル作業用に常駐し、必要なソース・テスト・seed・文書・設定ファイルだけを`/home/developer/work/logi-scope`へマウントする。ホストの`.env`・`.git`・`.local-data`はマウントしない。環境変数に加え、ファイル経由でも不要な資格情報を渡さない。CIで各サービスのファイルと環境変数の分離を確認する。管理用DBパスワードはDB・管理サービスだけへ渡し、アプリ・ingestには渡さない。LLMの接続先・モデル・有限の通信タイムアウトを環境変数で設定する。コンテナからホストのOllamaへ接続する。接続検証の実測結果は履歴を参照。

### 製品バージョンの管理

LogiScope全体の製品版は`pyproject.toml`の`project.version`を管理元とする。FastAPIのOpenAPI情報はインストール済みPythonパッケージの版を取得し、固定文字列を重複させない。frontendは同じ製品版を`package.json`に設定し、`package-lock.json`のルート情報も合わせる。製品版の変更後はuv・npmの標準コマンドでロックを更新する。ライブラリの版とは別に管理する。

Releaseを作成するときは、これらの表記・CI・受入結果を確認してから、そのmainコミットへ同じ版のGitタグを付ける。製品版はAPI入出力契約の独立した版番号ではない。

## 4. API契約

`POST /agent`に空でない日本語中心の`question`を送る。入力文字数上限は設定・検証する。会話セッションは本デモでは持たず、曖昧性がある場合は必要情報を含めた新しい質問を送る。

正常な調査結果はHTTP 200。回答不能や曖昧性、制御された部分回答も200とし、`unresolved`で区別する。入力不正は422。調査を成立させられないLLM接続障害等は適切な5xxで返し、成功結果を装わない。初回LLM接続/応答障害は502（`llm_unavailable`）、初回時間超過は504（`llm_timeout`）。未準備は503（`agent_not_ready`）、同時実行は503（`agent_busy`）。障害本文は`detail: {code, message}`とし内部例外やサーバー応答を返さない。単一利用者向けPoCとして実行中の追加リクエストは待ち行列へ入れず拒否する。

```json
{
  "answer": "対象を一意に特定できませんでした。顧客IDを指定してください。",
  "sources": [
    {"id": "customer:101", "kind": "customer", "record_id": 101},
    {"id": "customer:102", "kind": "customer", "record_id": 102}
  ],
  "steps": [
    {"tool": "search_customers", "args": {"customer_name": "顧客A"}, "ok": true}
  ],
  "unresolved": [
    {"code": "ambiguous_target", "message": "同名顧客が複数あります。", "details": {"required_fields": ["customer_id"]}}
  ]
}
```

これは契約例であり実行結果ではない。`sources`の`kind`に応じて`record_id`、`path`、`chunk_id`、正本への参照を持たせる。問い合わせ検索の場合はチャンクと正本の両方を追跡可能にする。本文は自然言語で対象ID等を示し、根拠の構造化情報はsourcesへ置く。問い合わせ正本の引用時は今回取得済みの対応チャンクも併記して検索経路を保持する。

`steps`はアプリ側で記録する。実行済みの成功/失敗だけを含め、`ok`は操作の成功を表す。失敗には公開用の分類コードを追加できるが、内部例外・スタックトレースは公開しない。未実行の引数拒否・キャッシュ再利用は実行履歴へ混ぜない。

`unresolved`は`code`、`message`、任意の`details`。想定コードは`not_found`、`ambiguous_target`、`insufficient_evidence`、`tool_error`、`invalid_tool_arguments`、`step_limit`、`no_progress`、`timeout`、`llm_error`。

荷物IDを使う業務Toolは、質問中に指定されたID、または成功したTool結果の荷物参照・問い合わせ・文書本文で確認できたIDだけを実行する。引数の型が正しくても出所のない荷物IDは検索せず、`ambiguous_target`と`required_fields: ["shipment_id", "customer_name"]`で追加指定を求める。この拒否は未実行なので`steps`へ記録しない。LLMは個別の荷物照会で対象情報が不足している場合、Toolを呼ばず追加指定を求めることもできる。検索せずに返した回答を受け入れられない場合は、Toolを利用できる再試行を1回だけ通常の呼び出し予算内で認める。顧客・問い合わせ等の数値ID全般や自然言語回答のすべての事実に対する完全な出所検証ではない。

`not_found`は検索対象が見つからなかった場合、`insufficient_evidence`は対象は存在するが必要な事実を確認できない場合に使う。復旧予定・配送再開時刻が未確定なら後者とする。空の検索結果を一度も観測していないのにLLMが`not_found`を返した場合、実行側が`insufficient_evidence`へ補正する。配送状態による一覧の0件は正常な検索結果であり、登録上の該当なしとして回答できる。0件だけを理由に未解決事項を追加する必要はなく、レコードの根拠がない場合はsourcesを空にし、stepsで検索条件を追跡する。空の検索結果がある場合の個別の意味判定はLLMに依存し、完全な分類保証ではない。

タイムアウト・Tool失敗・上限等の制御コードは実行側の観測に照合し、未発生のコードを含む最終回答は採用せず再生成する。同じコードでも内容の異なる未解決事項は保持し、完全に同じ項目だけを省略する。最終回答を生成できず最後の追加検索が空だった場合も、取得済みの根拠があれば`insufficient_evidence`とする。

## 5. Toolの構成方針

4つの業務Toolと`search_knowledge`を`src/logi_scope/tools.py`に登録した。検索にはロード済みの埋め込みモデルを渡す。能力を満たす範囲で分割は調整できる。

- `search_customers`: 名前等から候補を返す。複数候補を隠さない。
- `search_shipments`: 顧客ID・荷物ID・配送状態で検索する。状態だけで一覧・有無を調べられ、`scope=all`で全体の内訳も取得する。
- `get_shipment_details`: 配送状態・配送イベント・事故参照などを返す。
- `search_knowledge`: 文書と過去問い合わせチャンクを検索し、正本の識別情報を返す。
- `get_inquiry`: 問い合わせIDで正本を取得する。

PydanticモデルからTool引数スキーマを定義し、未知のTool・余分なフィールド・不正な型を拒否する。ORM検索の列や演算子をLLMへ自由指定させない。結果件数・本文長を制限し、省略があれば明示する。空の検索結果は正常、DB障害は失敗とする。

業務Toolの初期制限は検索件数10（最大20）、イベント20（最大20）、問い合わせ本文・対応内容とイベント説明を各2,000文字、Tool全体15秒。顧客検索・配送イベントは上限＋1件取得して省略を検出する。荷物検索はSQLAlchemyのウィンドウ集計`COUNT(*) OVER()`と例の取得を同じSQL文で実行し、同じDBスナップショットの総件数`total_count`と取得上限を比較して省略を検出する。全体検索では状態ごとの条件付きウィンドウ集計も同じSQL文に含め、`status_counts`を返す。0件では`total_count=0`、全体検索の状態別件数も0を返す。参照元は実際に返すレコードだけに付ける。配送イベントは新しい順に返す。Toolが返す業務日時は日本時間のISO 8601（+09:00）へ揃え、LLMのUTC変換間違いを避ける。DBにはタイムゾーン付き日時として保存する。顧客名の部分一致ではSQLワイルドカードをエスケープする。IDは厳密な正整数、荷物ID等は空白除去後の空文字を拒否する。未知Tool・引数不正は実行前に拒否し、Loopの1回修正処理へ接続済み。DB障害は`database_error`、時間超過は`timeout`として返せる例外型に変換する。

### 配送状態による調査

`search_shipments`は顧客ID・荷物IDに加え、`status`単独で状態別の一覧・有無を検索できる。複数条件はAND、件数上限と`truncated`は維持する。全体の概要・内訳は`scope=all`を明示して取得する。他の絞り込み条件との併用や、何も指定しない空の呼び出しは拒否する。個別照会で識別情報が不足する場合だけ追加指定を求める。自然言語からの条件・Toolの選択はLLMが行い、質問別の固定フローは追加しない。検索で得た荷物IDは、その後の配送イベント・報告書の取得に利用できる。

`missing`は所在不明として業務テーブルに登録済みの状態であり、遅延や古いイベントから推測しない。一覧はDB記録に基づき、実際の現在時刻の配送状態や全件取得を保証しない。検索条件に一致する総件数は`total_count`に基づいて回答し、`records`の件数から推測しない。全体検索の状態別件数は`status_counts`に基づいて回答する。取得したIDの一覧は`truncated=true`なら全件ではない。日時がある回答だけで日本時間を明示し、状態・件数に時差が適用されるという表現はしない。状態別検索の成功応答には、実行側が「現在の登録データに基づく回答です。」を付け、モデルの表現にかかわらず参照範囲を明示する。対象例と期待値は[追加データの案内](demo-data.md)を参照する。


## 6. Agent Loop

`src/logi_scope/agent.py`にLLMクライアントのProtocol、応答・操作履歴の型、Loopを実装した。`llm.py`にHTTPXによるOpenAI互換アダプターを実装。LLMクライアント、Toolレジストリ、結果・参照元の型、Loopを分離する。LLMが選んだToolを検証して実行し、呼び出しIDと対応する結果を履歴に戻す。実行結果の履歴はリクエストごとに保持する。

### 処理の流れ

LLMは次に使うToolと引数、または最終回答案を返す。Python側のLoopは、その案を検証し、許可されたToolだけを実行する。LLMがDBへ直接接続する構成ではない。

```mermaid
flowchart TD
    Start["質問・Tool定義・指示を準備"] --> Budget{"通常LLM回数・残り時間"}
    Budget -->|余裕あり| Ask["LLMへ質問と取得結果を送る"]
    Budget -->|上限・期限| Stop["終了理由を記録して通常調査を終了"]
    Ask --> Kind{"LLMの応答"}
    Kind -->|Tool呼び出し| Guard{"登録Tool・引数・IDの出所・試行上限を検証"}
    Guard -->|有効| Duplicate{"同じTool・正規化済み引数を試行済みか"}
    Guard -->|引数不正・修正可能| Feedback["公開可能な検証エラーをLLMへ返す"]
    Guard -->|修正失敗・上限・対象不明| Stop
    Duplicate -->|未試行| Execute["Toolを実行・成功または失敗をstepsへ記録"]
    Duplicate -->|試行済み| Reuse["再実行せず成功結果または既存の失敗を返す"]
    Execute --> Observe["呼出IDに対応する結果を履歴へ追加・取得済み根拠を保持"]
    Reuse --> Progress{"新しい処理が進んだか"}
    Observe --> Continue{"曖昧性・打ち切り条件"}
    Continue -->|継続可能| Budget
    Continue -->|調査を停止| Stop
    Progress -->|新しい処理もあり| Budget
    Progress -->|反復のみ| Stop
    Feedback --> Budget
    Kind -->|回答案| Validate{"形式・取得済み根拠・既知の整合性を検証"}
    Validate -->|有効| Response["公開JSONを組み立てて返す"]
    Validate -->|検索・正本の不足で修正可能| Repair["上限内で検索または正本取得の修正を求める"]
    Repair --> Budget
    Validate -->|その他の不正| Finish["残り時間内でToolなしの最終化を最大1回"]
    Stop --> Finish
    Finish --> FinalValid{"最終化が成功したか"}
    FinalValid -->|はい| Response
    FinalValid -->|失敗・時間なし| Fallback["取得済み根拠・steps・未解決事項で代替JSONを返す"]
    Fallback --> Response
    Kind -->|通信失敗・時間超過| Failure{"実行済みToolの履歴があるか"}
    Failure -->|あり| Fallback
    Failure -->|なし| Error["APIへ接続失敗を通知・502または504"]
```

図は制御の主要な分岐を示す。複数Toolが返った場合は逐次検証・実行し、結果をまとめて次のLLM要求へ渡す。引数不正・重複・予算超過で未実行の操作は`steps`へ追加しない。Tool実行時の失敗は`ok: false`として記録し、エラーをLLMへ返す。失敗しただけで必ず即終了するわけではなく、残り予算と停止条件に従う。

顧客が複数候補の場合は後続調査を止める。一方、対象情報が不足している質問では、Toolを実行せず追加指定を求める応答も可能。時間を使い切った場合は最終化のLLM呼び出しを行わず、代替応答へ進む。参照元照合・既知の表現の検証は、任意の回答の意味を完全に保証するものではない。

### 多段調査の実行例

「デモ青空商店の荷物が遅延している原因は？」という質問で、LLMが次の呼び出しを選んだ場合の例。これはコードに固定されたフローではなく、Tool結果を観測してIDを引き継ぐ仕組みを示す。

```mermaid
sequenceDiagram
    participant User as 利用者
    participant Loop as Agent Loop（Python）
    participant LLM as ローカルLLM
    participant Tools as 読み取り専用Tools
    participant DB as PostgreSQL / pgvector
    User->>Loop: 自然言語の質問
    Loop->>LLM: 質問・Tool定義・指示
    LLM-->>Loop: search_customersの呼び出し案
    Loop->>Tools: 検証後に顧客検索
    Tools->>DB: 顧客を検索
    DB-->>Tools: 顧客101
    Tools-->>Loop: レコード・根拠
    Loop->>LLM: 呼出IDに対応する検索結果
    LLM-->>Loop: customer_id=101でsearch_shipments
    Loop->>Tools: 検証後に荷物検索
    Tools->>DB: 顧客101の荷物を検索
    DB-->>Tools: SHP-DEMO-001
    Tools-->>Loop: レコード・根拠
    Loop->>LLM: 荷物検索結果
    LLM-->>Loop: get_shipment_detailsの呼び出し案
    Loop->>Tools: 荷物状態・配送イベントを取得
    Tools->>DB: 同じスナップショットで取得
    DB-->>Tools: 遅延・障害INC-DEMO-001への参照
    Tools-->>Loop: レコード・根拠
    Loop->>LLM: 配送詳細の取得結果
    LLM-->>Loop: 障害IDを使うsearch_knowledgeの呼び出し案
    Loop->>Tools: 関連文書を検索
    Note over Tools: CPUで検索語を埋め込み
    Tools->>DB: 障害IDで絞り、ベクトル検索
    DB-->>Tools: 障害報告のチャンク
    Tools-->>Loop: 本文・正本パス・チャンクID
    Loop->>LLM: 文書の検索結果
    LLM-->>Loop: 回答案・根拠ID・未解決事項
    Loop->>Loop: 応答形式と取得済み根拠を照合
    Loop-->>User: answer / sources / steps / unresolved
```

Loopが次のToolを決めるのではなく、LLMが取得した情報を使って呼び出しを選ぶ。Loopは、顧客101や障害IDなどの取得結果を次の要求へ渡し、引数・IDの出所・権限・上限を管理する。各ToolのDB接続は処理内で閉じ、LLMの応答待ち中にトランザクションを保持しない。

履歴には公開するTool操作だけを保持し、Chain-of-Thoughtは含めない。最終回答の`steps`は実行側が作り、`sources`は取得済み参照元に照合する。LLMがもっともらしい履歴や未取得の根拠を生成しても、そのまま公開応答には採用しない。

| 制御 | 方針 |
|---|---|
| 上限 | LLM呼び出し回数とTool呼び出し試行数を別々に数える。不正・重複も予算を消費する |
| 引数修正 | 検証エラーをTool結果として返す。1件の不正呼び出しに対する修正機会は1回。LLM呼び出しは全体上限に算入 |
| 重複 | Tool名＋検証・正規化した引数でリクエスト内比較。成功結果は再利用、無進展の反復は終了 |
| 失敗 | 公開可能なエラー分類をLLMに返す。無制限な再試行をしない |
| 時間 | 全体・LLM・DB/Toolに有限の期限。設定可能とし遅いローカル推論に合わせる |
| 複数Tool | 本デモは逐次実行。対応する呼び出しIDと結果を維持し、残り予算を超える呼び出しは実行しない |
| 最終応答 | LLMの回答・未解決事項を検証し、実行側のstepsと取得済みsourcesを合わせる |
| 打ち切り | 新たなTool実行を止める。残り時間内の回答専用LLM呼び出しは最大1回、追加呼び出しと明示して扱う |

最終化も失敗した場合は、取得済み参照元・stepsと終了理由を使った制御されたフォールバックJSONを返す。LLMが生成していない原因説明をアプリ側で創作しない。

LLM最終応答の内部契約は`answer`、`sources`（根拠IDの配列）、`unresolved`のみ。余分な`steps`や未知フィールド、未取得の根拠IDは拒否する。API向けの`AgentResponse`は照合済みのSource詳細と実行側のStepを持つ。JSON重複キー・非有限数・コードフェンス付きの出力は黙って修復しない。最終応答の再生成は最大1回。

回答に付けるsourcesは取得済みレジストリに照合する。問い合わせ正本を引用するときは、その正本へ対応する今回取得済みの検索チャンクを自動で追加する。この照合は参照元の存在を確認するもので、回答の事実性の完全保証ではない。日本語シナリオの受入確認で事実との一致を検証する。

初期制限は`Limits`で管理し、通常LLM呼び出し8回、Tool試行12回、全体900秒、LLM要求300秒、Tool15秒。回答専用の追加1回も全体期限を超えない。リクエストごとに状態・キャッシュ・根拠を分離し、呼び出し元のキャンセルを伝播する。通信障害・タイムアウトでまだ操作を実行していない場合は`AgentUnavailable`とし、APIで502/504へ変換する。操作済みなら履歴と`llm_error`等を持つ部分応答を返す。

引数不正は同じToolに対する未修正状態を管理し、1回の修正でも不正なら停止する。未実行の拒否や成功キャッシュ再利用をstepsへ混ぜない。失敗した同一操作も再実行せず、無進展なら終了する。Tool結果は呼び出しIDと対応させ、残り予算を超えるバッチ内操作には未実行を返す。

顧客名・営業所はSQLワイルドカードをエスケープした部分一致で検索する。営業所の略記で候補が複数残る場合も勝手に選択しない。顧客検索が複数候補または候補省略を返した場合は調査を停止し、顧客ID・営業所を求める。LLMが任意候補を選んだ回答も採用せず、制御された曖昧性応答を返す。候補の一覧取得を継続する会話は本デモでは持たない。問い合わせチャンクを回答根拠にする場合は、対応する正本の取得と根拠への採用を必須にする。取得済みsource.idと派生データのorigin_id/source_keyの混同、または正本の引用不足を検出した場合には、取得済みの根拠IDと必要な正本の参照IDをフィードバックし、通常のLLM回数・時間上限内で一度だけToolを使える修正機会を与える。正本の取得・引用または文書正本だけに基づく回答への修正はLLMが選択する。この検証は問い合わせ別のTool順序を固定するものではない。

顧客IDを使うTool呼び出しは、質問で顧客IDとして明示された数値、取得済みの顧客参照、または取得結果の`customer_id`に照合する。無関係な荷物番号や日時の数値では許可しない。未取得の顧客IDはDB検索前に拒否し、既存の引数修正1回・回数上限の範囲で修正を求める。

回答本文に肯定形の「未確定」があるのに`unresolved`が空の場合、最終化で、質問された不足事項の報告または不要な補足の削除を求める。それでも整合しなければ回答完了として採用しない。この文字表現の検証は限定的であり、任意の日本語表現から不足を完全判定するものではない。

LLMには実行側が保持した数値顧客IDと全体集計を再提示し、集計値が例の上限に依存しないことをTool結果にも明記する。任意の文書本文やユーザー入力をsystem指示へ昇格させず、質問別の固定フローを追加しない。

文書やTool結果はデータであり命令ではない。システム方針・利用者質問・Tool結果をメッセージの役割で区別する。内部推論は保存・公開せず、生LLM応答を丸ごとログへ書かない。

確認方法の案内と、確認を実施した事実を区別する。問い合わせ501の「配達完了時刻を確認する」という案内や配送イベントの完了時刻だけを根拠に、受領確認の実施・受領済みを断定しない。実モデルの確認では時刻の一致に加え、この意味の違いも確認する。

現在のデモの荷物Tool結果には`expected_delivery_basis`を付ける。遅延・所在不明では`original_schedule`とし、日時を`original_expected_delivery_at`として返し、当初の登録予定として扱う。それ以外は`registered_schedule`とし、日時は`expected_delivery_at`で返す。いずれも到着を確約する値ではない。変更後の予定日時は、別の根拠がない限り未確定である。日時を質問されていない場合は補足しない。この区別は現在のseedと、到着予定を変更しない配送更新デモの方針であり、将来予定変更を実装する場合は予定の版・変更履歴を別途設計する。

引用した荷物の当初予定の時刻を予定として回答しながら、当初・登録時・変更前の区別を欠く表現は、最終化で修正または不要な日時の省略を求める。修正後も同じ表記漏れがあれば採用しない。この検証は取得済み時刻と代表的な表現の照合であり、任意の言い換えや複数荷物への対応を完全に判定するものではない。

HTTPXで`/v1/chat/completions`へ非ストリーミング要求を送る。temperature 0、出力上限は既定1,200トークン。通常はtoolsを渡し、回答専用要求はtoolsなし＋JSON出力指定とする。応答はサイズ制限を設け、途中切れ・不正な形式・重複Tool ID・明示的なthinkタグを拒否する。reasoning/reasoning_content等はLoopへ渡さず保存もしない。HTTP接続・応答障害は公開コードへ変換する。

FastAPI lifespanで読み取り専用エンジン・HTTPクライアント・CPU埋め込みモデルを準備し、終了時にHTTPとDBを閉じる。管理資格情報を使用しない。モデルロードはワーカースレッドで行う。実行制限はSettingsとCompose環境変数で変更できる。

## 7. DB・権限

業務モデルは顧客、荷物、配送イベント、問い合わせ。Bの事故報告は対象荷物の配送イベントと共通の架空事故ID等で結び付け、拠点・時刻も整合させる。文書内の事故IDはファイル正本への論理参照でありDBのFKではない。

業務4テーブルをSQLAlchemyの型付きDeclarativeモデルで実装した。関連は暗黙の遅延ロードを禁止し、必要な関連をクエリで明示取得する。日時はタイムゾーン付き。荷物状態はDBのCHECK制約、関連IDはFKで検証する。顧客名は一意制約を付けず、同名候補を保持する。

Alembicは業務テーブル・pgvector拡張・実行用ロールのDDLを管理する。ロールのパスワードはマイグレーションへ固定せず、管理CLIが環境変数から設定する。実行用接続は`logi_scope_reader`に固定し、SELECTのみ付与する。DDL・認証設定だけをSQLで扱い、業務seed・検索はORMを使う。

`manage`はComposeの明示実行サービスで、管理資格情報を持つ。初期PoCではマイグレーションとseedを同じ管理ロールで行い、ランタイムから分離する。ingestは別サービス・別ロール`logi_scope_ingest`を使用し、問い合わせのSELECTとchunksのSELECT/INSERT/UPDATE/DELETEだけを付与する。業務更新とDDLは許可しない。アプリはchunksを含めSELECTのみ。業務seed再実行は既知IDの更新とし、全件削除はしない。DBへの反映は1トランザクションで行う。

chunksには本文、種別、文書パスまたは問い合わせFK、チャンク番号、正本の更新識別子、埋め込みモデル識別子、ベクトルを持たせる。問い合わせ由来と文書由来の参照を制約で区別する。ベクトルは採用したmultilingual-e5-baseの768次元。由来はCHECK制約、問い合わせは削除時CASCADEのFKで管理する。source_keyとチャンク番号は一意。

- 実行用: 必要な業務・検索テーブルのSELECTのみ。所有者・スーパーユーザーにしない。
- seed/ingest用: 必要な投入・派生更新権限。アプリの環境へ渡さない。
- マイグレーション用: スキーマ・拡張・権限管理用。

DB Sessionは短いTool処理内で閉じる。LLM待ちの間は保持しない。並行処理で同一AsyncSessionを共有しない。本デモのTool実行は逐次。

## 8. RAGと再生成

採用モデルは`intfloat/multilingual-e5-base`（MIT）。日本語を含む公式検索評価とSentence Transformers対応、CPUでの負荷を考慮して選定した。モデルのcommit、768次元、query/passageプレフィックス、L2正規化、512トークン上限を`rag/embeddings.py`に記録する。モデル本体はGit対象外のDocker named volumeにキャッシュする。LinuxのPyTorchはCPU配布インデックスを使用する。

文書・問い合わせを最大400文字のチャンクへ分割し、モデルのトークン上限を別途検証する。超過は黙って省略せず失敗させる。問い合わせ正本の読み取りSessionを閉じてからモデルをロード・埋め込みし、全ベクトル生成後にchunks全件を1トランザクションで置換する。モデル不一致の既存索引は検索で拒否する。検索種別と荷物/障害IDのフィルターを提供し、完全なコサイン距離検索をORMで行う。CPU計算は検索時にワーカースレッドへ移し、モデル呼び出しをロックで直列化する。タイムアウトは待機を中断するが、開始済みCPU処理を強制停止するものではない。

実モデルの検索品質と決定論的な制御テストは分離する。実測条件・結果は[基盤検証履歴](history/foundation-verification.md)、再現コマンドはREADMEと実行ガイドに記載する。

文書は`seed/docs/*.md`、問い合わせはDB正本から読み込む。文書は見出し・段落を基準にチャンク化し、問い合わせはIDと正本参照を維持する。

ingestとretrieveは同じ埋め込みモデル・版・次元・設定を使う。モデルが要求するquery/document用入力形式はそれぞれ遵守する。モデルはプロセス起動時にロードし、CPU処理をAPIのイベントループで直接長時間実行しない。

小規模なPoCでは近傍の完全検索から開始する。拠点・期間・文書種別の簡単なフィルター、業務IDの完全一致は許容する。リランキングや高度なハイブリッド検索は初期範囲に含めない。

本デモは全件再生成方式を基本とする。同じ入力で重複を増やさず、削除文書も反映する。埋め込みを生成し終えてから短いトランザクションで対象派生データを置換し、途中失敗で一部だけ公開しない。モデル変更時は必要なスキーマ変更と全件再生成を行う。

読み取りエンジンは`REPEATABLE READ`を使用する。Tool内の同じトランザクションで荷物と配送イベントを取得し、途中で更新がコミットされても単一Toolの結果は同じスナップショットに揃える。Tool終了時にセッションを閉じるため、次のToolは新しいスナップショットを取得する。LLM待ちの間はDB接続・トランザクションを保持しない。複数Tool間の観測時点の一致は保証しない。

### データ更新と埋め込み再計算

業務データの更新すべてに埋め込みの再計算が必要なわけではない。現在の構成では、荷物の配送状態や配送イベントをToolが業務テーブルから直接検索するため、これらだけの更新には埋め込みの再計算は不要である。更新のコミット後に行う検索で変更を参照できる。ただし、実行済みのTool結果や表示済みの回答を自動更新する仕組みはなく、調査全体で同一時点のDBスナップショットを保証するものでもない。

ベクトル検索対象の問い合わせ本文や文書を追加・変更した場合は、対応するチャンクと埋め込みを更新する必要がある。正本を削除した場合も、対応する派生データを除去する必要がある。現在のPoCでは自動追従・差分更新を実装せず、手動ingestで全件再生成する。正本の更新から再生成まで、検索用の派生データは最新とは限らない。実行手順は[実行ガイド](getting-started.md)を参照する。

将来、配送員などからのリアルタイム更新を追加する場合は、認証・権限を備えた更新APIに必要な書き込み権限を持たせ、Agentの読み取り専用ロールとは分離する。ベクトル検索対象も更新する場合は、変更・削除に追従する派生インデックスの更新方式を別途設計する。自動インデックス更新と配送員専用アプリは対象外である。ローカルの配送イベント更新デモは、別API・専用ロールで実装済みであり、Reactの報告欄またはcurlから利用できる。[配送更新デモ設計](delivery-updates.md)を参照する。

## 9. 検証

### ローカルLLMの事前検証

同じOpenAI互換エンドポイントで、日本語質問→Tool呼び出し→結果投入→最終回答、多段のID引き継ぎ、該当なし、複数候補、引数修正を小さなメモリ上の架空Toolで検証する。モデル名、サーバー版、量子化、コンテキスト、推論設定、ハードウェア、所要時間を記録する。数回繰り返して安定性を確認する。検証用の簡略データと完成デモのDB実装を区別する。

### 自動テスト

- 単体/制御: 偽LLMの規定応答で多段調査・引数修正・未知Tool・重複・例外・上限・不明・曖昧性を検証する。
- DB統合: 実PostgreSQL/pgvectorで検索、関連、正本参照、再ingest、読み取り権限を検証する。SQLiteで代替しない。
- 実LLM: A〜Eを実接続で確認する。自動テストの成功を実LLMによる自律選択の証明としない。

期待事実・根拠ID・必須の依存関係・未解決コードで判定し、文章や不要なTool順序を完全一致させない。実行した環境と結果を記録し、未実行を成功扱いしない。

自動判定は根拠ID・Tool依存・期待語句と、既知の否定・矛盾表現を確認する補助チェックであり、回答の意味の正しさを保証しません。`passed`は自動チェックの成功を表し、受入合格の確定ではありません。各結果の`manual_review_required`と`manual_review_check`に従って公開回答を正本と照合し、人による確認結果も記録してください。特にBは対象荷物の原因がセンサー故障による安全停止と一致すること、Cは問い合わせ501の配達完了時刻11:15（日本時間）と確認方法を反映し、受領確認の実施を断定していないことを確認します。 正規表現による矛盾検出は既知のケースに限定し、表現の網羅や一般的な事実検証を主張しない。

### CI

GitHub Actionsの標準Ubuntu runnerで、main向けPR・mainへのpush・手動実行を対象にDockerビルドと全自動テスト、マイグレーション差分を確認する。既存Composeとuv.lockを使用し、ローカルと別の依存定義を作らない。CIは使い捨てDBへinit・seedを実行し、限定権限のingest接続で決定論的なテスト用チャンクを投入する。実LLM・実埋め込みモデルをロードせず、意味検索の品質はローカル受入検証へ分離する。GitHub Secretsは不要。実行上限20分、重複実行のキャンセル、終了時の検証用ボリューム削除を設定する。

PythonはRuffの`E4`・`E7`・`E9`・`F`でsrc・tests・scripts・migrationsを検査する。frontendはESLintのflat configでJavaScript・TypeScriptの推奨ルール、React HooksとFast Refreshのルールを使う。警告もCIを失敗させる。設定と解決済みの版はpyproject・uvロック、frontendの設定・packageロックで管理する。CIの既存2ジョブに組み込み、ジョブ名は維持する。

mainのブランチ保護は`Tests and migrations`と`Frontend tests and build`をGitHub Actions由来の必須チェックに指定する。最新mainへの追従を要求し、管理者にも適用する。PRは必須、他人の承認数は0。強制pushとmainの削除を許可しない。GitHub側の設定であり、cloneだけでは再現されない。ジョブ名変更時は必須チェックも更新する。

## 10. ディレクトリ方針

```text
logi-scope/
  AGENTS.md
  README.md
  docs/{requirements,design}.md
  .agents/skills/<skill-name>/SKILL.md
  src/logi_scope/              # API、Loop、Tools、DB、RAG、設定
  frontend/                   # React画面・依存・ビルド設定・画面テスト
  tests/                      # 決定論的・DB統合テスト
  seed/docs/                  # 架空文書の正本
  migrations/                 # Alembic
  scripts/                    # 必要になった検証・準備用CLI
```

バックエンドのディレクトリ構成は実装済み。`src/logi_scope/db`に業務モデルと実行用接続、`manage.py`に明示実行する管理CLI、`migrations`にAlembic、`seed`に架空データと文書、`tests/integration`に実DB検証を置く。`tools.py`に登録済み業務Toolと型を実装。`rag`に文書分割・CPU埋め込み・ingest・検索を実装。`agent.py`に偽LLMで検証可能なLoop制御を実装。`llm.py`に通信アダプター、`api.py`に起動・終了管理とAgent API、`updates_api.py`と`delivery_updates.py`に専用更新APIとトランザクション処理を実装。秘密値は環境変数へ置き、`.env.example`にはダミー値だけを書く。

## 11. API版の実装工程（完了）

1. 設計文書・作業指針・検証skillsを公開する。
2. ホスト環境を確認し、ローカルLLMのTool Callingを検証する。
3. DBモデル・マイグレーション・権限・架空seedを準備する。
4. 業務Toolsとテストを実装する。
5. 文書/問い合わせingest・検索を実装する。
6. 偽LLMを使ってLoop制御とテストを実装する。
7. APIを統合し実LLMでA〜Eを検証する。
8. Docker再現手順、デモ実行例、制限、検証結果をREADMEへ反映する。

## 12. フロントエンド

画面構成・状態・API対応・検証方針は[フロントエンドUI設計](frontend-design.md)を参照する。

同じリポジトリの`frontend/`にReactのデモ画面を実装済み。Python側とは依存管理・ビルド・テストを分離する。既存のAPI契約を使用し、質問入力、5シナリオの質問例、実行中表示、回答・根拠・Tool履歴・未解決事項、エラー表示を最小範囲とする。モデルやDBへブラウザから直接接続しない。

非ストリーミングAPIのため、実行中は待機表示のみとし、Tool履歴は応答後に表示する。開発基盤はReact＋TypeScript＋Vite、Node.js 24 LTSの公式Debian bookworm slimイメージを採用。Reactは表示、TypeScriptはAPIデータの型確認、Viteは開発サーバー・ビルド・APIプロキシを担う。小規模な単一画面のためSSR・Next.js・ルーター・状態管理ライブラリは導入しない。依存範囲は`frontend/package.json`、解決済み版は`frontend/package-lock.json`、Nodeイメージは`frontend/Dockerfile`で管理する。

Composeのfrontendプロファイルに非rootのシェル作業用コンテナを追加し、5173番をlocalhostに限定して公開する。`/api`を既存FastAPIへ転送し、プロキシの期限は960秒とする。モデル・DB認証情報はfrontendへ渡さない。配送状況の報告欄は専用updatesサービスへ別のプロキシで接続し、AgentのToolによる更新は行わない。再送・受付結果の扱いは[UI設計](frontend-design.md)と[配送更新デモ](delivery-updates.md)に記載する。CIは別ジョブでイメージをビルドし、型チェックとViteビルドを実行する。画面は`App.tsx`、表示部品`Results.tsx`、API通信・形式確認`api.ts`、要求管理`useInvestigation.ts`に分ける。画面側も960秒の期限とAbortControllerを使い、重複送信と古い応答の反映を防ぐ。Vitest＋React Testing Library＋Happy DOMで重要な振る舞いだけをテストし、CIに追加した。見た目はブラウザで確認する。

## 13. 検証範囲と任意の改善

API・React画面と5シナリオの実装・受入確認は完了した。以下は既知の制限と将来の改善であり、今回のデモ完成に必須の未実装工程ではない。条件と実測は[検証履歴](history/README.md)、現在の実行手順は[実行ガイド](getting-started.md)を参照する。

### 未検証の範囲

- 第三者のホストに必要な最小スペック。確認したホストは必要最小構成を意味しない。
- WSL以外のOSでのDockerからホストLLMへの接続手順。
- 実機スマホ・Safari。PCブラウザでのスマホ幅と、利用者の実日本語IME操作は確認済み。
- 採用モデルに対するデモ以外の質問・データや、新しい文書への日本語RAG品質。モデル変更時は同条件で再検証する。

### 任意の改善

- 別のモデル・ホスト性能に合わせた回数・時間制限の調整。
- 回答本文の主張と根拠の対応をさらに細分化すること。現在は対象IDとsourcesで追跡する。
- 問い合わせIDなど、対象の出所検証の拡張。現在の荷物ID・顧客ID検証を、すべての事実の完全保証とは扱わない。

認証・本番デプロイなどの対象外機能は[要件](requirements.md#13-対象外)に従う。未検証の品質・性能を保証しない。

### 公開コードのライセンス方針

ソースコードは公開するが、`LICENSE`は追加しない。既存のタグ・Releaseは維持する。配送更新APIと報告画面を追加した版は`v0.3.0`とした。Pythonとfrontendのパッケージ版は製品版に揃える。検証スクリプトの修正と動画・文書の整備を含む版を`v0.3.1`として公開している。タグ・GitHub Releaseは版表記を揃え、mainへの統合とCI成功を確認して作成する。releaseブランチは作成しない。これはデモの機能・受入確認とは別の判断事項であり、採用ライブラリ・モデルのライセンスとは区別する。

## 参考資料

- [Ruff: リンタ](https://docs.astral.sh/ruff/linter/)
- [typescript-eslint: 設定](https://typescript-eslint.io/packages/typescript-eslint/)
- [GitHub: ブランチ保護API](https://docs.github.com/en/rest/branches/branch-protection)
- [FastAPI: 非同期処理](https://fastapi.tiangolo.com/async/)
- [SQLAlchemy: Sessionの管理](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [Alembic: マイグレーション自動生成](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [pgvector-python: SQLAlchemy連携](https://github.com/pgvector/pgvector-python)
- [Ollama: OpenAI互換API](https://docs.ollama.com/api/openai-compatibility)
- [llama.cpp: Tool Calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)
- [multilingual-e5-base: 公式モデルカード](https://huggingface.co/intfloat/multilingual-e5-base)
- [Sentence Transformers: 埋め込み](https://www.sbert.net/docs/sentence_transformer/usage/usage.html)
- [pytest: fixtures](https://www.pytest.org/en/latest/explanation/fixtures.html)
