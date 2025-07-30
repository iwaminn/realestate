# 並列スクレイピング設計書

## 概要

異なる情報サイトを並列でスクレイピングすることで、全体の実行時間を大幅に短縮します。

## 設計方針

### 1. 並列化の基本ルール

- **異なるサイトは並列実行可能**
  - SUUMO、LIFULL HOME'S、三井のリハウス、ノムコム、東急リバブルは同時実行
- **同一サイトの異なるエリアは直列実行**
  - サイトへの負荷を考慮し、レート制限を遵守

### 2. 実装アプローチ

#### 現在の構造（直列）
```
for scraper in scrapers:
    for area in areas:
        scrape(scraper, area)
```

#### 新しい構造（並列）
```
# サイトごとにワーカースレッドを作成
workers = []
for scraper in scrapers:
    worker = Thread(
        target=scrape_all_areas,
        args=(scraper, areas)
    )
    workers.append(worker)
    worker.start()

# 全ワーカーの完了を待つ
for worker in workers:
    worker.join()
```

## 技術的考慮事項

### 1. データベースのトランザクション管理

#### 問題点
- 複数スレッドが同時にDBアクセスすると、デッドロックの可能性
- SQLAlchemyのセッションはスレッドセーフではない

#### 解決策
```python
# 各スレッドで独立したセッションを使用
def scrape_worker(scraper_class, areas):
    # スレッドローカルなセッションを作成
    session = SessionLocal()
    try:
        scraper = scraper_class()
        scraper.session = session
        for area in areas:
            scraper.scrape_area(area)
    finally:
        session.close()
```

### 2. 一時停止・キャンセル機能

#### 現在の実装
- グローバルなpause_flag、cancel_flagを使用
- 各スクレイパーがフラグをチェック

#### 並列化での対応
```python
# タスクIDに基づくフラグ管理
task_flags = {
    task_id: {
        'pause': threading.Event(),
        'cancel': threading.Event(),
        'scraper_flags': {
            'suumo': {'pause': threading.Event(), 'cancel': threading.Event()},
            'homes': {'pause': threading.Event(), 'cancel': threading.Event()},
            # ...
        }
    }
}

# 一時停止時は全スクレイパーのフラグをセット
def pause_task(task_id):
    for scraper_flags in task_flags[task_id]['scraper_flags'].values():
        scraper_flags['pause'].set()
```

### 3. 進捗管理

#### スレッドセーフな進捗更新
```python
import threading

progress_lock = threading.Lock()

def update_progress(task_id, scraper_name, area_code, stats):
    with progress_lock:
        progress_key = f"{scraper_name}_{area_code}"
        scraping_tasks[task_id]["progress"][progress_key].update(stats)
```

### 4. エラーハンドリング

#### 個別スレッドのエラー処理
```python
def scrape_worker(scraper_name, areas, task_id):
    try:
        # スクレイピング処理
        pass
    except Exception as e:
        with error_lock:
            scraping_tasks[task_id]["errors"].append({
                "scraper": scraper_name,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
        # エラーが発生してもタスク全体は継続
```

## 実装計画

### Phase 1: 基盤整備
1. スレッドセーフな進捗管理機構の実装
2. スクレイパーごとの独立したセッション管理
3. フラグ管理の改修

### Phase 2: 並列実行エンジン
1. ワーカースレッドプールの実装
2. タスクキューの実装
3. 並列実行コーディネーターの実装

### Phase 3: UI対応
1. 並列実行状況の表示
2. 個別スクレイパーの一時停止・再開機能

## パフォーマンス予測

### 現在（直列実行）
- 5サイト × 23エリア × 平均2分 = 約230分

### 並列化後
- 最長サイトの実行時間 = 23エリア × 平均2分 = 約46分
- **約5倍の高速化**が期待できる

## リスクと対策

### 1. メモリ使用量の増加
- **対策**: スクレイパーごとのmax_propertiesを調整
- **注意**: max_propertiesは各スクレイパー・エリアごとに適用される
  - 例：max_properties=300の場合、SUUMO港区300件 + LIFULL HOME'S港区300件 = 合計600件

### 2. データベース接続数の増加
- **対策**: コネクションプールのサイズを適切に設定

### 3. 同時実行による競合状態
- **対策**: 適切なロック機構とトランザクション分離レベルの設定