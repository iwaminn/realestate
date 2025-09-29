import React, { useState } from 'react';
import { 
  AppBar, 
  Toolbar, 
  Typography, 
  Button, 
  Box,
  IconButton,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Divider,
  useTheme,
  useMediaQuery
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import HomeIcon from '@mui/icons-material/Home';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import LoginIcon from '@mui/icons-material/Login';
import MenuIcon from '@mui/icons-material/Menu';
import UpdateIcon from '@mui/icons-material/Update';
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings';
import SearchIcon from '@mui/icons-material/Search';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import { APP_CONFIG } from '../config/app';
import { useUserAuth } from '../contexts/UserAuthContext';
import { UserMenu } from './UserMenu';
import { LoginModal } from './LoginModal';

const Header: React.FC = () => {
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const { isAuthenticated, user } = useUserAuth();
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleMobileMenuToggle = () => {
    setMobileMenuOpen(!mobileMenuOpen);
  };

  const handleNavigate = (path: string) => {
    navigate(path);
    setMobileMenuOpen(false);
  };

  const menuItems = [
    { text: '物件検索', icon: <SearchIcon />, path: '/' },
    { text: 'ブックマーク', icon: <BookmarkIcon />, path: '/bookmarks' },
    { text: '更新情報', icon: <UpdateIcon />, path: '/updates' },
    { text: '取引価格', icon: <TrendingUpIcon />, path: '/transaction-prices' },
    { text: '管理画面', icon: <AdminPanelSettingsIcon />, path: '/admin' },
  ];

  return (
    <>
      <AppBar position="static">
        <Toolbar>
          <HomeIcon sx={{ mr: 2 }} />
          <Typography 
            variant="h6" 
            component="div" 
            sx={{ 
              flexGrow: 1, 
              cursor: 'pointer',
              fontSize: { xs: '1rem', sm: '1.25rem' }
            }}
            onClick={() => navigate('/')}
          >
            {APP_CONFIG.APP_NAME}
          </Typography>

          {/* デスクトップメニュー */}
          {!isMobile && (
            <>
              <Button color="inherit" onClick={() => navigate('/')}>
                物件検索
              </Button>
              <Button 
                color="inherit" 
                onClick={() => navigate('/bookmarks')}
                startIcon={<BookmarkIcon />}
              >
                ブックマーク
              </Button>
              <Button color="inherit" onClick={() => navigate('/updates')}>
                更新情報
              </Button>
              <Button color="inherit" onClick={() => navigate('/transaction-prices')}>
                取引価格
              </Button>
              <Button color="inherit" onClick={() => navigate('/admin')}>
                管理画面
              </Button>

              {/* ユーザー認証部分 */}
              <Box sx={{ ml: 2 }}>
                {isAuthenticated ? (
                  <UserMenu />
                ) : (
                  <Button 
                    color="inherit" 
                    onClick={() => setShowLoginModal(true)}
                    startIcon={<LoginIcon />}
                  >
                    ログイン
                  </Button>
                )}
              </Box>
            </>
          )}

          {/* モバイルメニューボタン */}
          {isMobile && (
            <>
              {/* ユーザー認証部分（モバイル） */}
              {isAuthenticated ? (
                <UserMenu />
              ) : (
                <IconButton
                  color="inherit"
                  onClick={() => setShowLoginModal(true)}
                  sx={{ mr: 1 }}
                >
                  <LoginIcon />
                </IconButton>
              )}
              <IconButton
                color="inherit"
                edge="end"
                onClick={handleMobileMenuToggle}
              >
                <MenuIcon />
              </IconButton>
            </>
          )}
        </Toolbar>
      </AppBar>

      {/* モバイルメニュードロワー */}
      <Drawer
        anchor="right"
        open={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
      >
        <Box
          sx={{ width: 250 }}
          role="presentation"
        >
          <List>
            {menuItems.map((item) => (
              <ListItem key={item.text} disablePadding>
                <ListItemButton onClick={() => handleNavigate(item.path)}>
                  <ListItemIcon>
                    {item.icon}
                  </ListItemIcon>
                  <ListItemText primary={item.text} />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
          
          {!isAuthenticated && (
            <>
              <Divider />
              <List>
                <ListItem disablePadding>
                  <ListItemButton onClick={() => {
                    setShowLoginModal(true);
                    setMobileMenuOpen(false);
                  }}>
                    <ListItemIcon>
                      <LoginIcon />
                    </ListItemIcon>
                    <ListItemText primary="ログイン" />
                  </ListItemButton>
                </ListItem>
              </List>
            </>
          )}
        </Box>
      </Drawer>
      
      <LoginModal 
        open={showLoginModal} 
        onClose={() => setShowLoginModal(false)} 
      />
    </>
  );
};

export default Header;