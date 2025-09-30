import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  Grid,
  Alert,
  CircularProgress,
  Card,
  CardContent,
  CardActions,
  Chip,
  LinearProgress,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Tooltip,
} from '@mui/material';
import {
  Update as UpdateIcon,
  Schedule as ScheduleIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Refresh as RefreshIcon,
  TrendingUp as TrendingUpIcon,
  Assessment as AssessmentIcon,
} from '@mui/icons-material';
import axios from 'axios';

interface QueueStatus {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
}

interface CacheStats {
  total_cached_changes: number;
  properties_with_changes: number;
  recent_changes_30days: number;
  latest_update: string | null;
  average_changes_per_property: number;
}

interface ListingStats {
  total_active_listings: number;
  total_inactive_listings: number;
  total_sold_properties: number;
  listings_checked_today: number;
  listings_not_checked_24h: number;
  oldest_unchecked_date: string | null;
}

interface TransactionPriceStats {
  total_count: number;
  latest_year: number | null;
  latest_quarter: number | null;
  oldest_year: number | null;
  oldest_quarter: number | null;
  recent_30days_count: number;
  area_count: number;
}

export const DataUpdateManagement: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [listingStats, setListingStats] = useState<ListingStats | null>(null);
  const [updateDialog, setUpdateDialog] = useState(false);
  const [updateType, setUpdateType] = useState<'listings' | 'price_changes'>('listings');
  const [updateDays, setUpdateDays] = useState(90);
  const [message, setMessage] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [updatingListingStatus, setUpdatingListingStatus] = useState(false);
  const [listingUpdateResult, setListingUpdateResult] = useState<{
    success: boolean;
    message: string;
    inactive_listings?: number;
    sold_properties?: number;
  } | null>(null);
  const [transactionPriceStats, setTransactionPriceStats] = useState<TransactionPriceStats | null>(null);
  const [updatingTransactionPrices, setUpdatingTransactionPrices] = useState(false);

  // キューステータスを取得
  const fetchQueueStatus = async () => {
    try {
      const response = await axios.get('/api/admin/price-changes/queue-status');
      setQueueStatus(response.data.queue_status);
    } catch (error) {
      console.error('キューステータスの取得に失敗:', error);
    }
  };

  // キャッシュ統計を取得
  const fetchCacheStats = async () => {
    try {
      const response = await axios.get('/api/admin/price-changes/cache-stats');
      setCacheStats(response.data);
    } catch (error) {
      console.error('キャッシュ統計の取得に失敗:', error);
    }
  };

  // 掲載状態の統計を取得
  const fetchListingStats = async () => {
    try {
      const response = await axios.get('/api/admin/listing-status-stats');
      setListingStats(response.data);
    } catch (error) {
      console.error('掲載状態統計の取得に失敗:', error);
    }
  };

  // 成約価格統計を取得
  const fetchTransactionPriceStats = async () => {
    try {
      const response = await axios.get('/api/admin/transaction-prices/stats');
      setTransactionPriceStats(response.data);
    } catch (error) {
      console.error('成約価格統計の取得に失敗:', error);
    }
  };

  useEffect(() => {
    fetchQueueStatus();
    fetchCacheStats();
    fetchListingStats();
    fetchTransactionPriceStats();

    // 定期的に更新
    const interval = setInterval(() => {
      fetchQueueStatus();
      fetchCacheStats();
      fetchListingStats();
      fetchTransactionPriceStats();
    }, 30000); // 30秒ごと

    return () => clearInterval(interval);
  }, []);



  // 価格改定日を更新
  const updatePriceChanges = async (immediate: boolean = false) => {
    setLoading(true);
    setMessage(null);
    
    try {
      const endpoint = immediate 
        ? '/api/admin/price-changes/refresh-immediate'
        : '/api/admin/price-changes/refresh-all';
        
      const response = await axios.post(endpoint, null, {
        params: { days: updateDays }
      });
      
      if (immediate) {
        const stats = response.data.stats || response.data.queue_stats;
        setMessage({
          type: 'success',
          text: `価格改定履歴を更新しました。処理件数: ${stats?.processed || 0}`
        });
      } else {
        setMessage({
          type: 'info',
          text: 'バックグラウンドで価格改定履歴の更新を開始しました'
        });
      }
      
      // ステータスを再取得
      await fetchQueueStatus();
      await fetchCacheStats();
      
      // フロントエンドのキャッシュをクリア
      try {
        localStorage.removeItem('recentUpdatesCache');
        console.log('フロントエンドキャッシュをクリアしました');
      } catch (e) {
        console.error('キャッシュクリアに失敗:', e);
      }
    } catch (error) {
      setMessage({
        type: 'error',
        text: '価格改定履歴の更新に失敗しました'
      });
    } finally {
      setLoading(false);
      setUpdateDialog(false);
    }
  };

  // 掲載状態を更新
  const updateListingStatus = async () => {
    if (!confirm('24時間以上確認されていない掲載を終了扱いにしますか？')) {
      return;
    }
    
    setUpdatingListingStatus(true);
    setListingUpdateResult(null);
    
    try {
      const response = await axios.post('/api/admin/update-listing-status');
      setListingUpdateResult({
        success: true,
        message: response.data.message,
        inactive_listings: response.data.inactive_listings,
        sold_properties: response.data.sold_properties,
      });
      setMessage({
        type: 'success',
        text: `掲載状態を更新しました。非掲載: ${response.data.inactive_listings || 0}件、販売終了: ${response.data.sold_properties || 0}件`
      });
      // 統計を再取得
      await fetchListingStats();

      // フロントエンドのキャッシュをクリア
      try {
        localStorage.removeItem('recentUpdatesCache');
        console.log('掲載状態更新後: フロントエンドキャッシュをクリアしました');
      } catch (e) {
        console.error('キャッシュクリアに失敗:', e);
      }
    } catch (error) {
      setListingUpdateResult({
        success: false,
        message: '掲載状態の更新に失敗しました',
      });
      setMessage({
        type: 'error',
        text: '掲載状態の更新に失敗しました'
      });
    } finally {
      setUpdatingListingStatus(false);
    }
  };

  // 成約価格情報を更新
  const updateTransactionPrices = async (mode: 'update' | 'full' = 'update') => {
    if (!confirm(`成約価格情報を${mode === 'full' ? '全期間' : '最新データのみ'}更新しますか？\n更新には数分かかる場合があります。`)) {
      return;
    }

    setUpdatingTransactionPrices(true);

    try {
      const response = await axios.post('/api/admin/transaction-prices/update', null, {
        params: { mode }
      });
      setMessage({
        type: 'success',
        text: response.data.message
      });
      // 統計を再取得
      await fetchTransactionPriceStats();
    } catch (error) {
      setMessage({
        type: 'error',
        text: '成約価格情報の更新に失敗しました'
      });
    } finally {
      setUpdatingTransactionPrices(false);
    }
  };

  // キューを処理
  const processQueue = async () => {
    setLoading(true);
    setMessage(null);
    
    try {
      const response = await axios.post('/api/admin/price-changes/process-queue', null, {
        params: { limit: 1000 }
      });
      
      const stats = response.data.stats;
      setMessage({
        type: 'success',
        text: `キューを処理しました。処理: ${stats.processed}件、失敗: ${stats.failed}件`
      });
      
      // キューステータスとキャッシュ統計を更新
      await fetchQueueStatus();
      await fetchCacheStats();

      // フロントエンドのキャッシュをクリア
      try {
        localStorage.removeItem('recentUpdatesCache');
        console.log('処理キュー実行後: フロントエンドキャッシュをクリアしました');
      } catch (e) {
        console.error('キャッシュクリアに失敗:', e);
      }
    } catch (error) {
      setMessage({
        type: 'error',
        text: 'キューの処理に失敗しました'
      });
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString('ja-JP');
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        データ更新管理
      </Typography>
      
      {message && (
        <Alert severity={message.type} sx={{ mb: 2 }} onClose={() => setMessage(null)}>
          {message.text}
        </Alert>
      )}

      {/* 価格改定履歴セクション */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
          <TrendingUpIcon sx={{ mr: 1 }} color="secondary" />
          価格改定履歴管理
        </Typography>
        
        <Grid container spacing={3}>
          {/* 更新ボタンカード */}
          <Grid item xs={12} md={6}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="subtitle1" gutterBottom fontWeight="bold">
                  価格改定履歴の更新
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  多数決ベースの価格変更を計算し、価格改定日をキャッシュテーブルに保存します。
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  • 複数サイトの価格を統合して判定
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  • 価格改定日を事前計算してキャッシュ
                </Typography>
              </CardContent>
              <CardActions>
                <Button
                  variant="contained"
                  color="secondary"
                  onClick={() => {
                    setUpdateType('price_changes');
                    setUpdateDialog(true);
                  }}
                  disabled={loading}
                  startIcon={loading ? <CircularProgress size={20} /> : <TrendingUpIcon />}
                >
                  価格改定日を更新
                </Button>
              </CardActions>
            </Card>
          </Grid>
          
          {/* 統計情報カード */}
          <Grid item xs={12} md={6}>
            {cacheStats && (
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="subtitle1" gutterBottom fontWeight="bold">
                    キャッシュ統計
                  </Typography>
                  <Box sx={{ mt: 2 }}>
                    <Grid container spacing={2}>
                      <Grid item xs={6}>
                        <Tooltip title="価格変更レコードの総数。各物件の価格変更履歴がすべて含まれます" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              キャッシュ済み
                            </Typography>
                            <Typography variant="h6">
                              {cacheStats.total_cached_changes.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="1回以上価格が変更された物件の総数（ユニーク数）" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              価格改定物件
                            </Typography>
                            <Typography variant="h6">
                              {cacheStats.properties_with_changes.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="過去30日以内に発生した価格変更の件数。最近の市場動向を示します" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              直近30日
                            </Typography>
                            <Typography variant="h6">
                              {cacheStats.recent_changes_30days.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="キャッシュテーブルが最後に更新された日時。データの鮮度を示します" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              最終更新
                            </Typography>
                            <Typography variant="body2">
                              {formatDate(cacheStats.latest_update)}
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                    </Grid>
                  </Box>
                </CardContent>
              </Card>
            )}
          </Grid>
          
          {/* キューステータスカード */}
          {queueStatus && (
            <Grid item xs={12}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle1" gutterBottom fontWeight="bold">
                    処理キューの状態
                  </Typography>
                  <Grid container spacing={3} sx={{ mt: 1 }}>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="h5" color="info.main">
                          {queueStatus.pending}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          待機中
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="h5" color="warning.main">
                          {queueStatus.processing}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          処理中
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="h5" color="success.main">
                          {queueStatus.completed}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          完了
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="h5" color="error.main">
                          {queueStatus.failed}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          失敗
                        </Typography>
                      </Box>
                    </Grid>
                  </Grid>
                  
                  {queueStatus.pending > 0 && (
                    <Box mt={3} display="flex" justifyContent="center">
                      <Button
                        variant="outlined"
                        onClick={processQueue}
                        disabled={loading}
                        startIcon={<RefreshIcon />}
                      >
                        キューを処理 ({queueStatus.pending}件)
                      </Button>
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>
          )}
        </Grid>
      </Box>

      {/* 成約価格情報セクション */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
          <AssessmentIcon sx={{ mr: 1 }} color="info" />
          成約価格情報管理
        </Typography>

        <Grid container spacing={3}>
          {/* 更新ボタンカード */}
          <Grid item xs={12} md={6}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="subtitle1" gutterBottom fontWeight="bold">
                  成約価格情報の更新
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  国土交通省の不動産情報ライブラリAPIから最新の成約価格データを取得します。
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  • 最新データのみ：直近の四半期のみ取得（推奨）
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  • 全期間：すべての期間のデータを再取得
                </Typography>
              </CardContent>
              <CardActions>
                <Button
                  variant="contained"
                  color="info"
                  onClick={() => updateTransactionPrices('update')}
                  disabled={updatingTransactionPrices || loading}
                  startIcon={updatingTransactionPrices ? <CircularProgress size={20} /> : <AssessmentIcon />}
                  sx={{ mr: 1 }}
                >
                  最新データを更新
                </Button>
                <Button
                  variant="outlined"
                  color="info"
                  onClick={() => updateTransactionPrices('full')}
                  disabled={updatingTransactionPrices || loading}
                  size="small"
                >
                  全期間更新
                </Button>
              </CardActions>
            </Card>
          </Grid>

          {/* 統計情報カード */}
          <Grid item xs={12} md={6}>
            {transactionPriceStats && (
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="subtitle1" gutterBottom fontWeight="bold">
                    成約価格統計
                  </Typography>
                  <Box sx={{ mt: 2 }}>
                    <Grid container spacing={2}>
                      <Grid item xs={6}>
                        <Tooltip title="データベースに保存されている成約価格レコードの総数" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              総件数
                            </Typography>
                            <Typography variant="h6">
                              {transactionPriceStats.total_count.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="データベースに含まれる最新の成約時期" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              最新データ
                            </Typography>
                            <Typography variant="body2">
                              {transactionPriceStats.latest_year && transactionPriceStats.latest_quarter
                                ? `${transactionPriceStats.latest_year}年Q${transactionPriceStats.latest_quarter}`
                                : '-'}
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="過去30日以内に取得された成約価格データの件数" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              直近30日追加
                            </Typography>
                            <Typography variant="h6">
                              {transactionPriceStats.recent_30days_count.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="成約データが存在するエリア（町名）の総数" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              対象エリア数
                            </Typography>
                            <Typography variant="h6">
                              {transactionPriceStats.area_count}エリア
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                    </Grid>
                  </Box>
                </CardContent>
              </Card>
            )}
          </Grid>
        </Grid>
      </Box>

      {/* 掲載状態セクション */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
          <UpdateIcon sx={{ mr: 1 }} color="primary" />
          掲載状態管理
        </Typography>
        
        <Grid container spacing={3}>
          {/* 更新ボタンカード */}
          <Grid item xs={12} md={6}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="subtitle1" gutterBottom fontWeight="bold">
                  掲載状態の更新
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  24時間以上確認されていない掲載を終了扱いにし、すべての掲載が終了した物件を販売終了とします。
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  • 古い掲載情報を自動的に非アクティブ化
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  • 販売終了物件の適切な管理
                </Typography>
                {listingStats && listingStats.listings_not_checked_24h > 0 && (
                  <Alert severity="warning" sx={{ mt: 2 }}>
                    {listingStats.listings_not_checked_24h}件の掲載が24時間以上確認されていません
                  </Alert>
                )}
              </CardContent>
              <CardActions>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={updateListingStatus}
                  disabled={updatingListingStatus || loading}
                  startIcon={updatingListingStatus ? <CircularProgress size={20} /> : <RefreshIcon />}
                >
                  {updatingListingStatus ? '更新中...' : '掲載状態を更新'}
                </Button>
              </CardActions>
            </Card>
          </Grid>
          
          {/* 統計情報カード */}
          <Grid item xs={12} md={6}>
            {listingStats && (
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="subtitle1" gutterBottom fontWeight="bold">
                    掲載状態統計
                  </Typography>
                  <Box sx={{ mt: 2 }}>
                    <Grid container spacing={2}>
                      <Grid item xs={6}>
                        <Tooltip title="現在各不動産サイトで公開されている掲載の総数" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              掲載中
                            </Typography>
                            <Typography variant="h6">
                              {listingStats.total_active_listings.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="サイトから削除されたか、24時間以上確認できなかった掲載の総数" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              非掲載
                            </Typography>
                            <Typography variant="h6">
                              {listingStats.total_inactive_listings.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="すべての掲載が終了し、販売完了と判定された物件の総数" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              販売終了
                            </Typography>
                            <Typography variant="h6">
                              {listingStats.total_sold_properties.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="本日のスクレイピングで存在が確認された掲載の数" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              本日確認済み
                            </Typography>
                            <Typography variant="h6">
                              {listingStats.listings_checked_today.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="まだアクティブだが24時間以上確認されていない掲載。更新ボタンで非掲載に変更される候補" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              24時間以上未確認
                            </Typography>
                            <Typography variant="h6">
                              {listingStats.listings_not_checked_24h.toLocaleString()}件
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                      <Grid item xs={6}>
                        <Tooltip title="アクティブな掲載の中で最も長期間確認されていない日時" arrow>
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              最古の未確認
                            </Typography>
                            <Typography variant="body2">
                              {formatDate(listingStats.oldest_unchecked_date)}
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                    </Grid>
                  </Box>
                </CardContent>
              </Card>
            )}
          </Grid>
        </Grid>
      </Box>





      {/* 更新ダイアログ */}
      <Dialog open={updateDialog} onClose={() => setUpdateDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          価格改定履歴の更新
        </DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <FormControl fullWidth sx={{ mb: 2 }}>
              <InputLabel>更新期間</InputLabel>
              <Select
                value={updateDays}
                onChange={(e) => setUpdateDays(Number(e.target.value))}
                label="更新期間"
              >
                <MenuItem value={30}>過去30日</MenuItem>
                <MenuItem value={60}>過去60日</MenuItem>
                <MenuItem value={90}>過去90日</MenuItem>
                <MenuItem value={180}>過去180日</MenuItem>
                <MenuItem value={365}>過去1年</MenuItem>
              </Select>
            </FormControl>
            
            <Alert severity="info">
              キューに入っている物件は全期間が再計算されます。
              それ以外の物件は指定期間のみ更新されます。
            </Alert>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUpdateDialog(false)}>
            キャンセル
          </Button>
          <Button onClick={() => updatePriceChanges(false)} variant="outlined">
            バックグラウンドで実行
          </Button>
          <Button onClick={() => updatePriceChanges(true)} variant="contained" color="primary">
            今すぐ実行
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};