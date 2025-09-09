import React, { useState, useEffect } from 'react';
import { IconButton, Tooltip, CircularProgress } from '@mui/material';
import { BookmarkBorder, Bookmark } from '@mui/icons-material';
import { BookmarkService } from '../services/bookmarkService';
import { useUserAuth } from '../contexts/UserAuthContext';
import { LoginModal } from './LoginModal';

interface BookmarkButtonProps {
  propertyId: number;
  initialBookmarked?: boolean;
  size?: 'small' | 'medium' | 'large';
  onBookmarkChange?: (isBookmarked: boolean) => void;
}

export const BookmarkButton: React.FC<BookmarkButtonProps> = ({
  propertyId,
  initialBookmarked = false,
  size = 'medium',
  onBookmarkChange
}) => {
  const { isAuthenticated } = useUserAuth();
  const [isBookmarked, setIsBookmarked] = useState(initialBookmarked);
  const [isLoading, setIsLoading] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);

  // 初期化時にブックマーク状態をチェック
  useEffect(() => {
    const checkInitialStatus = async () => {
      // 未認証の場合は状態チェックをスキップ
      if (!isAuthenticated) {
        setIsBookmarked(false);
        setIsInitialized(true);
        return;
      }

      try {
        const status = await BookmarkService.checkBookmarkStatus(propertyId);
        setIsBookmarked(status.is_bookmarked);
        setIsInitialized(true);
      } catch (error) {
        console.error('ブックマーク状態の初期チェックに失敗:', error);
        setIsBookmarked(false);
        setIsInitialized(true);
      }
    };

    checkInitialStatus();
  }, [propertyId, isAuthenticated]);

  const handleToggleBookmark = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation(); // 親要素のクリックイベントを防止
    
    if (isLoading) return;

    // 未認証の場合はログインモーダルを表示
    if (!isAuthenticated) {
      setShowLoginModal(true);
      return;
    }

    setIsLoading(true);
    try {
      const result = await BookmarkService.toggleBookmark(propertyId);
      const newBookmarkedState = result.action === 'added';
      
      setIsBookmarked(newBookmarkedState);
      onBookmarkChange?.(newBookmarkedState);
      
      console.log(
        newBookmarkedState 
          ? 'ブックマークに追加しました' 
          : 'ブックマークから削除しました'
      );
    } catch (error: any) {
      console.error('ブックマーク操作に失敗:', error);
      
      // 認証エラーの場合はログインモーダルを表示
      if (error.message?.includes('ログイン')) {
        setShowLoginModal(true);
      }
    } finally {
      setIsLoading(false);
    }
  };

  // 初期化中は何も表示しない
  if (!isInitialized) {
    return (
      <IconButton size={size} disabled>
        <CircularProgress size={size === 'small' ? 16 : size === 'medium' ? 20 : 24} />
      </IconButton>
    );
  }

  return (
    <>
      <Tooltip 
        title={
          !isAuthenticated 
            ? 'ログインしてブックマーク' 
            : isBookmarked 
              ? 'ブックマークから削除' 
              : 'ブックマークに追加'
        }
        arrow
      >
        <IconButton 
          onClick={handleToggleBookmark}
          disabled={isLoading}
          size={size}
          sx={{
            color: isBookmarked ? 'error.main' : 'action.disabled',
            '&:hover': {
              color: isBookmarked ? 'error.dark' : 'error.main',
              backgroundColor: 'rgba(244, 67, 54, 0.04)'
            },
            transition: 'all 0.2s ease-in-out'
          }}
        >
          {isLoading ? (
            <CircularProgress 
              size={size === 'small' ? 16 : size === 'medium' ? 20 : 24} 
              color="inherit" 
            />
          ) : isBookmarked ? (
            <Bookmark />
          ) : (
            <BookmarkBorder />
          )}
        </IconButton>
      </Tooltip>
      
      <LoginModal 
        open={showLoginModal} 
        onClose={() => setShowLoginModal(false)} 
      />
    </>
  );
};