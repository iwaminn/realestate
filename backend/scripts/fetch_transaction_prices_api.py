#!/usr/bin/env python3
"""
国土交通省 不動産情報ライブラリAPIを使用して成約価格情報を取得してデータベースに保存
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import requests
import json
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from app.models import TransactionPrice, TransactionDataFetchCompletion
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")
API_KEY = os.getenv("REINFOLIB_API_KEY", "97603fb774d448b1826804f92a6f6eff")

# 不動産情報ライブラリAPI
API_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001"

# 東京23区の市区町村コード
AREA_CODES = {
    "千代田区": "13101",
    "中央区": "13102",
    "港区": "13103",
    "新宿区": "13104",
    "文京区": "13105",
    "台東区": "13106",
    "墨田区": "13107",
    "江東区": "13108",
    "品川区": "13109",
    "目黒区": "13110",
    "大田区": "13111",
    "世田谷区": "13112",
    "渋谷区": "13113",
    "中野区": "13114",
    "杉並区": "13115",
    "豊島区": "13116",
    "北区": "13117",
    "荒川区": "13118",
    "板橋区": "13119",
    "練馬区": "13120",
    "足立区": "13121",
    "葛飾区": "13122",
    "江戸川区": "13123"
}

# デフォルトは港区
DEFAULT_AREA_CODE = "13103"


class TransactionPriceAPIFetcher:
    """不動産情報ライブラリAPI経由で成約価格情報を取得"""

    def __init__(self):
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(bind=engine)
        self.db = SessionLocal()
        self.api_key = API_KEY
        self.headers = {
            "Ocp-Apim-Subscription-Key": self.api_key
        }

    def fetch_data(self, year: int, quarter: Optional[int] = None, area: str = "13", city_code: Optional[str] = None) -> List[Dict]:
        """
        指定期間の成約価格情報を取得

        Args:
            year: 取引年
            quarter: 四半期（1-4）、省略時は年間全体
            area: 都道府県コード（13=東京都）

        Returns:
            成約価格情報のリスト
        """
        params = {
            "year": year,
            "area": area,
            "priceClassification": "02"  # 02=成約価格情報のみ
        }

        if quarter:
            params["quarter"] = quarter

        print(f"取得中: {year}年{f'第{quarter}四半期' if quarter else ''}...")

        try:
            response = requests.get(
                API_BASE_URL,
                params=params,
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 401:
                print("エラー: APIキーが無効です")
                return []

            response.raise_for_status()
            data = response.json()

            if "data" in data and data["data"]:
                # 指定された市区町村のデータをフィルタリング
                if city_code:
                    filtered_data = [
                        d for d in data["data"]
                        if d.get("MunicipalityCode") == city_code
                    ]
                    area_name = next((k for k, v in AREA_CODES.items() if v == city_code), city_code)
                    print(f"  {area_name}: {len(filtered_data)}件取得（全体: {len(data['data'])}件）")
                    return filtered_data
                else:
                    print(f"  全体: {len(data['data'])}件取得")
                    return data["data"]
            else:
                print(f"  データなし")
                return []

        except requests.RequestException as e:
            print(f"APIエラー: {e}")
            return []

    def parse_transaction(self, raw_data: Dict, city_code: str) -> Optional[TransactionPrice]:
        """
        APIレスポンスをTransactionPriceオブジェクトに変換

        Args:
            raw_data: APIから取得したデータ

        Returns:
            TransactionPriceオブジェクト
        """
        try:
            # マンション取引のみ対象
            property_type = raw_data.get("Type", "")
            if "マンション" not in property_type:
                return None

            # 取引時期をパース（例：2024年第1四半期）
            period = raw_data.get("Period", "")
            year = None
            quarter = None
            if period:
                if "年" in period:
                    year_str = period.split("年")[0]
                    try:
                        year = int(year_str)
                    except:
                        pass
                if "第" in period and "四半期" in period:
                    try:
                        quarter = int(period.split("第")[1].split("四半期")[0])
                    except:
                        pass

            # 価格を数値に変換（APIは万円単位で返す）
            price = None
            price_str = raw_data.get("TradePrice", "")
            if price_str:
                # カンマと単位を除去
                price_str = price_str.replace(",", "").replace("円", "").replace("万", "")
                try:
                    # APIが円単位の場合は万円に変換
                    if len(price_str) > 4:
                        price = int(price_str) // 10000
                    else:
                        price = int(price_str)
                except:
                    pass

            # 専有面積（㎡）
            floor_area = None
            area_str = raw_data.get("Area", "")
            if area_str:
                try:
                    floor_area = float(area_str.replace("㎡", "").replace(",", ""))
                except:
                    pass

            # 平米単価（万円/㎡）
            price_per_sqm = None
            if price and floor_area and floor_area > 0:
                price_per_sqm = int((price / floor_area) * 10000)  # 円/㎡に変換

            # 建築年を西暦に変換（数値形式で保存）
            built_year_str = raw_data.get("BuildingYear", "")
            built_year = None  # 数値形式で保存
            if built_year_str:
                try:
                    # "年"が含まれている場合は除去
                    if "年" in built_year_str:
                        built_year = int(built_year_str.split("年")[0])
                    else:
                        built_year = int(built_year_str)
                except:
                    pass

            # 間取り情報を取得（FloorPlanフィールドから）
            layout = raw_data.get("FloorPlan")

            # 一意のトランザクションID生成
            transaction_id = f"{city_code}_{year}Q{quarter}_{raw_data.get('DistrictName', '')}_{floor_area}_{price}".replace(" ", "_")

            transaction = TransactionPrice(
                transaction_id=transaction_id,

                # 物件情報
                property_type=property_type,
                district_code=city_code,
                district_name=raw_data.get("Municipality", ""),
                area_name=raw_data.get("DistrictName"),

                # 取引情報
                transaction_price=price,
                price_per_sqm=price_per_sqm,
                transaction_period=period,
                transaction_year=year,
                transaction_quarter=quarter,

                # 建物情報
                floor_area=floor_area,
                floor_number=None,  # 階数情報はAPIに含まれていない
                layout=layout,  # 間取り情報を正しく取得
                built_year=built_year,  # 建築年（数値）
                building_structure=raw_data.get("Structure"),
                use=raw_data.get("Use"),

                # 都市計画
                city_planning=raw_data.get("CityPlanning"),
                building_coverage_ratio=None,  # APIレスポンスに含まれない場合
                floor_area_ratio=None,  # APIレスポンスに含まれない場合

                # その他
                purpose=raw_data.get("Purpose"),
                remarks=raw_data.get("Remarks")
            )

            return transaction

        except Exception as e:
            print(f"パースエラー: {e}")
            print(f"データ: {json.dumps(raw_data, ensure_ascii=False, indent=2)}")
            return None

    def save_to_database(self, transactions: List[TransactionPrice]):
        """
        取引価格情報をデータベースに保存（重複チェック付き）

        Args:
            transactions: TransactionPriceオブジェクトのリスト
        """
        saved_count = 0
        updated_count = 0
        skipped_count = 0

        for transaction in transactions:
            try:
                # 既存レコードチェック
                existing = self.db.query(TransactionPrice).filter(
                    TransactionPrice.transaction_id == transaction.transaction_id
                ).first()

                if existing:
                    # 価格が変わっている場合は更新
                    if existing.transaction_price != transaction.transaction_price:
                        existing.transaction_price = transaction.transaction_price
                        existing.price_per_sqm = transaction.price_per_sqm
                        existing.updated_at = datetime.now()
                        updated_count += 1
                    else:
                        skipped_count += 1
                else:
                    self.db.add(transaction)
                    saved_count += 1

            except Exception as e:
                print(f"保存エラー: {e}")
                self.db.rollback()
                continue

        self.db.commit()
        print(f"保存完了: {saved_count}件追加、{updated_count}件更新、{skipped_count}件スキップ")

    def record_fetch_completion(self, city_code: str, city_name: str, year: int, quarter: int, record_count: int):
        """
        データ取得完了を記録
        
        Args:
            city_code: 市区町村コード
            city_name: 市区町村名
            year: 取得年
            quarter: 四半期
            record_count: 取得した件数
        """
        try:
            # 既存レコードをチェック
            existing = self.db.query(TransactionDataFetchCompletion).filter(
                TransactionDataFetchCompletion.city_code == city_code,
                TransactionDataFetchCompletion.year == year,
                TransactionDataFetchCompletion.quarter == quarter
            ).first()
            
            if existing:
                # 更新
                existing.record_count = record_count
                existing.completed_at = datetime.now()
                existing.updated_at = datetime.now()
            else:
                # 新規作成
                completion = TransactionDataFetchCompletion(
                    city_code=city_code,
                    city_name=city_name,
                    year=year,
                    quarter=quarter,
                    record_count=record_count,
                    completed_at=datetime.now()
                )
                self.db.add(completion)
            
            self.db.commit()
            print(f"完了記録を保存: {city_name} {year}年Q{quarter} ({record_count}件)")
        except Exception as e:
            print(f"完了記録の保存エラー: {e}")
            self.db.rollback()

    def is_fetch_completed(self, city_code: str, year: int, quarter: int) -> bool:
        """
        指定期間のデータ取得が完了しているかチェック
        
        Args:
            city_code: 市区町村コード
            year: 取得年
            quarter: 四半期
            
        Returns:
            完了していればTrue
        """
        completion = self.db.query(TransactionDataFetchCompletion).filter(
            TransactionDataFetchCompletion.city_code == city_code,
            TransactionDataFetchCompletion.year == year,
            TransactionDataFetchCompletion.quarter == quarter
        ).first()
        
        return completion is not None

    def fetch_recent_data(self, city_code: Optional[str] = None):
        """
        最新の成約価格情報を取得（過去1四半期分）
        """
        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1

        # 前四半期を計算
        if current_quarter == 1:
            year = current_year - 1
            quarter = 4
        else:
            year = current_year
            quarter = current_quarter - 1

        area_name = next((k for k, v in AREA_CODES.items() if v == city_code), "全エリア") if city_code else "全エリア"
        print(f"最新データを取得: {area_name} - {year}年第{quarter}四半期")

        # データ取得
        raw_data = self.fetch_data(year, quarter, city_code=city_code)

        # パース
        transactions = []
        for data in raw_data:
            # 市区町村コードを取得
            data_city_code = data.get("MunicipalityCode", city_code or DEFAULT_AREA_CODE)
            transaction = self.parse_transaction(data, data_city_code)
            if transaction:
                transactions.append(transaction)

        print(f"{len(transactions)}件のマンション成約データをパースしました")

        # 保存
        if transactions:
            self.save_to_database(transactions)
            
            # 完了記録を保存
            if city_code:
                self.record_fetch_completion(city_code, area_name, year, quarter, len(transactions))

    def fetch_historical_data(self, from_year: int = 2021, to_year: Optional[int] = None, city_code: Optional[str] = None, force_refetch: bool = False):
        """
        指定期間の成約価格情報を取得

        Args:
            from_year: 開始年（デフォルト: 2021、成約価格情報の提供開始年）
            to_year: 終了年（省略時は現在年）
            city_code: 市区町村コード
            force_refetch: Trueの場合、完了記録を無視して再取得
        """
        if to_year is None:
            to_year = datetime.now().year

        area_name = next((k for k, v in AREA_CODES.items() if v == city_code), "全エリア") if city_code else "全エリア"
        print(f"{area_name}の成約価格情報を取得します（{from_year}年〜{to_year}年）")

        all_transactions = []

        for year in range(from_year, to_year + 1):
            for quarter in range(1, 5):
                # 未来の四半期はスキップ
                current_date = datetime.now()
                if year == current_date.year and quarter > ((current_date.month - 1) // 3 + 1):
                    continue

                # 完了記録をチェック（force_refetchがFalseの場合のみ）
                if not force_refetch and city_code and self.is_fetch_completed(city_code, year, quarter):
                    print(f"{area_name} - {year}年第{quarter}四半期: 取得済み（スキップ）")
                    continue

                # データ取得
                raw_data = self.fetch_data(year, quarter, city_code=city_code)

                # パース
                period_transactions = []
                for data in raw_data:
                    # 市区町村コードを取得
                    data_city_code = data.get("MunicipalityCode", city_code or DEFAULT_AREA_CODE)
                    transaction = self.parse_transaction(data, data_city_code)
                    if transaction:
                        period_transactions.append(transaction)

                if period_transactions:
                    all_transactions.extend(period_transactions)
                    # 期間ごとに保存と完了記録
                    self.save_to_database(period_transactions)
                    if city_code:
                        self.record_fetch_completion(city_code, area_name, year, quarter, len(period_transactions))

                # レート制限対策
                time.sleep(1)

        print(f"合計{len(all_transactions)}件のマンション成約データを取得しました")

    def get_latest_data_period(self, city_code: Optional[str] = None):
        """
        データベースに保存されている最新のデータ期間を取得
        
        Args:
            city_code: 市区町村コード（指定時はその区の最新データを取得）

        Returns:
            (year, quarter) のタプル
        """
        query = self.db.query(
            TransactionPrice.transaction_year,
            TransactionPrice.transaction_quarter
        )
        
        # 市区町村コードが指定されている場合はフィルタリング
        if city_code:
            query = query.filter(TransactionPrice.district_code == city_code)
        
        latest = query.order_by(
            TransactionPrice.transaction_year.desc(),
            TransactionPrice.transaction_quarter.desc()
        ).first()

        if latest:
            return latest.transaction_year, latest.transaction_quarter
        else:
            return None, None

    def update_missing_periods(self, city_code: Optional[str] = None, force_refetch: bool = False):
        """
        データベースに存在しない期間のデータを自動取得
        
        Args:
            city_code: 市区町村コード（指定時はその区のみ更新）
            force_refetch: Trueの場合、完了記録を無視して再取得
        """
        # 区ごとの最新データを取得
        latest_year, latest_quarter = self.get_latest_data_period(city_code=city_code)

        current_date = datetime.now()
        current_year = current_date.year
        current_quarter = (current_date.month - 1) // 3 + 1

        area_name = next((k for k, v in AREA_CODES.items() if v == city_code), "全エリア") if city_code else "全エリア"

        if not latest_year:
            # データが全くない場合は2021年から取得
            print(f"{area_name}: データベースが空です。2021年から取得を開始します。")
            self.fetch_historical_data(from_year=2021, city_code=city_code, force_refetch=force_refetch)
            return

        print(f"{area_name} - 最新データ: {latest_year}年第{latest_quarter}四半期")
        print(f"現在: {current_year}年第{current_quarter}四半期")

        # 不足期間を取得
        all_transactions = []
        year = latest_year
        quarter = latest_quarter

        while year < current_year or (year == current_year and quarter < current_quarter):
            # 次の四半期に進める
            if quarter == 4:
                year += 1
                quarter = 1
            else:
                quarter += 1

            # 未来の四半期はスキップ
            if year == current_year and quarter > current_quarter:
                break

            # 完了記録をチェック（force_refetchがFalseの場合のみ）
            if not force_refetch and city_code and self.is_fetch_completed(city_code, year, quarter):
                print(f"{area_name} - {year}年第{quarter}四半期: 取得済み（スキップ）")
                continue

            print(f"不足データを取得: {area_name} - {year}年第{quarter}四半期")

            # データ取得
            raw_data = self.fetch_data(year, quarter, city_code=city_code)

            # パース
            period_transactions = []
            for data in raw_data:
                # 市区町村コードを取得
                data_city_code = data.get("MunicipalityCode", city_code or DEFAULT_AREA_CODE)
                transaction = self.parse_transaction(data, data_city_code)
                if transaction:
                    period_transactions.append(transaction)

            if period_transactions:
                all_transactions.extend(period_transactions)
                # 期間ごとに保存と完了記録
                self.save_to_database(period_transactions)
                if city_code:
                    self.record_fetch_completion(city_code, area_name, year, quarter, len(period_transactions))

            # レート制限対策
            time.sleep(1)

        if all_transactions:
            print(f"合計{len(all_transactions)}件の新規データを取得しました")
        else:
            print("新規データはありません")

    def close(self):
        """データベース接続をクローズ"""
        self.db.close()


def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(description='不動産情報ライブラリAPIから成約価格情報を取得')
    parser.add_argument('--mode', choices=['recent', 'historical', 'update'], default='update',
                        help='実行モード: recent(最新のみ), historical(過去全て), update(不足分のみ)')
    parser.add_argument('--area', type=str, default=None,
                        help='エリア名（例: 港区, 中央区, 千代田区）またはallで東京23区全体')
    parser.add_argument('--from-year', type=int, default=2021,
                        help='取得開始年（historicalモード時）')
    parser.add_argument('--to-year', type=int,
                        help='取得終了年（historicalモード時）')
    parser.add_argument('--force-refetch', action='store_true',
                        help='完了記録を無視して強制的に再取得')
    parser.add_argument('--list-areas', action='store_true',
                        help='利用可能なエリア一覧を表示')

    args = parser.parse_args()

    # エリア一覧を表示
    if args.list_areas:
        print("利用可能なエリア:")
        for area_name, area_code in AREA_CODES.items():
            print(f"  {area_name}: {area_code}")
        return

    # エリア名からコードを取得
    city_code = None
    if args.area:
        if args.area.lower() == 'all':
            # 全エリアを取得
            print("東京23区全体のデータを取得します")
            city_code = None
        elif args.area in AREA_CODES:
            city_code = AREA_CODES[args.area]
            print(f"{args.area}のデータを取得します（コード: {city_code}）")
        else:
            print(f"エラー: '{args.area}' は有効なエリア名ではありません")
            print("利用可能なエリア:")
            for area_name in AREA_CODES.keys():
                print(f"  - {area_name}")
            return
    else:
        # デフォルトは港区
        city_code = DEFAULT_AREA_CODE
        print("エリアが指定されていないため、デフォルトの港区を取得します")

    fetcher = TransactionPriceAPIFetcher()

    try:
        # city_code = Noneの場合は全23区を取得
        if city_code is None:
            city_codes = list(AREA_CODES.values())
            print(f"東京23区すべてのデータを取得します（{len(city_codes)}区）")
        else:
            city_codes = [city_code]

        for code in city_codes:
            area_name = next((k for k, v in AREA_CODES.items() if v == code), code)
            print(f"\n{'='*60}")
            print(f"処理中: {area_name} ({code})")
            print(f"{'='*60}\n")

            if args.mode == 'recent':
                # 最新四半期のみ取得
                fetcher.fetch_recent_data(city_code=code)
            elif args.mode == 'historical':
                # 指定期間すべて取得
                fetcher.fetch_historical_data(from_year=args.from_year, to_year=args.to_year, city_code=code, force_refetch=args.force_refetch)
            else:  # update
                # 不足期間を自動判定して取得
                fetcher.update_missing_periods(city_code=code, force_refetch=args.force_refetch)

        print(f"\n{'='*60}")
        print("すべての区の処理が完了しました")
        print(f"{'='*60}\n")
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()