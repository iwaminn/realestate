#!/usr/bin/env python
"""
期限切れの仮登録ユーザーを削除するスクリプト
cronで定期実行することを推奨（例：1日1回）
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.models import PendingUser

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

def cleanup_expired_pending_users():
    """期限切れの仮登録ユーザーを削除"""
    
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 期限切れの仮登録を検索
        expired_users = session.query(PendingUser).filter(
            PendingUser.expires_at < datetime.utcnow()
        ).all()
        
        count = len(expired_users)
        
        if count > 0:
            # 削除実行
            for user in expired_users:
                print(f"削除: {user.email} (作成日: {user.created_at}, 有効期限: {user.expires_at})")
                session.delete(user)
            
            session.commit()
            print(f"\n✅ {count}件の期限切れ仮登録を削除しました")
        else:
            print("ℹ️ 期限切れの仮登録はありません")
            
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    cleanup_expired_pending_users()