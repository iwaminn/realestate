#!/usr/bin/env python3
"""英語名の建物にカタカナエイリアスを生成して追加するスクリプト"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from app.database import SessionLocal
from app.models import Building, BuildingAlias

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
    
    # 地名・ブランド名
    'TOKYO': '東京',
    'YOKOHAMA': '横浜',
    'OSAKA': '大阪',
    'KYOTO': '京都',
    'KOBE': '神戸',
    'NAGOYA': '名古屋',
    'SAPPORO': '札幌',
    'FUKUOKA': '福岡',
    'SENDAI': '仙台',
    'HIROSHIMA': '広島',
    
    # 頻出する略語
    'ST': 'エスティー',
    'GT': 'ジーティー',
    'DX': 'デラックス',
    'EX': 'イーエックス',
    'MX': 'エムエックス',
    'NX': 'エヌエックス',
    'VX': 'ヴイエックス',
    'ZX': 'ゼットエックス',
    
    # 記号・符号
    '&': 'アンド',
    '+': 'プラス',
    '-': '',  # ハイフンは無視
    '_': '',  # アンダースコアは無視
    '.': '',  # ピリオドは無視
    ',': '',  # カンマは無視
    "'": '',  # アポストロフィは無視
    '"': '',  # クォートは無視
}


def english_to_katakana(text):
    """英語文字列をカタカナに変換（部分的な変換も対応）"""
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


def generate_katakana_aliases():
    """英語名の建物にカタカナエイリアスを生成"""
    
    session = SessionLocal()
    
    try:
        # 英語名を含む建物を取得（アルファベットが3文字以上連続している建物）
        buildings = session.query(Building).filter(
            Building.normalized_name.op('~')('[A-Z]{3,}')
        ).all()
        
        print(f"{len(buildings)}件の英語名建物を処理します...")
        
        added_count = 0
        skipped_count = 0
        
        for building in buildings:
            # カタカナ変換
            katakana_name = english_to_katakana(building.normalized_name)
            
            if not katakana_name:
                skipped_count += 1
                print(f"× {building.normalized_name} → 変換できませんでした")
                continue
            
            # 既存のエイリアスをチェック
            existing_alias = session.query(BuildingAlias).filter(
                BuildingAlias.building_id == building.id,
                BuildingAlias.alias_name == katakana_name
            ).first()
            
            if existing_alias:
                print(f"- {building.normalized_name} → {katakana_name} (既存)")
                continue
            
            # エイリアスを追加
            alias = BuildingAlias(
                building_id=building.id,
                alias_name=katakana_name,
                source='KATAKANA_CONVERSION'
            )
            session.add(alias)
            added_count += 1
            print(f"✓ {building.normalized_name} → {katakana_name}")
        
        # 変更を保存
        session.commit()
        
        print(f"\n完了:")
        print(f"  追加: {added_count}件")
        print(f"  スキップ: {skipped_count}件")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    generate_katakana_aliases()