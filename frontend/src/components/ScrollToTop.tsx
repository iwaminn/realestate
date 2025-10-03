import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * ページ遷移時に画面を先頭にスクロールするコンポーネント
 */
const ScrollToTop: React.FC = () => {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
};

export default ScrollToTop;
