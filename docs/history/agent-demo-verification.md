# Agentデモの実接続検証

検証日: 2026-10-06。FastAPIの`POST /agent`から実ローカルLLM・読み取り専用PostgreSQL/pgvector・CPU埋め込みを使用した。メモリ上の簡略Tool検証や偽LLMテストとは別の結果。

## 条件と再現

- WSL2 Ubuntu、WSLメモリ約30GiB、RTX 3060 12GB。
- Ollama 0.35.1、Qwen3 30B-A3B Instruct-2507 Q4_K_M。
- 実行別名: `logiscope-qwen30-probe`、ID `a49b4faf047f`、context 8192。CPU 46%・GPU 54%の分担。
- temperature 0、max_tokens 1200、reasoning_effort none、非ストリーミング。
- E5はCPUで起動時にロード。業務4テーブル、文書4件・問い合わせ2件由来の10チャンクを使用。
- 各質問は独立したHTTPリクエスト。2巡の検証中はモデルが常駐しており、初回モデルロード時間は表の時間に含まない。

READMEに従ってDB・ingest・Ollamaを準備し、コンテナ内でAPIを起動してから実行する。

```bash
docker compose exec app uv run --locked python scripts/verify_demo.py --repeat 2
```

公開応答、質問、所要時間、合否理由はGit対象外の`artifacts/demo-verification.json`へ保存する。内部推論やプロバイダーの生応答は保存しない。

## 結果

**10件中10件成功（5シナリオ各2回）。**

| シナリオ | 成功/実行数 | 時間（秒） | 確認できたこと |
|---|---|---|---|
| A | 2/2 | 6.13 / 5.10 | SHP-DEMO-002の配達完了と日本時間11:15、業務根拠、実行履歴、未解決なし |
| B | 2/2 | 15.02 / 14.44 | 顧客101→荷物SHP-DEMO-001→障害INC-DEMO-001で文書検索。センサー故障の回答と業務・文書の根拠 |
| C | 2/2 | 14.98 / 10.98 | 問い合わせ検索→正本501取得。11:15の対応内容、検索チャンクと正本の追跡 |
| D | 2/2 | 16.28 / 16.44 | 不存在荷物IDを実検索。荷物の根拠を捏造せずnot_foundを返す |
| E | 2/2 | 7.69 / 4.97 | 同名顧客201・202を提示。荷物検索へ進まずambiguous_targetと追加情報を返す |

Bは両回とも4つのTool、Cは3つのToolを使用した。Dは両回とも5つのToolを使い、類似検索で取得した別の問い合わせまで確認した。不存在回答は正しかったが、不要な追加検索がある。Eの候補選択防止は実行側の安全制御を含み、モデルだけの判断能力として主張しない。

脚本化した合否判定に加え、公開応答をseed正本と照合した。Bの復旧・配送再開時刻は未確定として回答。固定されたTool順序や文章の完全一致は合否条件にしていない。未知の質問やデータで同じ品質が出ることの保証ではない。

## 初回の問題と修正

初回の自動判定は5件中4件成功。Cは検索と正本取得に成功したが、回答のsourcesから検索チャンクが抜けたため不合格だった。取得済み問い合わせ正本を引用するとき、今回取得した対応チャンクも実行側で併記するよう修正した。未取得の根拠は追加しない。

Aは状態自体は正しかったが、DBから返ったUTCの02:15をタイムゾーンなしで回答した。初回判定はこの表記を検出していなかったため、レビューで指摘した。Toolの日時を日本時間のISO 8601（+09:00）へ揃え、回答にも日本時間を明示する方針を追加した。判定にはUTC表記の検査を追加し、質問と期待事実は変更せず2巡再検証した。初回記録は`artifacts/demo-verification-initial.json`に残した。

## 実際のBの公開応答（2巡目）

```json
{
  "answer": "デモ青空商店の荷物SHP-DEMO-001が遅延している原因は、2026年10月2日08時30分（日本時間）に架空青空物流センターで発生した仕分け設備のセンサー故障による安全停止です。この障害により、仕分け待ちの荷物が遅延しており、配送再開時刻や到着予定の変更はまだ確定していません。",
  "sources": [
    {
      "id": "shipment:SHP-DEMO-001",
      "kind": "shipment",
      "record_id": "SHP-DEMO-001"
    },
    {
      "id": "delivery_event:1002",
      "kind": "delivery_event",
      "record_id": 1002
    },
    {
      "id": "chunk:9112649d14aa15dc41c2546d9d76b903421890545f2ff030ba29fc92fb9f1340",
      "kind": "chunk",
      "path": "seed/docs/incident-demo-001.md",
      "chunk_id": "9112649d14aa15dc41c2546d9d76b903421890545f2ff030ba29fc92fb9f1340",
      "origin_id": "document:seed/docs/incident-demo-001.md",
      "source_revision": "3989f2c3583a8f87aee0dcc842adf615efa770f145aa9e3aeb2339a452b451a8"
    }
  ],
  "steps": [
    {
      "tool": "search_customers",
      "args": {
        "customer_name": "デモ青空商店",
        "branch": null,
        "limit": 5
      },
      "ok": true
    },
    {
      "tool": "search_shipments",
      "args": {
        "customer_id": 101,
        "shipment_id": null,
        "limit": 10
      },
      "ok": true
    },
    {
      "tool": "get_shipment_details",
      "args": {
        "shipment_id": "SHP-DEMO-001",
        "event_limit": 10
      },
      "ok": true
    },
    {
      "tool": "search_knowledge",
      "args": {
        "query": "仕分け停止による遅延",
        "kind": "document",
        "reference_id": "INC-DEMO-001",
        "limit": 5
      },
      "ok": true
    }
  ],
  "unresolved": []
}
```
