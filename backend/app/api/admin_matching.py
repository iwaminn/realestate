"""
曖昧な物件マッチングの管理用API
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from ..database import get_db
from ..api.auth import get_admin_user
from ..models_property_matching import AmbiguousPropertyMatch
from ..models import MasterProperty, Building

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-matching"],
    dependencies=[Depends(get_admin_user)]
)


@router.get("/ambiguous-matches")
async def get_ambiguous_matches(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    is_reviewed: Optional[bool] = None,
    confidence_threshold: Optional[float] = Query(None, ge=0, le=1),
    building_id: Optional[int] = None,
    days: int = Query(7, description="過去N日間のデータ"),
    db: Session = Depends(get_db),
):
    """曖昧なマッチング一覧を取得（管理者用）"""
    
    # ベースクエリ
    query = db.query(AmbiguousPropertyMatch)
    
    # フィルタリング
    if is_reviewed is not None:
        query = query.filter(AmbiguousPropertyMatch.is_reviewed == is_reviewed)
    
    if confidence_threshold is not None:
        query = query.filter(AmbiguousPropertyMatch.confidence_score <= confidence_threshold)
    
    if building_id:
        query = query.filter(AmbiguousPropertyMatch.building_id == building_id)
    
    # 日付フィルタ
    since_date = datetime.now() - timedelta(days=days)
    query = query.filter(AmbiguousPropertyMatch.created_at >= since_date)
    
    # ソート（信頼度が低い順）
    query = query.order_by(
        AmbiguousPropertyMatch.confidence_score.asc(),
        AmbiguousPropertyMatch.created_at.desc()
    )
    
    # 総件数を取得
    total = query.count()
    
    # ページネーション
    offset = (page - 1) * per_page
    matches = query.offset(offset).limit(per_page).all()
    
    # 統計情報を集計
    stats = db.query(
        func.count(AmbiguousPropertyMatch.id).label('total_matches'),
        func.count(func.case([(AmbiguousPropertyMatch.is_reviewed == False, 1)])).label('unreviewed'),
        func.count(func.case([(AmbiguousPropertyMatch.confidence_score < 0.5, 1)])).label('low_confidence'),
        func.avg(AmbiguousPropertyMatch.confidence_score).label('avg_confidence')
    ).filter(AmbiguousPropertyMatch.created_at >= since_date).first()
    
    return {
        'matches': [match.to_dict() for match in matches],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page,
        'stats': {
            'total_matches': stats.total_matches or 0,
            'unreviewed': stats.unreviewed or 0,
            'low_confidence': stats.low_confidence or 0,
            'avg_confidence': float(stats.avg_confidence or 0)
        }
    }


@router.get("/ambiguous-matches/{match_id}")
async def get_ambiguous_match_detail(
    match_id: int,
    db: Session = Depends(get_db),
):
    """曖昧なマッチングの詳細を取得"""
    
    match = db.query(AmbiguousPropertyMatch).filter(
        AmbiguousPropertyMatch.id == match_id
    ).first()
    
    if not match:
        raise HTTPException(status_code=404, detail="マッチング記録が見つかりません")
    
    # 候補物件の詳細情報を取得
    candidate_properties = []
    if match.candidate_property_ids:
        for prop_id in match.candidate_property_ids:
            prop = db.query(MasterProperty).get(prop_id)
            if prop:
                candidate_properties.append({
                    'id': prop.id,
                    'room_number': prop.room_number,
                    'floor_number': prop.floor_number,
                    'area': prop.area,
                    'layout': prop.layout,
                    'direction': prop.direction,
                    'is_selected': prop.id == match.selected_property_id
                })
    
    # 建物情報を取得
    building = None
    if match.building_id:
        bldg = db.query(Building).get(match.building_id)
        if bldg:
            building = {
                'id': bldg.id,
                'name': bldg.normalized_name,
                'address': bldg.address
            }
    
    return {
        'id': match.id,
        'source_site': match.source_site,
        'scraping_url': match.scraping_url,
        'scraping_data': match.scraping_data,
        'selected_property_id': match.selected_property_id,
        'selection_reason': match.selection_reason,
        'candidate_properties': candidate_properties,
        'candidate_count': match.candidate_count,
        'building': building,
        'confidence_score': match.confidence_score,
        'is_reviewed': match.is_reviewed,
        'is_correct': match.is_correct,
        'reviewed_by': match.reviewed_by,
        'reviewed_at': match.reviewed_at.isoformat() if match.reviewed_at else None,
        'review_notes': match.review_notes,
        'used_learning': match.used_learning,
        'learning_patterns': match.learning_patterns,
        'created_at': match.created_at.isoformat() if match.created_at else None
    }


@router.post("/ambiguous-matches/{match_id}/review")
async def review_ambiguous_match(
    match_id: int,
    request: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """曖昧なマッチングをレビュー"""
    
    match = db.query(AmbiguousPropertyMatch).filter(
        AmbiguousPropertyMatch.id == match_id
    ).first()
    
    if not match:
        raise HTTPException(status_code=404, detail="マッチング記録が見つかりません")
    
    # レビュー情報を更新
    match.is_reviewed = True
    match.is_correct = request.get('is_correct', False)
    match.reviewed_by = request.get('reviewed_by', 'admin')
    match.reviewed_at = datetime.now()
    match.review_notes = request.get('notes', '')
    
    # 正しくない場合、正しい物件IDが指定されていれば更新
    correct_property_id = request.get('correct_property_id')
    if not match.is_correct and correct_property_id:
        # 掲載情報を正しい物件に紐付け直す処理をここに追加
        # （実装は省略）
        pass
    
    db.commit()
    
    return {
        'success': True,
        'message': 'レビューを保存しました',
        'is_correct': match.is_correct
    }


@router.get("/ambiguous-matches/summary")
async def get_ambiguous_matches_summary(
    days: int = Query(30, description="過去N日間のデータ"),
    db: Session = Depends(get_db),
):
    """曖昧なマッチングのサマリー"""
    
    since_date = datetime.now() - timedelta(days=days)
    
    # 建物別の集計
    building_stats = db.query(
        Building.id,
        Building.normalized_name,
        func.count(AmbiguousPropertyMatch.id).label('match_count'),
        func.avg(AmbiguousPropertyMatch.confidence_score).label('avg_confidence')
    ).join(
        AmbiguousPropertyMatch,
        Building.id == AmbiguousPropertyMatch.building_id
    ).filter(
        AmbiguousPropertyMatch.created_at >= since_date
    ).group_by(
        Building.id,
        Building.normalized_name
    ).order_by(
        func.count(AmbiguousPropertyMatch.id).desc()
    ).limit(10).all()
    
    # 信頼度別の分布
    confidence_distribution = db.query(
        func.case([
            (AmbiguousPropertyMatch.confidence_score >= 0.8, '高（80%以上）'),
            (AmbiguousPropertyMatch.confidence_score >= 0.5, '中（50-80%）'),
            (AmbiguousPropertyMatch.confidence_score < 0.5, '低（50%未満）')
        ]).label('confidence_level'),
        func.count(AmbiguousPropertyMatch.id).label('count')
    ).filter(
        AmbiguousPropertyMatch.created_at >= since_date
    ).group_by('confidence_level').all()
    
    return {
        'period_days': days,
        'building_stats': [
            {
                'building_id': stat.id,
                'building_name': stat.normalized_name,
                'match_count': stat.match_count,
                'avg_confidence': float(stat.avg_confidence or 0)
            }
            for stat in building_stats
        ],
        'confidence_distribution': [
            {
                'level': dist.confidence_level,
                'count': dist.count
            }
            for dist in confidence_distribution
        ]
    }