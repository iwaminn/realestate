#!/usr/bin/env python3
"""
既存の成約価格データの建築年を数値形式に変換するスクリプト
"""
import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import TransactionPrice
from sqlalchemy import text

def update_built_year_num():
    """既存データのbuilt_yearから数値形式のbuilt_year_numを生成"""
    db = SessionLocal()
    try:
        print("既存データの建築年を数値形式に変換中...")

        # built_yearが存在するがbuilt_year_numがNULLのレコードを更新
        result = db.execute(text("""
            UPDATE transaction_prices
            SET built_year_num = CASE
                WHEN built_year ~ '^[0-9]{4}年?$' THEN
                    CAST(SUBSTRING(built_year FROM 1 FOR 4) AS INTEGER)
                WHEN built_year ~ '^[0-9]{4}' THEN
                    CAST(SUBSTRING(built_year FROM 1 FOR 4) AS INTEGER)
                ELSE NULL
            END
            WHERE built_year IS NOT NULL
              AND built_year != ''
              AND built_year_num IS NULL
        """))

        db.commit()
        print(f"✓ {result.rowcount}件の建築年を数値形式に変換しました")

        # 統計情報を表示
        stats = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(built_year) as with_text,
                COUNT(built_year_num) as with_num,
                MIN(built_year_num) as oldest,
                MAX(built_year_num) as newest,
                AVG(built_year_num) as average
            FROM transaction_prices
        """)).fetchone()

        print("\n=== 更新後の統計 ===")
        print(f"総レコード数: {stats.total:,}")
        print(f"建築年（文字列）: {stats.with_text:,}件")
        print(f"建築年（数値）: {stats.with_num:,}件")
        if stats.oldest:
            print(f"最古の建物: {stats.oldest}年")
            print(f"最新の建物: {stats.newest}年")
            print(f"平均築年: {stats.average:.1f}年")

        # 間取り情報の統計も表示
        layout_stats = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(layout) as with_layout,
                COUNT(DISTINCT layout) as unique_layouts
            FROM transaction_prices
        """)).fetchone()

        print("\n=== 間取り情報の統計 ===")
        print(f"間取り情報あり: {layout_stats.with_layout:,}件 ({layout_stats.with_layout*100/layout_stats.total:.1f}%)")
        print(f"間取りの種類: {layout_stats.unique_layouts}種類")

        # 上位の間取りを表示
        top_layouts = db.execute(text("""
            SELECT layout, COUNT(*) as count
            FROM transaction_prices
            WHERE layout IS NOT NULL
            GROUP BY layout
            ORDER BY count DESC
            LIMIT 10
        """)).fetchall()

        if top_layouts:
            print("\n上位の間取り:")
            for layout in top_layouts:
                print(f"  {layout.layout}: {layout.count:,}件")

    except Exception as e:
        print(f"エラー: {e}")
        db.rollback()
        return False
    finally:
        db.close()

    return True

def main():
    """メイン処理"""
    print("=== 既存成約価格データの更新 ===\n")

    if update_built_year_num():
        print("\n✅ 更新が正常に完了しました")
    else:
        print("\n❌ 更新に失敗しました")
        sys.exit(1)

if __name__ == "__main__":
    main()