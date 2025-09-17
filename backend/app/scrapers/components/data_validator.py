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
        
        # 間取りの妥当性チェック
        if data.get('layout'):
            layout = data['layout']
            # 不正な間取りパターンをチェック
            import re
            # 間取りに数字のIDが含まれていないか（例: "2LDK133553383"）
            if re.search(r'[A-Z]\d{5,}', layout):
                errors.append(
                    f"間取りに不正な値が含まれています: {layout}"
                )
            # 基本的な間取りパターンチェック（1-9の数字で始まり、R/K/DK/LDK/SLDKで終わる）
            elif not re.match(r'^[1-9]\d*[RSLDK]+(?:\+[SLDK]+)?$|^STUDIO$|^1R$', layout):
                errors.append(
                    f"間取りの形式が不正です: {layout}"
                )
            # 部屋数が異常に多くないか
            elif re.match(r'^\d+', layout):
                room_count = int(re.match(r'^(\d+)', layout).group(1))
                if room_count > 20:  # 20部屋以上は異常とみなす
                    errors.append(
                        f"間取りの部屋数が異常です: {layout}"
                    )
        
        # 論理チェック
        if data.get('floor_number') and data.get('total_floors'):
            if data['floor_number'] > data['total_floors']:
                errors.append(
                    f"階数の矛盾: {data['floor_number']}階 / {data['total_floors']}階建"
                )
        
        return len(errors) == 0, errors
    

    
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
    

    
