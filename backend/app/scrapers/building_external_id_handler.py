"""
BuildingExternalIdの安全な処理を提供するヘルパーモジュール
"""
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging

from ..models import BuildingExternalId


class BuildingExternalIdHandler:
    """BuildingExternalIdの安全な処理を行うハンドラー"""
    
    def __init__(self, session: Session, logger: Optional[logging.Logger] = None):
        self.session = session
        self.logger = logger or logging.getLogger(__name__)
    
    def add_external_id(self, building_id: int, source_site: str, external_id: str) -> bool:
        """BuildingExternalIdを安全に追加
        
        Args:
            building_id: 建物ID
            source_site: ソースサイト
            external_id: 外部ID
            
        Returns:
            bool: 追加成功（既存で同じ建物に紐付いている場合も含む）ならTrue
        """
        try:
            # まず既存のレコードをチェック（source_site + external_idの組み合わせ）
            existing = self.session.query(BuildingExternalId).filter(
                BuildingExternalId.source_site == source_site,
                BuildingExternalId.external_id == external_id
            ).first()
            
            if existing:
                if existing.building_id != building_id:
                    self.logger.warning(
                        f"外部ID {external_id} は既に建物ID {existing.building_id} に紐付いています"
                    )
                    return False
                else:
                    self.logger.debug(
                        f"外部ID {external_id} は既に同じ建物に紐付いています"
                    )
                    return True
            
            # 新規追加
            new_external = BuildingExternalId(
                building_id=building_id,
                source_site=source_site,
                external_id=external_id
            )
            self.session.add(new_external)
            self.session.flush()
            self.logger.info(
                f"外部ID {external_id} を建物ID {building_id} に追加しました"
            )
            return True
            
        except IntegrityError as e:
            # ユニーク制約違反（競合状態）
            self.session.rollback()
            self.logger.warning(f"ユニーク制約違反（競合状態の可能性）: {str(e)[:100]}")
            
            # 再度チェック
            try:
                existing = self.session.query(BuildingExternalId).filter(
                    BuildingExternalId.source_site == source_site,
                    BuildingExternalId.external_id == external_id
                ).first()
                
                if existing:
                    self.logger.info(
                        f"競合状態: 外部ID {external_id} は建物ID {existing.building_id} に追加済み"
                    )
                    return existing.building_id == building_id
            except Exception as check_e:
                self.logger.error(f"再チェック時のエラー: {check_e}")
            
            return False
            
        except Exception as e:
            self.logger.error(f"予期しないエラー: {type(e).__name__} - {str(e)[:100]}")
            self.session.rollback()
            return False
    
    def get_existing_external_id(self, source_site: str, external_id: str) -> Optional[BuildingExternalId]:
        """既存の外部IDを取得（エラーハンドリング付き）
        
        Args:
            source_site: ソースサイト
            external_id: 外部ID
            
        Returns:
            BuildingExternalId: 既存のレコード、またはNone
        """
        try:
            return self.session.query(BuildingExternalId).filter(
                BuildingExternalId.source_site == source_site,
                BuildingExternalId.external_id == external_id
            ).first()
        except Exception as e:
            if "current transaction is aborted" in str(e):
                self.logger.warning("トランザクションエラーのため外部IDチェックをスキップ")
                self.session.rollback()
            else:
                self.logger.error(f"外部ID取得エラー: {e}")
            return None