# 技術選定・検証の履歴

現在の機能と利用方法は[README](../../README.md)、準備手順は[セットアップガイド](../getting-started.md)、現在の設計は[設計書](../design.md)を参照。ここでは日時付きの実測条件、選定過程、修正経緯を扱う。各記録の件数はその時点の結果であり、現在のテスト総数とは限らない。

- [ローカルLLMの選定・事前検証](local-llm-selection.md)
- [DB・業務Tools・RAGの基盤検証](foundation-verification.md)
- [Agent APIの実接続検証と修正](agent-demo-verification.md)
- [空DB・埋め込みキャッシュからの再現性確認とCI](reproducibility-verification.md)
- [React画面・APIプロキシの検証](frontend-verification.md)

API版では自動テスト141件中141件成功、実LLMのA〜Eを各2回実行して10件中10件成功。別の空DB・埋め込みキャッシュでも5件中5件成功した。詳細と実行条件は各記録を参照。これらは小規模な架空データでの結果であり、任意の質問や別環境の品質を保証しない。
