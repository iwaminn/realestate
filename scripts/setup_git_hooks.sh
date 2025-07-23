#!/bin/bash
# Git hooksをセットアップするスクリプト

echo "Git hooksをセットアップしています..."

# Git hooksディレクトリを設定
git config core.hooksPath .githooks

echo "✅ Git hooksが有効化されました"
echo ""
echo "以下のhookが利用可能です:"
echo "- pre-commit: models.py 変更時のマイグレーションチェック"
echo ""
echo "無効化したい場合は以下を実行:"
echo "git config --unset core.hooksPath"