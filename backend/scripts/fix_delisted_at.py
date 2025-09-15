#!/usr/bin/env python3
"""
既存の非アクティブな掲載にdelisted_atを設定する修正スクリプト

非アクティブ（is_active=False）でdelisted_atがNULLの掲載について、
last_confirmed_at + 24時間 の値をdelisted_atに設定します。

（管理画面の「掲載情報を更新」は24時間以上確認されていない掲載を
非アクティブにするため、last_confirmed_atの24時間後が適切な
delisted_atとなります）
"""

import sys
import os
from datetime import datetime, timedelta

# パスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import SessionLocal
from backend.app.models import PropertyListing
from sqlalchemy import and_

def fix_delisted_at():
    """delisted_atがNULLの非アクティブ掲載を修正"""
    session = SessionLocal()
    
    try:
        # 対象となる掲載を取得
        print("delisted_atがNULLの非アクティブ掲載を検索中...")
        
        listings_to_fix = session.query(PropertyListing).filter(
            and_(
                PropertyListing.is_active == False,
                PropertyListing.delisted_at.is_(None),
                PropertyListing.last_confirmed_at.isnot(None)
            )
        ).all()
        
        total_count = len(listings_to_fix)
        print(f"\n修正対象: {total_count}件")
        
        if total_count == 0:
            print("修正対象の掲載はありません。")
            return
        
        # 確認
        print("\n修正内容:")
        print("- is_active=Falseでdelisted_at=NULLの掲載について")
        print("- last_confirmed_at + 24時間 の値をdelisted_atに設定します")
        print("  （管理画面の仕様に合わせ、24時間後を非掲載日時とします）")
        
        response = input("\n修正を実行しますか？ (yes/no): ")
        if response.lower() != 'yes':
            print("修正をキャンセルしました。")
            return
        
        # 修正実行
        print("\n修正を実行中...")
        fixed_count = 0
        
        for listing in listings_to_fix:
            if listing.last_confirmed_at:
                # last_confirmed_atの24時間後をdelisted_atとして設定
                listing.delisted_at = listing.last_confirmed_at + timedelta(hours=24)
                fixed_count += 1
                
                if fixed_count % 100 == 0:
                    print(f"  {fixed_count}/{total_count} 件完了...")
        
        # コミット
        session.commit()
        print(f"\n✅ 修正完了: {fixed_count}件のdelisted_atを設定しました")
        
        # 修正後の確認
        remaining = session.query(PropertyListing).filter(
            and_(
                PropertyListing.is_active == False,
                PropertyListing.delisted_at.is_(None)
            )
        ).count()
        
        if remaining > 0:
            print(f"⚠️ 警告: まだ{remaining}件の非アクティブ掲載でdelisted_atがNULLです")
            print("  （last_confirmed_atもNULLの掲載の可能性があります）")
        else:
            print("✅ すべての非アクティブ掲載にdelisted_atが設定されています")
            
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    print("=" * 60)
    print("delisted_at修正スクリプト")
    print("=" * 60)
    fix_delisted_at()