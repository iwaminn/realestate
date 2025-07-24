# 販売終了物件の価格多数決機能

## 概要

販売終了物件の最終価格を、販売終了日から過去1週間の価格履歴データを基に多数決で決定する機能です。

## 背景と目的

不動産情報サイトによって掲載を終了するタイミングが異なるため、以下の問題が発生することがあります：

1. **掲載終了タイミングの差**: サイトAでは販売終了直後に掲載を下げるが、サイトBでは数日後に下げることがある
2. **価格変更の反映遅れ**: 最後の数日間に価格変更があった場合、一部のサイトでは反映されないことがある
3. **誤った最終価格の記録**: 少数派の価格を最終価格として記録してしまう可能性

これらの問題を解決するため、販売終了前1週間の価格履歴から最も多く掲載されていた価格を最終価格として採用します。

## 実装詳細

### 1. 価格履歴の収集

- 対象期間: 販売終了日（`sold_at`）から過去7日間
- データソース: `listing_price_history`テーブル
- 集計方法: 価格ごとの出現回数をカウント

### 2. 多数決ロジック

```python
def get_majority_price_for_sold_property(price_votes: Dict[int, int]) -> Optional[int]:
    """
    多数決で最も多い価格を決定
    同数の場合は高い方の価格を採用（より保守的な価格設定）
    """
    if not price_votes:
        return None
    
    # 出現回数でソート（同数の場合は価格が高い方を優先）
    sorted_prices = sorted(
        price_votes.items(), 
        key=lambda x: (x[1], x[0]),  # (出現回数, 価格)
        reverse=True
    )
    
    return sorted_prices[0][0]
```

### 3. 更新対象

- `master_properties`テーブルの`last_sale_price`フィールド
- 販売終了物件（`sold_at IS NOT NULL`）のみが対象

## 使用方法

### 1. スクリプトによる実行

```bash
# 全件更新（ドライラン）
docker exec realestate-backend python /app/backend/scripts/update_sold_property_prices.py --dry-run

# 全件更新（実行）
docker exec realestate-backend python /app/backend/scripts/update_sold_property_prices.py

# 特定物件のみ更新
docker exec realestate-backend python /app/backend/scripts/update_sold_property_prices.py --property-id 2214

# 期間を変更（デフォルト7日）
docker exec realestate-backend python /app/backend/scripts/update_sold_property_prices.py --days 14
```

### 2. 管理APIによる実行

```bash
# 全件更新
curl -X POST http://localhost:8000/api/admin/update-sold-property-prices \
  -H "Authorization: Bearer YOUR_TOKEN"

# 特定物件のみ更新
curl -X POST http://localhost:8000/api/admin/update-sold-property-prices?property_id=2214 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3. 自動実行の推奨

販売終了物件の価格を正確に保つため、以下のタイミングでの実行を推奨します：

1. **販売終了処理後**: `update-listing-status`実行後に自動実行
2. **定期実行**: 1日1回、夜間バッチで実行

## 実行例

```
2025-07-24 16:06:19,689 - __main__ - INFO - 物件ID 2214 の価格を確認中...
2025-07-24 16:06:19,758 - __main__ - INFO - 価格の投票状況: {8980: 9, 9980: 3}
2025-07-24 16:06:19,758 - __main__ - INFO - 多数決による価格: 8980万円
2025-07-24 16:06:19,758 - __main__ - INFO - 現在の最終価格: 9980万円
2025-07-24 16:06:19,758 - __main__ - INFO - [DRY RUN] 価格を更新します: 9980万円 -> 8980万円
```

この例では：
- 8,980万円: 9回掲載
- 9,980万円: 3回掲載
- 多数決により8,980万円を採用

## 注意事項

1. **履歴データの必要性**: 価格履歴が存在しない物件は更新されません
2. **同数の場合の処理**: 同じ回数で複数の価格がある場合、高い方の価格を採用します
3. **パフォーマンス**: 全件更新は時間がかかる場合があります（約2,000件で数分程度）

## 関連ファイル

- `/backend/app/utils/majority_vote_updater.py`: 多数決ロジックの実装
- `/backend/scripts/update_sold_property_prices.py`: 実行スクリプト
- `/backend/app/api/admin.py`: 管理APIエンドポイント

## 今後の拡張案

1. **期間の動的調整**: 物件ごとに最適な集計期間を自動決定
2. **重み付け投票**: 信頼性の高いサイトの価格に重みを付ける
3. **異常値の除外**: 明らかに異常な価格変動を除外するロジック
4. **通知機能**: 大幅な価格変更があった場合の通知