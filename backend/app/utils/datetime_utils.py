"""
日付時刻のユーティリティ関数
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

# 日本のタイムゾーン (UTC+9)
JST = timezone(timedelta(hours=9))


def to_jst_string(dt: Optional[datetime]) -> Optional[str]:
    """
    日本時間のdatetimeを日本時間の文字列に変換
    
    データベースには日本時間で保存されているため、
    タイムゾーン情報を付加してISO形式で返す
    
    Args:
        dt: 日本時間の datetime オブジェクト（通常はnaive）
    
    Returns:
        日本時間のISO形式文字列（+09:00付き）、またはNone
    """
    if dt is None:
        return None
    
    # naive datetimeの場合は日本時間として扱う
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    
    # ISO形式で返す（タイムゾーン情報付き）
    return dt.isoformat()


def get_utc_now() -> datetime:
    """
    現在の日本時間を取得（タイムゾーンなし）
    
    PostgreSQLのtimestamp without time zone用に
    タイムゾーン情報を削除した日本時間を返す
    
    Returns:
        タイムゾーン情報なしの日本時間 datetime
    """
    # 日本時間で現在時刻を取得してタイムゾーン情報を削除
    jst_now = datetime.now(JST)
    return jst_now.replace(tzinfo=None)


def get_jst_now() -> datetime:
    """
    現在の日本時間を取得（タイムゾーンなし）
    
    get_utc_now()のエイリアス。実際は日本時間を返す。
    
    Returns:
        タイムゾーン情報なしの日本時間 datetime
    """
    return get_utc_now()