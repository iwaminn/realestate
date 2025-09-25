import React from 'react';
import { Link } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  Grid,
  Divider,
  useTheme,
  useMediaQuery,
} from '@mui/material';
import {
  Gavel,
  Security,
  Description,
  Warning,
} from '@mui/icons-material';
import { APP_CONFIG } from '../config/app';

const Footer: React.FC = () => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  return (
    <Box
      component="footer"
      sx={{
        backgroundColor: '#f5f5f5',
        borderTop: '1px solid #e0e0e0',
        mt: 'auto',
        py: 3,
      }}
    >
      <Container maxWidth="lg">
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Box sx={{ mb: 2 }}>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 'bold' }}>
                {APP_CONFIG.APP_NAME}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                本サイトは東京都心部の新築・中古マンション情報を集約した検索サービスです。
                物件情報は各不動産サイトから収集したものであり、最新の状況とは異なる場合があります。
              </Typography>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1, fontWeight: 500 }}>
                  ご利用にあたって
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                  掲載情報は各不動産サイトから収集した参考情報です。<br />
                  実際の物件情報は不動産会社に直接ご確認ください。<br />
                  本サイトは物件の仲介・販売は行っておりません。
                </Typography>
              </Box>
            </Box>
          </Grid>

          <Grid item xs={12} md={4}>
            <Typography variant="subtitle1" gutterBottom sx={{ fontWeight: 'bold' }}>
              法的情報
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              <Box
                component={Link}
                to="/terms/disclaimer"
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  textDecoration: 'none',
                  color: 'text.secondary',
                  '&:hover': {
                    color: 'primary.main',
                  },
                }}
              >
                <Warning sx={{ mr: 1, fontSize: 18 }} />
                <Typography variant="body2">免責事項</Typography>
              </Box>

              <Box
                component={Link}
                to="/terms"
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  textDecoration: 'none',
                  color: 'text.secondary',
                  '&:hover': {
                    color: 'primary.main',
                  },
                }}
              >
                <Gavel sx={{ mr: 1, fontSize: 18 }} />
                <Typography variant="body2">利用規約</Typography>
              </Box>

              <Box
                component={Link}
                to="/privacy"
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  textDecoration: 'none',
                  color: 'text.secondary',
                  '&:hover': {
                    color: 'primary.main',
                  },
                }}
              >
                <Security sx={{ mr: 1, fontSize: 18 }} />
                <Typography variant="body2">プライバシーポリシー</Typography>
              </Box>
            </Box>
          </Grid>
        </Grid>

        <Divider sx={{ my: 3 }} />

        <Box sx={{
          display: 'flex',
          flexDirection: isMobile ? 'column' : 'row',
          justifyContent: 'space-between',
          alignItems: isMobile ? 'center' : 'flex-start',
          gap: 2
        }}>
          <Typography variant="caption" color="text.secondary" sx={{ textAlign: isMobile ? 'center' : 'left' }}>
            本サイトは情報提供を目的としており、不動産の売買・仲介は行っておりません。<br />
            掲載されている物件情報は各不動産サイトから収集したものです。
          </Typography>
          <Typography variant="caption" color="text.secondary">
            © 2025 {APP_CONFIG.APP_NAME}
          </Typography>
        </Box>
      </Container>
    </Box>
  );
};

export default Footer;