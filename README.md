# LogiScope

**業務データとRAGを横断調査する Tool-calling Agent Loop のデモ。**

物流会社の架空データを題材に、自然言語の質問からLLMがToolを選び、結果を観測して次の調査を進め、根拠と未解決事項を返すことを目指します。案件獲得用ポートフォリオとして、Agentの設計・実装・検証を示すPoCです。

> **現在は開発環境の準備段階です。** 要件・設計・開発指針・検証skillsと、シェルで作業できるDocker構成があります。API、Agent、業務データ、テストはまだ実装されていません。以下のAPI例は予定仕様で、現時点では実行できません。

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

具体的なデータ・質問・実行結果は、実装と実LLM検証後に追加します。[受入条件](docs/requirements.md#9-デモシナリオと受入条件)

## セットアップ・データ準備・起動

Docker EngineとComposeが必要です。開発環境ではWSL2のUbuntu内へDocker Engineを直接導入し、Docker Desktopには依存しません。[Docker公式のUbuntu導入手順](https://docs.docker.com/engine/install/ubuntu/)を参照してください。リポジトリルートで`.env.example`を`.env`へコピーし、ダミーパスワードを変更してください。`LOCAL_UID`と`LOCAL_GID`はWSLユーザーの`id -u`と`id -g`に合わせます。

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

`app`は現在シェル作業用に常駐するだけで、8000番ポートにAPIはまだありません。Pythonライブラリもまだ導入していません。コンテナ内で手動インストールしたライブラリはコンテナ再作成時に失われるため、今後は依存定義・ロックファイルから再現する仕組みを追加します。

DBはComposeネットワーク内の`db:5432`です。ホストへDBポートは公開していません。管理用の接続は次で行えます。

```bash
docker compose exec db psql -U logi_scope_admin -d logi_scope
docker compose ps
docker compose down
```

DBデータはnamed volumeに残ります。`docker compose down -v`はDBデータも削除するため、通常の停止には使いません。現在のDBユーザーは準備用の管理ロールです。実行時アプリ用の読み取り専用ロールとマイグレーションは後続で作成し、管理者の認証情報を`app`へ渡しません。pgvectorはイメージに収録されていますが、拡張の有効化は後続のマイグレーションで行います。

LLMはホスト側で別途起動します。`LLM_BASE_URL`の初期値はホスト上のOllama用の接続候補であり、接続確認済みではありません。Windows側かWSL側か、待受アドレス・ポートによって設定を調整します。

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

開発ホストではOllama 0.35.1のバージョンAPI応答を確認済みです。モデルはまだ取得しておらず、GPU推論・Tool Calling・アプリコンテナからのLLM接続は未検証です。上記はホストからの確認で、コンテナ内のlocalhostは別の接続先になります。

Agent実装後に、次のデータ準備・実行手順を追加します。

1. 必要環境と検証済みモデルの準備。
2. マイグレーションと架空業務データ投入。
3. 文書・過去問い合わせのingest。
4. ローカルLLM接続とアプリ起動。
5. curlによる5シナリオの実行。

LLM・埋め込みモデル本体はリポジトリに格納しません。

モデルはOllamaやHugging Faceの通常のホスト側保存先を利用します。プロジェクト内に置く必要がある場合は`models/`、キャッシュは`.cache/`、再生成可能な出力は`artifacts/`または`.local-data/`へ置きます。これらと代表的な重みファイルは`.gitignore`・`.dockerignore`で除外しています。モデル名・版・設定や文書の正本`seed/docs`は管理対象です。

## テスト

テストは未実装です。pytestによる偽LLMを使った決定論的な制御テスト、PostgreSQL/pgvector統合テスト、実LLMのデモ検証を分けます。実行方法と検証結果は、実装後に追加します。

## Known Limitations

- 現在は開発コンテナとDBの準備までで、動作するAgentはまだありません。
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
