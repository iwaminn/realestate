#!/usr/bin/env python3
"""
開発環境用メール確認スクリプト
最新の仮登録ユーザーのメールアドレスを自動的に確認します
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import requests

# データベース接続
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_latest_pending_user():
    """最新の仮登録ユーザーを取得"""
    with SessionLocal() as session:
        result = session.execute(
            text("""
                SELECT email, verification_token, expires_at 
                FROM pending_users 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
        ).fetchone()
        
        if result:
            return {
                'email': result[0],
                'token': result[1],
                'expires_at': result[2]
            }
        return None

def verify_email(token):
    """メール確認APIを呼び出す"""
    url = f"http://localhost:8000/api/auth/verify-email"
    params = {'token': token}
    
    try:
        response = requests.get(url, params=params)
        return response.json(), response.status_code
    except requests.exceptions.RequestException as e:
        print(f"APIエラー: {e}")
        return None, None

def main():
    print("開発環境用メール確認ツール")
    print("=" * 40)
    
    # 最新の仮登録ユーザーを取得
    pending_user = get_latest_pending_user()
    
    if not pending_user:
        print("仮登録ユーザーが見つかりません")
        print("\nヒント: アカウントを作成してから実行してください")
        return
    
    print(f"見つかった仮登録ユーザー:")
    print(f"  メール: {pending_user['email']}")
    print(f"  期限: {pending_user['expires_at']}")
    
    # 期限チェック
    if pending_user['expires_at'] < datetime.utcnow():
        print("\n⚠️ トークンが期限切れです。再度アカウントを作成してください。")
        return
    
    print(f"\n確認URL:")
    print(f"  http://localhost:3001/verify-email?token={pending_user['token']}")
    
    # メール確認を実行
    print(f"\n自動確認を実行中...")
    result, status_code = verify_email(pending_user['token'])
    
    if status_code == 200:
        print(f"✅ メール確認成功: {result.get('message', '')}")
        print(f"   確認されたメール: {result.get('email', '')}")
        print(f"\nこのメールアドレスとパスワードでログインできます。")
    elif status_code:
        print(f"❌ メール確認失敗: {result.get('detail', 'エラーが発生しました')}")
    else:
        print("❌ APIへの接続に失敗しました")
    
    # 本登録済みユーザーの確認
    print("\n現在の本登録済みユーザー:")
    with SessionLocal() as session:
        users = session.execute(
            text("SELECT email, created_at FROM users ORDER BY created_at DESC LIMIT 5")
        ).fetchall()
        
        if users:
            for user in users:
                print(f"  - {user[0]} (登録: {user[1].strftime('%Y-%m-%d %H:%M')})")
        else:
            print("  （本登録済みユーザーはいません）")

if __name__ == "__main__":
    main()