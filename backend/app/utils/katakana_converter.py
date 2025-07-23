"""英語をカタカナに変換するユーティリティ"""

import re

# 英語→カタカナ変換辞書
ENGLISH_TO_KATAKANA = {
    # 一般的な建物関連の単語
    'WORLD': 'ワールド',
    'TOWER': 'タワー',
    'RESIDENCE': 'レジデンス',
    'COURT': 'コート',
    'PALACE': 'パレス',
    'HOUSE': 'ハウス',
    'VILLA': 'ヴィラ',
    'MAISON': 'メゾン',
    'PLAZA': 'プラザ',
    'GARDEN': 'ガーデン',
    'GARDENS': 'ガーデンズ',
    'PARK': 'パーク',
    'TERRACE': 'テラス',
    'FOREST': 'フォレスト',
    'GRAND': 'グランド',
    'GRANDE': 'グランデ',
    'EXCEL': 'エクセル',
    'PREMIER': 'プレミア',
    'PREMIERE': 'プレミエ',
    'ROYAL': 'ロイヤル',
    'CITY': 'シティ',
    'URBAN': 'アーバン',
    'STAGE': 'ステージ',
    'FRONT': 'フロント',
    'CREST': 'クレスト',
    'AXIS': 'アクシス',
    'HILLS': 'ヒルズ',
    'HILL': 'ヒル',
    'RIVER': 'リバー',
    'OCEAN': 'オーシャン',
    'BAY': 'ベイ',
    'SUNNY': 'サニー',
    'BRIGHT': 'ブライト',
    'FIRST': 'ファースト',
    'SECOND': 'セカンド',
    'THIRD': 'サード',
    'LUMINOUS': 'ルミナス',
    'GRACE': 'グレース',
    'ELEGANCE': 'エレガンス',
    'PRIME': 'プライム',
    'ALPHA': 'アルファ',
    'BETA': 'ベータ',
    'OMEGA': 'オメガ',
    'UNION': 'ユニオン',
    'CENTRAL': 'セントラル',
    'SOUTH': 'サウス',
    'NORTH': 'ノース',
    'EAST': 'イースト',
    'WEST': 'ウエスト',
    'ANNEX': 'アネックス',
    'EXCELLENT': 'エクセレント',
    'BRILLIANT': 'ブリリアント',
    'DIAMOND': 'ダイヤモンド',
    'RUBY': 'ルビー',
    'SAPPHIRE': 'サファイア',
    'EMERALD': 'エメラルド',
    'CRYSTAL': 'クリスタル',
    'PEARL': 'パール',
    'SUITE': 'スイート',
    'SWEET': 'スイート',
    'HOME': 'ホーム',
    'HOMES': 'ホームズ',
    'LIFE': 'ライフ',
    'LIVE': 'ライブ',
    'LIVING': 'リビング',
    'RISE': 'ライズ',
    'VIEW': 'ビュー',
    'VISTA': 'ビスタ',
    'SQUARE': 'スクエア',
    'CUBE': 'キューブ',
    'PLACE': 'プレイス',
    'GATE': 'ゲート',
    'STATION': 'ステーション',
    'PORT': 'ポート',
    'HARBOR': 'ハーバー',
    'BRIDGE': 'ブリッジ',
    'CROSS': 'クロス',
    'CROWN': 'クラウン',
    'KING': 'キング',
    'QUEEN': 'クイーン',
    'PRINCE': 'プリンス',
    'PRINCESS': 'プリンセス',
    'DUKE': 'デューク',
    'NOBLE': 'ノーブル',
    'ELITE': 'エリート',
    'PRESTIGE': 'プレステージ',
    'LUXURY': 'ラグジュアリー',
    'DELUXE': 'デラックス',
    'SUPREME': 'シュプリーム',
    'SUPERIOR': 'スーペリア',
    'PREMIUM': 'プレミアム',
    'SELECT': 'セレクト',
    'SPECIAL': 'スペシャル',
    'UNIQUE': 'ユニーク',
    'NEW': 'ニュー',
    'NEO': 'ネオ',
    'MODERN': 'モダン',
    'FUTURE': 'フューチャー',
    'NEXT': 'ネクスト',
    'ADVANCE': 'アドバンス',
    'PROGRESS': 'プログレス',
    'FORWARD': 'フォワード',
    'UP': 'アップ',
    'TOP': 'トップ',
    'HIGH': 'ハイ',
    'SKY': 'スカイ',
    'CLOUD': 'クラウド',
    'STAR': 'スター',
    'MOON': 'ムーン',
    'SUN': 'サン',
    'LIGHT': 'ライト',
    'BRIGHT': 'ブライト',
    'SHINE': 'シャイン',
    'GLOW': 'グロウ',
    'SPARK': 'スパーク',
    'FLAME': 'フレイム',
    'FIRE': 'ファイア',
    'WATER': 'ウォーター',
    'AQUA': 'アクア',
    'MARINE': 'マリン',
    'BLUE': 'ブルー',
    'GREEN': 'グリーン',
    'RED': 'レッド',
    'WHITE': 'ホワイト',
    'BLACK': 'ブラック',
    'GOLD': 'ゴールド',
    'SILVER': 'シルバー',
    'BRONZE': 'ブロンズ',
    'PLATINUM': 'プラチナ',
    'JEWEL': 'ジュエル',
    'GEM': 'ジェム',
    'STONE': 'ストーン',
    'ROCK': 'ロック',
    'MOUNTAIN': 'マウンテン',
    'VALLEY': 'バレー',
    'FIELD': 'フィールド',
    'MEADOW': 'メドウ',
    'SPRING': 'スプリング',
    'SUMMER': 'サマー',
    'AUTUMN': 'オータム',
    'WINTER': 'ウィンター',
    'SEASON': 'シーズン',
    'TIME': 'タイム',
    'MOMENT': 'モーメント',
    'ETERNAL': 'エターナル',
    'FOREVER': 'フォーエバー',
    'INFINITY': 'インフィニティ',
    'DREAM': 'ドリーム',
    'WISH': 'ウィッシュ',
    'HOPE': 'ホープ',
    'FAITH': 'フェイス',
    'TRUST': 'トラスト',
    'BOND': 'ボンド',
    'LINK': 'リンク',
    'CONNECT': 'コネクト',
    'JOINT': 'ジョイント',
    'TWIN': 'ツイン',
    'TWINS': 'ツインズ',
    'DUO': 'デュオ',
    'TRIO': 'トリオ',
    'QUARTET': 'カルテット',
    'ENSEMBLE': 'アンサンブル',
    'HARMONY': 'ハーモニー',
    'MELODY': 'メロディ',
    'RHYTHM': 'リズム',
    'BEAT': 'ビート',
    'SOUND': 'サウンド',
    'VOICE': 'ボイス',
    'ECHO': 'エコー',
    'WAVE': 'ウェーブ',
    'FLOW': 'フロー',
    'STREAM': 'ストリーム',
    'CURRENT': 'カレント',
    'DRIFT': 'ドリフト',
    'FLOAT': 'フロート',
    'FLY': 'フライ',
    'WING': 'ウィング',
    'WINGS': 'ウィングス',
    'FEATHER': 'フェザー',
    'BIRD': 'バード',
    'EAGLE': 'イーグル',
    'HAWK': 'ホーク',
    'FALCON': 'ファルコン',
    'PHOENIX': 'フェニックス',
    'DRAGON': 'ドラゴン',
    'TIGER': 'タイガー',
    'LION': 'ライオン',
    'BEAR': 'ベア',
    'WOLF': 'ウルフ',
    'FOX': 'フォックス',
    'DEER': 'ディア',
    'HORSE': 'ホース',
    'UNICORN': 'ユニコーン',
    'PEGASUS': 'ペガサス',
    
    # 頻出する略語
    'ST': 'エスティー',
    'GT': 'ジーティー',
    'DX': 'デラックス',
    'EX': 'イーエックス',
    'MX': 'エムエックス',
    'NX': 'エヌエックス',
    'VX': 'ヴイエックス',
    'ZX': 'ゼットエックス',
}


def english_to_katakana(text):
    """英語文字列をカタカナに変換（部分的な変換も対応）
    
    Args:
        text: 変換する文字列
        
    Returns:
        カタカナ変換された文字列、変換できない場合はNone
    """
    if not text:
        return None
        
    result = text
    
    # 辞書の単語を長い順にソート（長い単語を優先的にマッチ）
    sorted_words = sorted(ENGLISH_TO_KATAKANA.items(), key=lambda x: len(x[0]), reverse=True)
    
    # 各英単語をカタカナに置換
    for eng, kata in sorted_words:
        # 大文字小文字を無視してマッチ
        pattern = re.compile(re.escape(eng), re.IGNORECASE)
        result = pattern.sub(kata, result)
    
    # 変換されたかチェック（元のテキストと同じなら変換失敗）
    if result == text:
        return None
    
    # 残った英数字が多すぎる場合は変換失敗とする
    remaining_alpha = re.findall(r'[A-Za-z]{4,}', result)
    if remaining_alpha:
        return None
    
    return result


def has_english_words(text):
    """文字列に英単語が含まれているかチェック
    
    Args:
        text: チェックする文字列
        
    Returns:
        英単語が含まれている場合True
    """
    if not text:
        return False
    
    # 3文字以上の連続したアルファベットがあるかチェック
    return bool(re.search(r'[A-Za-z]{3,}', text))