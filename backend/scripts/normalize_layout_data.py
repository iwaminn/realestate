#!/usr/bin/env python3
"""
データベース内の間取りデータの表記ゆれを統一する
全角英数字を半角に変換
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models import TransactionPrice
from sqlalchemy import text

def normalize_layout(layout: str) -> str:
    """間取りを正規化（全角を半角に変換）"""
    if not layout:
        return None

    # 全角英数字を半角に変換
    layout = layout.translate(str.maketrans(
        '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ',
        '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    ))

    # 表記ゆれの統一
    layout = layout.replace('ＬＤＫ', 'LDK')
    layout = layout.replace('ＤＫ', 'DK')
    layout = layout.replace('Ｋ', 'K')
    layout = layout.replace('Ｓ', 'S')
    layout = layout.replace('Ｒ', 'R')
    layout = layout.replace('ＬＤ', 'LD')
    layout = layout.replace(' ', '')

    return layout

def normalize_all_layouts():
    """全ての間取りデータを正規化"""
    db = SessionLocal()

    try:
        print("=== 間取りデータの表記統一処理 ===\n")

        # 現在の統計を表示
        before_stats = db.execute(text("""
            SELECT COUNT(DISTINCT layout) as unique_layouts
            FROM transaction_prices
            WHERE layout IS NOT NULL
        """)).fetchone()

        print(f"処理前の間取りの種類: {before_stats.unique_layouts}")

        # 全ての間取りデータを取得
        transactions = db.query(TransactionPrice).filter(
            TransactionPrice.layout.isnot(None)
        ).all()

        print(f"処理対象: {len(transactions)}件")

        updated_count = 0
        for transaction in transactions:
            original = transaction.layout
            normalized = normalize_layout(original)

            if original != normalized:
                transaction.layout = normalized
                updated_count += 1

                if updated_count % 100 == 0:
                    print(f"{updated_count}件更新済み...")
                    db.commit()

        db.commit()

        print(f"\n=== 更新完了 ===")
        print(f"更新件数: {updated_count}件")

        # 最終統計
        after_stats = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(layout) as with_layout,
                COUNT(DISTINCT layout) as unique_layouts
            FROM transaction_prices
        """)).fetchone()

        print(f"\n最終統計:")
        print(f"  総レコード数: {after_stats.total:,}")
        print(f"  間取りあり: {after_stats.with_layout:,} ({after_stats.with_layout*100/after_stats.total:.1f}%)")
        print(f"  間取りの種類: {before_stats.unique_layouts} → {after_stats.unique_layouts}")

        # 間取り別の統計（上位15件）
        layout_stats = db.execute(text("""
            SELECT layout, COUNT(*) as count
            FROM transaction_prices
            WHERE layout IS NOT NULL
            GROUP BY layout
            ORDER BY count DESC
            LIMIT 15
        """)).fetchall()

        print(f"\n間取り別の件数:")
        for stat in layout_stats:
            print(f"  {stat.layout}: {stat.count:,}件")

    except Exception as e:
        print(f"エラー: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    """メイン処理"""
    normalize_all_layouts()

if __name__ == "__main__":
    main()