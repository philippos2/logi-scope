# 単体テスト分類表

テスト側から、対象・目的・依存を整理する。要件側からの対応は[要件と単体テストの対応表](requirements-test-matrix.md)を参照する。単体テストに加え、混同を避けるため実DBの統合テストと実モデルの確認を別表に示す。

件数はmain `6c6af46`のテストコードから収集したケース数。パラメータ展開後の件数であり、関数数・アサーション数・カバレッジではない。Pythonは191ケースの単体・コンポーネントテストと60ケースのDB統合テスト、計251ケース。frontendは17ケース。

## 単体・コンポーネントテスト

いずれも実LLM・実DB・実埋め込みモデルを使わず、CIで実行する。APIはHTTPXのASGITransport、画面はHappy DOMで確認するため、実サーバー・実ブラウザによる結合確認とは区別する。

| 対象 / ファイル | ケース数 | 主な目的（正常・異常・境界） | 代替する依存 | 代表テスト |
|---|---:|---|---|---|
| [Agent Loop](../tests/test_agent.py) | 84 | 多段調査、観測ID・参照元の照合、修正再試行、重複・上限・例外・中断、曖昧性 | 偽LLM・偽Tool | `test_multihop_uses_observed_id_and_records_only_executed_steps`、`test_limits_include_attempts_and_allow_only_one_finalization` |
| [業務Tool](../tests/test_tools.py) | 25 | 入力・登録Tool検証、DB例外の非公開化、タイムアウト時のセッション終了 | 偽セッション（実検索は統合テスト） | `test_invalid_input_is_rejected_before_database_access`、`test_timeout_cancels_query_and_closes_session` |
| [LLMクライアント](../tests/test_llm.py) | 18 | OpenAI互換要求、呼出ID、内部推論除外、不正応答・HTTP失敗・サイズ上限 | HTTPX MockTransport | `test_tool_request_and_call_id_roundtrip_drops_reasoning`、`test_malformed_truncated_or_reasoning_output_is_rejected` |
| [調査API](../tests/test_api.py) | 15 | 4項目の契約、入力拒否、HTTPエラー、同時要求拒否、起動・終了処理 | 偽Runner・ランタイム部品 | `test_success_returns_public_four_field_contract`、`test_concurrent_request_is_rejected_and_lock_released` |
| [設定・生存確認](../tests/test_foundation.py) | 5 | 接続先・モデル変更、タイムアウト境界、外部接続なしのhealth | 環境変数・ASGITransport | `test_llm_connection_can_be_overridden_by_environment`、`test_timeout_must_be_positive_and_bounded` |
| [RAG文書処理](../tests/test_rag_documents.py) | 9 | 正本パス・版、分割時の本文保持、由来の検証、外部へのsymlink拒否 | ローカル文書・一時ファイル | `test_long_paragraph_is_split_without_losing_text`、`test_source_cannot_mix_document_and_inquiry_origins` |
| [RAG索引準備](../tests/test_rag_ingest.py) | 3 | 正本ID・版・業務参照IDの保持、不正なベクトル件数拒否 | 偽埋め込み | `test_derived_rows_keep_origin_revision_and_reference_ids`、`test_bad_embedding_count_does_not_prepare_partial_index` |
| [配送更新API](../tests/test_delivery_updates_api.py) | 11 | 新規・再送のHTTP契約、入力拒否、内部情報を含まない失敗応答 | 偽更新サービス | `test_new_event_and_replay`、`test_invalid_input_never_reaches_writer` |
| [デモ判定](../tests/test_demo_assessment.py) | 21 | 同義表現、既知の否定・矛盾、受領確認の未裏付け断定を判定 | 固定の公開応答 | `test_delay_cause_rejects_contradictory_answer_with_valid_evidence`、`test_original_inquiry_rejects_denied_delivery_record` |
| **Python小計** | **191** | | | |
| [調査画面](../frontend/src/App.test.tsx) | 8 | サンプル入力、IME・入力上限、重複送信、部分回答、通信・形式エラー、古い応答の抑止 | fetch等のモック | `samples populate input without sending; empty, oversized and IME submissions are blocked` |
| [配送報告画面](../frontend/src/DeliveryUpdate.test.tsx) | 9 | 二重送信、拒否後の編集、同じキーでの再送、受付不明、調査との排他 | fetch等のモック | `timeout retains the report and late responses cannot replace a retry` |
| **frontend小計** | **17** | | | |

## 実DBの統合テスト

実PostgreSQL・pgvectorと管理用/reader/ingest/更新用ロールを使用する。実LLMを使わず、RAGのベクトルは決定論的な偽物。類似検索のSQL・参照元・権限は確認するが、日本語の意味検索の品質は保証しない。`LOGISCOPE_DB_TESTS=1`で有効化し、CIでは使い捨てDBで実行する。

| 対象 / ファイル | ケース数 | 確認範囲 | 代表テスト |
|---|---:|---|---|
| [業務検索](../tests/integration/test_business_tools.py) | 28 | 顧客候補・条件検索・イベント・問い合わせ正本・件数・上限・日本時間・障害参照 | `test_multistage_ids_and_incident_reference`、`test_shipment_total_count_is_independent_of_example_limit` |
| [DB・マイグレーション](../tests/integration/test_database.py) | 12 | FK、seed再実行、reader認証・書込拒否、pgvector、マイグレーション往復 | `test_db_permissions_reject_writes_even_without_readonly_default`、`test_seed_can_be_reapplied_without_duplicate_records` |
| [RAG索引・検索](../tests/integration/test_rag.py) | 11 | 正本読み込み、再生成・削除・ロールバック、正本遷移、参照IDフィルター、権限 | `test_vector_search_preserves_origin_for_original_lookup`、`test_failed_replacement_rolls_back_to_previous_index` |
| [配送更新](../tests/integration/test_delivery_updates.py) | 9 | 冪等性、時刻・遷移、同時更新、部分書込防止、専用権限、Tool内のスナップショット | `test_duplicate_concurrent_send_is_one_event`、`test_details_keep_one_snapshot_when_update_commits_between_reads` |
| **小計** | **60** | | |

## 実モデル・環境での確認

| 手段 | 対象 | 自動処理と人による確認の境界 |
|---|---|---|
| [verify_embeddings.py](../scripts/verify_embeddings.py) / [verify_rag.py](../scripts/verify_rag.py) | 実CPU埋め込み、日本語検索、DB・正本遷移 | 固定質問の候補とIDを確認。任意の質問の検索品質は未保証 |
| [verify_demo.py](../scripts/verify_demo.py) | 実LLM・API・DB・RAGのA〜E | 自動チェック成功の`passed`だけで受入合格にしない。公開回答を正本と人が照合 |
| [verify_delivery_updates.py](../scripts/verify_delivery_updates.py) | 更新前後の実LLM調査 | 登録状態と公開応答を確認。実画面操作は別途確認 |
| ブラウザの手操作 | 見た目・レスポンシブ・日本語IME・報告後の再調査 | DOMテストだけでは表示・実IME・実ブラウザを保証しない |
| [CI設定](../.github/workflows/ci.yml) | 資格情報分離、リンタ、型、ビルド、マイグレーション | pytest/Vitest以外のチェック。単体テスト件数に含めない |

## 実行と記録

実行コマンドは[READMEのテスト方法](../README.md#テスト)、実測は[検証記録](history/README.md)を参照。表の件数は収集値で、全件合格の継続保証ではない。文書作成時の確認（2026年10月7日、テストコードはmain `6c6af46`と同一）ではPythonの非integration 191件中191件、frontend 17件中17件が成功した。DB統合・実モデルは今回再実行していない。

Pythonの収集は `docker compose exec app uv run --locked pytest --collect-only -q`。件数には無効化中のDB統合テストも含む。テストの追加・削除・パラメータ変更時は収集数、分類、次の対応表を更新する。要件の追加・変更時も対応表を更新し、結果の日時・条件は履歴へ記録する。
