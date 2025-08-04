#!/usr/bin/env python3
"""
建物重複検出のパフォーマンス改善用インデックスを追加
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

# 環境変数から設定を読み込む
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@localhost:5432/realestate")

def main():
    """インデックスを追加"""
    print("建物重複検出用のインデックスを追加します...")
    
    # データベース接続
    engine = create_engine(DATABASE_URL)
    
    indexes = [
        # 建物名の前方一致検索用
        "CREATE INDEX IF NOT EXISTS idx_buildings_normalized_name_prefix ON buildings (LEFT(normalized_name, 3))",
        
        # 住所の前方一致検索用
        "CREATE INDEX IF NOT EXISTS idx_buildings_address_prefix ON buildings (LEFT(address, 10))",
        
        # 築年でのフィルタリング用
        "CREATE INDEX IF NOT EXISTS idx_buildings_built_year ON buildings (built_year)",
        
        # 総階数でのフィルタリング用
        "CREATE INDEX IF NOT EXISTS idx_buildings_total_floors ON buildings (total_floors)",
        
        # 複合インデックス：築年と総階数
        "CREATE INDEX IF NOT EXISTS idx_buildings_built_year_floors ON buildings (built_year, total_floors)",
        
        # 物件数カウント用（既に存在するはず）
        "CREATE INDEX IF NOT EXISTS idx_master_properties_building_id ON master_properties (building_id)"
    ]
    
    with engine.connect() as conn:
        for index_sql in indexes:
            try:
                print(f"実行中: {index_sql[:50]}...")
                conn.execute(text(index_sql))
                conn.commit()
                print("  ✓ 成功")
            except Exception as e:
                print(f"  ✗ エラー: {e}")
    
    print("\nインデックスの追加が完了しました。")
    
    # 統計情報を更新
    print("\n統計情報を更新しています...")
    with engine.connect() as conn:
        try:
            conn.execute(text("ANALYZE buildings"))
            conn.execute(text("ANALYZE master_properties"))
            conn.commit()
            print("✓ 統計情報の更新が完了しました")
        except Exception as e:
            print(f"✗ 統計情報の更新エラー: {e}")

if __name__ == "__main__":
    main()