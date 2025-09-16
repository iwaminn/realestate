"""
データバリデーターコンポーネント

データの検証と正規化を担当
- 必須フィールドチェック
- データ型検証
- 値の正規化
- ビジネスルール検証
"""
import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime


class DataValidatorComponent:
    """データ検証を担当するコンポーネント"""
    
    # 必須フィールド定義
    REQUIRED_FIELDS = {
        'property': [
            'building_name',
            'price', 
            'area',
            'layout'
        ],
        'building': [
            'normalized_name',
            'address'
        ]
    }
    
    # フィールドの妥当性範囲
    VALIDATION_RULES = {
        'price': {'min': 100, 'max': 500000},  # 100万円〜50億円
        'area': {'min': 10, 'max': 1000},      # 10㎡〜1000㎡
        'floor_number': {'min': -5, 'max': 100},  # 地下5階〜100階
        'total_floors': {'min': 1, 'max': 100},   # 1階建〜100階建
        'built_year': {'min': 1900, 'max': datetime.now().year + 5},
        'management_fee': {'min': 0, 'max': 200000},  # 0円〜20万円
        'repair_fund': {'min': 0, 'max': 100000},     # 0円〜10万円
    }
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初期化
        
        Args:
            logger: ロガーインスタンス
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def validate_property_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        物件データを検証
        
        Args:
            data: 物件データ
            
        Returns:
            (検証成功フラグ, エラーメッセージリスト) のタプル
        """
        errors = []
        
        # 必須フィールドチェック
        for field in self.REQUIRED_FIELDS['property']:
            if not data.get(field):
                errors.append(f"必須フィールド '{field}' が欠落しています")
        
        # 数値範囲チェック
        for field, rules in self.VALIDATION_RULES.items():
            if field in data and data[field] is not None:
                value = data[field]
                if isinstance(value, (int, float)):
                    if value < rules['min'] or value > rules['max']:
                        errors.append(
                            f"'{field}' の値が範囲外です: {value} "
                            f"(許容範囲: {rules['min']} - {rules['max']})"
                        )
        
        # 論理チェック
        if data.get('floor_number') and data.get('total_floors'):
            if data['floor_number'] > data['total_floors']:
                errors.append(
                    f"階数の矛盾: {data['floor_number']}階 / {data['total_floors']}階建"
                )
        
        return len(errors) == 0, errors
    
    def normalize_layout(self, layout: Optional[str]) -> Optional[str]:
        """
        間取りを正規化
        
        Args:
            layout: 間取りテキスト
            
        Returns:
            正規化された間取り
        """
        if not layout:
            return None
        
        # 全角を半角に変換
        import unicodedata
        layout = unicodedata.normalize('NFKC', layout)
        
        # 大文字に統一
        layout = layout.upper()
        
        # よくあるパターンの正規化
        patterns = {
            r'(\d+)LDK\+S': r'\1SLDK',  # 1LDK+S → 1SLDK
            r'(\d+)K\+L\+DK': r'\1LDK',  # 1K+L+DK → 1LDK
            r'(\d+)DK\+L': r'\1LDK',     # 1DK+L → 1LDK
            r'ワンルーム': '1R',
            r'STUDIO': '1R',
        }
        
        for pattern, replacement in patterns.items():
            layout = re.sub(pattern, replacement, layout)
        
        # 余分な記号を削除
        layout = re.sub(r'[^\dA-Z]', '', layout)
        
        return layout
    
    def normalize_direction(self, direction: Optional[str]) -> Optional[str]:
        """
        方角を正規化
        
        Args:
            direction: 方角テキスト
            
        Returns:
            正規化された方角
        """
        if not direction:
            return None
        
        # 全角を半角に変換
        import unicodedata
        direction = unicodedata.normalize('NFKC', direction)
        
        # マッピング
        direction_map = {
            '北': 'N',
            '南': 'S', 
            '東': 'E',
            '西': 'W',
            '北東': 'NE',
            '北西': 'NW',
            '南東': 'SE',
            '南西': 'SW',
            'NORTH': 'N',
            'SOUTH': 'S',
            'EAST': 'E',
            'WEST': 'W',
        }
        
        # 完全一致
        for key, value in direction_map.items():
            if key in direction:
                # 複合方角の処理
                if '北' in direction and '東' in direction:
                    return 'NE'
                elif '北' in direction and '西' in direction:
                    return 'NW'
                elif '南' in direction and '東' in direction:
                    return 'SE'
                elif '南' in direction and '西' in direction:
                    return 'SW'
                else:
                    return value
        
        # 英字の場合はそのまま大文字化
        direction = direction.upper()
        if direction in ['N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW']:
            return direction
        
        return None
    
    def validate_url(self, url: Optional[str]) -> bool:
        """
        URLの妥当性を検証
        
        Args:
            url: URL文字列
            
        Returns:
            妥当なURLかどうか
        """
        if not url:
            return False
        
        # 基本的なURL形式チェック
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        
        return bool(url_pattern.match(url))
    
    def sanitize_string(self, text: Optional[str], max_length: int = 500) -> Optional[str]:
        """
        文字列をサニタイズ
        
        Args:
            text: 入力テキスト
            max_length: 最大文字数
            
        Returns:
            サニタイズされたテキスト
        """
        if not text:
            return None
        
        # 制御文字を削除
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        
        # HTMLタグを削除（念のため）
        text = re.sub(r'<[^>]+>', '', text)
        
        # 前後の空白を削除
        text = text.strip()
        
        # 最大文字数でカット
        if len(text) > max_length:
            text = text[:max_length]
        
        return text if text else None
    
    def validate_building_name(self, name: Optional[str]) -> Tuple[bool, Optional[str]]:
        """
        建物名の妥当性を検証
        
        Args:
            name: 建物名
            
        Returns:
            (妥当フラグ, エラーメッセージ) のタプル
        """
        if not name:
            return False, "建物名が空です"
        
        # 最小文字数チェック
        if len(name) < 2:
            return False, "建物名が短すぎます"
        
        # 最大文字数チェック
        if len(name) > 200:
            return False, "建物名が長すぎます"
        
        # 不正な文字チェック
        invalid_patterns = [
            r'^\d+$',  # 数字のみ
            r'^[ぁ-ん]+$',  # ひらがなのみ
            r'test|テスト|dummy|ダミー',  # テストデータ
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, name, re.IGNORECASE):
                return False, f"建物名が不正です: {name}"
        
        return True, None
    
    def normalize_address(self, address: Optional[str]) -> Optional[str]:
        """
        住所を正規化
        
        Args:
            address: 住所テキスト
            
        Returns:
            正規化された住所
        """
        if not address:
            return None
        
        # 全角数字を半角に変換
        import unicodedata
        address = unicodedata.normalize('NFKC', address)
        
        # 都道府県の正規化
        address = re.sub(r'東京都', '東京都', address)
        
        # 番地の正規化（1-2-3 形式に統一）
        address = re.sub(r'(\d+)丁目(\d+)番(\d+)号', r'\1-\2-\3', address)
        address = re.sub(r'(\d+)番地?の?(\d+)', r'\1-\2', address)
        
        # 余分なスペースを削除
        address = re.sub(r'\s+', '', address)
        
        return address
    
    def calculate_property_hash(self, data: Dict[str, Any]) -> Optional[str]:
        """
        物件ハッシュを計算
        
        Args:
            data: 物件データ
            
        Returns:
            物件ハッシュ値
        """
        # ハッシュ計算に必要なフィールド
        required_fields = [
            'building_id',
            'floor_number', 
            'area',
            'layout',
            'direction'
        ]
        
        # 必須フィールドチェック
        for field in required_fields[:4]:  # directionは任意
            if not data.get(field):
                self.logger.warning(f"物件ハッシュ計算失敗: '{field}' が欠落")
                return None
        
        # ハッシュ値を生成
        import hashlib
        
        # 正規化
        layout = self.normalize_layout(str(data['layout']))
        direction = self.normalize_direction(data.get('direction', ''))
        
        # ハッシュ用文字列を作成（部屋番号は含めない）
        hash_str = f"{data['building_id']}_{data['floor_number']}_{data['area']:.1f}_{layout}_{direction}"
        
        # SHA256でハッシュ化
        return hashlib.sha256(hash_str.encode()).hexdigest()[:16]