# ローカルLLM選定・事前検証の履歴

2026-10-05〜06の選定時点の記録。現在の準備手順は[実行ガイド](../getting-started.md#wsl側のollama)を参照する。メモリ上の架空Toolによる事前検証であり、完成Agentの受入結果ではない。

Qwenは12件中12件成功、Mistralは曖昧性3件中0件成功、その他9件中9件成功（合計12件中9件成功）。Qwenを第一候補とし、不採用のMistralモデルと検証用別名は削除済み。以下のMistralコマンドは当時の検証を再現するための記録。

## Qwen3 30B-A3B Instructの事前検証

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

## Mistral Small 3.2 24Bの事前検証

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

## コンテナからの接続検証

2026-10-06にコンテナからモデル一覧とTool Callingを確認。多段調査・該当なし・曖昧性・人為的エラー後の再送を各1回実行し、4/4合格（27.69秒、2.69秒、3.14秒、8.34秒）。これは接続経路の確認であり、実DB/RAGや完成Agentの受入検証ではありません。

