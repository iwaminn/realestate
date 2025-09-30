# 成約価格情報API連携機能

## 概要

国土交通省の「不動産情報ライブラリ」APIを使用して、成約価格情報（レインズマーケットインフォメーション）を自動的に取得・更新する機能です。

## 機能

- 成約価格情報の自動取得
- 既存データとの重複チェック
- 不足期間の自動検出と補完
- 定期的な自動更新（cronジョブ対応）

## セットアップ

### 1. APIキーの設定

`.env`ファイルにAPIキーを設定します：

```bash
REINFOLIB_API_KEY=your-api-key-here
```

### 2. 初回データ取得

初めて使用する場合、過去のデータを一括取得します：

```bash
# Docker環境
docker exec realestate-backend poetry run python /app/backend/scripts/fetch_transaction_prices_api.py --mode historical

# ローカル環境
cd backend
poetry run python scripts/fetch_transaction_prices_api.py --mode historical
```

## 使用方法

### 手動実行

#### 最新データの取得（不足分を自動判定）

```bash
# Docker環境
docker exec realestate-backend poetry run python /app/backend/scripts/fetch_transaction_prices_api.py --mode update

# ローカル環境
cd backend
poetry run python scripts/fetch_transaction_prices_api.py --mode update
```

#### 特定期間のデータ取得

```bash
# 2021年から2024年のデータを取得
poetry run python scripts/fetch_transaction_prices_api.py --mode historical --from-year 2021 --to-year 2024
```

#### 最新四半期のみ取得

```bash
poetry run python scripts/fetch_transaction_prices_api.py --mode recent
```

### 自動実行（cronジョブ）

提供されているシェルスクリプトを使用して、cronで定期実行を設定できます：

```bash
# cronエディタを開く
crontab -e

# 毎日午前3時に実行する例
0 3 * * * /home/ubuntu/realestate/backend/scripts/update_transaction_prices.sh
```

## APIの仕様

### エンドポイント

```
https://www.reinfolib.mlit.go.jp/ex-api/external/XIT001
```

### 主要パラメータ

- `year`: 取引年（必須）
- `quarter`: 四半期（1-4）
- `area`: 都道府県コード（13=東京都）
- `priceClassification`: 価格分類（02=成約価格情報）

### APIキーの使用

HTTPヘッダーに含める必要があります：
```
Ocp-Apim-Subscription-Key: your-api-key
```

## データの特徴

### 取得可能期間

- 2021年以降の成約価格情報が利用可能
- 四半期ごとにデータが更新される
- 最新データは約1-2ヶ月の遅延がある

### 含まれる情報

- 取引価格（万円）
- 専有面積（㎡）
- 間取り
- 築年数
- 最寄り駅と徒歩分数
- 所在地（町名レベル）
- 取引時期（四半期）

### データの精度

- 個別の不動産取引が特定できないよう加工済み
- 統計的な分析に適したデータ
- 実際の取引価格をベースにした信頼性の高い情報

## ログ

実行ログは以下の場所に保存されます：
```
/home/ubuntu/realestate/logs/transaction_prices_update.log
```

## トラブルシューティング

### APIキーエラー（401 Unauthorized）

`.env`ファイルのAPIキーが正しく設定されているか確認してください。

### データ取得エラー

- ネットワーク接続を確認
- APIのレート制限（1秒間隔）が守られているか確認
- APIサービスの稼働状況を確認

### データベースエラー

- PostgreSQLが起動しているか確認
- データベース接続情報が正しいか確認
- テーブルが正しく作成されているか確認

## 注意事項

1. **レート制限**: API呼び出しは1秒以上の間隔を空ける
2. **データ量**: 初回取得時は数年分のデータを取得するため時間がかかる
3. **重複チェック**: 同じデータを重複して保存しないよう自動チェック
4. **エラー処理**: ネットワークエラーなどが発生しても処理を継続

## 関連ファイル

- `/backend/scripts/fetch_transaction_prices_api.py` - メインスクリプト
- `/backend/scripts/update_transaction_prices.sh` - cron実行用スクリプト
- `/backend/app/models.py` - TransactionPriceモデル定義
- `/backend/app/api/transaction_prices.py` - API エンドポイント