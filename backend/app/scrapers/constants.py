"""
スクレイピング対象サイトの定義
"""
from enum import Enum


class SourceSite(str, Enum):
    """スクレイピング対象サイト"""
    SUUMO = "suumo"
    HOMES = "homes"
    NOMU = "nomu"
    REHOUSE = "rehouse"
    LIVABLE = "livable"
    TEST = "test"
    
    def __str__(self) -> str:
        """文字列表現を値で返す（SQLAlchemyのため）"""
        return self.value
    
    @property
    def display_name(self) -> str:
        """表示名を取得"""
        names = {
            self.SUUMO: "SUUMO",
            self.HOMES: "LIFULL HOME'S",
            self.NOMU: "ノムコム",
            self.REHOUSE: "三井のリハウス",
            self.LIVABLE: "東急リバブル",
            self.TEST: "テスト"
        }
        return names.get(self, self.value)
    
    @property
    def base_url(self) -> str:
        """ベースURLを取得"""
        urls = {
            self.SUUMO: "https://suumo.jp",
            self.HOMES: "https://www.homes.co.jp",
            self.NOMU: "https://www.nomu.com",
            self.REHOUSE: "https://www.rehouse.co.jp",
            self.LIVABLE: "https://www.livable.co.jp",
            self.TEST: "http://localhost"
        }
        return urls.get(self, "")
    
    @classmethod
    def from_string(cls, value: str) -> "SourceSite":
        """文字列からEnumに変換（大文字小文字を無視）"""
        value_lower = value.lower()
        for site in cls:
            if site.value == value_lower:
                return site
        raise ValueError(f"Unknown source site: {value}")