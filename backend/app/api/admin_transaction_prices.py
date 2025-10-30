"""管理者向け成約価格情報API"""
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import subprocess
import os
from typing import Dict

from ..database import get_db
from ..api.auth import get_admin_user
from ..models import TransactionPrice

router = APIRouter(
    dependencies=[Depends(get_admin_user)]
)

# ロックファイルのパス
LOCK_FILE_PATH = "/app/logs/transaction_prices_update.lock"


@router.get("/transaction-prices/update-status")
async def get_update_status() -> Dict:
    """成約価格情報更新の実行状態を取得"""
    if os.path.exists(LOCK_FILE_PATH):
        try:
            with open(LOCK_FILE_PATH, 'r') as lock:
                lock_info = lock.read()
            return {
                "is_running": True,
                "details": lock_info
            }
        except Exception:
            return {
                "is_running": True,
                "details": "実行中（詳細不明）"
            }
    else:
        return {
            "is_running": False,
            "details": None
        }


@router.get("/transaction-prices/stats")
async def get_transaction_price_stats(
    db: Session = Depends(get_db),
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


async def run_update_script(mode: str = "update", force_refetch: bool = False):
    """バックグラウンドで成約価格更新スクリプトを実行"""
    try:
        # modeの変換: "full" -> "historical"
        script_mode = "historical" if mode == "full" else mode
        
        # コンテナ内で直接実行
        script_path = "/app/backend/scripts/fetch_transaction_prices_api.py"
        log_path = f"/app/logs/transaction_prices_update_{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # ロックファイルを作成
        with open(LOCK_FILE_PATH, 'w') as lock:
            lock.write(f"{datetime.now().isoformat()}\n")
            lock.write(f"mode: {mode}\n")
            lock.write(f"force_refetch: {force_refetch}\n")

        # ログファイルを開く
        log_file = open(log_path, 'w')

        # force_refetchオプションを追加
        force_refetch_flag = " --force-refetch" if force_refetch else ""

        # バックグラウンドで実行（ログファイルに出力）
        # 完了後にロックファイルを削除するラッパースクリプトを使用
        wrapper_cmd = f"""
python {script_path} --mode {script_mode} --area all{force_refetch_flag}
rm -f {LOCK_FILE_PATH}
"""
        subprocess.Popen(
            ["sh", "-c", wrapper_cmd],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
            cwd="/app"  # 作業ディレクトリを明示的に指定
        )

        return {"success": True, "message": f"更新処理を開始しました（ログ: {log_path}）"}
    except Exception as e:
        # エラー時はロックファイルを削除
        if os.path.exists(LOCK_FILE_PATH):
            os.remove(LOCK_FILE_PATH)
        return {"success": False, "message": f"更新処理の開始に失敗しました: {str(e)}"}


@router.post("/transaction-prices/update")
async def update_transaction_prices(
    background_tasks: BackgroundTasks,
    mode: str = "update",  # "update" or "full"
    force_refetch: bool = False,  # 強制再取得フラグ
    db: Session = Depends(get_db),
) -> Dict:
    """
    成約価格情報を更新

    Parameters:
    - mode: "update" (最新データのみ) または "full" (全期間)
    - force_refetch: True の場合、完了記録を無視して強制的に再取得
    """

    # 実行中チェック
    if os.path.exists(LOCK_FILE_PATH):
        # ロックファイルの内容を読み取る
        try:
            with open(LOCK_FILE_PATH, 'r') as lock:
                lock_info = lock.read()
            raise HTTPException(
                status_code=409,
                detail=f"成約価格情報の更新が既に実行中です。\n{lock_info}"
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=409,
                detail="成約価格情報の更新が既に実行中です。"
            )

    # バックグラウンドで実行
    background_tasks.add_task(run_update_script, mode, force_refetch)

    force_refetch_msg = "（強制再取得）" if force_refetch else ""
    return {
        "success": True,
        "message": f"成約価格情報の更新を開始しました{force_refetch_msg}（モード: {mode}）",
        "mode": mode,
        "force_refetch": force_refetch
    }
