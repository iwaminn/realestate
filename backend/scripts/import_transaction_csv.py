#!/usr/bin/env python3
"""
国土交通省 不動産情報ライブラリからダウンロードしたCSVファイルをインポート

使用方法:
1. https://www.reinfolib.mlit.go.jp/realEstatePrices/ から港区のCSVをダウンロード
2. /home/ubuntu/realestate/data/transaction_prices/ にCSVファイルを配置
3. このスクリプトを実行
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import csv
import re
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import TransactionPrice
from app.utils.logger import setup_logger

logger = setup_logger(__name__, "import_csv.log")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")

class TransactionCSVImporter:
    """CSVインポートクラス"""

    def __init__(self):
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(bind=engine)
        self.db = SessionLocal()

    def parse_csv_file(self, csv_path: str, check_anomaly: bool = True) -> list:
        """CSVファイルを解析"""
        transactions = []
        self.anomaly_count = 0  # 異常値のカウンタ

        # CSVファイルのエンコーディングを試す（Shift-JIS or UTF-8）
        encodings = ['shift_jis', 'cp932', 'utf-8', 'utf-8-sig']

        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding) as f:
                    # ヘッダー行を確認
                    first_line = f.readline()
                    logger.info(f"CSVヘッダー（{encoding}）: {first_line[:100]}")

                    # ファイルを最初から読み直す
                    f.seek(0)
                    reader = csv.DictReader(f)

                    for row_num, row in enumerate(reader, 1):
                        if row_num == 1:
                            logger.info(f"カラム名: {list(row.keys())}")

                        transaction = self.parse_row(row, row_num, check_anomaly)
                        if transaction:
                            transactions.append(transaction)

                        if row_num % 100 == 0:
                            logger.info(f"{row_num}行処理済み...")

                    logger.info(f"CSVファイルから{len(transactions)}件の取引データを読み込みました")
                    break

            except UnicodeDecodeError:
                logger.debug(f"エンコーディング {encoding} で読み込み失敗")
                continue
            except Exception as e:
                logger.error(f"CSVファイル読み込みエラー: {e}")
                raise

        return transactions

    def parse_row(self, row: Dict[str, Any], row_num: int, check_anomaly: bool = True) -> Optional[TransactionPrice]:
        """CSV行をTransactionPriceオブジェクトに変換"""
        try:
            # カラム名の可能性があるパターン（国土交通省のCSVフォーマット）
            # 種類、地域、市区町村、地区名、取引価格、坪単価、間取り、面積、取引時点、建築年、建物の構造、用途、今後の利用目的、前面道路、都市計画、建ぺい率、容積率、最寄駅、駅距離など

            # カラム名のマッピング（国土交通省のCSVフォーマットに対応）
            property_type = row.get('種類') or row.get('Type') or row.get('物件種別')

            # マンション取引のみ対象
            if property_type and 'マンション' not in property_type and '中古' not in property_type:
                return None

            # 港区のデータのみ対象
            district = row.get('市区町村名') or row.get('市区町村') or row.get('Municipality')
            if district and '港区' not in district:
                return None

            # 取引時期のパース（「取引時期」カラムを使用）
            period = row.get('取引時期') or row.get('取引時点') or row.get('Period')
            year, quarter = self.parse_period(period)

            # 価格のパース（「取引価格（総額）」カラムを使用）
            price = self.parse_price(row.get('取引価格（総額）') or row.get('取引価格') or row.get('TradePrice'))

            # 面積のパース
            floor_area = self.parse_area(row.get('面積（㎡）') or row.get('面積') or row.get('Area'))

            # 単価の計算
            price_per_sqm = None
            if price and floor_area and floor_area > 0:
                price_per_sqm = int((price * 10000) / floor_area)  # 円/㎡に変換

            # 駅距離のパース
            station_distance = self.parse_station_distance(
                row.get('最寄駅：距離（分）') or row.get('駅距離') or row.get('MinTimeToNearestStation')
            )

            # 価格情報区分（成約価格情報/不動産取引価格情報）を取得
            price_info_type = row.get('価格情報区分') or ""
            
            # 成約価格情報のみを対象とする
            if price_info_type != "成約価格情報":
                return None
            
            # 異常値チェック（データベースに接続済みの場合のみ実行）
            area_name = row.get('地区名') or row.get('DistrictName') or ""
            built_year = row.get('建築年') or row.get('BuildingYear')
            if check_anomaly and price and floor_area and year and quarter and area_name:
                is_anomaly, reason, stats = self.check_price_anomaly(
                    price, floor_area, "港区", area_name, year, quarter, built_year
                )
                
                if is_anomaly:
                    # 異常値を検出した場合の詳細ログ
                    logger.warning(f"異常値検出 - 行{row_num}: {row.get('地区名', '')} {period}")
                    logger.warning(f"  価格: {price}万円, 面積: {floor_area}㎡, 平米単価: {price/floor_area:.1f}万円/㎡")
                    logger.warning(f"  判定理由: {reason}")
                    logger.warning(f"  統計情報: {stats}")
                    
                    # 異常値カウンタをインクリメント
                    if hasattr(self, 'anomaly_count'):
                        self.anomaly_count += 1
                    
                    # 異常値はスキップ
                    return None
            
            # TransactionPriceオブジェクトを作成
            transaction = TransactionPrice(
                transaction_id=f"csv_{price_info_type}_{row_num}_{period}_{row.get('地区名', '')}".replace(" ", "_"),

                # 物件情報
                property_type=property_type,
                district_code="13103",  # 港区のコード
                district_name="港区",
                area_name=row.get('地区名') or row.get('DistrictName') or "",
                nearest_station=row.get('最寄駅：名称') or row.get('最寄駅') or row.get('Station'),
                station_distance=station_distance,

                # 取引情報
                transaction_price=price,
                price_per_sqm=price_per_sqm,
                transaction_period=period,
                transaction_year=year,
                transaction_quarter=quarter,

                # 建物情報
                floor_area=floor_area,
                floor_number=row.get('階') or row.get('Floor'),
                layout=row.get('間取り') or row.get('Layout'),
                built_year=row.get('建築年') or row.get('BuildingYear'),
                building_structure=row.get('建物の構造') or row.get('Structure'),
                use=row.get('用途') or row.get('Use'),

                # 都市計画
                city_planning=row.get('都市計画') or row.get('CityPlanning'),
                building_coverage_ratio=self.parse_int(row.get('建ぺい率（％）') or row.get('建ぺい率')),
                floor_area_ratio=self.parse_int(row.get('容積率（％）') or row.get('容積率')),

                # その他
                purpose=row.get('今後の利用目的') or row.get('Purpose'),
                remarks=row.get('備考') or row.get('Remarks')
            )

            return transaction

        except Exception as e:
            logger.warning(f"行{row_num}のパースエラー: {e}")
            if row_num <= 5:  # 最初の5行はデバッグ情報を出力
                logger.debug(f"行データ: {row}")
            return None

    def parse_period(self, period_str: str) -> tuple:
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

    def parse_price(self, price_str) -> Optional[int]:
        """価格をパース（万円単位）"""
        if not price_str:
            return None

        # 既に数値の場合
        if isinstance(price_str, (int, float)):
            # 円単位を万円単位に変換
            return int(price_str / 10000)

        # 文字列の場合
        price_str = str(price_str).replace(',', '').replace('円', '').replace('万', '')

        try:
            # 億円の処理
            if '億' in price_str:
                parts = price_str.split('億')
                oku = int(parts[0]) * 10000
                man = int(parts[1]) if parts[1] else 0
                return oku + man
            else:
                # 数値が大きい場合は円単位として扱う
                price_num = int(price_str)
                if price_num > 100000:  # 10万以上なら円単位として扱う
                    return price_num // 10000
                else:
                    return price_num  # 万円単位
        except:
            return None

    def parse_area(self, area_str: str) -> Optional[float]:
        """面積をパース"""
        if not area_str:
            return None

        # ㎡、平米などを除去
        area_str = area_str.replace('㎡', '').replace('平米', '').replace(',', '')

        try:
            return float(area_str)
        except:
            return None

    def parse_station_distance(self, distance_str: str) -> Optional[int]:
        """駅距離をパース（分）"""
        if not distance_str:
            return None

        # 分、駅などを除去
        distance_str = distance_str.replace('分', '').replace('駅', '').replace('-', '').strip()

        try:
            # "5～10分" のようなパターンの場合は最小値を取る
            if '～' in distance_str or '〜' in distance_str:
                distance_str = re.split('[～〜]', distance_str)[0]
            return int(distance_str)
        except:
            return None

    def parse_int(self, value_str: str) -> Optional[int]:
        """整数値をパース"""
        if not value_str:
            return None

        try:
            # パーセント記号などを除去
            value_str = value_str.replace('%', '').replace('％', '').strip()
            return int(float(value_str))
        except:
            return None

    def check_price_anomaly(self, price: int, area: float, district: str, area_name: str, year: int, quarter: int, built_year: str = None) -> tuple:
        """
        同時期・同エリアの成約事例から価格の異常値を判定
        
        Returns:
            (is_anomaly: bool, reason: str, stats: dict)
        """
        if not price or not area or area <= 0:
            return False, "", {}
        
        # 平米単価を計算（万円/㎡）
        price_per_sqm = price / area
        
        # 当該四半期・同エリア（細分化）のデータを取得して統計を計算
        from sqlalchemy import and_, or_
        
        # まず同じ細分化エリア・同じ四半期のデータを取得
        similar_transactions = self.db.query(
            TransactionPrice.transaction_price,
            TransactionPrice.floor_area
        ).filter(
            TransactionPrice.area_name == area_name,  # 細分化されたエリアで比較
            TransactionPrice.transaction_year == year,
            TransactionPrice.transaction_quarter == quarter,
            TransactionPrice.transaction_price.isnot(None),
            TransactionPrice.floor_area.isnot(None),
            TransactionPrice.floor_area > 0
        ).all()
        
        # サンプル数が少ない場合は1期前のデータも追加
        if len(similar_transactions) < 10:
            # 1期前の年・四半期を計算
            prev_year = year
            prev_quarter = quarter - 1
            if prev_quarter == 0:
                prev_year = year - 1
                prev_quarter = 4
            
            # 1期前のデータを追加取得
            prev_transactions = self.db.query(
                TransactionPrice.transaction_price,
                TransactionPrice.floor_area
            ).filter(
                TransactionPrice.area_name == area_name,
                TransactionPrice.transaction_year == prev_year,
                TransactionPrice.transaction_quarter == prev_quarter,
                TransactionPrice.transaction_price.isnot(None),
                TransactionPrice.floor_area.isnot(None),
                TransactionPrice.floor_area > 0
            ).all()
            
            similar_transactions.extend(prev_transactions)
        
        if len(similar_transactions) < 5:
            # それでもサンプル数が少なすぎる場合は判定しない
            return False, "", {"sample_size": len(similar_transactions), "area": area_name}
        
        # 平米単価のリストを作成
        price_per_sqm_list = [
            t.transaction_price / t.floor_area 
            for t in similar_transactions
        ]
        
        # 統計値を計算
        import statistics
        mean = statistics.mean(price_per_sqm_list)
        stdev = statistics.stdev(price_per_sqm_list)
        median = statistics.median(price_per_sqm_list)
        
        # 四分位数を計算
        sorted_prices = sorted(price_per_sqm_list)
        n = len(sorted_prices)
        q1 = sorted_prices[n // 4]
        q3 = sorted_prices[3 * n // 4]
        iqr = q3 - q1
        
        # 異常値判定（複数の基準を使用）
        stats = {
            "sample_size": len(similar_transactions),
            "mean": round(mean, 1),
            "median": round(median, 1),
            "stdev": round(stdev, 1),
            "q1": round(q1, 1),
            "q3": round(q3, 1),
            "iqr": round(iqr, 1),
            "price_per_sqm": round(price_per_sqm, 1)
        }
        
        # 築年数による補正係数を計算
        adjustment_factor = 1.0
        if built_year:
            try:
                # 築年数を計算
                import re
                year_match = re.search(r'(\d{4})', str(built_year))
                if year_match:
                    built = int(year_match.group(1))
                    building_age = year - built
                    
                    # 築年数による補正
                    if building_age <= 5:  # 築5年以内は新築・築浅
                        adjustment_factor = 1.3  # 閾値を30%緩める
                    elif building_age <= 10:  # 築10年以内
                        adjustment_factor = 1.15  # 閾値を15%緩める
                    # それ以上は補正なし
            except:
                pass  # 築年数が解析できない場合は補正なし
        
        # 判定基準（築年数で補正）：
        # 1. IQR法: Q3 + 4*IQR を超える（さらに緩い基準）
        # 2. 標準偏差法: 平均 + 5*標準偏差を超える（さらに緩い基準）
        # 3. 中央値からの乖離: 中央値の7倍を超える
        
        upper_bound_iqr = q3 + 4 * iqr * adjustment_factor
        upper_bound_std = mean + 5 * stdev * adjustment_factor
        upper_bound_median = median * 7 * adjustment_factor
        
        reasons = []
        
        if price_per_sqm > upper_bound_iqr:
            reasons.append(f"IQR法の閾値（{round(upper_bound_iqr, 1)}万円/㎡）を超過")
        
        if price_per_sqm > upper_bound_std:
            reasons.append(f"標準偏差法の閾値（{round(upper_bound_std, 1)}万円/㎡）を超過")
        
        if price_per_sqm > upper_bound_median:
            reasons.append(f"中央値の7倍（{round(upper_bound_median, 1)}万円/㎡）を超過")
        
        # 3つすべての基準に該当した場合のみ異常値と判定（厳格な基準）
        if len(reasons) >= 3:
            return True, "、".join(reasons), stats
        
        return False, "", stats

    def save_transactions(self, transactions: list):
        """データベースに保存"""
        saved_count = 0
        skipped_count = 0

        for transaction in transactions:
            try:
                # 既存チェック
                existing = self.db.query(TransactionPrice).filter(
                    TransactionPrice.transaction_id == transaction.transaction_id
                ).first()

                if existing:
                    skipped_count += 1
                    continue

                self.db.add(transaction)
                saved_count += 1

                if saved_count % 100 == 0:
                    self.db.commit()
                    logger.info(f"{saved_count}件保存済み...")

            except Exception as e:
                logger.error(f"保存エラー: {e}")
                self.db.rollback()
                continue

        self.db.commit()
        logger.info(f"保存完了: {saved_count}件追加、{skipped_count}件スキップ")

    def clear_existing_data(self):
        """既存データを削除"""
        try:
            count = self.db.query(TransactionPrice).count()
            self.db.query(TransactionPrice).delete()
            self.db.commit()
            logger.info(f"既存データを削除しました: {count}件")
            return count
        except Exception as e:
            logger.error(f"データ削除エラー: {e}")
            self.db.rollback()
            return 0
    
    def import_csv_files(self, directory: str = "/app/data/transaction_prices", clear_existing: bool = False):
        """指定ディレクトリのCSVファイルをすべてインポート"""
        
        # 既存データのクリア
        if clear_existing:
            deleted_count = self.clear_existing_data()
            print(f"既存データを削除しました: {deleted_count}件")
        
        csv_files = list(Path(directory).glob("*.csv"))

        if not csv_files:
            logger.warning(f"CSVファイルが見つかりません: {directory}")
            print(f"\nCSVファイルを以下の場所に配置してください: {directory}")
            print("ファイル名例: minato_transactions_2024.csv")
            return

        logger.info(f"{len(csv_files)}個のCSVファイルを処理します")

        all_transactions = []
        total_anomalies = 0
        for csv_file in csv_files:
            logger.info(f"処理中: {csv_file}")
            transactions = self.parse_csv_file(str(csv_file))
            all_transactions.extend(transactions)
            if hasattr(self, 'anomaly_count'):
                total_anomalies += self.anomaly_count

        if all_transactions:
            logger.info(f"合計{len(all_transactions)}件の取引データを保存します")
            self.save_transactions(all_transactions)

            # 統計情報を表示
            total_count = self.db.query(TransactionPrice).count()
            minato_count = self.db.query(TransactionPrice).filter(
                TransactionPrice.district_name == "港区"
            ).count()
            logger.info(f"データベース内の総件数: {total_count}")
            logger.info(f"港区の件数: {minato_count}")
            
            if total_anomalies > 0:
                logger.info(f"異常値として除外されたデータ: {total_anomalies}件")
                print(f"\n異常値検出: {total_anomalies}件のデータを除外しました")
        else:
            logger.warning("インポート可能なデータがありませんでした")

    def close(self):
        """データベース接続をクローズ"""
        self.db.close()


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='国土交通省 不動産取引価格CSVインポートツール')
    parser.add_argument('--clear', action='store_true', help='既存データをクリアしてから新規インポート')
    parser.add_argument('--file', type=str, help='特定のCSVファイルを指定（UTF-8変換済みファイル推奨）')
    args = parser.parse_args()
    
    importer = TransactionCSVImporter()

    try:
        print("=" * 60)
        print("国土交通省 不動産取引価格CSVインポートツール")
        print("=" * 60)
        print("\n使用方法:")
        print("1. https://www.reinfolib.mlit.go.jp/realEstatePrices/ から")
        print("   港区の取引価格CSVをダウンロード")
        print("2. /app/data/transaction_prices/ (Docker内) または")
        print("   /home/ubuntu/realestate/data/transaction_prices/ (ホスト側) に配置")
        print("3. このスクリプトを実行\n")
        
        if args.file:
            # 特定のファイルを処理
            print(f"指定ファイルを処理: {args.file}")
            transactions = importer.parse_csv_file(args.file)
            if transactions:
                if args.clear:
                    deleted_count = importer.clear_existing_data()
                    print(f"既存データを削除しました: {deleted_count}件")
                print(f"{len(transactions)}件の取引データを保存します")
                importer.save_transactions(transactions)
                
                # 統計情報を表示
                total_count = importer.db.query(TransactionPrice).count()
                logger.info(f"データベース内の総件数: {total_count}")
                print(f"\nデータベース内の総件数: {total_count}")
        else:
            # ディレクトリ内のすべてのCSVを処理
            importer.import_csv_files(clear_existing=args.clear)
    finally:
        importer.close()


if __name__ == "__main__":
    main()