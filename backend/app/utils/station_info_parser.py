#!/usr/bin/env python3
"""
交通情報（駅情報）のパース・正規化・多数決処理

駅ごとに分解して集計することで、順序や駅数の違いに依存しない
精度の高い多数決を実現する。
"""

import re
from typing import List, Dict, Tuple, Optional
from collections import defaultdict, Counter
import logging

logger = logging.getLogger(__name__)


def normalize_station_text(text: str) -> str:
    """
    駅情報のテキストを正規化

    - 全角英数字→半角
    - 鍵括弧の除去
    - スペースの統一
    """
    if not text:
        return ""

    # 全角英数字を半角に変換
    normalized = text.translate(str.maketrans(
        '０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ',
        '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    ))

    # 鍵括弧を除去
    normalized = normalized.replace('「', '').replace('」', '')
    normalized = normalized.replace('『', '').replace('』', '')

    # 複数のスペースを1つに統一
    normalized = re.sub(r'\s+', ' ', normalized)

    return normalized.strip()


def parse_station_info(station_info: str) -> List[Dict]:
    """
    交通情報から駅情報をパースして正規化

    入力例:
        "ＪＲ山手線「田町」歩14分\\n都営浅草線「三田」歩12分"

    出力例:
        [
            {'line': 'JR山手線', 'station': '田町', 'walk_min': 14, 'key': 'JR山手線_田町'},
            {'line': '都営浅草線', 'station': '三田', 'walk_min': 12, 'key': '都営浅草線_三田'}
        ]

    Returns:
        パースされた駅情報のリスト
    """
    if not station_info:
        return []

    stations = []
    
    # 【重要】正規化の前に、半角スペース区切りデータを改行に変換
    # nomuサイトのデータ: 「山手線「田町」駅 徒歩11分 都営三田線「三田」駅 徒歩13分」
    # 正規化すると改行がスペースに統一されてしまうので、先に処理
    
    # パターン1: 「駅 徒歩X分 」→ 「駅 徒歩X分\n」
    station_info = re.sub(r'(駅\s*徒歩\d+分)\s+', r'\1\n', station_info)
    # パターン2: 「徒歩X分」の直後に漢字やひらがなが続く場合（スペースなし）
    station_info = re.sub(r'(徒歩\d+分)([ぁ-んァ-ヶ一-龥])', r'\1\n\2', station_info)
    
    # 改行で分割してから正規化
    lines = station_info.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 正規化
        normalized = normalize_station_text(line)

        # 【住所除去】先頭の住所パターンを削除
        # 例：「港区芝浦4丁目山手線...」→「山手線...」
        # 数字+「丁目」を含む住所部分を削除
        normalized = re.sub(r'^.+?\d+丁目\s*', '', normalized)
        
        # パターンマッチング
        # 路線名は「線」で終わることを利用
        # 例：「JR山手線田町歩14分」または「JR山手線 田町駅 徒歩14分」
        pattern = r'(.+線)\s*([^\s歩徒駅]+)(駅)?\s*(歩|徒歩)(\d+)分'
        match = re.search(pattern, normalized)

        if match:
            line_name = match.group(1).strip()
            station_name = match.group(2).strip()
            walk_minutes = int(match.group(5))

            # 駅の一意キー（路線名_駅名）
            station_key = f"{line_name}_{station_name}"

            stations.append({
                'line': line_name,
                'station': station_name,
                'walk_min': walk_minutes,
                'key': station_key
            })
        else:
            logger.debug(f"駅情報のパースに失敗: '{line}' (正規化後: '{normalized}')")

    return stations


def vote_for_stations(station_infos_with_source: List[Tuple[str, str]],
                     site_priority_func) -> List[Dict]:
    """
    駅ごとに段階的な投票を行い、最も信頼性の高い駅情報を決定
    
    【段階的多数決の流れ】
    1. 駅（路線名+駅名）ごとに投票数を集計
    2. 投票数が多い駅を採用
    3. 採用された各駅について、徒歩時間を再度多数決

    Args:
        station_infos_with_source: [(交通情報, ソースサイト), ...]
        site_priority_func: サイト優先度を取得する関数

    Returns:
        [{'line': ..., 'station': ..., 'walk_min': ..., 'votes': ..., 'priority': ...}, ...]
        票数順にソート済み
    """
    # 【ステップ1】駅キーごとに投票データを収集
    # {駅キー: [(路線名, 駅名, 徒歩分, ソース), ...]}
    station_votes = defaultdict(list)

    for station_info, source in station_infos_with_source:
        stations = parse_station_info(station_info)
        for station in stations:
            key = station['key']
            station_votes[key].append((
                station['line'],
                station['station'],
                station['walk_min'],
                source
            ))

    # 【ステップ2】各駅について段階的多数決を実行
    result_stations = []

    for station_key, votes in station_votes.items():
        vote_count = len(votes)

        # 路線名の最頻値
        line_counter = Counter([v[0] for v in votes])
        most_common_line = line_counter.most_common(1)[0][0]

        # 駅名の最頻値
        station_counter = Counter([v[1] for v in votes])
        most_common_station = station_counter.most_common(1)[0][0]

        # 【重要】徒歩時間の最頻値を決定
        # 同数の場合は小さい方を優先
        walk_min_counter = Counter([v[2] for v in votes])
        most_common_walks = walk_min_counter.most_common()
        max_walk_count = most_common_walks[0][1]
        # 同じ出現回数の徒歩時間から最小値を選択
        most_common_walk_min = min([w for w, c in most_common_walks if c == max_walk_count])

        # サイト優先度の最高値を取得（参考情報）
        sources = [v[3] for v in votes]
        best_priority = min(site_priority_func(s) for s in sources)

        result_stations.append({
            'line': most_common_line,
            'station': most_common_station,
            'walk_min': most_common_walk_min,
            'votes': vote_count,
            'priority': best_priority,
            'key': station_key
        })

    # 票数順→サイト優先度順→徒歩時間順でソート
    result_stations.sort(key=lambda x: (-x['votes'], x['priority'], x['walk_min']))

    return result_stations


def select_top_stations(stations: List[Dict],
                        total_sources: int,
                        min_vote_ratio: float = 0.3,
                        max_stations: int = 3) -> List[Dict]:
    """
    閾値を超えた駅を選択

    Args:
        stations: 投票結果（票数順ソート済み）
        total_sources: 総掲載数
        min_vote_ratio: 最低投票率（例：0.3 = 30%以上の掲載に含まれる駅を採用）
        max_stations: 最大駅数

    Returns:
        選択された駅のリスト
    """
    min_votes = max(1, int(total_sources * min_vote_ratio))

    selected = []
    for station in stations:
        if station['votes'] >= min_votes and len(selected) < max_stations:
            selected.append(station)

    return selected


def format_station_info(stations: List[Dict]) -> str:
    """
    駅情報を統一フォーマットで出力

    Args:
        stations: 選択された駅のリスト

    Returns:
        "路線「駅名」徒歩X分\\n..." 形式の文字列
    """
    if not stations:
        return ""

    lines = []
    for station in stations:
        line = f"{station['line']}「{station['station']}」徒歩{station['walk_min']}分"
        lines.append(line)

    return '\n'.join(lines)


def get_majority_station_info(station_infos_with_source: List[Tuple[str, str]],
                               site_priority_func,
                               min_vote_ratio: float = 0.3,
                               max_stations: int = 3) -> Optional[str]:
    """
    交通情報の多数決（駅ごと集計方式）

    Args:
        station_infos_with_source: [(交通情報, ソースサイト), ...]
        site_priority_func: サイト優先度を取得する関数
        min_vote_ratio: 最低投票率（デフォルト: 0.3 = 30%）
        max_stations: 最大駅数（デフォルト: 3駅）

    Returns:
        多数決で決定された交通情報（統一フォーマット）
    """
    if not station_infos_with_source:
        return None

    # 1. 駅ごとに投票
    stations = vote_for_stations(station_infos_with_source, site_priority_func)

    if not stations:
        logger.warning("駅情報のパースに失敗しました")
        return None

    # 2. 閾値を超えた駅を選択
    total_sources = len(station_infos_with_source)
    selected_stations = select_top_stations(
        stations,
        total_sources,
        min_vote_ratio=min_vote_ratio,
        max_stations=max_stations
    )

    # 3. 統一フォーマットで出力
    if selected_stations:
        result = format_station_info(selected_stations)
        logger.debug(
            f"交通情報の多数決: {len(station_infos_with_source)}件の掲載から"
            f"{len(stations)}駅を抽出、{len(selected_stations)}駅を選択"
        )
        return result

    return None
