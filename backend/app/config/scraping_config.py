"""
スクレイピング関連の設定値
"""

# タイムアウト設定（秒）
PAUSE_TIMEOUT_SECONDS = 1800  # 一時停止中のタイムアウト（30分）

# 停止タスク判定の閾値（分）
STALLED_TASK_THRESHOLD_MINUTES = 30  # 通常のタスク（エリアごとの処理に時間がかかる場合を考慮）
STALLED_PAUSED_TASK_THRESHOLD_MINUTES = 60  # 一時停止中のタスク

# プロセス停止判定の閾値（分）
PROCESS_CHECK_PAUSE_THRESHOLD_MINUTES = 5  # 一時停止操作時のチェック
PROCESS_CHECK_RESUME_THRESHOLD_MINUTES = 10  # 再開操作時のチェック