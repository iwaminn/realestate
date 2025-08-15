#!/usr/bin/env python3
"""
不動産物件API サーバー v2.0
重複排除と複数サイト管理に対応
リファクタリング版
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import time

from backend.app.database import init_db
from backend.app.utils.logger import api_logger, error_logger

# APIルーターのインポート
from backend.app.api.admin import router as admin_router
from backend.app.api import admin_listings
from backend.app.api import admin_properties
from backend.app.api import admin_buildings
from backend.app.api import admin_matching
from backend.app.api import properties_v2
from backend.app.api import buildings_v2
from backend.app.api import stats
from backend.app.api import grouped_properties

app = FastAPI(title="不動産横断検索API v2", version="2.0.0")

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
app.include_router(properties_v2.router)
app.include_router(buildings_v2.router)
app.include_router(stats.router)
app.include_router(grouped_properties.router)

# 起動時の初期化
@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の処理"""
    init_db()

# ヘルスチェック
@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy"}

# 互換性のための旧APIエンドポイント（リダイレクト）
@app.get("/api/properties")
async def get_properties_legacy():
    """旧APIエンドポイント（v2にリダイレクト）"""
    return {"message": "このエンドポイントは非推奨です。/api/v2/properties を使用してください。"}

@app.get("/api/buildings")
async def get_buildings_legacy():
    """旧APIエンドポイント（v2にリダイレクト）"""
    return {"message": "このエンドポイントは非推奨です。/api/v2/buildings を使用してください。"}

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