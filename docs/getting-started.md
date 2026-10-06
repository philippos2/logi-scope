# セットアップ・実行ガイド

検証対象はWSL2 Ubuntu上のDocker EngineとOllama。確認したホストはRTX 3060 12GB、WSL割当メモリ約30GiB、CPU/GPU分担でQwen3 30B-A3B Instruct-2507 Q4_K_Mを使用した。必要最小スペックを測定したものではない。モデルは約18〜19GBで、初回はモデル・コンテナ・Python依存の取得にインターネット接続と空きディスクが必要。

ホスト上へのPythonライブラリ導入は不要。ローカルLLMはホスト、PythonアプリとPostgreSQLはDockerコンテナで動かす。他OSでの接続は未検証。

## 実行順序

1. Docker Engine・Compose・Ollamaをホストに用意する。
2. リポジトリを取得し、`.env`を作成・編集する。
3. ホストでQwenのモデル取得・別名作成とOllamaの待ち受け設定を行う。
4. コンテナをビルドし、DBのinit・seedを実行する。
5. ingestで埋め込みモデルを取得し、文書とDB問い合わせから索引を生成する。
6. アプリコンテナ内でAPIを起動し、別窓からcurlを実行する。

```bash
git clone https://github.com/philippos2/logi-scope.git
cd logi-scope
cp .env.example .env
# .envを編集: 3つのパスワードを異なる値にし、LOCAL_UID/LOCAL_GIDをidの値へ合わせる
```

以下の詳細を確認してホスト側のOllamaとモデルを準備した後、リポジトリルートのホストシェルで実行する。

```bash
docker compose up -d --build
docker compose run --build --rm manage init
docker compose run --rm manage seed
docker compose run --build --rm ingest
docker compose exec app bash
```

最後のコマンド以降はコンテナ内。API起動時の`Application startup complete`を待つ。

```bash
uv run --locked uvicorn logi_scope.api:app --host 0.0.0.0 --port 8000 --reload
```

別のホスト窓から:

```bash
curl --fail http://localhost:8000/health
curl --fail --max-time 960 http://localhost:8000/agent \
  -H 'Content-Type: application/json' \
  -d '{"question":"デモ青空商店の荷物が遅延している原因は？"}'
```

GUIはなく、curlの質問からLLMがToolを選ぶ。応答の4項目・テスト方法は[README](../README.md)、5つの質問例は以下の「DB準備」を参照する。停止時はコンテナ内でCtrl+C、ホストで`docker compose down`。通常停止では`-v`を付けない。

## 詳細

### コンテナ・設定

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
# 以下のDB・RAG・Ollamaの準備を済ませてからAPIを起動
uv run --locked uvicorn logi_scope.api:app --host 0.0.0.0 --port 8000 --reload
```

別のWSL窓から`curl --fail http://localhost:8000/health`で`{"status":"ok"}`を取得できます。これはアプリの生存確認のみで、DB・LLMの接続状態を保証しません。API起動時にCPU埋め込みモデルをロードするため、起動完了を待ってから質問します。

DBはComposeネットワーク内の`db:5432`です。ホストへDBポートは公開していません。管理用の接続は次で行えます。

```bash
docker compose exec db psql -U logi_scope_admin -d logi_scope
docker compose ps
docker compose down
```

DBデータはnamed volumeに残ります。`docker compose down -v`はDBデータも削除するため、通常の停止には使いません。管理者の認証情報は`db`と明示的に実行する`manage`だけへ渡します。`ingest`は専用ロールの認証情報だけを持ち、業務データを更新できません。`app`は`logi_scope_reader`として接続し、業務4テーブルとchunksのSELECT権限だけを持ちます。業務テーブルの所有者・スーパーユーザーではなく、publicスキーマへのテーブル作成もできません。

業務テーブルの関係は[DBスキーマ・ER図](database-schema.md)を参照してください。DBeaverからの接続手順も記載しています。

### DB準備

リポジトリルートのWSLシェルから実行します。管理サービスは常駐させません。

```bash
docker compose run --build --rm manage init
docker compose run --rm manage seed
```

`init`はAlembicで業務4テーブル・chunks・pgvector拡張・読み取り専用/ingestロールを作成し、`.env`の`POSTGRES_READER_PASSWORD`と`POSTGRES_INGEST_PASSWORD`を各ロールへ設定します。再実行しても適用済みマイグレーションは繰り返しません。新規マイグレーション追加後もこのコマンドで更新できます。

`seed`はSQLAlchemy ORMで架空顧客4件、荷物4件、配送イベント5件、問い合わせ2件を投入します。同じIDを更新する方式で、再実行しても重複を増やさず、他のIDを削除しません。seedファイルは初期投入用であり、投入後の業務データの正本はDBです。文書4ファイルはリポジトリ内の正本であり、検索チャンク・埋め込みは以下のingestコマンドで生成します。

| シナリオ | 用意したデータ／質問例 |
|---|---|
| A | 「SHP-DEMO-002の配送状態は？」（配達完了） |
| B | 「デモ青空商店の荷物が遅延している原因は？」（SHP-DEMO-001 → INC-DEMO-001 → 障害報告） |
| C | 「配達完了後の受領確認について、過去の問い合わせでの対応を調べて」（問い合わせ501の正本） |
| D | 「SHP-NOT-FOUNDの配送状態は？」（不存在） |
| E | 「デモ双葉商会の荷物を調べて」（同名2顧客、異なる営業所） |

各質問は独立したリクエストとして送ります。復旧予定・配送再開時刻が未確定という情報不足も含みます。

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

CPU検索と実PostgreSQLでの検索は、それぞれ4ケース中4ケース成功しました。条件・実測時間・制約は[基盤検証履歴](history/foundation-verification.md)を参照してください。これらは検索基盤単独の検証で、Agentの受入結果とは分けています。

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

開発ホストではOllama 0.35.1とQwen3 30B-A3B Instruct-2507 Q4_K_Mで、CPU/GPU分担による推論と日本語のTool Callingを確認しました。4ケース各3回の事前検証を経て採用しました。下記はメモリ上の架空Toolによる接続検証で、完成アプリのA〜Eの受入結果ではありません。コンテナ内のlocalhostはホストとは別の接続先になります。

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

コンテナからの事前検証は4ケース中4ケース成功しました。[接続検証の記録](history/local-llm-selection.md#コンテナからの接続検証)。

### 使用モデルの準備

Qwen3 30B-A3B Instruct-2507 Q4_K_Mを使用します。WSLホスト側で取得し、コンテキスト8,192の別名を作成します。配布テンプレートは変更しません。

```bash
ollama pull qwen3:30b-a3b-instruct-2507-q4_K_M
printf 'FROM qwen3:30b-a3b-instruct-2507-q4_K_M\nPARAMETER num_ctx 8192\n' > /tmp/logiscope-qwen30.Modelfile
ollama create logiscope-qwen30-probe -f /tmp/logiscope-qwen30.Modelfile
```

モデルは約18〜19GBで、検証ホストではCPU/GPUに分担して動作しました。VRAM 12GBだけに全体を収める構成ではありません。選定理由・比較結果・検証条件は[ローカルLLM選定履歴](history/local-llm-selection.md)に記載しています。

`.env`のLLM接続先・モデルを変更したら、`docker compose up -d app`で環境変数を反映し、コンテナ内のAPIを再起動します。実行制限は`AGENT_MAX_LLM_CALLS`、`AGENT_MAX_TOOL_ATTEMPTS`、`AGENT_TOTAL_TIMEOUT`。`LLM_REASONING_EFFORT=omit`で未対応サーバーへのreasoning_effort送信を省略できます。

LLM・埋め込みモデル本体はリポジトリに格納しません。

モデルはOllamaやHugging Faceの通常のホスト側保存先を利用します。プロジェクト内に置く必要がある場合は`models/`、キャッシュは`.cache/`、再生成可能な出力は`artifacts/`または`.local-data/`へ置きます。これらと代表的な重みファイルは`.gitignore`・`.dockerignore`で除外しています。モデル名・版・設定や文書の正本`seed/docs`は管理対象です。

