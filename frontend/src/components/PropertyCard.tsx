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

interface PropertyCardProps {
  property: Property;
}

const PropertyCard: React.FC<PropertyCardProps> = ({ property }) => {
  const navigate = useNavigate();

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

  // 価格表示を決定（最小価格〜最大価格、または単一価格）
  const priceDisplay = property.min_price === property.max_price
    ? formatPrice(property.min_price)
    : `${formatPrice(property.min_price)} 〜 ${formatPrice(property.max_price)}`;

  return (
    <Card
      sx={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        cursor: 'pointer',
        opacity: property.has_active_listing === false ? 0.6 : 1,
        position: 'relative',
        '&:hover': {
          boxShadow: 6,
        },
      }}
      onClick={handleClick}
    >
      <CardContent sx={{ flexGrow: 1 }}>
        {/* 掲載終了バッジ */}
        {property.has_active_listing === false && (
          <Chip
            label="掲載終了"
            size="small"
            color="error"
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
              top: property.has_active_listing === false ? 40 : 8, 
              right: 8 
            }}
          />
        )}
        
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          <Box sx={{ display: 'flex', gap: 0.5 }}>
            {property.source_sites.map((site) => (
              <Chip
                key={site}
                label={site}
                size="small"
                color="primary"
                variant="outlined"
              />
            ))}
          </Box>
          {property.listing_count > 1 && (
            <Chip
              label={`${property.listing_count}件`}
              size="small"
              color="secondary"
            />
          )}
        </Box>

        <Typography gutterBottom variant="h6" component="h2">
          {property.building.normalized_name}
          {property.room_number && ` ${property.room_number}`}
        </Typography>

        <Typography variant="h5" color="primary" gutterBottom>
          {priceDisplay}
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
              {property.has_active_listing !== false ? (
                <>（販売開始から{Math.floor((new Date().getTime() - new Date(property.earliest_published_at).getTime()) / (1000 * 60 * 60 * 24))}日経過）</>
              ) : property.delisted_at ? (
                <>（{format(new Date(property.delisted_at), 'yyyy年MM月dd日', { locale: ja })}掲載終了）</>
              ) : (
                <>（掲載終了）</>
              )}
            </Typography>
            {/* 価格改定日を表示（売出確認日と異なる場合のみ） */}
            {property.latest_price_update && 
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