#!/usr/bin/env python3
"""
国土交通省 不動産情報ライブラリAPIから間取りデータを取得して更新
"""
import os
import sys
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models import TransactionPrice
from sqlalchemy import text

# API設定
API_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001"
API_KEY = os.getenv("REINFOLIB_API_KEY", "97603fb774d448b1826804f92a6f6eff")

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

def fetch_transaction_data(year: int, quarter: int, city_code: str) -> List[Dict[str, Any]]:
    """
    APIから取引データを取得

    Args:
        year: 年（西暦）
        quarter: 四半期（1-4）
        city_code: 市区町村コード（港区: 13103）

    Returns:
        取引データのリスト
    """
    headers = {
        'Ocp-Apim-Subscription-Key': API_KEY,
        'Content-Type': 'application/json'
    }

    params = {
        'year': year,
        'quarter': quarter,
        'city': city_code
    }

    try:
        print(f"  APIから{year}年Q{quarter}のデータを取得中...")
        response = requests.get(API_BASE_URL, headers=headers, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            if 'data' in data:
                # デバッグ: 最初のアイテムを表示
                if data['data'] and len(data['data']) > 0:
                    print(f"  サンプルデータのキー: {list(data['data'][0].keys())[:10]}")
                # 成約価格情報のみフィルタリング、またはすべて返す
                return data['data']
            return []
        else:
            print(f"  ✗ API応答エラー (status: {response.status_code})")
            if response.status_code == 401:
                print(f"  ✗ APIキーが無効です。正しいAPIキーを設定してください。")
            return []

    except requests.exceptions.Timeout:
        print(f"  ✗ APIタイムアウト")
        return []
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return []

def update_layouts_from_api():
    """APIから間取りデータを取得して更新"""
    db = SessionLocal()

    # 区コードのマッピング
    district_codes = {
        "中央区": "13102",
        "千代田区": "13101",
        "新宿区": "13104",
        "渋谷区": "13113",
        "港区": "13103"
    }

    try:
        print("=== APIから間取りデータ更新処理開始 ===\n")

        # 間取りがNULLのレコードの統計を取得
        null_layout_count = db.query(TransactionPrice).filter(
            TransactionPrice.layout.is_(None)
        ).count()

        print(f"間取りがNULLのレコード数: {null_layout_count:,}件")

        if null_layout_count == 0:
            print("\n更新対象がありません")
            return

        # 区・年・四半期の組み合わせを取得
        combinations = db.execute(text("""
            SELECT DISTINCT district_name, transaction_year, transaction_quarter
            FROM transaction_prices
            WHERE layout IS NULL
            AND district_name IN ('中央区', '千代田区', '新宿区', '渋谷区')
            AND transaction_year IS NOT NULL
            AND transaction_quarter IS NOT NULL
            ORDER BY district_name, transaction_year DESC, transaction_quarter DESC
        """)).fetchall()

        print(f"更新対象の期間: {len(combinations)}件\n")

        total_updated = 0

        for i, (district_name, year, quarter) in enumerate(combinations):
            print(f"[{i+1}/{len(combinations)}] {district_name} {year}年Q{quarter}")
            
            # 区コードを取得
            city_code = district_codes.get(district_name)
            if not city_code:
                print(f"  ✗ 区コード未定義: {district_name}")
                continue

            # APIからデータを取得
            api_data = fetch_transaction_data(year, quarter, city_code)

            if not api_data:
                print(f"  - データなし")
                if i < len(combinations) - 1:
                    time.sleep(1)  # API負荷軽減
                continue

            print(f"  取得件数: {len(api_data)}件")
            
            # デバッグ: データのカテゴリー別統計
            if api_data and i == 0:  # 最初の期間のみ詳細表示
                categories = {}
                for item in api_data:
                    cat = item.get('PriceCategory', 'なし')
                    categories[cat] = categories.get(cat, 0) + 1
                    
                print(f"  カテゴリー別内訳:")
                for cat, count in categories.items():
                    print(f"    {cat}: {count}件")
                    
                # 成約価格情報のサンプルを探す
                for item in api_data:
                    if item.get('PriceCategory') == '成約価格情報':
                        print(f"  成約価格情報のサンプル:")
                        print(f"    DistrictName: {item.get('DistrictName')}")
                        print(f"    Area: {item.get('Area')}")
                        print(f"    FloorPlan: {item.get('FloorPlan')}")
                        break

            # 間取り情報のマッピングを作成
            layout_map = {}
            for item in api_data:
                # 成約価格情報のみ処理
                if item.get('PriceCategory') != '成約価格情報':
                    continue
                    
                # 間取り情報を取得（英語キー）
                layout = item.get('FloorPlan')
                if not layout:
                    continue

                # 地区名と面積で特定（英語キー）
                area_name = item.get('DistrictName', '')
                floor_area = item.get('Area')

                if area_name and floor_area:
                    try:
                        floor_area = float(str(floor_area).replace('㎡', '').replace(',', ''))
                        # 正規化した間取りを保存
                        key = f"{area_name}_{floor_area:.1f}"
                        layout_map[key] = normalize_layout(layout)
                    except:
                        continue

            if not layout_map:
                print(f"  - 間取りデータなし")
                if i < len(combinations) - 1:
                    time.sleep(1)
                continue
                    
            # デバッグ: layout_mapの最初の5件を表示
            if i == 0:
                print(f"  layout_mapのサンプル:")
                for j, (k, v) in enumerate(layout_map.items()):
                    if j >= 5:
                        break
                    print(f"    {k}: {v}")

            # データベースの既存レコードを更新
            updated = 0
            transactions = db.query(TransactionPrice).filter(
                TransactionPrice.district_name == district_name,
                TransactionPrice.transaction_year == year,
                TransactionPrice.transaction_quarter == quarter,
                TransactionPrice.layout.is_(None)
            ).all()
            
            # デバッグ: データベースの最初の5件を表示
            if i == 0 and transactions:
                print(f"  DBレコードのサンプル:")
                for j, t in enumerate(transactions[:5]):
                    print(f"    {t.area_name}_{t.floor_area:.1f}")

            for transaction in transactions:
                if transaction.area_name and transaction.floor_area:
                    key = f"{transaction.area_name}_{transaction.floor_area:.1f}"
                    if key in layout_map:
                        transaction.layout = layout_map[key]
                        updated += 1

            if updated > 0:
                db.commit()
                total_updated += updated
                print(f"  ✓ {updated}件更新")
            else:
                print(f"  - 更新なし")

            # API負荷軽減のため待機
            if i < len(combinations) - 1:
                time.sleep(1)

        print(f"\n=== 更新完了 ===")
        print(f"合計更新件数: {total_updated:,}件")

        # 最終統計
        final_stats = db.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(layout) as with_layout,
                COUNT(DISTINCT layout) as unique_layouts
            FROM transaction_prices
        """)).fetchone()

        print(f"\n最終統計:")
        print(f"  総レコード数: {final_stats.total:,}")
        print(f"  間取りあり: {final_stats.with_layout:,} ({final_stats.with_layout*100/final_stats.total:.1f}%)")
        print(f"  間取りの種類: {final_stats.unique_layouts}")

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
    finally:
        db.close()

def main():
    """メイン処理"""
    if not API_KEY:
        print("エラー: APIキーが設定されていません")
        print("環境変数 REINFOLIB_API_KEY を設定してください")
        return

    print(f"APIキー: {API_KEY[:8]}...")
    update_layouts_from_api()

if __name__ == "__main__":
    main()