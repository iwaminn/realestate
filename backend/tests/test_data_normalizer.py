"""
データ正規化フレームワークのテスト
"""

import pytest
from datetime import datetime
from backend.app.scrapers.data_normalizer import (
    DataNormalizer,
    extract_price,
    extract_area,
    extract_floor_number,
    extract_total_floors,
    normalize_layout,
    normalize_direction,
    normalize_structure,
    format_station_info,
    parse_date,
    extract_monthly_fee,
    extract_built_year,
    normalize_integer
)


class TestDataNormalizer:
    """DataNormalizerクラスのテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.normalizer = DataNormalizer()


class TestPriceExtraction:
    """価格抽出のテスト"""
    
    def test_extract_price_basic(self):
        """基本的な価格抽出"""
        assert extract_price("5,480万円") == 5480
        assert extract_price("3980万円") == 3980
        assert extract_price("980万円") == 980
    
    def test_extract_price_oku(self):
        """億単位の価格抽出"""
        assert extract_price("1億2000万円") == 12000
        assert extract_price("2億円") == 20000
        assert extract_price("1億円") == 10000
        assert extract_price("5億8000万円") == 58000
    
    def test_extract_price_with_text(self):
        """テキスト付きの価格抽出"""
        assert extract_price("販売価格：5,480万円（税込）") == 5480
        assert extract_price("価格 3,980万円") == 3980
        assert extract_price("物件価格2億3000万円") == 23000
    
    def test_extract_price_invalid(self):
        """無効な入力"""
        assert extract_price("") is None
        assert extract_price("価格未定") is None
        assert extract_price("要相談") is None


class TestAreaExtraction:
    """面積抽出のテスト"""
    
    def test_extract_area_basic(self):
        """基本的な面積抽出"""
        assert extract_area("81.3㎡") == 81.3
        assert extract_area("70㎡") == 70.0
        assert extract_area("125.5㎡") == 125.5
    
    def test_extract_area_variants(self):
        """様々な表記での面積抽出"""
        assert extract_area("85.5m2") == 85.5
        assert extract_area("70.2m²") == 70.2
        assert extract_area("80平米") == 80.0
        assert extract_area("75.3平方メートル") == 75.3
    
    def test_extract_area_with_text(self):
        """テキスト付きの面積抽出"""
        assert extract_area("専有面積：70.2㎡") == 70.2
        assert extract_area("バルコニー面積 12.5㎡") == 12.5
        assert extract_area("面積(81.3㎡)") == 81.3
    
    def test_extract_area_invalid(self):
        """無効な入力"""
        assert extract_area("") is None
        assert extract_area("面積不明") is None


class TestFloorExtraction:
    """階数抽出のテスト"""
    
    def test_extract_floor_number_basic(self):
        """基本的な階数抽出"""
        assert extract_floor_number("4階") == 4
        assert extract_floor_number("12階") == 12
        assert extract_floor_number("1階") == 1
    
    def test_extract_floor_number_compound(self):
        """複合的な階数抽出"""
        assert extract_floor_number("4階/SRC9階建") == 4
        assert extract_floor_number("12階/20階建") == 12
    
    def test_extract_floor_number_with_text(self):
        """テキスト付きの階数抽出"""
        assert extract_floor_number("所在階：12階") == 12
        assert extract_floor_number("12階部分") == 12
    
    def test_extract_total_floors(self):
        """総階数と地下階数の抽出"""
        assert extract_total_floors("地上12階建") == (12, 0)
        assert extract_total_floors("RC21階地下1階建") == (21, 1)
        assert extract_total_floors("SRC42階建") == (42, 0)
        assert extract_total_floors("地上30階地下2階建") == (30, 2)
        assert extract_total_floors("15階建") == (15, 0)


class TestLayoutNormalization:
    """間取り正規化のテスト"""
    
    def test_normalize_layout_basic(self):
        """基本的な間取り正規化"""
        assert normalize_layout("2LDK") == "2LDK"
        assert normalize_layout("3LDK") == "3LDK"
        assert normalize_layout("1K") == "1K"
    
    def test_normalize_layout_fullwidth(self):
        """全角文字の正規化"""
        assert normalize_layout("２ＬＤＫ") == "2LDK"
        assert normalize_layout("３ＬＤＫ") == "3LDK"
        assert normalize_layout("１Ｋ") == "1K"
    
    def test_normalize_layout_special(self):
        """特殊な間取り"""
        assert normalize_layout("ワンルーム") == "1R"
        assert normalize_layout("1ルーム") == "1R"
        assert normalize_layout("スタジオ") == "STUDIO"
        assert normalize_layout("STUDIO") == "STUDIO"
    
    def test_normalize_layout_with_s(self):
        """S付き間取り"""
        assert normalize_layout("2SLDK") == "2SLDK"
        assert normalize_layout("1SK") == "1SK"
        assert normalize_layout("3SLDK") == "3SLDK"
    
    def test_normalize_layout_r_type(self):
        """Rタイプの間取り"""
        assert normalize_layout("1R") == "1R"
        assert normalize_layout("2R") == "2R"


class TestDirectionNormalization:
    """方角正規化のテスト"""
    
    def test_normalize_direction_basic(self):
        """基本的な方角正規化"""
        assert normalize_direction("南") == "南"
        assert normalize_direction("北") == "北"
        assert normalize_direction("東") == "東"
        assert normalize_direction("西") == "西"
    
    def test_normalize_direction_compound(self):
        """複合方角の正規化"""
        assert normalize_direction("南東") == "南東"
        assert normalize_direction("南西") == "南西"
        assert normalize_direction("北東") == "北東"
        assert normalize_direction("北西") == "北西"
    
    def test_normalize_direction_english(self):
        """英語表記の正規化"""
        assert normalize_direction("S") == "南"
        assert normalize_direction("N") == "北"
        assert normalize_direction("SE") == "南東"
        assert normalize_direction("SW") == "南西"
    
    def test_normalize_direction_with_text(self):
        """テキスト付きの方角正規化"""
        assert normalize_direction("南向き") == "南"
        assert normalize_direction("バルコニー：南東向き") == "南東"


class TestStructureNormalization:
    """構造正規化のテスト"""
    
    def test_normalize_structure_basic(self):
        """基本的な構造正規化"""
        assert normalize_structure("RC造") == "RC"
        assert normalize_structure("SRC造") == "SRC"
        assert normalize_structure("S造") == "S造"
        assert normalize_structure("木造") == "木造"
    
    def test_normalize_structure_full(self):
        """正式名称の正規化"""
        assert normalize_structure("鉄筋コンクリート造") == "RC"
        assert normalize_structure("鉄骨鉄筋コンクリート造") == "SRC"
        assert normalize_structure("鉄骨造") == "S造"


class TestStationInfoFormatting:
    """駅情報フォーマットのテスト"""
    
    def test_format_station_info_basic(self):
        """基本的な駅情報フォーマット"""
        result = format_station_info("東京メトロ銀座線銀座駅徒歩5分")
        assert "東京メトロ銀座線銀座駅徒歩5分" in result
    
    def test_format_station_info_multiple(self):
        """複数駅の情報フォーマット"""
        input_text = "東京メトロ銀座線銀座駅徒歩5分都営浅草線東銀座駅徒歩3分"
        result = format_station_info(input_text)
        assert "\n" in result
    
    def test_format_station_info_with_comma(self):
        """カンマ区切りの駅情報"""
        result = format_station_info("銀座駅徒歩5分、東銀座駅徒歩3分")
        assert result == "銀座駅徒歩5分\n東銀座駅徒歩3分"


class TestDateParsing:
    """日付解析のテスト"""
    
    def test_parse_date_japanese(self):
        """日本語形式の日付解析"""
        result = parse_date("2024年1月15日")
        assert result == datetime(2024, 1, 15)
        
        result = parse_date("2023年12月1日")
        assert result == datetime(2023, 12, 1)
    
    def test_parse_date_slash(self):
        """スラッシュ区切りの日付解析"""
        result = parse_date("2024/01/15")
        assert result == datetime(2024, 1, 15)
        
        result = parse_date("2024/1/5")
        assert result == datetime(2024, 1, 5)
    
    def test_parse_date_hyphen(self):
        """ハイフン区切りの日付解析"""
        result = parse_date("2024-01-15")
        assert result == datetime(2024, 1, 15)
    
    def test_parse_date_invalid(self):
        """無効な日付"""
        assert parse_date("") is None
        assert parse_date("日付なし") is None


class TestMonthlyFeeExtraction:
    """月額費用抽出のテスト"""
    
    def test_extract_monthly_fee_basic(self):
        """基本的な月額費用抽出"""
        assert extract_monthly_fee("12,000円") == 12000
        assert extract_monthly_fee("8,500円") == 8500
        assert extract_monthly_fee("15000円") == 15000
    
    def test_extract_monthly_fee_with_text(self):
        """テキスト付きの月額費用抽出"""
        assert extract_monthly_fee("管理費：8,500円/月") == 8500
        assert extract_monthly_fee("修繕積立金 12,000円") == 12000


class TestBuiltYearExtraction:
    """築年抽出のテスト"""
    
    def test_extract_built_year_basic(self):
        """基本的な築年抽出"""
        assert extract_built_year("2020年築") == 2020
        assert extract_built_year("1995年築") == 1995
    
    def test_extract_built_year_with_month(self):
        """月付きの築年抽出"""
        assert extract_built_year("築年月：2015年3月") == 2015
        assert extract_built_year("2018年12月築") == 2018


class TestIntegerNormalization:
    """整数正規化のテスト"""
    
    def test_normalize_integer_basic(self):
        """基本的な整数正規化"""
        assert normalize_integer(123) == 123
        assert normalize_integer("456") == 456
        assert normalize_integer("789円") == 789
    
    def test_normalize_integer_none(self):
        """None値の処理"""
        assert normalize_integer(None) is None
        assert normalize_integer("") is None


class TestDataValidation:
    """データ検証のテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.normalizer = DataNormalizer()
    
    def test_validate_price(self):
        """価格検証"""
        assert self.normalizer.validate_price(5000) is True
        assert self.normalizer.validate_price(50) is False
        assert self.normalizer.validate_price(200000) is False
        assert self.normalizer.validate_price(None) is False
    
    def test_validate_area(self):
        """面積検証"""
        assert self.normalizer.validate_area(70.5) is True
        assert self.normalizer.validate_area(5.0) is False
        assert self.normalizer.validate_area(600.0) is False
        assert self.normalizer.validate_area(None) is False
    
    def test_validate_floor_number(self):
        """階数検証"""
        assert self.normalizer.validate_floor_number(5, 10) is True
        assert self.normalizer.validate_floor_number(12, 10) is False
        assert self.normalizer.validate_floor_number(0) is False
        assert self.normalizer.validate_floor_number(None) is False
    
    def test_validate_built_year(self):
        """築年検証"""
        current_year = datetime.now().year
        assert self.normalizer.validate_built_year(2020) is True
        assert self.normalizer.validate_built_year(1899) is False
        assert self.normalizer.validate_built_year(current_year + 1) is False
        assert self.normalizer.validate_built_year(None) is False


class TestComprehensiveNormalization:
    """総合的なデータ正規化のテスト"""
    
    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.normalizer = DataNormalizer()
    
    def test_normalize_property_data(self):
        """物件データの総合的な正規化"""
        raw_data = {
            'price': '5,480万円',
            'management_fee': '管理費：12,000円/月',
            'repair_fund': '15,000円',
            'area': '専有面積：81.3㎡',
            'balcony_area': 'バルコニー 12.5m2',
            'floor_number': '4階',
            'total_floors': 'RC造14階建',
            'built_year': '2020年築',
            'layout': '３ＬＤＫ',
            'direction': '南東向き',
            'structure': 'RC造',
            'station_info': '銀座駅徒歩5分、東銀座駅徒歩3分',
            'published_at': '2024年1月15日',
            'other_field': 'そのまま保持'
        }
        
        result = self.normalizer.normalize_property_data(raw_data)
        
        assert result['price'] == 5480
        assert result['management_fee'] == 12000
        assert result['repair_fund'] == 15000
        assert result['area'] == 81.3
        assert result['balcony_area'] == 12.5
        assert result['floor_number'] == 4
        assert result['total_floors'] == 14
        assert result['basement_floors'] == 0
        assert result['built_year'] == 2020
        assert result['layout'] == '3LDK'
        assert result['direction'] == '南東'
        assert result['structure'] == 'RC'
        assert '銀座駅徒歩5分' in result['station_info']
        assert result['published_at'] == datetime(2024, 1, 15)
        assert result['other_field'] == 'そのまま保持'
    
    def test_get_validation_errors(self):
        """検証エラーの取得"""
        # 正常なデータ
        valid_data = {
            'price': 5000,
            'area': 70.5,
            'floor_number': 5,
            'total_floors': 10,
            'built_year': 2020
        }
        errors = self.normalizer.get_validation_errors(valid_data)
        assert len(errors) == 0
        
        # エラーを含むデータ
        invalid_data = {
            'price': 50,  # 安すぎる
            'area': 5.0,  # 狭すぎる
            'floor_number': 12,
            'total_floors': 10,  # 階数が総階数より大きい
            'built_year': 1850  # 古すぎる
        }
        errors = self.normalizer.get_validation_errors(invalid_data)
        assert len(errors) == 4
        assert any('価格' in error for error in errors)
        assert any('専有面積' in error for error in errors)
        assert any('階数' in error for error in errors)
        assert any('築年' in error for error in errors)