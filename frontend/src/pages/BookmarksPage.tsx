import React, { useState, useEffect } from 'react';
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
  Button
} from '@mui/material';
import { BookmarkBorder, Bookmark as BookmarkIcon, Login as LoginIcon } from '@mui/icons-material';
import { BookmarkService } from '../services/bookmarkService';
import { Bookmark } from '../types/property';
import { BookmarkButton } from '../components/BookmarkButton';
import { useNavigate } from 'react-router-dom';
import { useUserAuth } from '../contexts/UserAuthContext';
import { LoginModal } from '../components/LoginModal';

export const BookmarksPage: React.FC = () => {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const navigate = useNavigate();
  const { isAuthenticated, isLoading: authLoading } = useUserAuth();

  useEffect(() => {
    if (!authLoading) {
      if (isAuthenticated) {
        loadBookmarks();
      } else {
        setLoading(false);
      }
    }
  }, [isAuthenticated, authLoading]);

  const loadBookmarks = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await BookmarkService.getBookmarks();
      setBookmarks(data);
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
      // ブックマークが削除された場合、一覧から除外
      setBookmarks(prev => prev.filter(bookmark => bookmark.master_property_id !== propertyId));
    }
  };

  const formatPrice = (price?: number) => {
    if (!price) return '価格情報なし';
    return `${price.toLocaleString()}万円`;
  };

  const formatArea = (area?: number) => {
    if (!area) return '';
    return `${area}㎡`;
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

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box display="flex" alignItems="center" mb={4}>
        <BookmarkIcon color="error" sx={{ mr: 2, fontSize: 32 }} />
        <Typography variant="h4" component="h1">
          ブックマーク
        </Typography>
        <Chip 
          label={`${bookmarks.length}件`} 
          color="primary" 
          sx={{ ml: 2 }}
        />
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
          <Button onClick={loadBookmarks} sx={{ ml: 2 }}>
            再読み込み
          </Button>
        </Alert>
      )}

      {bookmarks.length === 0 ? (
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
          {bookmarks.map((bookmark) => {
            const property = bookmark.master_property;
            if (!property) return null;

            return (
              <Grid item xs={12} md={6} lg={4} key={bookmark.id}>
                <Card 
                  sx={{ 
                    height: '100%',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease-in-out',
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
                      <Typography variant="h6" component="div" sx={{ flex: 1, mr: 1 }}>
                        {property.display_building_name || property.building?.normalized_name || '建物名不明'}
                      </Typography>
                      <BookmarkButton
                        propertyId={property.id}
                        initialBookmarked={true}
                        size="small"
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
                      </Typography>
                      {property.building?.address && (
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                          {property.building.address}
                        </Typography>
                      )}
                    </Box>

                    {/* 価格情報 */}
                    <Box mb={2}>
                      <Typography variant="h6" color="primary">
                        {formatPrice(property.final_price || property.majority_price || property.min_price)}
                      </Typography>
                      {property.management_fee && (
                        <Typography variant="caption" color="text.secondary">
                          管理費: {property.management_fee.toLocaleString()}円/月
                        </Typography>
                      )}
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
    </Container>
  );
};