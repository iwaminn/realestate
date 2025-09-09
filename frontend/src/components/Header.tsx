import React, { useState } from 'react';
import { AppBar, Toolbar, Typography, Button, Box } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import HomeIcon from '@mui/icons-material/Home';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import LoginIcon from '@mui/icons-material/Login';
import { APP_CONFIG } from '../config/app';
import { useUserAuth } from '../contexts/UserAuthContext';
import { UserMenu } from './UserMenu';
import { LoginModal } from './LoginModal';

const Header: React.FC = () => {
  const navigate = useNavigate();
  const { isAuthenticated, user } = useUserAuth();
  const [showLoginModal, setShowLoginModal] = useState(false);

  return (
    <AppBar position="static">
      <Toolbar>
        <HomeIcon sx={{ mr: 2 }} />
        <Typography 
          variant="h6" 
          component="div" 
          sx={{ flexGrow: 1, cursor: 'pointer' }}
          onClick={() => navigate('/')}
        >
{APP_CONFIG.APP_NAME}
        </Typography>
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
      </Toolbar>
      
      <LoginModal 
        open={showLoginModal} 
        onClose={() => setShowLoginModal(false)} 
      />
    </AppBar>
  );
};

export default Header;