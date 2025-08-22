#!/usr/bin/env python
"""
既存の物件の最初の掲載日（earliest_listing_date）を再計算するスクリプト

アクティブ・非アクティブに関わらず、その物件に紐づくすべての掲載情報の中で
最も古い日付を設定します。
"""

import os
import sys
from pathlib import Path

# プロジェクトルートのパスを追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

os.environ.setdefault('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')

from sqlalchemy import func, case
from backend.app.database import SessionLocal
from backend.app.models import MasterProperty, PropertyListing


def recalculate_earliest_listing_dates():
    """すべての物件のearliest_listing_dateを再計算"""
    db = SessionLocal()
    
    try:
        # すべての物件を取得
        properties = db.query(MasterProperty).all()
        total = len(properties)
        updated_count = 0
        
        print(f"総物件数: {total}")
        
        for i, property in enumerate(properties, 1):
            # すべての掲載情報の中で最も古い掲載日を取得
            # first_published_at > published_at > first_seen_at > created_at の優先順位で最も古い日付を選択
            
            # 各掲載の最も信頼できる日付を取得
            effective_date = case(
                (PropertyListing.first_published_at.isnot(None), PropertyListing.first_published_at),
                (PropertyListing.published_at.isnot(None), PropertyListing.published_at),
                (PropertyListing.first_seen_at.isnot(None), PropertyListing.first_seen_at),
                else_=PropertyListing.created_at
            )
            
            # 最も古い日付を取得
            earliest_date = db.query(func.min(effective_date))\
                .filter(PropertyListing.master_property_id == property.id)\
                .scalar()
            
            # 更新が必要な場合のみ更新
            if earliest_date != property.earliest_listing_date:
                old_date = property.earliest_listing_date
                property.earliest_listing_date = earliest_date
                updated_count += 1
                
                if updated_count % 100 == 0:
                    print(f"進捗: {i}/{total} ({i*100/total:.1f}%) - 更新済み: {updated_count}件")
                    db.commit()  # 定期的にコミット
        
        # 最終コミット
        db.commit()
        
        print(f"\n完了: {total}件中{updated_count}件を更新しました")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("earliest_listing_dateの再計算を開始します...")
    recalculate_earliest_listing_dates()