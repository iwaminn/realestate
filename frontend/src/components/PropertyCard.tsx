import React from 'react';
import {
  Card,
  CardContent,
  CardMedia,
  Typography,
  Box,
  Chip,
  Grid,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import SquareFootIcon from '@mui/icons-material/SquareFoot';
import ApartmentIcon from '@mui/icons-material/Apartment';
import StairsIcon from '@mui/icons-material/Stairs';
import ExploreIcon from '@mui/icons-material/Explore';
import CachedIcon from '@mui/icons-material/Cached';
import { format } from 'date-fns';
import { ja } from 'date-fns/locale';
import { Property } from '../types/property';
import { BookmarkButton } from './BookmarkButton';

interface PropertyCardProps {
  property: Property;
}

const PropertyCard: React.FC<PropertyCardProps> = ({ property }) => {
  const navigate = useNavigate();

  // 販売終了からの経過日数を計算
  const getDaysSinceSold = () => {
    if (!property.sold_at) return null;
    const soldDate = new Date(property.sold_at);
    const today = new Date();
    const diffTime = Math.abs(today.getTime() - soldDate.getTime());
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
    return diffDays;
  };

  const daysSinceSold = getDaysSinceSold();

  const formatPrice = (price: number | undefined) => {
    if (!price) return '価格未定';
    
    // 1億円以上の場合
    if (price >= 10000) {
      const oku = Math.floor(price / 10000);
      const man = price % 10000;
      
      if (man === 0) {
        // ちょうど億の場合
        return `${oku}億円`;
      } else {
        // 億と万の組み合わせ
        return `${oku}億${man.toLocaleString()}万円`;
      }
    }
    
    // 1億円未満の場合
    return `${price.toLocaleString()}万円`;
  };

  const handleClick = () => {
    navigate(`/properties/${property.id}`);
  };

  // 価格表示を決定（多数決価格を優先）
  const priceDisplay = formatPrice(property.majority_price || property.min_price);

  return (
    <Card
      sx={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        cursor: 'pointer',
        position: 'relative',
        backgroundColor: property.sold_at ? '#f5f5f5' : 'background.paper',
        border: property.sold_at ? '2px solid #e0e0e0' : '1px solid rgba(0, 0, 0, 0.12)',
        opacity: property.sold_at ? 0.85 : (property.has_active_listing === false ? 0.7 : 1),
        transition: 'all 0.3s ease',
        '&:hover': {
          boxShadow: property.sold_at ? 3 : 6,
          opacity: property.sold_at ? 0.95 : 1,
        },
      }}
      onClick={handleClick}
    >
      <CardContent sx={{ flexGrow: 1 }}>
        {/* 販売終了バッジと経過日数 */}
        {property.sold_at && (
          <Box sx={{ position: 'absolute', top: 8, right: 8, display: 'flex', gap: 0.5, flexDirection: 'column', alignItems: 'flex-end' }}>
            <Chip
              label="販売終了"
              size="small"
              sx={{ 
                backgroundColor: '#d32f2f',
                color: 'white',
                fontWeight: 'bold',
                '& .MuiChip-label': {
                  px: 1.5
                }
              }}
            />
            {daysSinceSold !== null && daysSinceSold > 0 && (
              <Typography variant="caption" sx={{ 
                backgroundColor: 'rgba(0, 0, 0, 0.7)', 
                color: 'white', 
                px: 1, 
                py: 0.25, 
                borderRadius: 1,
                fontSize: '0.7rem'
              }}>
                {daysSinceSold < 7 ? `${daysSinceSold}日前` : 
                 daysSinceSold < 30 ? `${Math.floor(daysSinceSold / 7)}週間前` :
                 daysSinceSold < 365 ? `${Math.floor(daysSinceSold / 30)}ヶ月前` :
                 `${Math.floor(daysSinceSold / 365)}年前`}
              </Typography>
            )}
          </Box>
        )}
        
        {/* 掲載終了バッジ（販売終了でない場合のみ表示） */}
        {!property.sold_at && property.has_active_listing === false && (
          <Chip
            label="掲載終了"
            size="small"
            color="warning"
            sx={{ position: 'absolute', top: 8, right: 8 }}
          />
        )}
        
        {/* 買い取り再販バッジ */}
        {property.is_resale && (
          <Chip
            icon={<CachedIcon />}
            label="買い取り再販"
            size="small"
            color="warning"
            sx={{ 
              position: 'absolute', 
              top: (property.sold_at || property.has_active_listing === false) ? 40 : 8, 
              right: 8 
            }}
          />
        )}
        
        {/* ブックマークボタン（右上） */}
        <Box sx={{ position: 'absolute', top: 8, right: property.sold_at || property.has_active_listing === false || property.is_resale ? 72 : 8, zIndex: 1 }}>
          <BookmarkButton propertyId={property.id} size="small" />
        </Box>

        {/* 物件数のみ表示（複数ある場合のみ） */}
        {property.listing_count > 1 && (
          <Box sx={{ mb: 1 }}>
            <Chip
              label={`${property.listing_count}件`}
              size="small"
              color="secondary"
            />
          </Box>
        )}

        <Typography gutterBottom variant="h6" component="h2" sx={{ color: property.sold_at ? 'text.secondary' : 'text.primary' }}>
          {property.building.normalized_name}
          {property.room_number && ` ${property.room_number}`}
        </Typography>

        <Typography variant="h5" color={property.sold_at ? "text.secondary" : "primary"} gutterBottom>
          {property.sold_at && property.last_sale_price 
            ? (
              <>
                <Box component="span" sx={{ textDecoration: 'line-through', opacity: 0.6, fontSize: '0.9em' }}>
                  {formatPrice(property.last_sale_price)}
                </Box>
                <Box component="span" sx={{ ml: 1, fontSize: '0.85em', color: 'text.secondary' }}>
                  販売終了
                </Box>
              </>
            )
            : priceDisplay}
        </Typography>

        <Grid container spacing={1} sx={{ mb: 2 }}>
          <Grid item xs={12}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <LocationOnIcon fontSize="small" sx={{ mr: 0.5 }} />
              <Typography variant="body2" color="text.secondary">
                {property.building.address || '住所情報なし'}
              </Typography>
            </Box>
          </Grid>
          {property.area && (
            <Grid item xs={6}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <SquareFootIcon fontSize="small" sx={{ mr: 0.5 }} />
                <Typography variant="body2">
                  {property.area}㎡
                </Typography>
              </Box>
            </Grid>
          )}
          {property.layout && (
            <Grid item xs={6}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <ApartmentIcon fontSize="small" sx={{ mr: 0.5 }} />
                <Typography variant="body2">
                  {property.layout}
                </Typography>
              </Box>
            </Grid>
          )}
          {property.floor_number && (
            <Grid item xs={6}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <StairsIcon fontSize="small" sx={{ mr: 0.5 }} />
                <Typography variant="body2">
                  {property.floor_number}階{property.building.total_floors ? `/${property.building.total_floors}階${property.building.basement_floors ? `地下${property.building.basement_floors}階建` : '建'}` : ''}
                </Typography>
              </Box>
            </Grid>
          )}
          {property.direction && (
            <Grid item xs={6}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <ExploreIcon fontSize="small" sx={{ mr: 0.5 }} />
                <Typography variant="body2">
                  {property.direction}向き
                </Typography>
              </Box>
            </Grid>
          )}
        </Grid>
        
        {/* 売出確認日と価格改定日の表示 */}
        {property.earliest_published_at && (
          <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid #e0e0e0' }}>
            <Typography variant="caption" color="text.secondary">
              売出確認日: {format(new Date(property.earliest_published_at), 'yyyy年MM月dd日', { locale: ja })}
              {property.sold_at ? (
                <>　販売終了日: {format(new Date(property.sold_at), 'yyyy年MM月dd日', { locale: ja })}</>
              ) : property.has_active_listing !== false ? (
                <>（販売開始から{Math.floor((new Date().getTime() - new Date(property.earliest_published_at).getTime()) / (1000 * 60 * 60 * 24))}日経過）</>
              ) : property.delisted_at ? (
                <>（{format(new Date(property.delisted_at), 'yyyy年MM月dd日', { locale: ja })}掲載終了）</>
              ) : (
                <>（掲載終了）</>
              )}
            </Typography>
            {/* 価格改定日を表示（価格変更があった場合のみ） */}
            {property.has_price_change && 
             property.latest_price_update && 
             property.earliest_published_at &&
             format(new Date(property.latest_price_update), 'yyyy-MM-dd') !== format(new Date(property.earliest_published_at), 'yyyy-MM-dd') && (
              <Typography variant="caption" color="text.secondary" display="block">
                価格改定日: {format(new Date(property.latest_price_update), 'yyyy年MM月dd日', { locale: ja })}
                （{Math.floor((new Date().getTime() - new Date(property.latest_price_update).getTime()) / (1000 * 60 * 60 * 24))}日前）
              </Typography>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default PropertyCard;