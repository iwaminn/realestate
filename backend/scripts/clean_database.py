#!/usr/bin/env python3
"""
データベースをクリーンアップするスクリプト
確認なしで全テーブルを削除して再作成
"""

import sys
import os
from sqlalchemy import create_engine, text

# プロジェクトルートをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.database import DATABASE_URL
from backend.app.models import Base


def clean_database():
    """データベースをクリーンアップ"""
    print("データベースをクリーンアップ中...")
    
    # エンジンを作成
    engine = create_engine(DATABASE_URL)
    
    try:
        # 全てのテーブルを削除
        print("既存のテーブルを削除中...")
        Base.metadata.drop_all(bind=engine)
        print("✅ 全てのテーブルを削除しました")
        
        # 全てのテーブルを再作成
        print("\nテーブルを再作成中...")
        Base.metadata.create_all(bind=engine)
        
        print("✅ 以下のテーブルが作成されました:")
        print("  - buildings (建物マスター)")
        print("  - building_aliases (建物名エイリアス)")
        print("  - master_properties (物件マスター)")
        print("  - property_listings (物件掲載情報)")
        print("  - listing_price_history (掲載価格履歴)")
        print("  - property_images (物件画像)")
        
        # テーブルの件数を確認
        with engine.connect() as conn:
            for table_name in ['buildings', 'master_properties', 'property_listings']:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.scalar()
                print(f"  - {table_name}: {count} 件")
        
        print("\n✅ データベースのクリーンアップが完了しました！")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        raise


if __name__ == "__main__":
    clean_database()