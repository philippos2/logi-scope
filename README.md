# LogiScope

**業務データとRAGを横断調査する Tool-calling Agent Loop のデモ。**

物流会社の架空データを題材に、自然言語の質問からLLMがToolを選び、結果を観測して次の調査を進め、根拠と未解決事項を返すことを目指します。案件獲得用ポートフォリオとして、Agentの設計・実装・検証を示すPoCです。

> **現在はRAG基盤まで実装・検証済みです。** 業務4テーブルとTool、文書・問い合わせチャンクの生成と検索を実装しています。Agent Loopと`POST /agent`は未実装です。以下のAgent API例は予定仕様で、現時点では実行できません。

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

これらはPython内のToolであり、HTTP公開やLLMによる自律選択への統合はまだ行っていません。`search_knowledge`にはロード済みの埋め込みモデルを渡します。業務Toolだけを使う場合はモデルをロードする必要はありません。

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

2026-10-06のCPU事前検証は4ケース中4ケース成功。期待する障害報告・遅延報告・過去問い合わせ・FAQが各ケースで1位でした（合否条件は上位3件以内）。メモリ上の10チャンクの検証で、初回のモデル取得込みロード100.19秒、ロード後の質問埋め込み＋順位付け0.019〜0.021秒。実DBやLLMを含む問い合わせ全体の時間ではありません。結果はGit対象外の`artifacts/embedding-verification.json`に保存します。

実E5モデル＋読み取り専用PostgreSQL/pgvectorの検索も4ケース中4ケース成功。10チャンクで、期待する情報源が各ケースで1位に出て、問い合わせ501の正本も追加取得できました。モデルロード後のケース時間は0.021〜0.049秒。取得済み情報をLLMで統合する時間は含みません。`artifacts/rag-verification.json`に結果を保存します。Agentによる自律選択やA〜E全体の受入成功とは区別します。

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

2026-10-06にコンテナからモデル一覧とTool Callingを確認。多段調査・該当なし・曖昧性・人為的エラー後の再送を各1回実行し、4/4合格（27.69秒、2.69秒、3.14秒、8.34秒）。これは接続経路の確認であり、実DB/RAGや完成Agentの受入検証ではありません。

### Qwen3 30B-A3B Instructの事前検証

検証日: 2026-10-06。WSL2、RAM約30GiB、RTX 3060 12GB、Ollama 0.35.1。
配布タグは`qwen3:30b-a3b-instruct-2507-q4_K_M`、取得IDは`19e422b02313`。
配布サイトの表示は約19GB、取得後の`ollama list`表示は18GBです。
30.5BのMoEモデルで、量子化はQ4_K_M。非思考モード専用のInstruct-2507を使います。
[配布情報](https://ollama.com/library/qwen3:30b-a3b-instruct-2507-q4_K_M)、
[公式モデルカード](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507)。

```bash
# ホスト側で実行
ollama pull qwen3:30b-a3b-instruct-2507-q4_K_M
printf 'FROM qwen3:30b-a3b-instruct-2507-q4_K_M\nPARAMETER num_ctx 8192\n' > /tmp/logiscope-qwen30.Modelfile
ollama create logiscope-qwen30-probe -f /tmp/logiscope-qwen30.Modelfile
python3 scripts/verify_local_tools.py --model logiscope-qwen30-probe \
  --repeat 3 --reasoning-effort none --request-timeout 300 --case-timeout 900 \
  --output artifacts/qwen30-verification.json
```

検証用別名のIDは`a49b4faf047f`。コンテキスト以外は配布テンプレートを使用します。
Mistralと同じ質問・架空データ・Tool引数・合否判定で、temperature 0、出力上限700、
非ストリーミング。Tool結果を対応する呼び出しIDで戻し、最終JSONはToolなしの別要求で生成します。
検証前に空の`/api/generate`要求でモデルをロードしました。ロード時間は未測定です。

| ケース | 合格/実行数 | ケース全体の所要時間 |
|---|---|---|
| 顧客ID→荷物→事故ID→報告取得 | 3/3 | 6.15〜6.24秒（初回ケースは18.50秒） |
| 該当なし | 3/3 | 2.61〜2.80秒 |
| 同名顧客の曖昧性 | 3/3 | 2.80〜3.24秒 |
| エラー後の1回再送＋調査完了 | 3/3 | 7.20〜7.44秒（初回ケースは12.23秒） |

同名候補では追加の荷物検索をせず`ambiguous_target`を返しました。
該当なしでは`not_found`、多段調査では取得済みの顧客IDと事故IDを次のToolへ引き継ぎました。
`ollama ps`はCPU 46%・GPU 54%、ロードサイズ約19GB、context 8192。
GPU全体使用量の観測値は11,679MiBで、最大使用量の測定ではありません。

この短い架空ケースでは、曖昧性と処理時間の双方でQwenを実装の第一候補とします。
これはモデル一般の性能順位や、実DB/RAGでの品質保証ではありません。
再送試験は正しい引数への人為的な拒否であり、実際の不正引数の修正は未検証です。
自動判定は必要なTool・ID利用・回答中の期待語・未解決コードを確認する粗い検証です。
実アプリでは、候補の一意性・根拠の照合・未解決事項を実行側でも検証します。
成果物はGit対象外の`artifacts/`に置き、内部推論・生LLM応答全体は保存しません。

### Mistral Small 3.2 24Bの事前検証

検証日: 2026-10-05。WSL2、RAM約30GiB、RTX 3060 12GB。
配布モデル`mistral-small3.2:24b`の取得IDは`5a408ab55df5`、配布サイズ約15GB。
コンテキスト8,192、temperature 0、出力上限700トークン、非ストリーミング。
OpenAI互換APIでTool結果を呼び出しIDに対応付けて戻し、JSONの最終化は別リクエストで行います。

```bash
# ホスト側で実行
ollama pull mistral-small3.2:24b
python3 scripts/prepare_mistral_probe.py
python3 scripts/verify_local_tools.py --model logiscope-mistral24-tools-probe \
  --repeat 3 --request-timeout 300 --case-timeout 900 \
  --output artifacts/mistral24-verification.json
```

顧客検索の引数名は`customer_name`とします。`name`ではTool呼び出しが空になり、
名前変更で呼び出しが返ることを実測しました。[関連するOllamaの不具合報告](https://github.com/ollama/ollama/issues/16932)。
さらに配布テンプレートのTool一覧挿入条件を、Tool結果追加後も一覧が残るよう調整した
検証用別名を使用します。調整は`prepare_mistral_probe.py`で再現でき、元モデルは変更しません。

| ケース | 合格/実行数 | ケース全体の所要時間 |
|---|---|---|
| 顧客ID→荷物→事故ID→報告取得 | 3/3 | 20.62〜23.70秒 |
| 該当なし | 3/3 | 10.81〜12.74秒 |
| 同名顧客の曖昧性 | 0/3 | 候補選択を実行前に拒否 |
| エラー後の1回再送＋調査完了 | 3/3 | 23.95〜29.39秒 |

`ollama ps`の表示はCPU 42%・GPU 58%、ロードサイズ約16GB。
GPU全体使用量は観測時11,689MiB。これは最大使用量の測定ではありません。
時間はモデル常駐後の短い架空データによるケース全体で、初回ロード・実DB・RAGは含みません。
再送試験は正しい引数を人為的に一度拒否する試験で、モデルが生成した不正引数の修正は未検証です。
自動判定はIDの利用・必要Tool・回答中の期待語・未解決コードを確認する粗い検証です。
回答の事実性の完全性や、未完成のA〜Eの合格を保証するものではありません。

曖昧性では候補IDによる荷物検索を試みたため、実行前に拒否しました。
元の配布設定ではTool呼び出しが失われ、引数名だけの修正では多段調査が継続しませんでした。
上表は引数名とテンプレートの両方を修正した組み合わせの結果です。
生成された操作記録はGit対象外の`artifacts/`へ置き、内部推論・生LLM応答全体は保存しません。

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

2026-10-06にPython 3.13のコンテナと実PostgreSQLで検証し、基盤5件＋DB統合10件の計15件が合格。`alembic check`も追加の変更なしと確認しました。通常実行は基盤5件が合格し、DB統合10件をスキップします。

業務Tool追加後は単体・基盤20件＋実DB統合21件の計41件が合格しました。通常実行では20件合格・DB統合21件スキップです。業務Toolの実DB11件は候補・ID引き継ぎ・件数省略・正本取得・不存在・セッション返却を確認します。単体テストは入力異常・未知Tool・DB例外の公開情報制限・時間超過時のセッション終了を検証します。

RAG追加後は単体・基盤34件＋実DB統合29件、計63件中63件が成功（失敗・スキップ0件）。外部DBなしの通常実行では34件成功・29件スキップです。モデル本体は通常の自動テストで読み込まず、実モデル検証は上記のスクリプトで分離します。

Agentの制御と完成デモの実LLM検証は後続です。

## Known Limitations

- 現在はRAG基盤までで、動作するAgentはまだありません。
- 実行速度・Tool Calling品質・日本語検索品質は採用モデルとホスト性能に依存します。
- 架空データのみを対象とする、単一利用者向けの読み取り専用PoCです。
- GUI、認証、マルチテナント、ストリーミング、高度な検索改善、本番デプロイは対象外です。
- 参照元の検証だけで回答の事実性を完全保証するものではありません。

## 本番化する場合

利用者・組織ごとの認証と参照権限、個人情報保護、運用監視、負荷・信頼性評価、秘密管理、データ更新運用、モデル変更時の評価などが別途必要です。本PoCの実装範囲には含めません。

## 文書と開発用skills

- [要件・制約・受入条件](docs/requirements.md)
- [設計・技術選定・未決定事項](docs/design.md)
- [AGENTS.md](AGENTS.md)
- [ローカルTool Calling検証skill](.agents/skills/verify-local-tool-calling/SKILL.md)
- [デモシナリオ検証skill](.agents/skills/verify-demo-scenarios/SKILL.md)

skillsは開発支援用の手順です。実行時Agentの機能ではありません。
