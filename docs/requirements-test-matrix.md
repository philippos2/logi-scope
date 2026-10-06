# 要件と単体テストの対応表

[要件文書](requirements.md)の各項目を、実在するテストと対応づける。新しい要件や受入条件を追加する表ではない。テスト構成・件数・実行方法は[単体テスト分類表](test-catalog.md)を参照する。

「単体」は偽LLM・偽Tool・偽HTTP等による制御の確認、「統合」は実PostgreSQL、「実モデル/手動」は実LLM・埋め込み・正本照合・ブラウザ確認を指す。表は確認範囲を示し、テストの存在だけでPASSとはしない。実行結果は[検証記録](history/README.md)と対象コミットのCIを参照する。要件の粒度が異なるため要件カバー率は算出しない。

## Agent・Tool・API・データ

各テスト名はリンク先ファイルに存在する関数名。パラメータ展開された個々のケースは分類表の収集方法で確認できる。

| 要件の参照 | 確認する動作 | 対応テスト | 方法・確認範囲 / 残る確認 |
|---|---|---|---|
| [§1・§2・§7](requirements.md#1-目的) | 前段の結果を使う多段調査 | [test_agent.py](../tests/test_agent.py): `test_multihop_uses_observed_id_and_records_only_executed_steps`、`test_business_and_document_results_are_combined_through_observed_ids` | 単体：結果を次のLLM要求へ渡す。偽LLMの予定応答なので実LLMの自律選択・固定フロー不在の証明は別途実モデルとコードレビュー |
| [§2 LLM](requirements.md#llm) | OpenAI互換接続・設定差し替え | [test_llm.py](../tests/test_llm.py): `test_tool_request_and_call_id_roundtrip_drops_reasoning` / [test_foundation.py](../tests/test_foundation.py): `test_llm_connection_can_be_overridden_by_environment` | 単体：要求形式・設定。採用モデルとの互換性は実接続 |
| [§2 エージェント](requirements.md#エージェント) | 最大回数・打ち切り | [test_agent.py](../tests/test_agent.py): `test_limits_include_attempts_and_allow_only_one_finalization`、`test_invalid_attempt_consumes_tool_budget` | 単体：不正試行も予算へ含め、最終化回数を制限 |
| §2 エージェント | 同一操作の反復防止 | [test_agent.py](../tests/test_agent.py): `test_duplicate_is_normalized_cached_and_stops_without_second_execution`、`test_repeated_failed_operation_is_not_reexecuted_or_leaked` | 単体：引数正規化後の重複・失敗済み操作を再実行しない |
| §2 エージェント・§10 | 引数検証・限定的修正 | [test_tools.py](../tests/test_tools.py): `test_invalid_input_is_rejected_before_database_access` / [test_agent.py](../tests/test_agent.py): `test_one_invalid_argument_correction_is_not_an_executed_step`、`test_repeated_invalid_arguments_stop_after_one_correction` | 単体：型・範囲・未知フィールド拒否、1回の修正上限 |
| §2 エージェント・§10 | Tool例外・タイムアウト | [test_agent.py](../tests/test_agent.py): `test_unexpected_tool_exception_is_sanitized_and_recorded`、`test_tool_timeout_cancels_execution_and_preserves_failure_step`、`test_total_timeout_cancels_tool_and_does_not_start_finalization` | 単体：制御された失敗・キャンセル・部分履歴 |
| §2 Tools | 登録Toolのみ実行 | [test_tools.py](../tests/test_tools.py): `test_unknown_tool_is_not_dispatched` / [test_agent.py](../tests/test_agent.py): `test_unregistered_or_invalid_json_never_executes` | 単体：任意SQLを含む未知Toolを拒否 |
| §2 Tools・§10 | 顧客・荷物・イベント・問い合わせの正常検索 | [test_business_tools.py](../tests/integration/test_business_tools.py): `test_simple_shipment_status_and_combined_filters`、`test_multistage_ids_and_incident_reference`、`test_inquiry_original_includes_resolution` | 正常なORM検索は単体で代替せず、実DB統合で確認 |
| §2 Tools | DB権限による読み取り専用 | [test_database.py](../tests/integration/test_database.py): `test_runtime_authenticates_as_reader`、`test_db_permissions_reject_writes_even_without_readonly_default` / [test_rag.py](../tests/integration/test_rag.py): `test_reader_cannot_delete_derived_index` | 統合：DBロールと実際の書込拒否。資格情報のコンテナ分離はCIの`verify_container_credentials.py` |
| §2 エージェント・[§6](requirements.md#6-応答形式) | 内部推論を公開しない・実行側の履歴 | [test_llm.py](../tests/test_llm.py): `test_tool_request_and_call_id_roundtrip_drops_reasoning` / [test_agent.py](../tests/test_agent.py): `test_invalid_final_has_one_retry_and_never_adopts_fake_history_or_sources` | 単体：推論フィールド除外、偽履歴・参照元不採用。任意の本文の意味まで網羅しない |
| [§3](requirements.md#3-データ要件) | 架空・日本語データ | [test_rag_documents.py](../tests/test_rag_documents.py): `test_repository_documents_keep_original_paths_and_incident_ids` | 正本パスの単体確認はあるが、架空性・日本語品質の専用単体テストなし。seed/文書レビュー、実検索・回答の確認 |
| §2 DB・[§4](requirements.md#4-正本と派生データ) | PostgreSQL＋pgvector、正本との関連 | [test_database.py](../tests/integration/test_database.py): `test_pgvector_and_restricted_role_are_configured`、`test_foreign_key_rejects_unknown_customer` | 統合：拡張・FK。DB構成はComposeとマイグレーションのレビュー |
| §4 | 派生データの由来・再生成 | [test_rag_ingest.py](../tests/test_rag_ingest.py): `test_derived_rows_keep_origin_revision_and_reference_ids` / [test_rag.py](../tests/integration/test_rag.py): `test_regeneration_removes_deleted_sources_and_does_not_duplicate`、`test_failed_replacement_rolls_back_to_previous_index` | 単体：ID・版。統合：再生成・削除・原子性。実埋め込みの品質は別検証 |
| §4・[§9 C](requirements.md#c-非構造化検索--正本取得) | 問い合わせ検索から正本取得・引用 | [test_agent.py](../tests/test_agent.py): `test_inquiry_search_requires_cited_authoritative_original`、`test_search_chunk_alone_is_not_accepted_as_authoritative_inquiry` / [test_rag.py](../tests/integration/test_rag.py): `test_vector_search_preserves_origin_for_original_lookup` | 単体：正本取得・引用を要求。統合：検索IDで実際に正本取得。回答の正本反映は人による意味確認 |
| [§5](requirements.md#5-api)・§6 | 質問入力と4項目のHTTP契約 | [test_api.py](../tests/test_api.py): `test_success_returns_public_four_field_contract`、`test_invalid_input_never_runs_agent` | 単体/ASGI：契約と拒否。実HTTP・curl・画面は実環境確認 |
| [§8](requirements.md#8-不明曖昧な情報)・§9 D | 不存在・情報不足 | [test_agent.py](../tests/test_agent.py): `test_nonexistent_shipment_has_search_history_and_unresolved`、`test_unknown_recovery_time_is_missing_evidence_not_missing_target`、`test_model_cannot_claim_not_found_without_attempting_search` | 単体：検索履歴とコード補正。任意の質問への事実性保証はなし |
| §8・§9 E | 曖昧な候補を選ばない | [test_agent.py](../tests/test_agent.py): `test_customer_ambiguity_never_selects_candidate_even_in_same_batch` / [test_business_tools.py](../tests/integration/test_business_tools.py): `test_customer_candidates_are_preserved_and_can_be_disambiguated` | 単体：調査停止。統合：候補保持・営業所条件。実モデル回答は別確認 |
| [§10](requirements.md#10-自動テスト) | 実LLMなしの主要制御検証と分離 | 上記単体群、[CI](../.github/workflows/ci.yml) | 単体は偽依存、統合は実DB＋偽ベクトル。CIで実LLMを起動しない |
| [§11](requirements.md#11-再現性) | 第三者のセットアップ・モデル非格納 | [再現性検証記録](history/reproducibility-verification.md)、Compose・ロック・gitignore | 対応する単体テストなし。別Compose環境の再構築確認とファイルレビュー。任意の第三者PCは未検証 |
| [§12](requirements.md#12-readme)・[§13](requirements.md#13-対象外) | 文書の完全性・対象外・主張の適切さ | README・文書・コードレビュー | 専用自動テストなし。人による確認 |

## A〜Eの受入条件

| シナリオ | 単体 / 統合で確認する部分 | 実モデル・人による確認 |
|---|---|---|
| A：単純検索 | `test_single_lookup_answer_has_evidence_and_one_operation`（Agent）と実DBの状態検索 | 実際の荷物正本と状態・時刻・根拠が一致するか |
| B：多段調査 | 観測IDの引き継ぎ、業務・文書結果の統合、実DBの障害参照 | 対象荷物に関連する原因を正しく説明するか。無関係な報告や未確定の到着予定を断定していないか |
| C：正本取得 | チャンクだけの回答拒否、問い合わせ正本の取得と参照元 | 11:15（日本時間）の配達完了記録と案内を正しく反映し、受領確認の実施を捏造していないか |
| D：回答不能 | 不存在の検索・履歴・`not_found` | 実検索後、存在しない情報を生成していないか |
| E：曖昧性 | 両候補保持・勝手な後続検索の拒否 | 両候補と追加情報を示し、任意の候補を選んでいないか |

[verify_demo.py](../scripts/verify_demo.py)は実LLMへ送信し、期待語句・根拠ID・依存関係と既知の矛盾を自動チェックする。`test_demo_assessment.py`はその判定器への固定入力を検証するもので、実モデルの回答品質の証明ではない。`passed`は自動チェックの成功に限り、受入合格には`manual_review_check`に沿った正本照合が必要。[実測記録](history/final-runtime-verification.md)は記載コミット・条件での結果であり、現在版の新規実行結果に読み替えない。

## フロントエンドと配送更新

| 要件の参照 | 確認する動作 | 対応テスト | 方法・残る確認 |
|---|---|---|---|
| [§12.1](requirements.md#121-デモ用フロントエンド) | 質問例・入力制限・重複送信・4項目表示 | [App.test.tsx](../frontend/src/App.test.tsx): `samples populate input without sending; empty, oversized and IME submissions are blocked`、`duplicate sends are blocked and partial answer, sources and failed tool remain visible` | DOM＋偽通信。見た目・実IME・レスポンシブは手動 |
| §12.1 | 通信・形式・タイムアウト失敗、再操作 | [App.test.tsx](../frontend/src/App.test.tsx): `busy error retains input and allows another send`、`invalid response is shown as an error, not a successful investigation`、`client timeout ends waiting and ignores late response` | DOM＋偽通信。実HTTP・開発プロキシは実環境確認 |
| [§16](requirements.md#16-ローカル配送更新デモの追加範囲) | 新規・同一再送・入力・制御されたエラー | [test_delivery_updates_api.py](../tests/test_delivery_updates_api.py): `test_new_event_and_replay`、`test_invalid_input_never_reaches_writer` | 単体/ASGI。実DBの冪等性は次行 |
| §16 | 重複・キー衝突・時刻逆転・同時更新・遷移 | [test_delivery_updates.py](../tests/integration/test_delivery_updates.py): `test_duplicate_concurrent_send_is_one_event`、`test_conflicting_replay_rolls_back`、`test_old_event_and_terminal_transition_leave_no_partial_write`、`test_distinct_concurrent_updates_keep_newest_state` | 実DB統合。通信断・自動再処理等の本番運用は対象外 |
| §16 | 部分書込防止・専用荷物と権限・固定データ分離 | 同ファイル：`test_failure_after_flush_rolls_back_event_and_shipment`、`test_missing_recovery_and_restricted_targets`、`test_reader_cannot_update_and_writer_cannot_change_other_columns` | 実DB統合。コンテナの資格情報分離は別CIチェック |
| §16・[更新設計](delivery-updates.md) | 更新後の参照・Tool内の同一スナップショット | 同ファイル：`test_update_and_replay_visible_to_reader`、`test_details_keep_one_snapshot_when_update_commits_between_reads` | 統合。複数Tool間で同じ観測時点になる保証はない |
| §16 | 調査/報告の排他・受付不明時の同一再送 | [App.test.tsx](../frontend/src/App.test.tsx): `report submission blocks investigation and the report link selects the update shipment` / [DeliveryUpdate.test.tsx](../frontend/src/DeliveryUpdate.test.tsx): `an ongoing investigation blocks update submission`、`timeout retains the report and late responses cannot replace a retry` | DOM＋偽通信。報告後の実LLM再調査は別の実環境確認 |
| §16 | 問い合わせ・文書・埋め込みは更新しない | 更新API契約、更新ロールの統合テスト、コードレビュー | 任意文書入力を受け付けない構成を確認。全資源の不変性を一括検証する専用単体テストはなし |

## 保守

要件・テスト・パラメータを変更したときに、この表と分類表の参照・件数を見直す。新しい要件に対応テストがなければ、未対応と理由を明記する。手動確認で補う項目を自動確認済みと扱わず、検証日時・モデル・環境・対象コミット・未検証範囲は履歴へ記録する。
