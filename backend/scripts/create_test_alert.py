#!/usr/bin/env python3
"""
テスト用のスクレイパーアラートを作成するスクリプト
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.app.database import SessionLocal
from backend.app.models import ScraperAlert
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_alerts():
    """テスト用アラートを作成"""
    session = SessionLocal()
    
    try:
        # 既存のテストアラートを削除
        session.query(ScraperAlert).filter(
            ScraperAlert.message.like('%テスト%')
        ).delete()
        
        # テストアラート1: 高レベルアラート
        alert1 = ScraperAlert(
            source_site='SUUMO',
            alert_type='critical_field_error',
            severity='high',
            message='SUUMOのスクレイパーで重要フィールド\'floor_number\'のエラー率が80.0%（40件）に達しました。HTML構造の変更を確認してください。',
            details={
                'field_name': 'floor_number',
                'error_count': 40,
                'error_rate': 0.8,
                'threshold': {
                    'critical_error_rate': 0.5,
                    'critical_error_count': 10,
                    'consecutive_errors': 5
                }
            },
            is_active=True,
            created_at=datetime.now()
        )
        
        # テストアラート2: 中レベルアラート
        alert2 = ScraperAlert(
            source_site='LIFULL HOME\'S',
            alert_type='critical_field_error',
            severity='medium',
            message='LIFULL HOME\'Sのスクレイパーで重要フィールド\'area\'のエラー率が35.0%（14件）に達しました。HTML構造の変更を確認してください。',
            details={
                'field_name': 'area',
                'error_count': 14,
                'error_rate': 0.35,
                'threshold': {
                    'critical_error_rate': 0.5,
                    'critical_error_count': 10,
                    'consecutive_errors': 5
                }
            },
            is_active=True,
            created_at=datetime.now()
        )
        
        # テストアラート3: HTML構造変更
        alert3 = ScraperAlert(
            source_site='三井のリハウス',
            alert_type='html_structure_change',
            severity='high',
            message='致命的なHTML構造の変更を検出しました。\'物件詳細テーブル\'が5回連続で見つかりません。',
            details={
                'field_name': 'missing_物件詳細テーブル',
                'error_count': 5,
                'error_rate': 1.0
            },
            is_active=True,
            created_at=datetime.now()
        )
        
        session.add(alert1)
        session.add(alert2)
        session.add(alert3)
        session.commit()
        
        logger.info("テストアラートを3件作成しました")
        
        # 作成したアラートを確認
        alerts = session.query(ScraperAlert).filter(ScraperAlert.is_active == True).all()
        logger.info(f"アクティブなアラート数: {len(alerts)}")
        for alert in alerts:
            logger.info(f"- {alert.source_site}: {alert.alert_type} ({alert.severity})")
        
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def main():
    """メイン処理"""
    logger.info("=== テストアラート作成開始 ===")
    create_test_alerts()
    logger.info("=== 完了 ===")


if __name__ == "__main__":
    main()