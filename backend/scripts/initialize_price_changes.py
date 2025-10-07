#!/usr/bin/env python
"""
価格改定履歴キャッシュテーブルの初期データ投入スクリプト
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# パスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from app.models import MasterProperty, PropertyListing, PropertyPriceChange, PropertyPriceChangeQueue
from app.utils.price_change_calculator import PriceChangeCalculator

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# データベース接続
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://realestate:realestate_pass@localhost:5432/realestate')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def initialize_price_changes(batch_size: int = 100, days_back: int = None):
    """
    価格改定履歴を初期化
    
    Args:
        batch_size: バッチサイズ
        days_back: 何日前までのデータを計算するか（Noneの場合は全期間）
    """
    session = SessionLocal()
    calculator = PriceChangeCalculator(session)
    
    try:
        # すべての物件を取得（アクティブ・非アクティブ問わず）
        logger.info("物件を取得中...")
        all_properties = session.query(MasterProperty.id).join(
            PropertyListing,
            PropertyListing.master_property_id == MasterProperty.id
        ).distinct().all()
        
        total = len(all_properties)
        logger.info(f"処理対象物件数: {total}")
        
        # 既存のキャッシュをクリア
        if days_back is None:
            logger.info("既存の価格改定履歴をクリア...")
            session.query(PropertyPriceChange).delete()
            session.commit()
        
        # バッチ処理
        processed = 0
        changes_found = 0
        errors = 0
        
        for i in range(0, total, batch_size):
            batch = all_properties[i:i+batch_size]
            batch_changes = 0
            
            for (property_id,) in batch:
                try:
                    # 価格改定履歴を計算
                    if days_back:
                        start_date = datetime.now().date() - timedelta(days=days_back)
                        changes = calculator.calculate_price_changes(property_id, start_date)
                    else:
                        changes = calculator.calculate_price_changes(property_id)
                    
                    # 保存
                    if changes:
                        saved_count = calculator.save_price_changes(property_id, changes)
                        batch_changes += saved_count
                        changes_found += saved_count
                    
                    processed += 1
                    
                except Exception as e:
                    logger.error(f"物件 {property_id} の処理に失敗: {e}")
                    errors += 1
            
            # 進捗表示
            logger.info(f"進捗: {min(i+batch_size, total)}/{total} 件完了 "
                       f"（このバッチで {batch_changes} 件の価格改定を検出）")
            
            # コミット
            session.commit()
        
        # 統計情報
        logger.info("=" * 50)
        logger.info("処理完了")
        logger.info(f"処理済み物件数: {processed}")
        logger.info(f"検出された価格改定数: {changes_found}")
        logger.info(f"エラー数: {errors}")
        
        # キャッシュテーブルの統計
        total_cached = session.query(func.count(PropertyPriceChange.id)).scalar()
        properties_with_changes = session.query(
            func.count(func.distinct(PropertyPriceChange.master_property_id))
        ).scalar()
        
        logger.info(f"キャッシュされた価格改定総数: {total_cached}")
        logger.info(f"価格改定がある物件数: {properties_with_changes}")
        
        if properties_with_changes > 0:
            avg_changes = total_cached / properties_with_changes
            logger.info(f"物件あたりの平均価格改定回数: {avg_changes:.2f}")
        
    except Exception as e:
        logger.error(f"初期化処理に失敗: {e}")
        session.rollback()
        raise
    
    finally:
        session.close()


def main():
    """メイン処理"""
    import argparse
    
    parser = argparse.ArgumentParser(description='価格改定履歴キャッシュの初期化')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='バッチサイズ（デフォルト: 100）')
    parser.add_argument('--days-back', type=int, default=None,
                       help='何日前までのデータを計算するか（指定なしで全期間）')
    parser.add_argument('--clear-queue', action='store_true',
                       help='キューをクリアする')
    
    args = parser.parse_args()
    
    if args.clear_queue:
        session = SessionLocal()
        try:
            logger.info("キューをクリア...")
            session.query(PropertyPriceChangeQueue).delete()
            session.commit()
            logger.info("キューをクリアしました")
        finally:
            session.close()
    
    # 初期化実行
    logger.info("価格改定履歴の初期化を開始...")
    logger.info(f"バッチサイズ: {args.batch_size}")
    if args.days_back:
        logger.info(f"計算期間: 過去 {args.days_back} 日")
    else:
        logger.info("計算期間: 全期間")
    
    initialize_price_changes(args.batch_size, args.days_back)


if __name__ == "__main__":
    main()