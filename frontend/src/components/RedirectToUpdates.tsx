import React, { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

interface RedirectToUpdatesProps {
  defaultTab: number;
}

const RedirectToUpdates: React.FC<RedirectToUpdatesProps> = ({ defaultTab }) => {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // 現在のクエリパラメータを保持しつつ、新しいURLにリダイレクト
    const searchParams = new URLSearchParams(location.search);
    searchParams.set('tab', defaultTab.toString());
    navigate(`/updates?${searchParams.toString()}`, { replace: true });
  }, [navigate, location.search, defaultTab]);

  return null;
};

export default RedirectToUpdates;