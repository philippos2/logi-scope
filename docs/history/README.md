# 技術選定・検証の履歴

現在の機能と利用方法は[README](../../README.md)、準備手順は[セットアップガイド](../getting-started.md)、現在の設計は[設計書](../design.md)を参照。ここでは日時付きの実測条件、選定過程、修正経緯を扱う。各記録の件数はその時点の結果であり、現在のテスト総数とは限らない。

- [ローカルLLMの選定・事前検証](local-llm-selection.md)
- [DB・業務Tools・RAGの基盤検証](foundation-verification.md)
- [Agent APIの実接続検証と修正](agent-demo-verification.md)
- [空DB・埋め込みキャッシュからの再現性確認とCI](reproducibility-verification.md)
- [React画面・APIプロキシの検証](frontend-verification.md)
- [対象未指定の荷物調査の修正](agent-target-grounding.md)
- [完成後の文書・版表記の整理](release-documentation-cleanup.md)
- [CIのリンタとmainのマージ制限](ci-lint-and-branch-protection.md)
- [配送状態による一覧検索と架空データの拡充](shipment-status-search-and-seed.md)
- [荷物の総件数と概要回答の補正](shipment-count-accuracy.md)
- [顧客30件・荷物90件への架空データ拡充](demo-data-expansion.md)
- [追加質問の導線と当初予定の表記](sample-questions-and-schedule.md)
- [デモデータと質問例の日本語整理](japanese-wording-cleanup.md)
- [コンテナの資格情報分離](container-credential-isolation.md)
- [配送イベント更新デモ](delivery-updates.md)
- [配送状況の報告画面の検証](delivery-update-ui.md)

API版では自動テスト141件中141件成功、実LLMのA〜Eを各2回実行して10件中10件成功。別の空DB・埋め込みキャッシュでも5件中5件成功した。詳細と実行条件は各記録を参照。これらは小規模な架空データでの結果であり、任意の質問や別環境の品質を保証しない。
