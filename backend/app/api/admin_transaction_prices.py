"""管理者向け成約価格情報API"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import subprocess
import os
from typing import Dict

from ..database import get_db
from ..models import TransactionPrice
from ..auth import verify_admin_credentials

router = APIRouter()


@router.get("/admin/transaction-prices/stats")
async def get_transaction_price_stats(
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_credentials)
) -> Dict:
    """成約価格情報の統計を取得"""

    # 総件数
    total_count = db.query(func.count(TransactionPrice.id)).scalar() or 0

    # 最新データの年・四半期
    latest = db.query(
        TransactionPrice.transaction_year,
        TransactionPrice.transaction_quarter
    ).order_by(
        TransactionPrice.transaction_year.desc(),
        TransactionPrice.transaction_quarter.desc()
    ).first()

    # 最古データの年・四半期
    oldest = db.query(
        TransactionPrice.transaction_year,
        TransactionPrice.transaction_quarter
    ).order_by(
        TransactionPrice.transaction_year.asc(),
        TransactionPrice.transaction_quarter.asc()
    ).first()

    # 過去30日の新規データ数
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_count = db.query(func.count(TransactionPrice.id)).filter(
        TransactionPrice.created_at >= thirty_days_ago
    ).scalar() or 0

    # エリア数
    area_count = db.query(func.count(func.distinct(TransactionPrice.area_name))).scalar() or 0

    return {
        "total_count": total_count,
        "latest_year": latest.transaction_year if latest else None,
        "latest_quarter": latest.transaction_quarter if latest else None,
        "oldest_year": oldest.transaction_year if oldest else None,
        "oldest_quarter": oldest.transaction_quarter if oldest else None,
        "recent_30days_count": recent_count,
        "area_count": area_count
    }


async def run_update_script(mode: str = "update"):
    """バックグラウンドで成約価格更新スクリプトを実行"""
    try:
        # Dockerコンテナ内で実行
        script_path = "/app/backend/scripts/fetch_transaction_prices_api.py"
        cmd = [
            "docker", "exec", "realestate-backend",
            "poetry", "run", "python", script_path,
            "--mode", mode
        ]

        # バックグラウンドで実行
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        return {"success": True, "message": "更新処理を開始しました"}
    except Exception as e:
        return {"success": False, "message": f"更新処理の開始に失敗しました: {str(e)}"}


@router.post("/admin/transaction-prices/update")
async def update_transaction_prices(
    background_tasks: BackgroundTasks,
    mode: str = "update",  # "update" or "full"
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_credentials)
) -> Dict:
    """
    成約価格情報を更新

    Parameters:
    - mode: "update" (最新データのみ) または "full" (全期間)
    """

    # バックグラウンドで実行
    background_tasks.add_task(run_update_script, mode)

    return {
        "success": True,
        "message": f"成約価格情報の更新を開始しました（モード: {mode}）",
        "mode": mode
    }