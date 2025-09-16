# base_scraper.py リファクタリング (2025年1月)

## 概要
base_scraper.pyのコンポーネント化リファクタリングを実施し、保守性と拡張性を向上させました。

## リファクタリング内容

### Phase 1: 旧HTTP実装の削除 ✅
- `requests.Session`の直接利用を削除
- HTTPクライアントはHttpClientComponentに完全移行
- 不要なセッションクローズ処理を削除

### Phase 2: 重複コンポーネントの統合 ✅
- `property_validator`と`data_validator`を統一
  - すべての検証処理を`data_validator`に集約
- 建物名正規化処理をコンポーネント化
  - `BuildingNormalizerComponent`を作成
  - `normalize()`, `canonicalize()`, `extract_room_number()`メソッドを提供
- 物件マッチング処理をコンポーネント化  
  - `PropertyMatcherComponent`を作成
  - `find_similar_property()`, `calculate_similarity()`, `is_duplicate()`メソッドを提供

### Phase 3: データベース処理のコンポーネント化 ✅
- `DbRepositoryComponent`を拡張
  - property_hash生成
  - 既存物件の検索
  - 建物・物件の作成/更新
  - 価格履歴の記録
- `db_repository_scope`コンテキストマネージャーを追加
  - トランザクション管理を含むDB操作の一元化

### Phase 4: エラー処理の統一 ✅
- `ErrorHandlerComponent`（実装済み）
  - エラー分類と記録
  - リトライ判定
  - 異常検知とアラート
  - 統計情報管理

### Phase 5: 進捗管理の改善 ✅  
- `ProgressTrackerComponent`（実装済み）
  - 進捗状況の追跡
  - 統計情報の収集
  - 時間推定
  - フェーズ別管理

## アーキテクチャ

```
base_scraper.py
├── コンポーネント層
│   ├── HttpClientComponent     - HTTP通信
│   ├── HtmlParserComponent     - HTML解析
│   ├── DataValidatorComponent  - データ検証
│   ├── BuildingNormalizerComponent - 建物名正規化
│   ├── PropertyMatcherComponent - 物件マッチング  
│   ├── DbRepositoryComponent   - データベース操作
│   ├── CacheManagerComponent   - キャッシュ管理
│   ├── RateLimiterComponent    - レート制限
│   ├── ErrorHandlerComponent   - エラー処理
│   └── ProgressTrackerComponent - 進捗管理
└── ビジネスロジック層
    ├── スクレイピング制御
    ├── データ変換
    └── 統計管理
```

## コンポーネント利用例

### db_repository_scopeの使用
```python
with self.db_repository_scope() as db_repo:
    # 建物の作成/更新
    building = db_repo.find_or_create_building(building_data)
    
    # マスター物件の検索
    master_property = db_repo.find_master_property(property_hash)
    
    # 掲載情報の作成/更新
    listing, is_new = db_repo.find_or_create_listing(
        master_property_id=master_property.id,
        source_site=self.source_site,
        source_id=source_id
    )
    
    # 価格変更の記録
    if old_price != new_price:
        db_repo.record_price_change(listing.id, old_price, new_price)
    
    # トランザクションのコミット（自動）
```

### 建物名正規化の使用
```python
# 建物名の正規化
normalized_name = self.building_normalizer.normalize(building_name)

# 建物名の正準化（より厳密）
canonical_name = self.building_normalizer.canonicalize(building_name)

# 部屋番号の抽出
building, room_number = self.building_normalizer.extract_room_number(building_name)
```

### 物件マッチングの使用
```python
# 類似物件の検索
similar = self.property_matcher.find_similar_property(
    property_data=new_property,
    existing_properties=existing_list,
    threshold=0.85
)

# 重複判定
is_dup = self.property_matcher.is_duplicate(property1, property2)
```

## 効果

1. **保守性向上**
   - 責任の分離により各コンポーネントが独立してテスト・修正可能
   - コンポーネント単位での機能追加・変更が容易

2. **コード再利用性**
   - 各スクレイパーでコンポーネントを再利用可能
   - 共通処理の重複を排除

3. **エラー処理の一元化**
   - ErrorHandlerComponentによる統一的なエラー管理
   - 異常検知とアラート機能

4. **パフォーマンス最適化**
   - CacheManagerによる重複リクエストの削減
   - RateLimiterによる適切なレート制御

## 移行時の注意点

- 既存のスクレイパー（suumo, homes, rehouse, nomu, livable）は後方互換性を維持
- 新規スクレイパー作成時は新しいコンポーネントベースのアーキテクチャを推奨
- 段階的な移行が可能（各コンポーネントは独立して利用可能）

## テスト実施結果

```bash
# SUUMOスクレイパーでのテスト
poetry run python scripts/run_scrapers.py --scraper suumo --area minato --max-properties 1
# 結果: 正常動作を確認
```

## 今後の拡張ポイント

1. **非同期処理の導入**
   - asyncioベースのコンポーネント実装
   - 並列処理の最適化

2. **プラグイン機構**
   - 動的なコンポーネントロード
   - サードパーティコンポーネントのサポート

3. **メトリクス収集**
   - 各コンポーネントのパフォーマンスメトリクス
   - ダッシュボード連携

## 関連ファイル

- `/backend/app/scrapers/base_scraper.py` - ベーススクレイパー本体
- `/backend/app/scrapers/components/` - コンポーネント実装
  - `http_client.py` - HTTP通信
  - `html_parser.py` - HTML解析
  - `data_validator.py` - データ検証
  - `building_normalizer.py` - 建物名正規化
  - `property_matcher.py` - 物件マッチング
  - `db_repository.py` - データベース操作
  - `cache_manager.py` - キャッシュ管理
  - `rate_limiter.py` - レート制限
  - `error_handler.py` - エラー処理
  - `progress_tracker.py` - 進捗管理