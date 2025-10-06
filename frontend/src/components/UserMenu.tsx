import React, { useState } from 'react';
import {
  IconButton,
  Menu,
  MenuItem,
  Avatar,
  Divider,
  ListItemIcon,
  ListItemText,
  Typography,
  Box
} from '@mui/material';
import {
  Person as PersonIcon,
  Logout as LogoutIcon,
  BookmarkBorder as BookmarkIcon,
  Settings as SettingsIcon
} from '@mui/icons-material';
import { useUserAuth } from '../contexts/UserAuthContext';
import { useNavigate } from 'react-router-dom';

export const UserMenu: React.FC = () => {
  const { user, logout } = useUserAuth();
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);

  const handleClick = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = async () => {
    await logout();
    handleClose();
    // ログアウト後は現在のページに留まる（ページをリロード）
    window.location.reload();
  };

  const handleBookmarks = () => {
    handleClose();
    navigate('/bookmarks');
  };

  const handleSettings = () => {
    handleClose();
    navigate('/account/settings');
  };

  if (!user) return null;

  // アバターのイニシャル（メールアドレスの最初の文字）
  const avatarText = user.email.charAt(0).toUpperCase();

  return (
    <>
      <IconButton
        onClick={handleClick}
        size="small"
        sx={{ ml: 2 }}
        aria-controls={open ? 'user-menu' : undefined}
        aria-haspopup="true"
        aria-expanded={open ? 'true' : undefined}
      >
        <Avatar sx={{ 
          width: 32, 
          height: 32, 
          bgcolor: 'white',
          color: 'primary.main'
        }}>
          {avatarText}
        </Avatar>
      </IconButton>
      
      <Menu
        id="user-menu"
        anchorEl={anchorEl}
        open={open}
        onClose={handleClose}
        onClick={handleClose}
        PaperProps={{
          elevation: 0,
          sx: {
            overflow: 'visible',
            filter: 'drop-shadow(0px 2px 8px rgba(0,0,0,0.32))',
            mt: 1.5,
            minWidth: 200,
            '& .MuiAvatar-root': {
              width: 32,
              height: 32,
              ml: -0.5,
              mr: 1,
            },
            '&:before': {
              content: '""',
              display: 'block',
              position: 'absolute',
              top: 0,
              right: 14,
              width: 10,
              height: 10,
              bgcolor: 'background.paper',
              transform: 'translateY(-50%) rotate(45deg)',
              zIndex: 0,
            },
          },
        }}
        transformOrigin={{ horizontal: 'right', vertical: 'top' }}
        anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
      >
        {/* ユーザー情報表示 */}
        <Box sx={{ px: 2, py: 1 }}>
          <Typography variant="body2" color="textSecondary" noWrap>
            {user.email}
          </Typography>
        </Box>
        
        <Divider />
        
        {/* ブックマーク */}
        <MenuItem onClick={handleBookmarks}>
          <ListItemIcon>
            <BookmarkIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>ブックマーク</ListItemText>
        </MenuItem>
        
        {/* アカウント設定 */}
        <MenuItem onClick={handleSettings}>
          <ListItemIcon>
            <SettingsIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>アカウント設定</ListItemText>
        </MenuItem>
        
        <Divider />
        
        {/* ログアウト */}
        <MenuItem onClick={handleLogout}>
          <ListItemIcon>
            <LogoutIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>ログアウト</ListItemText>
        </MenuItem>
      </Menu>
    </>
  );
};