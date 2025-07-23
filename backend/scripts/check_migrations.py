#!/usr/bin/env python3
"""
モデル変更時にマイグレーションが作成されているかチェックするスクリプト
"""

import subprocess
import sys
import os

def check_pending_migrations():
    """
    未適用のマイグレーションがあるかチェック
    """
    try:
        # 環境変数を設定
        env = os.environ.copy()
        env['DATABASE_URL'] = env.get('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate_db')
        
        # 現在のリビジョンを取得
        current_result = subprocess.run(
            ['poetry', 'run', 'alembic', 'current'],
            capture_output=True,
            text=True,
            env=env
        )
        
        # ヘッドリビジョンを取得
        head_result = subprocess.run(
            ['poetry', 'run', 'alembic', 'heads'],
            capture_output=True,
            text=True,
            env=env
        )
        
        current_rev = current_result.stdout.strip()
        head_rev = head_result.stdout.strip()
        
        if current_rev != head_rev:
            print("⚠️  警告: 未適用のマイグレーションがあります")
            print(f"現在: {current_rev}")
            print(f"最新: {head_rev}")
            print("\n以下のコマンドを実行してください:")
            print("poetry run alembic upgrade head")
            return False
            
        # 自動生成で検出される変更があるかチェック
        check_result = subprocess.run(
            ['poetry', 'run', 'alembic', 'check'],
            capture_output=True,
            text=True,
            env=env
        )
        
        if check_result.returncode != 0 and 'No changes detected' not in check_result.stderr:
            print("⚠️  警告: モデルの変更が検出されました")
            print("マイグレーションを作成してください:")
            print('poetry run alembic revision --autogenerate -m "説明"')
            return False
            
        print("✅ データベーススキーマは最新です")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"エラー: {e}")
        return False
    except FileNotFoundError:
        print("エラー: poetryまたはalembicがインストールされていません")
        return False

def check_models_file_changed():
    """
    models.pyが変更されているかgitで確認
    """
    try:
        # git diffでmodels.pyの変更を確認
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD', 'backend/app/models.py'],
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip():
            print("📝 models.py が変更されています")
            return True
            
        # ステージングエリアも確認
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', 'backend/app/models.py'],
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip():
            print("📝 models.py が変更されています（ステージング済み）")
            return True
            
        return False
        
    except subprocess.CalledProcessError:
        return False

def main():
    """
    メイン処理
    """
    print("=== データベースマイグレーションチェック ===\n")
    
    # models.pyが変更されているかチェック
    models_changed = check_models_file_changed()
    
    # マイグレーションの状態をチェック
    migrations_ok = check_pending_migrations()
    
    if models_changed and migrations_ok:
        print("\n⚠️  models.pyが変更されていますが、マイグレーションは作成されていません")
        print("変更内容を確認して、必要に応じてマイグレーションを作成してください:")
        print('poetry run alembic revision --autogenerate -m "変更の説明"')
        sys.exit(1)
    elif not migrations_ok:
        sys.exit(1)
    else:
        print("\n✅ すべてのチェックが完了しました")
        sys.exit(0)

if __name__ == "__main__":
    main()