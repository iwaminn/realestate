# スクレイパーエラーログ機能

## 概要

スクレイパーのエラーを詳細に記録し、分析するための機能を実装しました。これにより、エラーが発生した物件の特定、HTMLセレクタの変更検知、エラーパターンの分析が可能になります。

## 主な機能

### 1. 詳細なエラーログ記録

エラー発生時に以下の情報を自動的に記録：
- エラーが発生した物件のURL
- 建物名
- 処理中の物件データ
- エラーメッセージとスタックトレース
- 処理フェーズ（一覧取得、詳細取得、保存など）

### 2. エラーログファイル

- `logs/scraper_errors.json` - 構造化されたエラー詳細（JSON形式）
- `logs/scraper_debug.log` - デバッグ用の詳細ログ
- `logs/scraper.log` - 通常のログ（従来通り）

### 3. エラー分析機能

- エラータイプ別の集計
- 問題のあるURLの特定
- HTMLセレクタ変更の検知
- バリデーションエラーの詳細分析

## 使用方法

### エラーレポートの生成

```bash
# 過去24時間のエラーレポート
python backend/scripts/scraper_error_report.py

# 過去1時間のエラーレポート
python backend/scripts/scraper_error_report.py --hours 1

# JSON形式で出力
python backend/scripts/scraper_error_report.py --json

# 問題のあるURLをファイルにエクスポート
python backend/scripts/scraper_error_report.py --export-urls
```

### プログラムからの使用

```python
from backend.app.utils.scraper_error_logger import ScraperErrorLogger

# エラーロガーの作成（BaseScraper内で自動的に作成される）
error_logger = ScraperErrorLogger("suumo")

# エラーサマリーの取得
summary = error_logger.get_error_summary(hours=24)
print(f"過去24時間のエラー数: {summary['total_errors']}")

# セレクタ変更の検出
problematic_selectors = error_logger.check_selector_changes()
for selector in problematic_selectors:
    if selector['possible_change']:
        print(f"⚠️ {selector['selector']} が変更された可能性があります")
```

## エラーレポートの読み方

### スクレイパー別サマリー

```
suumo:
  総エラー数: 45
  影響を受けたURL数: 32
  影響を受けた建物数: 28
  エラータイプ:
    - validation: 20件
    - detail_page: 15件
    - parsing: 10件
```

- **総エラー数**: 発生したエラーの総数
- **影響を受けたURL数**: エラーが発生したユニークなURL数
- **影響を受けた建物数**: エラーが発生したユニークな建物数

### HTMLセレクタの問題

```
【HTMLセレクタの問題】
以下のセレクタが見つかりませんでした（サイト構造が変更された可能性があります）:
  - .price-value: 25件
  - .building-name: 20件
```

10回以上失敗しているセレクタは、サイトの構造が変更された可能性が高いです。

### 問題のあるURL

`--export-urls`オプションを使用すると、`problem_urls.txt`ファイルに問題のあるURLが出力されます：

```
URL: https://suumo.jp/chukoikkodate/tokyo/sc_minato/nc_12345678/
エラー数: 5
エラータイプ: validation(3), detail_page(2)
最新エラー: 価格が取得できませんでした
```

## トラブルシューティング

### よくあるエラーパターン

1. **価格が取得できない**
   - 原因: 価格表示のHTMLセレクタが変更された
   - 対処: 該当スクレイパーの`parse_property_detail`メソッドを確認

2. **建物名が無効**
   - 原因: 広告文が建物名として取得されている
   - 対処: 広告文判定ロジックを強化

3. **連続エラーでサーキットブレーカー作動**
   - 原因: サイトの大幅な変更、またはアクセス制限
   - 対処: セレクタを更新、またはアクセス間隔を調整

### エラーログのクリーンアップ

エラーログは自動的に最新1000件のみ保持されますが、手動でクリアすることも可能：

```bash
# エラーログをクリア
rm logs/scraper_errors.json
rm logs/scraper_debug.log
```

## 今後の拡張案

1. **エラー通知機能**
   - 特定のエラーパターンが繰り返される場合のメール通知
   - Slack通知の実装

2. **自動修復機能**
   - よくあるエラーパターンの自動修正
   - セレクタの自動更新提案

3. **ダッシュボード**
   - Web UIでエラー状況をリアルタイム監視
   - エラートレンドのグラフ表示