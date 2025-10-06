import React, { useState, useEffect, useMemo } from 'react';
import { 
  Container, 
  Typography, 
  Card, 
  CardContent, 
  Grid, 
  Box, 
  Alert,
  CircularProgress,
  Chip,
  Button,
  ToggleButtonGroup,
  ToggleButton,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider,
  Stack,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Snackbar,
  IconButton
} from '@mui/material';
import { 
  BookmarkBorder, 
  Bookmark as BookmarkIcon, 
  Login as LoginIcon,
  ViewList,
  LocationOn,
  Apartment,
  ExpandMore,
  Close as CloseIcon
} from '@mui/icons-material';
import { BookmarkService } from '../services/bookmarkService';
import { Bookmark } from '../types/property';
import { BookmarkButton } from '../components/BookmarkButton';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useUserAuth } from '../contexts/UserAuthContext';
import { LoginModal } from '../components/LoginModal';

export const BookmarksPage: React.FC = () => {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [groupedData, setGroupedData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { isAuthenticated, isLoading: authLoading } = useUserAuth();
  
  // URLパラメータから表示モードと並び順を取得
  const viewMode = (searchParams.get('view') as 'all' | 'ward' | 'building') || 'all';
  const sortBy = (searchParams.get('sort') as 'bookmark_date_desc' | 'bookmark_date_asc' | 'updated_at_desc' | 'updated_at_asc' | 'price_asc' | 'price_desc' | 'area_asc' | 'area_desc' | 'built_year_asc' | 'built_year_desc' | 'tsubo_price_asc' | 'tsubo_price_desc') || 'bookmark_date_desc';

  // アコーディオンの展開状態を管理（エリア別・建物別の場合のみ）
  const [expandedAccordions, setExpandedAccordions] = useState<Set<string>>(new Set());
  const [hasInteracted, setHasInteracted] = useState(false);

  // Undo機能用のstate
  const [undoSnackbarOpen, setUndoSnackbarOpen] = useState(false);
  const [deletedBookmark, setDeletedBookmark] = useState<{ propertyId: number; propertyName: string } | null>(null);

  // viewModeが変更されたら、すべて展開した状態に初期化
  useEffect(() => {
    if (viewMode !== 'all' && groupedData?.grouped_bookmarks) {
      const allKeys = Object.keys(groupedData.grouped_bookmarks);
      setExpandedAccordions(new Set(allKeys));
      setHasInteracted(false); // 初回表示状態にリセット
    }
  }, [viewMode, groupedData]);

  useEffect(() => {
    if (!authLoading) {
      if (isAuthenticated) {
        loadBookmarks();
      } else {
        setLoading(false);
      }
    }
  }, [isAuthenticated, authLoading, viewMode]); // viewModeが変更されたら再読み込み

  const loadBookmarks = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // viewModeに応じてAPIを呼び出し
      if (viewMode === 'all') {
        const data = await BookmarkService.getBookmarks();
        setBookmarks(data);
        setGroupedData(null);
      } else {
        const data = await BookmarkService.getBookmarks(viewMode);
        setGroupedData(data);
        setBookmarks([]);
      }
    } catch (err: any) {
      if (err.message === 'ログインが必要です') {
        setError(null); // エラーメッセージは表示しない
      } else {
        setError('ブックマーク一覧の読み込みに失敗しました');
        console.error('ブックマーク読み込みエラー:', err);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleBookmarkChange = (propertyId: number, isBookmarked: boolean) => {
    if (!isBookmarked) {
      // 削除された物件の情報を保存（undo用）
      const deletedProperty = bookmarks.find(b => b.master_property_id === propertyId)?.master_property;
      const propertyName = deletedProperty?.display_building_name || deletedProperty?.building?.normalized_name || '物件';
      
      setDeletedBookmark({ propertyId, propertyName });
      setUndoSnackbarOpen(true);
      
      // UIから即座に削除
      setBookmarks(prev => prev.filter(bookmark => bookmark.master_property_id !== propertyId));
    }
  };

  // Undo: ブックマークを再追加
  const handleUndo = async () => {
    if (!deletedBookmark) return;
    
    try {
      await BookmarkService.addBookmark(deletedBookmark.propertyId);
      setUndoSnackbarOpen(false);
      setDeletedBookmark(null);
      // ブックマークを再読み込み
      loadBookmarks();
    } catch (error) {
      console.error('ブックマークの復元に失敗:', error);
    }
  };

  // Snackbarを閉じる
  const handleCloseSnackbar = () => {
    setUndoSnackbarOpen(false);
    setDeletedBookmark(null);
  };

  const formatPrice = (price?: number) => {
    if (!price) return '価格情報なし';
    return `${price.toLocaleString()}万円`;
  };

  const formatArea = (area?: number) => {
    if (!area) return '';
    return `${area}㎡`;
  };

  const formatDate = (dateString: string | undefined) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    });
  };

  const calculateDaysFromPublished = (dateString: string | undefined): string => {
    if (!dateString) return '-';
    
    const publishedDate = new Date(dateString);
    const today = new Date();
    
    // 日付のみで比較（時刻を00:00:00にリセット）
    publishedDate.setHours(0, 0, 0, 0);
    today.setHours(0, 0, 0, 0);
    
    const diffTime = Math.abs(today.getTime() - publishedDate.getTime());
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) {
      return '本日';
    } else if (diffDays === 1) {
      return '1日前';
    } else if (diffDays < 7) {
      return `${diffDays}日前`;
    } else if (diffDays < 30) {
      const weeks = Math.floor(diffDays / 7);
      return `${weeks}週間前`;
    } else if (diffDays < 365) {
      const months = Math.floor(diffDays / 30);
      return `${months}ヶ月前`;
    } else {
      const years = Math.floor(diffDays / 365);
      const remainingMonths = Math.floor((diffDays % 365) / 30);
      if (remainingMonths > 0) {
        return `${years}年${remainingMonths}ヶ月前`;
      }
      return `${years}年前`;
    }
  };

  const formatFloor = (floor?: number, totalFloors?: number) => {
    if (!floor) return '';
    const floorStr = `${floor}階`;
    return totalFloors ? `${floorStr}/${totalFloors}階建` : floorStr;
  };

  const handlePropertyClick = (propertyId: number) => {
    navigate(`/properties/${propertyId}`);
  };

  const handleLoginSuccess = () => {
    setShowLoginModal(false);
    loadBookmarks(); // ログイン成功後にブックマークを読み込む
  };

  if (loading || authLoading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  // 未ログイン時の表示
  if (!isAuthenticated) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box display="flex" alignItems="center" mb={4}>
          <BookmarkIcon color="error" sx={{ mr: 2, fontSize: 32 }} />
          <Typography variant="h4" component="h1">
            ブックマーク
          </Typography>
        </Box>

        <Card sx={{ p: 4, textAlign: 'center' }}>
          <LoginIcon sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
          <Typography variant="h6" color="text.secondary" gutterBottom>
            ログインが必要です
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            ブックマーク機能を利用するにはログインしてください
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
            <Button 
              variant="contained" 
              onClick={() => setShowLoginModal(true)}
            >
              ログイン
            </Button>
            <Button 
              variant="outlined" 
              onClick={() => navigate('/properties')}
            >
              物件を見る
            </Button>
          </Box>
        </Card>

        <LoginModal 
          open={showLoginModal}
          onClose={() => setShowLoginModal(false)}
          onSuccess={handleLoginSuccess}
        />
      </Container>
    );
  }

  // ブックマークを並び替え
  const sortBookmarks = (bookmarksToSort: Bookmark[]) => {
    const sorted = [...bookmarksToSort];

    switch (sortBy) {
      case 'bookmark_date_desc':
        return sorted.sort((a, b) => {
          const dateA = new Date(a.created_at).getTime();
          const dateB = new Date(b.created_at).getTime();
          return dateB - dateA; // 新しい順
        });
      case 'bookmark_date_asc':
        return sorted.sort((a, b) => {
          const dateA = new Date(a.created_at).getTime();
          const dateB = new Date(b.created_at).getTime();
          return dateA - dateB; // 古い順
        });
      case 'updated_at_desc':
        return sorted.sort((a, b) => {
          const dateA = new Date(a.master_property?.updated_at || 0).getTime();
          const dateB = new Date(b.master_property?.updated_at || 0).getTime();
          return dateB - dateA;
        });
      case 'updated_at_asc':
        return sorted.sort((a, b) => {
          const dateA = new Date(a.master_property?.updated_at || 0).getTime();
          const dateB = new Date(b.master_property?.updated_at || 0).getTime();
          return dateA - dateB;
        });
      case 'price_asc':
        return sorted.sort((a, b) => {
          const priceA = a.master_property?.current_price || a.master_property?.final_price || 0;
          const priceB = b.master_property?.current_price || b.master_property?.final_price || 0;
          return priceA - priceB;
        });
      case 'price_desc':
        return sorted.sort((a, b) => {
          const priceA = a.master_property?.current_price || a.master_property?.final_price || 0;
          const priceB = b.master_property?.current_price || b.master_property?.final_price || 0;
          return priceB - priceA;
        });
      case 'area_asc':
        return sorted.sort((a, b) => {
          const areaA = a.master_property?.area || 0;
          const areaB = b.master_property?.area || 0;
          return areaA - areaB;
        });
      case 'area_desc':
        return sorted.sort((a, b) => {
          const areaA = a.master_property?.area || 0;
          const areaB = b.master_property?.area || 0;
          return areaB - areaA;
        });
      case 'built_year_desc':
        return sorted.sort((a, b) => {
          const yearA = a.master_property?.building?.built_year || 0;
          const yearB = b.master_property?.building?.built_year || 0;
          return yearB - yearA; // 新しい順（築年数が浅い順）
        });
      case 'built_year_asc':
        return sorted.sort((a, b) => {
          const yearA = a.master_property?.building?.built_year || 0;
          const yearB = b.master_property?.building?.built_year || 0;
          return yearA - yearB; // 古い順（築年数が深い順）
        });
      case 'tsubo_price_asc':
        return sorted.sort((a, b) => {
          const priceA = a.master_property?.current_price || a.master_property?.final_price || 0;
          const priceB = b.master_property?.current_price || b.master_property?.final_price || 0;
          const areaA = a.master_property?.area || 1;
          const areaB = b.master_property?.area || 1;
          const tsuboPriceA = (priceA / areaA) * 3.30579; // 坪単価
          const tsuboPriceB = (priceB / areaB) * 3.30579;
          return tsuboPriceA - tsuboPriceB;
        });
      case 'tsubo_price_desc':
        return sorted.sort((a, b) => {
          const priceA = a.master_property?.current_price || a.master_property?.final_price || 0;
          const priceB = b.master_property?.current_price || b.master_property?.final_price || 0;
          const areaA = a.master_property?.area || 1;
          const areaB = b.master_property?.area || 1;
          const tsuboPriceA = (priceA / areaA) * 3.30579; // 坪単価
          const tsuboPriceB = (priceB / areaB) * 3.30579;
          return tsuboPriceB - tsuboPriceA;
        });
      default:
        return sorted;
    }
  };

  // グループ内の物件を並び替え
  const sortGroupedProperties = (properties: any[]) => {
    const sorted = [...properties];

    switch (sortBy) {
      case 'bookmark_date_desc':
        return sorted.sort((a, b) => {
          const dateA = new Date(a.created_at).getTime();
          const dateB = new Date(b.created_at).getTime();
          return dateB - dateA; // 新しい順
        });
      case 'bookmark_date_asc':
        return sorted.sort((a, b) => {
          const dateA = new Date(a.created_at).getTime();
          const dateB = new Date(b.created_at).getTime();
          return dateA - dateB; // 古い順
        });
      case 'updated_at_desc':
        return sorted.sort((a, b) => {
          const dateA = new Date(a.master_property?.updated_at || 0).getTime();
          const dateB = new Date(b.master_property?.updated_at || 0).getTime();
          return dateB - dateA;
        });
      case 'updated_at_asc':
        return sorted.sort((a, b) => {
          const dateA = new Date(a.master_property?.updated_at || 0).getTime();
          const dateB = new Date(b.master_property?.updated_at || 0).getTime();
          return dateA - dateB;
        });
      case 'price_asc':
        return sorted.sort((a, b) => {
          const priceA = a.master_property?.current_price || 0;
          const priceB = b.master_property?.current_price || 0;
          return priceA - priceB;
        });
      case 'price_desc':
        return sorted.sort((a, b) => {
          const priceA = a.master_property?.current_price || 0;
          const priceB = b.master_property?.current_price || 0;
          return priceB - priceA;
        });
      case 'area_asc':
        return sorted.sort((a, b) => {
          const areaA = a.master_property?.area || 0;
          const areaB = b.master_property?.area || 0;
          return areaA - areaB;
        });
      case 'area_desc':
        return sorted.sort((a, b) => {
          const areaA = a.master_property?.area || 0;
          const areaB = b.master_property?.area || 0;
          return areaB - areaA;
        });
      case 'built_year_desc':
        return sorted.sort((a, b) => {
          const yearA = a.master_property?.building?.built_year || 0;
          const yearB = b.master_property?.building?.built_year || 0;
          return yearB - yearA;
        });
      case 'built_year_asc':
        return sorted.sort((a, b) => {
          const yearA = a.master_property?.building?.built_year || 0;
          const yearB = b.master_property?.building?.built_year || 0;
          return yearA - yearB;
        });
      case 'tsubo_price_asc':
        return sorted.sort((a, b) => {
          const priceA = a.master_property?.current_price || 0;
          const priceB = b.master_property?.current_price || 0;
          const areaA = a.master_property?.area || 1;
          const areaB = b.master_property?.area || 1;
          const tsuboPriceA = (priceA / areaA) * 3.30579;
          const tsuboPriceB = (priceB / areaB) * 3.30579;
          return tsuboPriceA - tsuboPriceB;
        });
      case 'tsubo_price_desc':
        return sorted.sort((a, b) => {
          const priceA = a.master_property?.current_price || 0;
          const priceB = b.master_property?.current_price || 0;
          const areaA = a.master_property?.area || 1;
          const areaB = b.master_property?.area || 1;
          const tsuboPriceA = (priceA / areaA) * 3.30579;
          const tsuboPriceB = (priceB / areaB) * 3.30579;
          return tsuboPriceB - tsuboPriceA;
        });
      default:
        return sorted;
    }
  };

  // 総件数を計算
  const getTotalCount = () => {
    if (viewMode === 'all') {
      return bookmarks.length;
    } else if (groupedData?.grouped_bookmarks) {
      return Object.values(groupedData.grouped_bookmarks).reduce(
        (sum: number, group: any) => sum + group.count, 
        0
      );
    }
    return 0;
  };

  // すべて開く/閉じるボタンのハンドラ
  const handleExpandAll = () => {
    if (groupedData?.grouped_bookmarks) {
      const allKeys = Object.keys(groupedData.grouped_bookmarks);
      setExpandedAccordions(new Set(allKeys));
      setHasInteracted(true);
    }
  };

  const handleCollapseAll = () => {
    setExpandedAccordions(new Set());
    setHasInteracted(true);
  };

  // アコーディオンの開閉ハンドラ
  const handleAccordionChange = (key: string) => (event: React.SyntheticEvent, isExpanded: boolean) => {
    setExpandedAccordions(prev => {
      const newSet = new Set(prev);
      if (isExpanded) {
        newSet.add(key);
      } else {
        newSet.delete(key);
      }
      return newSet;
    });
    setHasInteracted(true);
  };

  // グループ表示用のレンダリング関数
  const renderGroupedView = () => {
    if (!groupedData?.grouped_bookmarks) return null;

    const groups = Object.entries(groupedData.grouped_bookmarks);
    
    if (groups.length === 0) {
      return (
        <Card sx={{ p: 4, textAlign: 'center' }}>
          <BookmarkBorder sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
          <Typography variant="h6" color="text.secondary">
            ブックマークされた物件がありません
          </Typography>
        </Card>
      );
    }

    return (
      <Box>
        {groups.map(([key, groupData]: [string, any]) => {
          return (
            <Accordion 
              key={key}
              expanded={expandedAccordions.has(key)}
              onChange={handleAccordionChange(key)}
              sx={{ mb: 2 }}
              TransitionProps={{ timeout: hasInteracted ? undefined : 0 }}
            >
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Box sx={{ 
                display: 'flex', 
                flexDirection: { xs: 'column', sm: 'row' },
                alignItems: { xs: 'flex-start', sm: 'center' },
                width: '100%', 
                pr: { xs: 1, sm: 2 },
                gap: { xs: 0.5, sm: 0 }
              }}>
                {/* 建物名/エリア名の行 */}
                <Box sx={{ display: 'flex', alignItems: 'center', flex: 1, width: { xs: '100%', sm: 'auto' } }}>
                  {viewMode === 'ward' ? (
                    <LocationOn color="primary" sx={{ mr: 1, fontSize: { xs: 20, sm: 24 } }} />
                  ) : (
                    <Apartment color="primary" sx={{ mr: 1, fontSize: { xs: 20, sm: 24 } }} />
                  )}
                  <Typography 
                    variant="h6" 
                    sx={{ 
                      fontSize: { xs: '0.95rem', sm: '1.25rem' },
                      flex: 1,
                      lineHeight: 1.3,
                      wordBreak: 'break-word'
                    }}
                  >
                    {viewMode === 'ward' ? groupData.ward : groupData.building_name}
                  </Typography>
                </Box>
                
                {/* 件数の行 */}
                <Box sx={{ 
                  display: 'flex', 
                  alignItems: 'center',
                  ml: { xs: 4, sm: 0 }
                }}>
                  <Chip 
                    label={`${groupData.count}件`} 
                    color="primary" 
                    size="small"
                    sx={{ height: { xs: 20, sm: 24 } }}
                  />
                </Box>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              {/* 建物統計情報 */}
              {viewMode === 'building' && groupData.building_info && (
                <Box sx={{ mb: 2 }}>
                  {/* 全物件を見るリンク */}
                  <Button
                    variant="outlined"
                    size="small"
                    fullWidth
                    startIcon={<Apartment />}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/buildings/${groupData.building_id}/properties`);
                    }}
                    sx={{ 
                      fontSize: { xs: '0.85rem', sm: '0.9rem' },
                      py: 1,
                      mb: 1.5
                    }}
                  >
                    全{groupData.building_stats?.active_count || 0}件の物件を見る
                  </Button>

                  {/* 平均坪単価 */}
                  {groupData.building_stats?.avg_price_per_tsubo && (
                    <Box sx={{ textAlign: 'center', py: 1 }}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        平均坪単価
                      </Typography>
                      <Typography 
                        variant="h6" 
                        color="primary"
                        sx={{ fontSize: { xs: '1.1rem', sm: '1.2rem' }, fontWeight: 600 }}
                      >
                        {groupData.building_stats.avg_price_per_tsubo.toLocaleString()}万円
                      </Typography>
                    </Box>
                  )}
                </Box>
              )}
              
              {viewMode === 'ward' && (
                <Box sx={{ mb: 2 }}>
                  {/* エリア物件一覧へのリンク */}
                  <Button
                    variant="outlined"
                    size="small"
                    fullWidth
                    startIcon={<LocationOn />}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/properties?wards=${encodeURIComponent(groupData.ward)}`);
                    }}
                    sx={{ 
                      fontSize: { xs: '0.85rem', sm: '0.9rem' },
                      py: 1
                    }}
                  >
                    {groupData.ward}の物件一覧を見る
                  </Button>
                </Box>
              )}

              <Divider sx={{ mb: 2 }} />
              
              {/* 物件一覧 */}
              <Grid container spacing={{ xs: 1.5, sm: 2 }}>
                {sortGroupedProperties(groupData.properties).map((bookmark: any) => {
                  const property = bookmark.master_property;
                  if (!property) return null;

                  return (
                    <Grid item xs={12} sm={6} md={6} key={bookmark.id}>
                      <Card 
                        sx={{ 
                          cursor: 'pointer',
                          transition: 'all 0.2s',
                          backgroundColor: !property.has_active_listing ? 'grey.50' : 'background.paper',
                          opacity: !property.has_active_listing ? 0.85 : 1,
                          '&:hover': {
                            transform: 'translateY(-2px)',
                            boxShadow: 3
                          }
                        }}
                        onClick={() => handlePropertyClick(property.id)}
                      >
                        <CardContent sx={{ p: { xs: 1.5, sm: 2 }, '&:last-child': { pb: { xs: 1.5, sm: 2 } } }}>
                          <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={{ xs: 0.5, sm: 1 }}>
                            <Box sx={{ flex: 1, mr: 1 }}>
                              <Typography 
                                variant="subtitle1" 
                                sx={{ 
                                  fontSize: { xs: '0.9rem', sm: '1rem' },
                                  lineHeight: 1.3,
                                  fontWeight: 500
                                }}
                              >
                                {property.display_building_name || property.building?.normalized_name || '建物名不明'}
                              </Typography>
                              {!property.has_active_listing && (
                                <Chip 
                                  label="販売終了" 
                                  size="small" 
                                  color="default"
                                  sx={{ 
                                    mt: 0.5,
                                    height: 20,
                                    fontSize: '0.7rem',
                                    backgroundColor: 'grey.300'
                                  }}
                                />
                              )}
                            </Box>
                            <BookmarkButton
                              propertyId={property.id}
                              initialBookmarked={true}
                              size="small"
                              skipInitialCheck={true}
                              onBookmarkChange={(isBookmarked) =>
                                handleBookmarkChange(property.id, isBookmarked)
                              }
                            />
                          </Box>
                          
                          {property.room_number && (
                            <Typography 
                              variant="body2" 
                              color="text.secondary"
                              sx={{ fontSize: { xs: '0.8rem', sm: '0.875rem' } }}
                            >
                              {property.room_number}
                            </Typography>
                          )}
                          
                          <Typography 
                            variant="body2" 
                            color="text.secondary"
                            sx={{ fontSize: { xs: '0.8rem', sm: '0.875rem' } }}
                          >
                            {formatFloor(property.floor_number, property.building?.total_floors)}
                            {property.layout && ` • ${property.layout}`}
                            {property.area && ` • ${formatArea(property.area)}`}
                            {property.direction && ` • ${property.direction}向き`}
                          </Typography>
                          
                          <Box sx={{ mt: { xs: 0.5, sm: 1 } }}>
                            <Typography 
                              variant="h6" 
                              color={!property.has_active_listing ? "text.secondary" : "primary"}
                              sx={{ 
                                fontSize: { xs: '1rem', sm: '1.25rem' }
                              }}
                            >
                              {formatPrice(property.has_active_listing ? property.current_price : property.final_price)}
                            </Typography>
                            
                            {/* 坪単価 */}
                            <Typography variant="body1" color="text.secondary" sx={{ mt: 0.5 }}>
                              坪単価: {property.price_per_tsubo ? `${Math.round(property.price_per_tsubo).toLocaleString()}万円/坪` : '-'}
                            </Typography>
                            
                            {/* 売出確認日・価格改定・販売終了日 */}
                            <Box sx={{ mt: 1, p: 1, bgcolor: 'grey.50', borderRadius: 1 }}>
                              <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                                売出確認日: {formatDate(property.earliest_published_at)}
                                {property.earliest_published_at && (
                                  <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 0.5, fontSize: '0.8rem' }}>
                                    ({calculateDaysFromPublished(property.earliest_published_at)})
                                  </Typography>
                                )}
                              </Typography>
                              {property.price_change_info && (
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                                  <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                                    価格改定: {formatDate(property.price_change_info.date)}
                                  </Typography>
                                  <Typography 
                                    variant="body2" 
                                    sx={{ 
                                      fontSize: '0.8rem',
                                      color: property.price_change_info.change_amount > 0 ? 'error.main' : 'success.main',
                                      fontWeight: 'bold'
                                    }}
                                  >
                                    {property.price_change_info.change_amount > 0 ? '↑' : '↓'}
                                    {Math.abs(property.price_change_info.change_amount).toLocaleString()}万円
                                    ({property.price_change_info.change_rate > 0 ? '+' : ''}{property.price_change_info.change_rate}%)
                                  </Typography>
                                </Box>
                              )}
                              {!property.has_active_listing && property.delisted_at && (
                                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, fontSize: '0.8rem' }}>
                                  販売終了日: {formatDate(property.delisted_at)}
                                </Typography>
                              )}
                            </Box>
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>
                  );
                })}
              </Grid>
            </AccordionDetails>
          </Accordion>
          );
        })}
      </Box>
    );
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box display="flex" alignItems="center" mb={4}>
        <BookmarkIcon color="error" sx={{ mr: 2, fontSize: 32 }} />
        <Typography variant="h4" component="h1">
          ブックマーク
        </Typography>
        <Chip 
          label={`${getTotalCount()}件`} 
          color="primary" 
          sx={{ ml: 2 }}
        />
      </Box>

      {/* 表示切り替えボタン */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'center' }}>
        <ToggleButtonGroup
          value={viewMode}
          exclusive
          onChange={(_, newMode) => {
            if (newMode) {
              const params: any = { view: newMode };
              if (sortBy !== 'default') {
                params.sort = sortBy;
              }
              setSearchParams(params);
            }
          }}
          aria-label="表示モード"
        >
          <ToggleButton value="all" aria-label="すべて">
            <ViewList sx={{ mr: 1 }} />
            すべて
          </ToggleButton>
          <ToggleButton value="ward" aria-label="エリア別">
            <LocationOn sx={{ mr: 1 }} />
            エリア別
          </ToggleButton>
          <ToggleButton value="building" aria-label="建物別">
            <Apartment sx={{ mr: 1 }} />
            建物別
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* 並び替えとアコーディオン操作 */}
      {(viewMode !== 'all' || bookmarks.length > 0) && (
        <Box sx={{ 
          mb: 2, 
          display: 'flex', 
          flexDirection: { xs: 'column', sm: 'row' },
          gap: 2, 
          alignItems: { xs: 'stretch', sm: 'center' },
          justifyContent: 'space-between'
        }}>
          {/* 並び替え */}
          <FormControl size="small" sx={{ minWidth: { xs: '100%', sm: 200 } }}>
            <InputLabel>並び替え</InputLabel>
            <Select
              value={sortBy}
              label="並び替え"
              onChange={(e) => {
                const params: any = {};
                if (viewMode !== 'all') {
                  params.view = viewMode;
                }
                // デフォルト以外の場合のみsortパラメータを設定
                if (e.target.value !== 'bookmark_date_desc') {
                  params.sort = e.target.value;
                }
                setSearchParams(params);
              }}
            >
              <MenuItem value="bookmark_date_desc">ブックマーク登録日（新しい順）</MenuItem>
              <MenuItem value="bookmark_date_asc">ブックマーク登録日（古い順）</MenuItem>
              <MenuItem value="updated_at_desc">物件更新日（新しい順）</MenuItem>
              <MenuItem value="updated_at_asc">物件更新日（古い順）</MenuItem>
              <MenuItem value="price_desc">価格（高い順）</MenuItem>
              <MenuItem value="price_asc">価格（安い順）</MenuItem>
              <MenuItem value="area_desc">面積（広い順）</MenuItem>
              <MenuItem value="area_asc">面積（狭い順）</MenuItem>
              <MenuItem value="built_year_desc">築年数（新しい順）</MenuItem>
              <MenuItem value="built_year_asc">築年数（古い順）</MenuItem>
              <MenuItem value="tsubo_price_desc">坪単価（高い順）</MenuItem>
              <MenuItem value="tsubo_price_asc">坪単価（安い順）</MenuItem>
            </Select>
          </FormControl>

          {/* すべて開く/閉じるボタン（グループ表示時のみ） */}
          {viewMode !== 'all' && groupedData?.grouped_bookmarks && Object.keys(groupedData.grouped_bookmarks).length > 0 && (
            <Box sx={{ display: 'flex', gap: 1, justifyContent: { xs: 'center', sm: 'flex-end' } }}>
              <Button 
                size="small" 
                variant="outlined"
                onClick={handleExpandAll}
              >
                すべて開く
              </Button>
              <Button 
                size="small" 
                variant="outlined"
                onClick={handleCollapseAll}
              >
                すべて閉じる
              </Button>
            </Box>
          )}
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
          <Button onClick={loadBookmarks} sx={{ ml: 2 }}>
            再読み込み
          </Button>
        </Alert>
      )}

      {/* グループ表示モード */}
      {viewMode !== 'all' ? (
        renderGroupedView()
      ) : bookmarks.length === 0 ? (
        <Card sx={{ p: 4, textAlign: 'center' }}>
          <BookmarkBorder sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
          <Typography variant="h6" color="text.secondary" gutterBottom>
            ブックマークされた物件がありません
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            気になる物件をブックマークしてここに保存しましょう
          </Typography>
          <Button 
            variant="contained" 
            onClick={() => navigate('/properties')}
          >
            物件を探す
          </Button>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {sortBookmarks(bookmarks).map((bookmark) => {
            const property = bookmark.master_property;
            if (!property) return null;

            return (
              <Grid item xs={12} md={6} lg={4} key={bookmark.id}>
                <Card 
                  sx={{ 
                    height: '100%',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease-in-out',
                    backgroundColor: !property.has_active_listing ? 'grey.50' : 'background.paper',
                    opacity: !property.has_active_listing ? 0.85 : 1,
                    '&:hover': {
                      transform: 'translateY(-2px)',
                      boxShadow: 3
                    }
                  }}
                  onClick={() => handlePropertyClick(property.id)}
                >
                  <CardContent>
                    {/* ヘッダー部分 */}
                    <Box display="flex" justifyContent="between" alignItems="flex-start" mb={2}>
                      <Box sx={{ flex: 1, mr: 1 }}>
                        <Typography variant="h6" component="div">
                          {property.display_building_name || property.building?.normalized_name || '建物名不明'}
                        </Typography>
                        {!property.has_active_listing && (
                          <Chip 
                            label="販売終了" 
                            size="small" 
                            color="default"
                            sx={{ 
                              mt: 0.5,
                              height: 20,
                              fontSize: '0.7rem',
                              backgroundColor: 'grey.300'
                            }}
                          />
                        )}
                      </Box>
                      <BookmarkButton
                        propertyId={property.id}
                        initialBookmarked={true}
                        size="small"
                        skipInitialCheck={true}
                        onBookmarkChange={(isBookmarked) => 
                          handleBookmarkChange(property.id, isBookmarked)
                        }
                      />
                    </Box>

                    {/* 物件基本情報 */}
                    <Box mb={2}>
                      {property.room_number && (
                        <Typography variant="body2" color="text.secondary">
                          部屋番号: {property.room_number}
                        </Typography>
                      )}
                      <Typography variant="body2" color="text.secondary">
                        {formatFloor(property.floor_number, property.building?.total_floors)} 
                        {property.layout && ` • ${property.layout}`}
                        {property.area && ` • ${formatArea(property.area)}`}
                        {property.direction && ` • ${property.direction}向き`}
                      </Typography>
                      {property.building?.address && (
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                          {property.building.address}
                        </Typography>
                      )}
                    </Box>

                    {/* 価格情報 */}
                    <Box mb={2}>
                      <Typography variant="h6" color={!property.has_active_listing ? "text.secondary" : "primary"}>
                        {formatPrice(property.has_active_listing ? property.current_price : property.final_price)}
                      </Typography>
                      
                      {/* 坪単価 */}
                      <Typography variant="body1" color="text.secondary" sx={{ mt: 0.5 }}>
                        坪単価: {property.price_per_tsubo ? `${property.price_per_tsubo.toLocaleString()}万円/坪` : '-'}
                      </Typography>
                      
                      {/* 売出確認日・価格改定・販売終了日 */}
                      <Box sx={{ mt: 1, p: 1, bgcolor: 'grey.50', borderRadius: 1 }}>
                        <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                          売出確認日: {formatDate(property.earliest_published_at)}
                          {property.earliest_published_at && (
                            <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 0.5, fontSize: '0.8rem' }}>
                              ({calculateDaysFromPublished(property.earliest_published_at)})
                            </Typography>
                          )}
                        </Typography>
                        {property.price_change_info && (
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                            <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                              価格改定: {formatDate(property.price_change_info.date)}
                            </Typography>
                            <Typography 
                              variant="body2" 
                              sx={{ 
                                fontSize: '0.8rem',
                                color: property.price_change_info.change_amount > 0 ? 'error.main' : 'success.main',
                                fontWeight: 'bold'
                              }}
                            >
                              {property.price_change_info.change_amount > 0 ? '↑' : '↓'}
                              {Math.abs(property.price_change_info.change_amount).toLocaleString()}万円
                              ({property.price_change_info.change_rate > 0 ? '+' : ''}{property.price_change_info.change_rate}%)
                            </Typography>
                          </Box>
                        )}
                        {!property.has_active_listing && property.delisted_at && (
                          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, fontSize: '0.8rem' }}>
                            販売終了日: {formatDate(property.delisted_at)}
                          </Typography>
                        )}
                      </Box>
                    </Box>

                    {/* ブックマーク日時 */}
                    <Typography variant="caption" color="text.secondary">
                      ブックマーク: {new Date(bookmark.created_at).toLocaleDateString('ja-JP')}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}

      {/* Undo Snackbar */}
      <Snackbar
        open={undoSnackbarOpen}
        autoHideDuration={6000}
        onClose={handleCloseSnackbar}
        message={deletedBookmark ? `「${deletedBookmark.propertyName}」をブックマークから削除しました` : ''}
        action={
          <>
            <Button
              size="small"
              onClick={handleUndo}
              sx={{
                color: '#fff',
                fontWeight: 'bold',
                '&:hover': {
                  backgroundColor: 'rgba(255, 255, 255, 0.1)'
                }
              }}
            >
              元に戻す
            </Button>
            <IconButton size="small" color="inherit" onClick={handleCloseSnackbar}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </>
        }
      />
    </Container>
  );
};