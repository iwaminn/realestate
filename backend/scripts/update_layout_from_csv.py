#!/usr/bin/env python3
"""
CSVファイルから間取り情報を取得して既存のデータベースレコードを更新
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import csv
import re
from app.database import SessionLocal
from app.models import TransactionPrice
from sqlalchemy import text

def parse_period(period_str: str) -> tuple:
    """取引時期をパース"""
    if not period_str:
        return None, None

    # "2024年第1四半期" or "令和6年第1四半期" のパターン
    if '年' in period_str:
        year_match = re.search(r'(\d{4})年', period_str)
        if year_match:
            year = int(year_match.group(1))
        else:
            # 令和の場合
            reiwa_match = re.search(r'令和(\d+)年', period_str)
            if reiwa_match:
                year = 2018 + int(reiwa_match.group(1))
            else:
                year = None

        # 四半期の抽出
        quarter_match = re.search(r'第(\d)四半期', period_str)
        if quarter_match:
            quarter = int(quarter_match.group(1))
        else:
            quarter = None

        return year, quarter

    return None, None

def parse_area(area_str: str) -> float:
    """面積をパース"""
    if not area_str:
        return None

    # ㎡、平米などを除去
    area_str = str(area_str).replace('㎡', '').replace('平米', '').replace(',', '')

    try:
        return float(area_str)
    except:
        return None

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

def update_layouts_from_csv(csv_path: str):
    """CSVファイルから間取り情報を読み取ってデータベースを更新"""
    db = SessionLocal()

    try:
        # CSVファイルを読み込み
        encodings = ['utf-8', 'utf-8-sig', 'shift_jis', 'cp932']

        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)

                    # CSVデータを読み込んで辞書に格納
                    layout_map = {}

                    for row in reader:
                        # 中古マンションのみ対象
                        property_type = row.get('種類') or row.get('Type')
                        if property_type and '中古マンション' not in property_type:
                            continue

                        # 成約価格情報のみ対象
                        price_info = row.get('価格情報区分')
                        if price_info != "成約価格情報":
                            continue

                        # 必要な情報を抽出
                        area_name = row.get('地区名') or row.get('DistrictName')
                        period = row.get('取引時期') or row.get('取引時点')
                        floor_area = parse_area(row.get('面積（㎡）') or row.get('面積'))
                        layout = row.get('間取り') or row.get('Layout')

                        if not layout or not area_name or not period or not floor_area:
                            continue

                        year, quarter = parse_period(period)
                        if not year or not quarter:
                            continue

                        # 正規化
                        layout = normalize_layout(layout)

                        # キーを作成（地区名、年、四半期、面積で特定）
                        key = f"{area_name}_{year}_{quarter}_{floor_area:.1f}"
                        layout_map[key] = layout

                    print(f"CSVから{len(layout_map)}件の間取り情報を読み込みました")
                    break

            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"エラー: {e}")
                raise

        # データベースの既存レコードを更新
        updated_count = 0

        # 間取りがNULLのレコードを取得
        transactions = db.query(TransactionPrice).filter(
            TransactionPrice.layout.is_(None),
            TransactionPrice.district_name == "港区"
        ).all()

        print(f"間取りがNULLのレコード: {len(transactions)}件")

        for transaction in transactions:
            # キーを作成
            if transaction.area_name and transaction.transaction_year and transaction.transaction_quarter and transaction.floor_area:
                key = f"{transaction.area_name}_{transaction.transaction_year}_{transaction.transaction_quarter}_{transaction.floor_area:.1f}"

                if key in layout_map:
                    transaction.layout = layout_map[key]
                    updated_count += 1

                    if updated_count % 100 == 0:
                        print(f"{updated_count}件更新済み...")
                        db.commit()

        db.commit()
        print(f"\n=== 更新完了 ===")
        print(f"更新件数: {updated_count}件")

        # 最終統計
        stats = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(layout) as with_layout,
                COUNT(DISTINCT layout) as unique_layouts
            FROM transaction_prices
        """)).fetchone()

        print(f"\n最終統計:")
        print(f"  総レコード数: {stats.total:,}")
        print(f"  間取りあり: {stats.with_layout:,} ({stats.with_layout*100/stats.total:.1f}%)")
        print(f"  間取りの種類: {stats.unique_layouts}")

        # 間取り別の統計
        layout_stats = db.execute(text("""
            SELECT layout, COUNT(*) as count
            FROM transaction_prices
            WHERE layout IS NOT NULL
            GROUP BY layout
            ORDER BY count DESC
            LIMIT 10
        """)).fetchall()

        print(f"\n上位の間取り:")
        for stat in layout_stats:
            print(f"  {stat.layout}: {stat.count:,}件")

    except Exception as e:
        print(f"エラー: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    """メイン処理"""
    csv_path = "/home/ubuntu/realestate/data/transaction_prices/Tokyo_Minato_Ward_20192_20251_utf8.csv"

    print("=== CSVファイルから間取り情報を更新 ===\n")
    print(f"CSVファイル: {csv_path}")

    if not Path(csv_path).exists():
        print(f"エラー: CSVファイルが見つかりません: {csv_path}")
        return

    update_layouts_from_csv(csv_path)

if __name__ == "__main__":
    main()