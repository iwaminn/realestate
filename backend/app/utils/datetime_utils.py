"""
日付時刻のユーティリティ関数
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

# 日本のタイムゾーン (UTC+9)
JST = timezone(timedelta(hours=9))


def to_jst_string(dt: Optional[datetime]) -> Optional[str]:
    """
    UTC datetimeを日本時間の文字列に変換
    
    Args:
        dt: UTC datetime オブジェクト
    
    Returns:
        日本時間のISO形式文字列、またはNone
    """
    if dt is None:
        return None
    
    # naive datetimeの場合はUTCとして扱う
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # 日本時間に変換
    jst_dt = dt.astimezone(JST)
    
    # ISO形式で返す（タイムゾーン情報付き）
    return jst_dt.isoformat()