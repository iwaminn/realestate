# Cronジョブ設定ガイド

## 掲載状態更新ジョブ

### 概要
24時間以上確認されていない掲載を自動的に終了扱いにし、販売終了物件を適切に管理するためのcronジョブです。

### cronエントリの例

```bash
# 毎日午前3時に掲載状態を更新
0 3 * * * /home/ubuntu/realestate/backend/scripts/cron_update_listing_status.sh
```

### 設定手順

1. crontabを編集:
```bash
crontab -e
```

2. 上記のcronエントリを追加

3. ログファイルの確認:
```bash
tail -f /home/ubuntu/realestate/logs/update_listing_status.log
```

### 手動実行

cronジョブを手動で実行する場合:
```bash
/home/ubuntu/realestate/backend/scripts/cron_update_listing_status.sh
```

または、Dockerコンテナ内で直接実行:
```bash
docker exec realestate-backend poetry run python /app/backend/scripts/update_listing_status.py
```

### 処理内容

1. 24時間以上確認されていない掲載を非アクティブ化
2. 全掲載が非アクティブになった物件に販売終了日を設定
3. 最終販売価格を記録

### 注意事項

- ログファイルのサイズに注意（定期的なログローテーションを推奨）
- データベースの負荷を考慮して実行時間を設定
- 本番環境では、バックアップ後に実行することを推奨