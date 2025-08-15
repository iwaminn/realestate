"""
管理者API モジュール
機能別に分割された管理者向けAPIエンドポイント
"""

from fastapi import APIRouter

# 各サブモジュールのルーターをインポート
from .scraping import router as scraping_router
from .duplicates import router as duplicates_router
from .exclusions import router as exclusions_router
from .history import router as history_router
from .status_updates import router as status_router
from .alerts import router as alerts_router

# メインルーターを作成
router = APIRouter(prefix="/api/admin", tags=["admin"])

# サブルーターを統合
router.include_router(scraping_router)
router.include_router(duplicates_router)
router.include_router(exclusions_router)
router.include_router(history_router)
router.include_router(status_router)
router.include_router(alerts_router)