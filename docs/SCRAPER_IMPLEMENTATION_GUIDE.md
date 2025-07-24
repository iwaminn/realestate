# スクレイパー実装ガイド

このドキュメントは、新しいスクレイパーを追加する際の実装ガイドラインです。
既存の問題を回避し、管理画面との統合をスムーズに行うための重要なポイントをまとめています。

## 目次

1. [基本的な実装フロー](#基本的な実装フロー)
2. [重要な実装ポイント](#重要な実装ポイント)
3. [スマートスクレイピング機能](#スマートスクレイピング機能)
4. [管理画面との統合](#管理画面との統合)
5. [よくある問題と解決策](#よくある問題と解決策)
6. [チェックリスト](#チェックリスト)

## 基本的な実装フロー

### 1. 収集フェーズと処理フェーズの分離

**推奨される実装パターン**:

```python
def scrape_area(self, area: str, max_pages: int = 5):
    """エリアの物件をスクレイピング"""
    
    # ===== フェーズ1: 物件一覧の収集 =====
    all_properties = []
    
    for page in range(1, max_pages + 1):
        print(f"ページ {page} を取得中...")
        
        # ページを取得
        soup = self.fetch_page(list_url)
        if not soup:
            break
            
        # 物件リストを解析
        properties = self.parse_property_list(soup)
        if not properties:
            break
            
        # 統計を記録
        self.record_property_found(len(properties))
        all_properties.extend(properties)
        
        # ページ間の遅延
        time.sleep(self.delay)
    
    # 処理対象数を記録（max_properties制限を考慮）
    total_to_process = min(len(all_properties), self.max_properties) if self.max_properties else len(all_properties)
    self.record_property_processed(total_to_process)
    
    # ===== フェーズ2: 詳細取得と保存 =====
    print(f"\n合計 {len(all_properties)} 件の物件を処理します...")
    
    for i, property_data in enumerate(all_properties):
        # 最大取得件数チェック
        if self.max_properties and i >= self.max_properties:
            break
            
        print(f"[{i+1}/{total_to_process}] {property_data.get('building_name', 'Unknown')}")
        self.record_property_attempted()
        
        try:
            # 詳細ページを取得
            detail_data = self.get_property_detail(property_data['url'])
            if detail_data:
                self.record_property_scraped()
                property_data.update(detail_data)
                
                # データベースに保存
                saved = self.save_property(property_data)
                if saved:
                    saved_count += 1
                    
            time.sleep(self.delay)
            
        except Exception as e:
            self.record_detail_fetch_failed()
            logger.error(f"詳細取得エラー: {e}")
```

**アンチパターン** (避けるべき実装):

```python
# ❌ 各ページごとに詳細取得・保存を行う
for page in range(1, max_pages + 1):
    properties = self.parse_property_list(soup)
    
    # ページごとに処理してしまうと進捗管理が困難
    for prop in properties:
        detail_data = self.get_property_detail(prop['url'])
        self.save_property(detail_data)
```

### 2. 統計トラッキングの実装

基底クラス(BaseScraper)が提供する統計記録メソッドを適切に使用します：

- `record_property_found(count)` - 一覧ページから発見した物件数
- `record_property_processed(count)` - 処理対象とした物件数（max_properties制限後）
- `record_property_attempted()` - 処理を試行した物件
- `record_property_scraped()` - 詳細取得に成功した物件
- `record_listing_skipped()` - スキップした物件
- `record_detail_fetch_failed()` - 詳細取得に失敗
- `record_building_info_missing()` - 建物情報不足
- `record_save_failed()` - 保存失敗

## 重要な実装ポイント

### 1. User-Agent の設定

最新のブラウザのUser-Agentを使用します：

```python
# ❌ 古いUser-Agent
'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# ✅ 最新のUser-Agent
'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
```

### 2. fetch_page メソッドの使用

基底クラスの`fetch_page()`メソッドを使用することで、一時停止機能が自動的に有効になります：

```python
# ✅ 正しい実装
soup = self.fetch_page(url)

# ❌ 避けるべき実装
response = self.http_session.get(url)  # 一時停止機能が効かない
```

### 3. parse_property_list の実装

BeautifulSoupオブジェクトとHTML文字列の両方を受け付けるようにします：

```python
def parse_property_list(self, soup_or_html) -> List[Dict]:
    """一覧ページから物件情報を抽出"""
    # BeautifulSoupオブジェクトまたはHTML文字列を受け取る
    if isinstance(soup_or_html, str):
        soup = BeautifulSoup(soup_or_html, 'html.parser')
    else:
        soup = soup_or_html
    
    # 物件の解析処理...
```

### 4. 必須フィールドの確保

最低限以下のフィールドは取得する必要があります：

- `url` - 物件詳細ページのURL
- `building_name` - 建物名
- `price` - 価格（万円単位の整数）
- `source_site` - ソースサイト識別子

### 5. listing_* フィールドの保存

掲載サイトごとの属性値を保存します：

```python
listing = self.create_or_update_listing(
    master_property=master_property,
    url=property_data['url'],
    title=property_data.get('title', ''),
    price=property_data['price'],
    # 掲載サイトごとの物件属性
    listing_floor_number=property_data.get('floor_number'),
    listing_area=property_data.get('area'),
    listing_layout=property_data.get('layout'),
    listing_direction=property_data.get('direction'),
    listing_total_floors=property_data.get('total_floors'),
    listing_balcony_area=property_data.get('balcony_area'),
    listing_address=property_data.get('address')
)
```

## スマートスクレイピング機能

### 1. 概要

スマートスクレイピングは、詳細ページの取得を最適化する機能です。以下の場合を除いて、詳細ページの取得をスキップします：

- 初回スクレイピング時
- 一覧ページに更新マークがある場合
- 最後の詳細取得から90日以上経過している場合（デフォルト）
- 強制詳細取得モードが有効な場合

### 2. 実装方法

#### 方法A: 共通メソッドを使用（推奨）

```python
def scrape_area(self, area: str, max_pages: int = 5):
    """エリアの物件をスクレイピング"""
    if self.force_detail_fetch:
        print("※ 強制詳細取得モードが有効です - すべての物件の詳細ページを取得します")
    
    # ... フェーズ1: 物件一覧の収集 ...
    
    # フェーズ2: 詳細取得と保存
    for i, property_data in enumerate(all_properties):
        # 共通メソッドを使用
        saved = self.process_property_with_smart_scraping(
            property_data,
            get_detail_func=self.get_property_detail,
            save_func=self.save_property
        )
        if saved:
            saved_count += 1
        
        time.sleep(self.delay)
```

#### 方法B: 独自実装

```python
# 既存の掲載を確認
from ..models import PropertyListing
existing_listing = self.session.query(PropertyListing).filter(
    PropertyListing.url == prop['url']
).first()

# 詳細ページの取得が必要かチェック
needs_detail = True
if existing_listing and not self.force_detail_fetch:
    needs_detail = self.needs_detail_fetch(existing_listing)
    if not needs_detail:
        print(f"  → 詳細ページの取得をスキップ（最終取得: {existing_listing.detail_fetched_at}）")
        # 一覧ページの情報のみで保存
        saved = self.save_property(prop)
        if saved:
            saved_count += 1
            self.record_listing_skipped()
        time.sleep(self.delay)
        continue
```

### 3. 設定

環境変数で詳細ページの再取得間隔を設定できます：

```bash
# 全スクレイパー共通（デフォルト: 90日）
export SCRAPER_DETAIL_REFETCH_DAYS=90

# スクレイパー固有の設定（優先）
export SCRAPER_SUUMO_DETAIL_REFETCH_DAYS=60
export SCRAPER_HOMES_DETAIL_REFETCH_DAYS=120
```

### 4. 統計記録

スキップした場合は必ず `record_listing_skipped()` を呼び出して統計に記録します。

### 5. コミットタイミング

**重要**: `save_property` メソッド内では `session.flush()` のみを使用し、`session.commit()` は `scrape_area` メソッドの最後に一括で実行します。これにより、管理画面での統計表示が正確になります。

## 管理画面との統合

### 1. スクレイパーの登録

`/home/ubuntu/realestate/frontend/src/components/AdminScraping.tsx` に追加：

```typescript
const scraperOptions = [
    { value: 'suumo', label: 'SUUMO' },
    { value: 'homes', label: "LIFULL HOME'S" },
    { value: 'rehouse', label: '三井のリハウス' },
    { value: 'nomu', label: 'ノムコム' },
    // 新しいスクレイパーを追加
];
```

### 2. バックエンドでの登録

`/home/ubuntu/realestate/backend/app/api/admin.py` に追加：

```python
# スクレイパーのインポート
from ..scrapers.suumo_scraper import SUUMOScraper
from ..scrapers.homes_scraper import HomeScraper
from ..scrapers.rehouse_scraper import RehouseScraper
from ..scrapers.nomu_scraper import NomuScraper
# 新しいスクレイパーをインポート

# スクレイパーマッピング
scrapers = {
    "suumo": SUUMOScraper,
    "homes": HomeScraper,
    "rehouse": RehouseScraper,
    "nomu": NomuScraper,
    # 新しいスクレイパーを追加
}
```

## よくある問題と解決策

### 1. 物件が0件になる問題

**原因**: User-Agentが古い、またはサイトの構造が変更された

**解決策**:
```python
# 1. User-Agentを最新に更新
# 2. ブラウザの開発者ツールで実際のHTMLを確認
# 3. セレクタを更新
```

### 2. 一時停止ボタンが効かない

**原因**: `fetch_page()`メソッドを使用していない

**解決策**: 基底クラスの`fetch_page()`メソッドを使用する

### 3. 進捗表示が正しくない

**原因**: ページごとに処理を行っている

**解決策**: すべての物件を収集してから処理する

### 4. 統計が0のまま

**原因**: 統計記録メソッドを呼び出していない

**解決策**: 適切なタイミングで`record_*`メソッドを呼び出す

## チェックリスト

新しいスクレイパーを実装する際のチェックリスト：

- [ ] BaseScraper を継承している
- [ ] SOURCE_SITE を定義している
- [ ] コンストラクタで force_detail_fetch パラメータをサポートしている
- [ ] scrape_area メソッドを実装している
  - [ ] force_detail_fetch モードの説明を表示している
  - [ ] すべての物件を収集してから処理している（二段階処理パターン）
  - [ ] max_properties 制限を考慮している
  - [ ] 統計記録メソッドを適切に呼び出している
  - [ ] 最後に session.commit() を実行している
- [ ] parse_property_list メソッドを実装している
  - [ ] BeautifulSoupオブジェクトとHTML文字列の両方に対応している
- [ ] get_property_detail メソッドを実装している
  - [ ] fetch_page() を使用している
- [ ] save_property メソッドを実装している
  - [ ] listing_* フィールドを保存している
  - [ ] 多数決更新を呼び出している
  - [ ] session.flush() のみを使用（commit は使用しない）
- [ ] スマートスクレイピング機能を実装している
  - [ ] process_property_with_smart_scraping() を使用するか、独自実装
  - [ ] needs_detail_fetch() でチェックしている
  - [ ] スキップ時に record_listing_skipped() を呼び出している
- [ ] 必須フィールドを取得している
  - [ ] url
  - [ ] building_name
  - [ ] price
  - [ ] source_site
- [ ] 最新のUser-Agentを使用している
- [ ] エラーハンドリングを実装している
- [ ] アクセス間隔（delay）を守っている
- [ ] 管理画面に登録している
  - [ ] フロントエンド（AdminScraping.tsx）
  - [ ] バックエンド（admin.py）

## 参考実装

良い実装例として以下のスクレイパーを参照してください：

- **SUUMOScraper** - 最も標準的な実装（二段階処理パターンの模範例）
- **HomeScraper** - スマートスクレイピング機能の実装例
- **NomuScraper** - シンプルな実装例（二段階処理パターン適用済み）
- **RehouseScraper** - 三井のリハウスの実装例（二段階処理パターン適用済み）

## テスト方法

```python
# 基本的なテスト
from backend.app.scrapers.your_scraper import YourScraper

with YourScraper(max_properties=5) as scraper:
    scraper.scrape_area('area_code', max_pages=1)
    
    stats = scraper.get_scraping_stats()
    print(f"Found: {stats['properties_found']}")
    print(f"Processed: {stats['properties_processed']}")
    print(f"Scraped: {stats['detail_fetched']}")
```

## まとめ

スクレイパーの実装で最も重要なのは：

1. **収集と処理の分離** - すべての物件を収集してから処理する
2. **統計の正確な記録** - 管理画面での進捗表示のため
3. **基底クラスのメソッド活用** - 一時停止機能などの共通機能のため
4. **エラーハンドリング** - 安定した動作のため

これらのポイントを守ることで、管理画面と適切に統合され、ユーザーフレンドリーなスクレイパーを実装できます。