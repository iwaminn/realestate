# 価格変更ベースのスマートスクレイピング仕様

## 概要

2025年1月より、スクレイパーのスマートスクレイピング機能を「更新マークベース」から「価格変更ベース」に変更しました。これにより、より効率的かつ確実に物件情報の変更を検出できるようになりました。

## 背景

### 従来の問題点
- 各不動産サイトの「NEW」「更新」マークの基準が異なる
- 同じ物件でも日付だけで「NEW」扱いになることがある（例：東急リバブルの「NEW 7/24」）
- 実際には情報が変わっていないのに詳細ページを取得してしまう

### 新しいアプローチの利点
- 価格変更は物件情報の実質的な変更を示す最も重要な指標
- 一覧ページで価格は必ず表示されるため、確実に検出可能
- 無駄な詳細ページ取得を大幅に削減

## 技術仕様

### 1. 詳細取得の判定ロジック

```python
def process_property_with_detail_check():
    # 価格が変更されているかチェック
    price_changed = False
    if 'price' in property_data and property_data['price'] is not None:
        if existing_listing.current_price != property_data['price']:
            price_changed = True
            print(f"  → 価格変更検出: {existing_listing.current_price}万円 → {property_data['price']}万円")
    
    # 価格変更があれば詳細を取得、なければ通常の判定
    if price_changed:
        needs_detail = True
    else:
        needs_detail = self.needs_detail_fetch(existing_listing)
```

### 2. 詳細取得が必要なケース

1. **新規物件**：必ず詳細を取得
2. **価格変更**：価格が変わった場合は必ず詳細を取得
3. **定期更新**：90日以上詳細を取得していない場合（環境変数で設定可能）
4. **強制取得**：`force_detail_fetch=True`オプション使用時

### 3. 更新マークの扱い

- `has_update_mark`フィールドは引き続き取得・保存する
- ただし、詳細取得の判断には使用しない
- 将来的な分析や参考情報として活用

## 実装詳細

### base_scraper.py の変更点

1. `process_property_with_detail_check`メソッドに価格比較ロジックを追加
2. `needs_detail_fetch`メソッドから更新マークチェックを削除

### 各スクレイパーの対応

以下のスクレイパーは共通の`process_property_with_detail_check`を使用しており、価格変更ベースの動作が適用されています：

- **SUUMO**: 対応済み（`common_scrape_area_logic`使用）
- **LIFULL HOME'S**: 対応済み（`common_scrape_area_logic`使用）
- **三井のリハウス**: 対応済み（2025年1月更新、`common_scrape_area_logic`使用）
- **ノムコム**: 対応済み（2025年1月更新、`common_scrape_area_logic`使用）
- **東急リバブル**: 対応済み（`common_scrape_area_logic`使用）

すべてのスクレイパーが統一された価格変更ベースのスマートスクレイピングを実装しています。

## 運用上の注意

### 1. 価格が取得できない場合

一覧ページで価格が取得できない場合は、安全のため詳細ページを取得します。

### 2. 価格以外の変更

以下の変更は詳細取得のトリガーになりません：
- 管理費・修繕積立金の変更
- 物件説明文の変更
- 画像の追加・変更

これらの情報は定期更新（90日ごと）で最新化されます。

### 3. 価格履歴

価格変更は自動的に`listing_price_history`テーブルに記録されます。

## パフォーマンスへの影響

### メリット
- 詳細ページ取得数の大幅削減（推定60-80%削減）
- スクレイピング時間の短縮
- サーバー負荷の軽減

### デメリット
- 価格以外の情報更新の遅延（最大90日）
- ただし、重要な価格情報は常に最新

## 設定と調整

### 環境変数

```bash
# 定期更新の間隔（日数）
export SCRAPER_DETAIL_REFETCH_DAYS=90     # 全スクレイパー共通
export SCRAPER_SUUMO_DETAIL_REFETCH_DAYS=60  # SUUMOのみ60日に設定

# 強制詳細取得（コマンドラインオプション）
poetry run python backend/scripts/run_scrapers.py --scraper suumo --area 港区 --force-detail-fetch
```

### 推奨設定

- 通常運用：90日（デフォルト）
- 頻繁に更新されるエリア：30-60日
- あまり更新されないエリア：120-180日

## 今後の拡張

### 検討中の機能
1. 管理費・修繕積立金の変更も検出対象に追加
2. 価格変更率の閾値設定（例：5%以上の変更のみ対象）
3. エリアごとの更新頻度の自動調整

### 長期的な改善
1. 機械学習による更新パターンの学習
2. 物件ごとの最適な更新頻度の自動決定