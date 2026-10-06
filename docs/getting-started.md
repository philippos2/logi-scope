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
7. React画面を使う場合は、[フロントエンド開発基盤](#フロントエンド開発基盤)に従って起動し、ブラウザから調査する。

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

curl・React画面のどちらからも質問でき、LLMがToolを選ぶ。画面の起動方法は[フロントエンド開発基盤](#フロントエンド開発基盤)を参照する。応答の4項目・テスト方法は[README](../README.md)、5つの質問例は以下の「DB準備」を参照する。停止時はコンテナ内でCtrl+C、ホストで`docker compose down`。frontendも起動している場合は`docker compose --profile frontend down`を使う。通常停止では`-v`を付けない。

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

既存環境でデータを更新する場合も、`manage init` → `manage seed` → `ingest`の順に実行し、起動中のAPIを再起動する。新しい配送状態のDB制約とTool定義を反映するため、seedだけを実行しない。DBeaverを使う場合は[閲覧用Compose設定](database-schema.md#dbeaverで確認する)を含めてDBを起動する。通常のCompose構成でDBを再作成すると、閲覧用ポートの公開が外れる。

`seed`はSQLAlchemy ORMで架空顧客14件、荷物34件、配送イベント65件、問い合わせ12件を投入します。同じIDを更新する方式で、再実行しても重複を増やさず、他のIDを削除しません。seedファイルは初期投入用であり、投入後の業務データの正本はDBです。文書10ファイルはリポジトリ内の正本であり、検索チャンク・埋め込みは以下のingestコマンドで生成します。

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

検索基盤単独の実測条件・結果・制約は[基盤検証履歴](history/foundation-verification.md)を参照してください。これらは検索基盤単独の検証で、Agentの受入結果とは分けています。

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

検証済みの組み合わせはOllama 0.35.1とQwen3 30B-A3B Instruct-2507 Q4_K_Mです。下記はメモリ上の架空Toolによる接続検証で、完成アプリのA〜Eの受入結果ではありません。コンテナ内のlocalhostはホストとは別の接続先になります。

### 使用モデルの準備

Qwen3 30B-A3B Instruct-2507 Q4_K_Mを使用します。WSLホスト側で取得し、コンテキスト8,192の別名を作成します。配布テンプレートは変更しません。

```bash
ollama pull qwen3:30b-a3b-instruct-2507-q4_K_M
printf 'FROM qwen3:30b-a3b-instruct-2507-q4_K_M\nPARAMETER num_ctx 8192\n' > /tmp/logiscope-qwen30.Modelfile
ollama create logiscope-qwen30-probe -f /tmp/logiscope-qwen30.Modelfile
```

モデルは約18〜19GBで、検証ホストではCPU/GPUに分担して動作しました。VRAM 12GBだけに全体を収める構成ではありません。選定理由・比較結果・検証条件は[ローカルLLM選定履歴](history/local-llm-selection.md)に記載しています。

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

実測結果は[接続検証の記録](history/local-llm-selection.md#コンテナからの接続検証)を参照してください。

`.env`のLLM接続先・モデルを変更したら、`docker compose up -d app`で環境変数を反映し、コンテナ内のAPIを再起動します。実行制限は`AGENT_MAX_LLM_CALLS`、`AGENT_MAX_TOOL_ATTEMPTS`、`AGENT_TOTAL_TIMEOUT`。`LLM_REASONING_EFFORT=omit`で未対応サーバーへのreasoning_effort送信を省略できます。

LLM・埋め込みモデル本体はリポジトリに格納しません。

LLMはOllamaのホスト側保存先、埋め込みモデルはDockerの`embedding_cache` named volumeを利用します。プロジェクト内に置く必要がある場合は`models/`、キャッシュは`.cache/`、再生成可能な出力は`artifacts/`または`.local-data/`へ置きます。これらと代表的な重みファイルは`.gitignore`・`.dockerignore`で除外しています。モデル名・版・設定や文書の正本`seed/docs`は管理対象です。


## フロントエンド開発基盤

Reactの質問入力・調査結果画面とAPIプロキシは実装済み。ホストへのNode.js導入は不要。既存のDB・索引・LLMを準備し、別窓でAPIを起動した状態で使用する。

ホストのリポジトリルートから:

```bash
docker compose --profile frontend up -d --build frontend
docker compose exec frontend bash
```

コンテナ内の作業場所は`/home/developer/work/logi-scope/frontend`。非rootで作業し、次のコマンドで開発サーバーを起動する。

```bash
npm run dev
```

ブラウザで`http://localhost:5173`を開く。`/api/agent`と`/api/health`はViteがCompose内の`app:8000`へ転送する。CORSの追加は不要。APIが別途起動していない場合はプロキシ経由の接続は失敗する。`/api/health`の成功はLLM・DBの準備完了を保証しない。

型確認・ビルドはコンテナ内で`npm run build`、または別のホスト窓から:

```bash
docker compose exec frontend npm run build
```

ホストのソースとnamed volumeの`node_modules`を分ける。依存変更時はコンテナ内で`npm install`し、`package.json`と`package-lock.json`を保存する。clone直後はイメージの依存が空のvolumeへコピーされる。ブランチ変更・依存更新・再ビルド時に既存volumeの依存が古い場合は、`docker compose exec frontend npm ci`でロックへ合わせる。DBを消す`down -v`で依存を更新しない。

通常の起動ではfrontendプロファイルを有効にしない限り、フロント用コンテナは追加されない。停止は開発サーバーのCtrl+Cと`docker compose --profile frontend stop frontend`。通常の全体停止は`docker compose --profile frontend down`。

Viteは開発用サーバーであり、本番ホスティングは今回の範囲外。スマホの実機からのアクセスは既定のlocalhost限定公開ではできない。レスポンシブ確認はまずPCブラウザの画面幅変更で行う。

### 画面から調査する

ブラウザでサンプル質問を選択し、「調査する」を押す。サンプル選択だけでは送信しない。Ctrl/Cmd+Enterでも送信できる。完了すると回答、未解決事項、根拠、Tool履歴を表示する。スマホ幅では根拠・履歴を初期状態で折りたたむ。

「待機を終了」はブラウザの応答待ちを中断するだけで、サーバ側の調査停止を保証しない。再送で「別の調査を実行中」と返った場合は完了を待つ。画面のタイムアウトとAPIプロキシは960秒。サーバの全体上限を変更するときは両方を調整する。

フロント用コンテナ内で`npm run lint`を実行して静的検査し、`npm test`でテストする。Vitest・React Testing Library・Happy DOMによる偽APIテストで、重要な送信・エラー・待機終了の処理に絞る。見た目はブラウザで確認する。CIではESLint、画面テスト、型チェック、ビルドを別ジョブで実行する。Pythonの静的検査はアプリコンテナ内で`uv run --locked ruff check .`を実行する。
