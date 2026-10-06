# LogiScope

**業務データとRAGを横断調査する Tool-calling Agent Loop のデモ。**

物流会社の架空データを題材に、自然言語の質問からLLMがToolを選び、結果を観測して次の調査を進め、根拠と未解決事項を返すことを目指します。案件獲得用ポートフォリオとして、Agentの設計・実装・検証を示すPoCです。

> **現在はAgent Loopの制御まで実装・検証済みです。** 業務Tool・RAG検索に加え、偽LLMによる多段調査とLoop制御を検証しています。実LLMクライアントとの統合と`POST /agent`は未実装です。以下のAgent API例は予定仕様で、現時点では実行できません。

## 示すこと

- 顧客・荷物・配送イベントの構造化検索と、日本語文書・過去問い合わせのRAG検索。
- 前段の検索結果を次のToolへ利用する複数段階の調査。
- 根拠付き回答とTool実行履歴。情報不足・曖昧性の明示。
- 引数検証、重複防止、例外処理、上限によるAgent Loopの制御。
- 有料クラウドLLMに依存しないローカル再現性。

問い合わせ別の固定処理フローを作るデモではありません。LLMが次の操作を選びます。モデル内部のChain-of-Thoughtは記録・公開しません。

## 構成と正本

FastAPI → Agent Loop → 読み取り専用Tools → PostgreSQL + pgvector。LLMはホスト上で実行し、OpenAI互換APIで接続します。

業務テーブルが顧客・荷物・配送イベント・問い合わせの正本、`seed/docs`のMarkdownが文書の正本です。チャンクと埋め込みは再生成可能な派生データです。過去問い合わせの検索結果から、IDで正本を取得します。

ORMはSQLAlchemy、マイグレーションはAlembic、テストはpytestを採用します。構成の詳細と未決定事項は[設計書](docs/design.md)に記載しています。

## 実装済みのTool

| Tool | 動作 |
|---|---|
| `search_customers` | `customer_name`の部分一致で候補を返す。`branch`で営業所を絞り込める |
| `search_shipments` | `customer_id`または`shipment_id`で検索。両方指定すると両条件で絞る |
| `get_shipment_details` | 荷物IDで状態と配送イベントを取得。関連する障害IDを返す |
| `get_inquiry` | `inquiry_id`から問い合わせの正本と対応内容を取得 |
| `search_knowledge` | 文書・問い合わせの派生チャンクをベクトル検索。種類と荷物・障害IDで絞り込める |

登録済みToolのみを呼び出し、Pydanticで未知フィールド・不正な型・空の条件を拒否します。数値文字列やboolをIDへ自動変換しません。顧客名の`%`・`_`はワイルドカードではなく文字として検索します。同名候補を任意に選ぶ処理はありません。

結果は`records`、取得済みレコードを識別する`sources`、省略を示す`truncated`を持ちます。検索件数は既定10・最大20、配送イベントは既定20・最大20、本文は各項目2,000文字に制限します。空の検索結果は正常結果です。DB例外は公開用コードに置き換え、各Toolに15秒のタイムアウトを設けます。DBセッションはToolの処理内で閉じます。

これらはPython内のToolであり、HTTP公開と実LLMへの接続はまだ行っていません。`search_knowledge`にはロード済みの埋め込みモデルを渡します。業務Toolだけを使う場合はモデルをロードする必要はありません。

## Agent Loop

`src/logi_scope/agent.py`でLLM応答・Tool実行・最終応答を分離しています。LLMが操作を選び、呼び出しIDに対応する結果を次のLLM要求へ戻します。問い合わせ別の固定フローはありません。

- LLM呼び出しとTool試行数を別々に制限。不正・重複も予算を消費します。
- 引数修正は1回。同じ操作は正規化した引数で検出し、成功結果を再利用します。
- 無進展の反復・例外・時間超過では停止し、履歴と未解決事項を返します。
- 顧客検索が複数候補または省略ありの場合は停止し、特定に必要な情報を求めます。
- `steps`は実行側で生成し、根拠は取得済みIDへ照合。問い合わせチャンクの引用には正本の取得・引用も必要です。

打ち切り後の回答専用LLM呼び出しは最大1回で、全体の時間制限内に収めます。最終化も失敗した場合は制御された応答を返します。初期値と詳細は[設計書](docs/design.md#6-agent-loop)を参照してください。偽LLMの検証であり、実モデルによるA〜Eの受入確認は後続です。

## API予定仕様

```bash
curl -X POST http://localhost:8000/agent \
  -H 'Content-Type: application/json' \
  -d '{"question":"顧客Aの荷物が遅延している原因を調べてください"}'
```

応答には`answer`、`sources`、`steps`、`unresolved`を含みます。Toolを何回・どの順で使うかを利用者が指定する必要はありません。

## デモシナリオ

| シナリオ | 確認する振る舞い |
|---|---|
| A: 単純検索 | 業務データによる回答、根拠、実行履歴 |
| B: 複数段階の調査 | 前段の結果を利用し、業務データと報告文書を統合 |
| C: 非構造化検索 → 正本取得 | 類似問い合わせの検索後、対応する正本を追加取得 |
| D: 回答不能 | 存在しない荷物を捏造せず、未解決事項を返す |
| E: 曖昧性 | 同名顧客を勝手に選ばず、追加情報を求める |

架空データは`seed/business.json`と`seed/docs/*.md`にあります。質問例は以下のDB準備節に記載しています。Agentの実行結果は実装と実LLM検証後に追加します。[受入条件](docs/requirements.md#9-デモシナリオと受入条件)

## セットアップ・データ準備・起動

Docker EngineとComposeが必要です。開発環境ではWSL2のUbuntu内へDocker Engineを直接導入し、Docker Desktopには依存しません。[Docker公式のUbuntu導入手順](https://docs.docker.com/engine/install/ubuntu/)を参照してください。リポジトリルートで`.env.example`を`.env`へコピーし、管理用・読み取り専用・ingest用のダミーパスワードを、それぞれ異なる値に変更してください。`LOCAL_UID`と`LOCAL_GID`はWSLユーザーの`id -u`と`id -g`に合わせます。

```bash
cp .env.example .env
# .envを編集してから起動
docker compose up -d --build
docker compose exec app bash
```

コンテナ内の作業場所は`/home/developer/work/logi-scope`です。ホストのリポジトリをマウントしているため、ここでのファイル編集はホストにも残ります。非rootユーザーで作業し、Python仮想環境`/opt/venv`が有効です。

```bash
# コンテナ内
python --version
pip --version
exit
```

`app`はシェル作業用に常駐します。依存は`pyproject.toml`と`uv.lock`からビルド時に導入し、仮想環境を`/opt/venv`へ置きます。[uvのDocker連携](https://docs.astral.sh/uv/guides/integration/docker/)を利用します。コンテナ内で依存を変更した場合は定義・ロックを保存し、再ビルドします。

```bash
# コンテナ内。変更後のロックを同期する場合
uv sync --locked
# APIを起動。開発用リロードを有効化
uv run --locked uvicorn logi_scope.api:app --host 0.0.0.0 --port 8000 --reload
```

別のWSL窓から`curl --fail http://localhost:8000/health`で`{"status":"ok"}`を取得できます。これはアプリの生存確認のみで、DB・LLMの接続状態やAgent完成を表しません。

DBはComposeネットワーク内の`db:5432`です。ホストへDBポートは公開していません。管理用の接続は次で行えます。

```bash
docker compose exec db psql -U logi_scope_admin -d logi_scope
docker compose ps
docker compose down
```

DBデータはnamed volumeに残ります。`docker compose down -v`はDBデータも削除するため、通常の停止には使いません。管理者の認証情報は`db`と明示的に実行する`manage`だけへ渡します。`ingest`は専用ロールの認証情報だけを持ち、業務データを更新できません。`app`は`logi_scope_reader`として接続し、業務4テーブルとchunksのSELECT権限だけを持ちます。業務テーブルの所有者・スーパーユーザーではなく、publicスキーマへのテーブル作成もできません。

業務テーブルの関係は[DBスキーマ・ER図](docs/database-schema.md)を参照してください。DBeaverからの接続手順も記載しています。

### DB準備

リポジトリルートのWSLシェルから実行します。管理サービスは常駐させません。

```bash
docker compose run --build --rm manage init
docker compose run --rm manage seed
```

`init`はAlembicで業務4テーブル・chunks・pgvector拡張・読み取り専用/ingestロールを作成し、`.env`の`POSTGRES_READER_PASSWORD`と`POSTGRES_INGEST_PASSWORD`を各ロールへ設定します。再実行しても適用済みマイグレーションは繰り返しません。新規マイグレーション追加後もこのコマンドで更新できます。

`seed`はSQLAlchemy ORMで架空顧客4件、荷物4件、配送イベント5件、問い合わせ2件を投入します。同じIDを更新する方式で、再実行しても重複を増やさず、他のIDを削除しません。seedファイルは初期投入用であり、投入後の業務データの正本はDBです。文書4ファイルはリポジトリ内の正本であり、検索チャンク・埋め込みは以下のingestコマンドで生成します。

| シナリオ | 用意したデータ／予定質問例 |
|---|---|
| A | 「SHP-DEMO-002の配送状態は？」（配達完了） |
| B | 「デモ青空商店の荷物が遅延している原因は？」（SHP-DEMO-001 → INC-DEMO-001 → 障害報告） |
| C | 「配達完了後の受領確認について、過去の問い合わせでの対応を調べて」（問い合わせ501の正本） |
| D | 「SHP-NOT-FOUNDの配送状態は？」（不存在） |
| E | 「デモ双葉商会の荷物を調べて」（同名2顧客、異なる営業所） |

これらはデータ準備と予定質問であり、完成Agentによる合格結果ではありません。復旧予定・配送再開時刻が未確定という情報不足も含みます。

### RAGの準備と事前検証

CPU版PyTorchとSentence Transformersを使います。埋め込みモデルは`intfloat/multilingual-e5-base`、768次元、MITライセンス。[公式モデルカード](https://huggingface.co/intfloat/multilingual-e5-base)に従い、日本語でも検索質問に`query: `、索引本文に`passage: `を付け、L2正規化します。版と設定は`src/logi_scope/rag/embeddings.py`で固定し、ingestと検索で共有します。

```bash
# モデルを取得し、メモリ上の架空データで検索を検証
docker compose exec app uv run --locked python scripts/verify_embeddings.py
# 管理用サービスとは別の、限定権限のサービスで派生データを生成
docker compose run --build --rm ingest
# 実モデル＋実PostgreSQLの検索と問い合わせ正本取得を確認
docker compose exec app uv run --locked python scripts/verify_rag.py
```

モデル本体はDockerの`embedding_cache` named volumeに保存し、Gitやアプリイメージに含めません。`docker compose down -v`はDBとモデルキャッシュの両方を削除します。初回のみモデルの取得が必要で、匿名のHugging Face取得に対応します。トークン設定は必須ではありません。

文書は見出し・段落を基準に最大400文字で分割し、問い合わせはDBの正本から本文・対応内容を取得します。モデルの512トークン上限を超える入力は、黙って切り捨てずエラーとします。本文・見出しの変更時にこの上限を超えた場合は分割を調整する必要があります。

全チャンクの埋め込みを生成してから、短いトランザクションでchunks全件を置換します。再実行で重複を増やさず、削除された文書も反映し、置換途中の失敗はロールバックします。CPU推論中にはDBセッションを保持しません。検索はpgvectorのコサイン距離による完全検索で、近似インデックスやリランキングは使いません。

検索結果には文書パス／問い合わせID、チャンクID、正本のハッシュ、モデル識別子を保持します。問い合わせ検索の根拠は派生チャンクであり、正本の根拠とは別です。`get_inquiry`で元IDを追加取得できます。類似度は関連する候補を順位付けする値で、根拠の正しさや確信度を保証しません。

CPU検索と実PostgreSQLでの検索は、それぞれ4ケース中4ケース成功しました。条件・実測時間・制約は[基盤検証履歴](docs/history/foundation-verification.md)を参照してください。完成Agentの受入検証は後続です。

LLMはWSLホスト側で別途起動します。コンテナは`host.docker.internal`からホストへ接続し、`LLM_BASE_URL`・`LLM_MODEL`・`LLM_REQUEST_TIMEOUT`をCompose経由で渡します。管理用DBパスワードを含むホストの`.env`をアプリ自身が読み込むことはありません。

### WSL側のOllama

まずOllamaを使用し、選んだモデルでTool Callingが成立しない場合はllama-serverを検討します。WSLのUbuntu側（アプリコンテナの外）で[公式インストーラー](https://docs.ollama.com/linux)を取得して確認し、導入します。

```bash
sudo apt install -y zstd
curl -fsSL https://ollama.com/install.sh -o /tmp/ollama-install.sh
less /tmp/ollama-install.sh
OLLAMA_VERSION=0.35.1 sh /tmp/ollama-install.sh
systemctl status ollama --no-pager
curl --fail http://127.0.0.1:11434/api/version
```

開発ホストではOllama 0.35.1とQwen3 30B-A3B Instruct-2507 Q4_K_Mで、CPU/GPU分担による推論と日本語のTool Callingを確認しました。4ケース各3回の事前検証がすべて合格し、実装の第一候補とします。下記はメモリ上の架空Toolによる接続検証で、完成アプリのA〜Eの受入結果ではありません。コンテナ内のlocalhostはホストとは別の接続先になります。

### コンテナからOllamaへの接続

WSL内のDocker Engineでは、Ollamaの初期設定（127.0.0.1待受）にコンテナから接続できません。[公式のsystemd設定方法](https://docs.ollama.com/faq#setting-environment-variables-on-linux)に沿って、ホスト側で次を設定します。

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"\n' | sudo tee /etc/systemd/system/ollama.service.d/logiscope-network.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama

docker compose exec app curl --fail http://host.docker.internal:11434/v1/models
docker compose exec app python scripts/verify_local_tools.py \
  --base-url http://host.docker.internal:11434/v1 \
  --model logiscope-qwen30-probe --repeat 1 --reasoning-effort none \
  --request-timeout 300 --case-timeout 900 \
  --output artifacts/qwen30-container-verification.json
```

全インターフェースで待ち受けるため、ネットワーク構成によっては他端末からもアクセス可能になります。11434番ポートを公開する用途ではありません。

コンテナからの事前検証は4ケース中4ケース成功しました。[接続検証の記録](docs/history/local-llm-selection.md#コンテナからの接続検証)。

### 使用モデルの準備

Qwen3 30B-A3B Instruct-2507 Q4_K_Mを使用します。WSLホスト側で取得し、コンテキスト8,192の別名を作成します。配布テンプレートは変更しません。

```bash
ollama pull qwen3:30b-a3b-instruct-2507-q4_K_M
printf 'FROM qwen3:30b-a3b-instruct-2507-q4_K_M\nPARAMETER num_ctx 8192\n' > /tmp/logiscope-qwen30.Modelfile
ollama create logiscope-qwen30-probe -f /tmp/logiscope-qwen30.Modelfile
```

モデルは約18〜19GBで、検証ホストではCPU/GPUに分担して動作しました。VRAM 12GBだけに全体を収める構成ではありません。選定理由・比較結果・検証条件は[ローカルLLM選定履歴](docs/history/local-llm-selection.md)に記載しています。

Agent実装後に、次のデータ準備・実行手順を追加します。

1. 必要環境と検証済みモデルの準備。
2. マイグレーションと架空業務データ投入。
3. 文書・過去問い合わせのingest。
4. ローカルLLM接続とアプリ起動。
5. curlによる5シナリオの実行。

LLM・埋め込みモデル本体はリポジトリに格納しません。

モデルはOllamaやHugging Faceの通常のホスト側保存先を利用します。プロジェクト内に置く必要がある場合は`models/`、キャッシュは`.cache/`、再生成可能な出力は`artifacts/`または`.local-data/`へ置きます。これらと代表的な重みファイルは`.gitignore`・`.dockerignore`で除外しています。モデル名・版・設定や文書の正本`seed/docs`は管理対象です。

## テスト

```bash
docker compose exec app uv run --locked pytest
```

通常のテストは外部サービスなしで実行します。実DBテストは既定でスキップし、DB準備後に管理サービスで明示的に実行します。

```bash
docker compose run --rm --entrypoint uv -e LOGISCOPE_DB_TESTS=1 manage run --locked pytest
docker compose run --rm --entrypoint uv manage run --locked alembic check
```

DBテストは実PostgreSQLで、ORMの関連取得・同名候補・不存在・seed再実行・FK・pgvector拡張・読み取り専用ロールを確認します。書き込み拒否はトランザクションのread-only設定を解除してもDB権限で拒否されることを検証します。テスト用の更新はロールバックします。管理認証情報はアプリサービスに渡しません。

最新の検証はLoop制御43件＋単体・基盤34件＋実DB統合29件、計106件中106件成功（失敗・スキップ0件）。通常実行では77件成功・実DB29件スキップです。実モデルの検証は上記のスクリプトで分離します。[過去の検証記録](docs/history/foundation-verification.md)

Loop制御は偽LLMで検証済みです。実LLMクライアント・API統合と完成デモの受入検証は後続です。

## Known Limitations

- Loop制御は実装済みですが、実LLMクライアント・Agent APIはまだありません。
- 実行速度・Tool Calling品質・日本語検索品質は採用モデルとホスト性能に依存します。
- 架空データのみを対象とする、単一利用者向けの読み取り専用PoCです。
- GUI、認証、マルチテナント、ストリーミング、高度な検索改善、本番デプロイは対象外です。
- 参照元の検証だけで回答の事実性を完全保証するものではありません。

## 本番化する場合

利用者・組織ごとの認証と参照権限、個人情報保護、運用監視、負荷・信頼性評価、秘密管理、データ更新運用、モデル変更時の評価などが別途必要です。本PoCの実装範囲には含めません。

## 文書と開発用skills

- [要件・制約・受入条件](docs/requirements.md)
- [設計・技術選定・未決定事項](docs/design.md)
- [ローカルLLM選定・事前検証の履歴](docs/history/local-llm-selection.md)
- [基盤実装・検証の履歴](docs/history/foundation-verification.md)
- [AGENTS.md](AGENTS.md)
- [ローカルTool Calling検証skill](.agents/skills/verify-local-tool-calling/SKILL.md)
- [デモシナリオ検証skill](.agents/skills/verify-demo-scenarios/SKILL.md)

skillsは開発支援用の手順です。実行時Agentの機能ではありません。
