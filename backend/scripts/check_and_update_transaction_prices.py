#!/usr/bin/env python3
"""
成約価格情報の自動更新チェックスクリプト

毎日実行し、不動産情報ライブラリAPIに新しい四半期のデータがあれば自動的に取得する。
cronで実行: 0 6 * * * docker exec realestate-backend python /app/backend/scripts/check_and_update_transaction_prices.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import requests
import subprocess
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from app.models import TransactionPrice, TransactionDataFetchCompletion
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://realestate:realestate_pass@postgres:5432/realestate")
API_KEY = os.getenv("REINFOLIB_API_KEY", "97603fb774d448b1826804f92a6f6eff")
API_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001"

# ログ出力先
LOG_DIR = "/app/logs"


def log(message: str):
    """ログ出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def get_db_latest_quarter() -> Tuple[Optional[int], Optional[int]]:
    """
    データベースに保存されている最新の四半期を取得

    Returns:
        (year, quarter) のタプル。データがない場合は (None, None)
    """
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # 完了記録から最新の四半期を取得
        latest = db.query(
            TransactionDataFetchCompletion.year,
            TransactionDataFetchCompletion.quarter
        ).order_by(
            TransactionDataFetchCompletion.year.desc(),
            TransactionDataFetchCompletion.quarter.desc()
        ).first()

        if latest:
            return latest.year, latest.quarter

        # 完了記録がない場合、実際のデータから取得
        latest_data = db.query(
            TransactionPrice.transaction_year,
            TransactionPrice.transaction_quarter
        ).order_by(
            TransactionPrice.transaction_year.desc(),
            TransactionPrice.transaction_quarter.desc()
        ).first()

        if latest_data:
            return latest_data.transaction_year, latest_data.transaction_quarter

        return None, None
    finally:
        db.close()


def check_api_for_new_data(year: int, quarter: int) -> bool:
    """
    APIに指定された四半期のデータがあるかチェック

    Args:
        year: チェックする年
        quarter: チェックする四半期

    Returns:
        データがあればTrue
    """
    headers = {
        "Ocp-Apim-Subscription-Key": API_KEY
    }

    params = {
        "year": year,
        "quarter": quarter,
        "area": "13",  # 東京都
        "priceClassification": "02"  # 成約価格情報
    }

    try:
        response = requests.get(
            API_BASE_URL,
            params=params,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            # データが存在するかチェック
            if data and len(data) > 0:
                log(f"APIに{year}年Q{quarter}のデータがあります（{len(data)}件）")
                return True
            else:
                log(f"APIに{year}年Q{quarter}のデータはありません（空のレスポンス）")
                return False
        else:
            log(f"APIリクエストエラー: status={response.status_code}")
            return False

    except Exception as e:
        log(f"APIチェックエラー: {e}")
        return False


def get_next_quarter(year: int, quarter: int) -> Tuple[int, int]:
    """
    次の四半期を計算

    Args:
        year: 現在の年
        quarter: 現在の四半期

    Returns:
        (next_year, next_quarter) のタプル
    """
    if quarter == 4:
        return year + 1, 1
    else:
        return year, quarter + 1


def run_update_script():
    """
    成約価格更新スクリプトを実行
    """
    script_path = "/app/backend/scripts/fetch_transaction_prices_api.py"
    log_path = f"{LOG_DIR}/transaction_prices_auto_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    log(f"更新スクリプトを実行します: {script_path}")
    log(f"ログファイル: {log_path}")

    try:
        with open(log_path, 'w') as log_file:
            result = subprocess.run(
                ["python", script_path, "--mode", "update", "--area", "all"],
                stdout=log_file,
                stderr=log_file,
                cwd="/app",
                timeout=3600  # 1時間タイムアウト
            )

        if result.returncode == 0:
            log("更新スクリプトが正常に完了しました")
            return True
        else:
            log(f"更新スクリプトがエラーで終了しました: returncode={result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        log("更新スクリプトがタイムアウトしました")
        return False
    except Exception as e:
        log(f"更新スクリプトの実行エラー: {e}")
        return False


def main():
    """
    メイン処理
    """
    log("=" * 60)
    log("成約価格情報の自動更新チェックを開始します")
    log("=" * 60)

    # データベースの最新四半期を取得
    db_year, db_quarter = get_db_latest_quarter()

    if db_year is None:
        log("データベースにデータがありません。初回取得を実行します。")
        run_update_script()
        return

    log(f"データベースの最新データ: {db_year}年Q{db_quarter}")

    # 次の四半期をチェック
    next_year, next_quarter = get_next_quarter(db_year, db_quarter)

    # 現在の日時から、まだ公開されていない可能性のある四半期はスキップ
    now = datetime.now()
    current_year = now.year
    current_quarter = (now.month - 1) // 3 + 1

    # 現在の四半期より先のデータはチェックしない
    if (next_year > current_year) or (next_year == current_year and next_quarter > current_quarter):
        log(f"次の四半期（{next_year}年Q{next_quarter}）はまだ終了していません。チェックをスキップします。")
        return

    log(f"次の四半期（{next_year}年Q{next_quarter}）のデータをチェックします...")

    # APIでデータの有無をチェック
    if check_api_for_new_data(next_year, next_quarter):
        log(f"新しいデータが見つかりました！更新を開始します。")
        run_update_script()
    else:
        log(f"新しいデータはまだ公開されていません。")

    log("=" * 60)
    log("チェック完了")
    log("=" * 60)


if __name__ == "__main__":
    main()
