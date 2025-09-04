import React from 'react';
import { AppBar, Toolbar, Typography, Button } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import HomeIcon from '@mui/icons-material/Home';
import { APP_CONFIG } from '../config/app';

const Header: React.FC = () => {
  const navigate = useNavigate();

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
        <Button color="inherit" onClick={() => navigate('/updates')}>
          更新情報
        </Button>
        <Button color="inherit" onClick={() => navigate('/admin')}>
          管理画面
        </Button>
      </Toolbar>
    </AppBar>
  );
};

export default Header;