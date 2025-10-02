#!/usr/bin/env python3
"""
不動産物件API サーバー v2.0
重複排除と複数サイト管理に対応
リファクタリング版
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import time

from .database import init_db
from .utils.logger import api_logger, error_logger
from .scheduler import start_scheduler, stop_scheduler

# APIルーターのインポート
from .api.admin import router as admin_router
from .api import admin_listings
from .api import admin_properties
from .api import admin_buildings
from .api import admin_matching
from .api import admin_schedules
from .api import admin_users
from .api import admin_transaction_prices
from .api.admin import price_changes as admin_price_changes
from .api import properties
from .api import properties_recent_updates
from .api import buildings
from .api import stats
from .api import grouped_properties
from .api import bookmarks
from .api import auth
from .api import oauth
from .api import geocoding
from .api import transaction_prices

app = FastAPI(title="不動産横断検索API", version="1.0.0")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ロギングミドルウェア
@app.middleware("http")
async def log_requests(request, call_next):
    """すべてのHTTPリクエストをログに記録"""
    start_time = time.time()
    
    # リクエストログ
    auth_header = request.headers.get("authorization", "None")
    if request.url.path == "/api/auth/me":
        print(f"[Middleware] /auth/me request, Authorization header: {auth_header[:50] if auth_header != 'None' else 'None'}...")
    
    api_logger.info(
        "API Request",
        extra={
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params)
        }
    )
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # レスポンスログ
        api_logger.info(
            "API Response",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": process_time
            }
        )
        
        response.headers["X-Process-Time"] = str(process_time)
        return response
        
    except Exception as e:
        process_time = time.time() - start_time
        error_logger.error(
            f"Request failed: {str(e)}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "process_time": process_time
            },
            exc_info=True
        )
        raise

# ルーターの登録
app.include_router(admin_router)
app.include_router(admin_listings.router)
app.include_router(admin_properties.router)
app.include_router(admin_buildings.router)
app.include_router(admin_matching.router)
app.include_router(admin_schedules.router)
app.include_router(admin_users.router, prefix="/api/admin", tags=["admin-users"])
app.include_router(admin_transaction_prices.router, prefix="/api", tags=["admin-transaction-prices"])
app.include_router(admin_price_changes.router, prefix="/api", tags=["admin-price-changes"])
app.include_router(properties_recent_updates.router)  # より具体的なパスを先に登録
app.include_router(properties.router)
app.include_router(buildings.router)
app.include_router(stats.router)
app.include_router(grouped_properties.router)
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(oauth.router, prefix="/api/oauth", tags=["oauth"])
app.include_router(bookmarks.router, prefix="/api/bookmarks", tags=["bookmarks"])
app.include_router(geocoding.router)
app.include_router(transaction_prices.router)


# 起動時の初期化
@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の処理"""
    try:
        print("DEBUG: startup_event 開始")
        api_logger.info("FastAPI startup_event が開始されました")
        
        print("DEBUG: データベース初期化開始")
        # データベース初期化
        init_db()
        print("DEBUG: データベース初期化完了")
        api_logger.info("データベース初期化完了")
        
        print("DEBUG: スケジューラー開始処理開始")
        # スケジューラーを安全に開始
        try:
            result = start_scheduler()
            print(f"DEBUG: start_scheduler結果: {result}")
            
            if result:
                api_logger.info("スケジューラーサービスを開始しました")
                print("DEBUG: スケジューラー開始成功")
                
                # 診断実行
                from .scheduler import diagnose_scheduler
                diagnosis = diagnose_scheduler()
                print(f"DEBUG: 診断結果: {diagnosis}")
                api_logger.info(f"起動後診断結果: {diagnosis}")
            else:
                api_logger.warning("スケジューラーの開始に失敗しました")
                print("DEBUG: スケジューラー開始失敗")
                
        except Exception as scheduler_error:
            print(f"DEBUG: スケジューラーエラー: {scheduler_error}")
            api_logger.error(f"スケジューラー開始エラー: {scheduler_error}", exc_info=True)
            # スケジューラーエラーでもアプリケーションは継続
        
        print("DEBUG: startup_event 処理完了")
        api_logger.info("startup_event 処理完了")
        
    except Exception as e:
        print(f"CRITICAL ERROR in startup_event: {e}")
        api_logger.error(f"startup_event でクリティカルエラー: {e}", exc_info=True)
        import traceback
        print("TRACEBACK:")
        traceback.print_exc()
        # エラーが発生してもプロセスは続行させる
        # エラーが発生してもプロセスは続行させる

# 終了時の処理
@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時の処理"""
    try:
        result = stop_scheduler()
        if result:
            api_logger.info("スケジューラーサービスを停止しました")
        else:
            api_logger.warning("スケジューラーの停止に失敗しました")
    except Exception as e:
        error_logger.error(f"shutdown_event でエラー: {e}", exc_info=True)

# ヘルスチェック
@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy"}

# スケジューラー管理エンドポイント
@app.get("/scheduler/status")
async def scheduler_status():
    """スケジューラーの状態を確認"""
    try:
        from .scheduler import diagnose_scheduler
        diagnosis = diagnose_scheduler()
        return {
            "status": "success",
            "scheduler": diagnosis
        }
    except Exception as e:
        return {
            "status": "error", 
            "message": str(e)
        }

@app.post("/scheduler/start")
async def scheduler_start():
    """スケジューラーを手動で開始"""
    try:
        from .scheduler import start_scheduler, diagnose_scheduler
        result = start_scheduler()
        diagnosis = diagnose_scheduler()
        return {
            "status": "success",
            "started": result,
            "scheduler": diagnosis
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

# 旧エンドポイントは削除（統一されたため不要）

if __name__ == "__main__":
    import uvicorn
    import sys
    
    # ポート番号の設定
    port = 8001
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"無効なポート番号: {sys.argv[1]}")
            sys.exit(1)
    
    print(f"APIサーバーを起動中... http://localhost:{port}")
    print(f"対話的APIドキュメント: http://localhost:{port}/docs")
    
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )