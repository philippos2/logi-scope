# CIのリンタとmainのマージ制限

設定日: 2026-10-06。作業ブランチ: `feature/ci-lint-and-branch-protection`。

従来のCIは自動テスト・型チェック・ビルド・マイグレーション差分確認のみで、リンタは未導入だった。GitHub APIでもmainは未保護だった。

## 追加した静的検査

- Python: Ruff。src・tests・scripts・migrationsの35ファイルに`E4`・`E7`・`E9`・`F`を適用。
- React・TypeScript: ESLint、typescript-eslint、React Hooks、Fast Refreshの推奨ルール。`--max-warnings 0`で警告も失敗にする。
- CIの既存2ジョブへリンタを追加し、必須チェックに使うジョブ名は維持した。
- 依存は開発用グループへ追加し、uv・npmロックで固定。既存npmパッケージの解決済み版は変更していない。

## GitHubへ適用した設定

mainのブランチ保護をGitHub APIで設定し、読み戻して確認した。

| 設定 | 値 |
|---|---|
| 必須チェック | `Tests and migrations`、`Frontend tests and build` |
| チェックの提供元 | GitHub Actions（app ID 15368） |
| 最新mainへの追従 | 必須（strict） |
| 管理者への適用 | 有効 |
| PR | 必須 |
| 他人の承認数 | 0（一人開発のため） |
| 強制push・main削除 | 不許可 |

この設定はGitHub側に保持され、cloneでは作成されない。必須チェックの名前を変える場合はブランチ保護も更新する。リンタを含む新しいワークフローのGitHub上の実行結果は、この変更のPRで確認する。

## ローカル検証

- Ruff・ESLintとも既存コードに合格。
- Ruffが未定義名、ESLintが未使用変数を検出して終了コード1になることを標準入力で確認。異常コードのファイルはリポジトリへ追加していない。
- 実DB統合を含むバックエンドテスト: 165件中165件成功。
- frontendテスト: 7件中7件成功。型チェック・ビルド成功。
- ソースをマウントしないfrontendイメージでESLint成功。
- 更新したPythonイメージのビルドと、CIと同じ管理サービスのRuff実行も成功。Compose設定・文書参照・差分チェック成功。

今回の変更は開発時の検査とGitHub設定であり、実LLMの受入シナリオは再実行していない。
