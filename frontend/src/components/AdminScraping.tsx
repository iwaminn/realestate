import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Button,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  LinearProgress,
  IconButton,
  Tooltip,
  Checkbox,
  FormControlLabel,
  FormGroup,
  Collapse,
  List,
  ListItem,
  ListItemText,
  Tabs,
  Tab,
  Autocomplete,
  CircularProgress,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Pause as PauseIcon,
  Refresh as RefreshIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Delete as DeleteIcon,
} from '@mui/icons-material';
import axios from 'axios';
import DeleteConfirmDialog from './DeleteConfirmDialog';

interface Area {
  code: string;
  name: string;
}

interface ScrapingTask {
  task_id: string;
  type?: 'serial' | 'parallel';
  status: string;
  scrapers: string[];
  area_codes: string[];
  max_properties: number;
  started_at: string;
  completed_at: string | null;
  created_at?: string;
  progress: {
    [key: string]: {
      scraper: string;
      area?: string;  // 並列タスクで使用
      area_code: string;
      area_name: string;
      status: string;
      properties_scraped: number;
      new_listings: number;
      updated_listings?: number;  // 旧フィールド（互換性のため）
      price_updated?: number;  // 価格更新
      refetched_unchanged?: number;  // 再取得（変更なし）
      other_updates?: number;  // その他更新
      skipped_listings: number;
      // 並列タスクのフィールド
      processed?: number;
      new?: number;
      updated?: number;
      errors?: number;
      // 詳細統計
      properties_found?: number;
      properties_processed?: number;
      properties_attempted?: number;
      detail_fetched?: number;  // 詳細取得成功数
      detail_skipped?: number;  // 詳細スキップ数
      detail_fetch_failed?: number;
      save_failed?: number;
      price_missing?: number;
      building_info_missing?: number;
      other_errors?: number;
      // 時刻情報
      start_time?: string;
      end_time?: string;
      started_at: string;
      completed_at: string | null;
      error: string | null;
    };
  };
  errors: string[];
  logs?: Array<{
    timestamp: string;
    type: 'new' | 'update';
    scraper: string;
    area: string;
    url: string;
    title: string;
    price: number;
    message: string;
    price_change?: {
      old: number;
      new: number;
    };
  }>;
  error_logs?: Array<{
    timestamp: string;
    scraper: string;
    area?: string;
    area_code?: string;
    url?: string;
    reason?: string;
    building_name?: string;
    price?: string;
    message: string;
  }>;
}

const AdminScraping: React.FC = () => {
  const [areas, setAreas] = useState<Area[]>([]);
  const [selectedAreas, setSelectedAreas] = useState<string[]>(['13103']); // 港区
  const [selectedScrapers, setSelectedScrapers] = useState<string[]>(['suumo']);
  const [maxProperties, setMaxProperties] = useState(100);
  const [tasks, setTasks] = useState<ScrapingTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [selectedTaskLog, setSelectedTaskLog] = useState<string | null>(null);
  const [logTabValues, setLogTabValues] = useState<{ [taskId: string]: number }>({});
  const [loadingButtons, setLoadingButtons] = useState<{ [key: string]: boolean }>({});
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const scraperOptions = [
    { value: 'suumo', label: 'SUUMO' },
    { value: 'homes', label: "LIFULL HOME'S" },
    { value: 'rehouse', label: '三井のリハウス' },
    { value: 'nomu', label: 'ノムコム' },
    { value: 'livable', label: '東急リバブル' },
  ];

  useEffect(() => {
    const init = async () => {
      try {
        await fetchAreas();
        await fetchTasks();
      } catch (error) {
        console.error('初期化エラー:', error);
      }
    };
    init();
  }, []);

  // 自動更新の制御（実行中のタスクがある場合のみ）
  useEffect(() => {
    // ダイアログが開いている場合は自動更新を停止
    if (deleteDialogOpen) {
      return;
    }
    
    if (autoRefreshEnabled) {
      // 実行中のタスクがあるかチェック
      const hasRunningTasks = tasks.some(task => 
        task.status === 'running' || task.status === 'pending' || task.status === 'initializing'
      );
      
      if (hasRunningTasks) {
        // 実行中のタスクのみを更新（5秒ごと）
        const interval = setInterval(() => fetchTasks(true), 5000);
        return () => clearInterval(interval);
      }
    }
  }, [autoRefreshEnabled, tasks, deleteDialogOpen]);

  // ボタン操作中は自動更新を停止
  useEffect(() => {
    const isAnyButtonLoading = Object.values(loadingButtons).some(loading => loading);
    setAutoRefreshEnabled(!isAnyButtonLoading);
  }, [loadingButtons]);

  const fetchAreas = async () => {
    try {
      const response = await axios.get('/api/admin/areas');
      setAreas(response.data.areas);
    } catch (error: any) {
      console.error('Failed to fetch areas:', error);
      if (error.response?.status === 401) {
        setError('認証エラー: 管理画面にログインしてください');
        window.location.href = '/admin/login';
      } else {
        setError(`エリア取得エラー: ${error.message}`);
      }
    }
  };

  const fetchTasks = async (activeOnly: boolean = false, checkStalled: boolean = false) => {
    try {
      // 停止タスクチェック（リクエストされた場合のみ）
      if (checkStalled) {
        try {
          const checkResponse = await axios.post('/api/admin/scraping/check-stalled-tasks', {
            threshold_minutes: 10
          });
          if (checkResponse.data.stalled_tasks > 0) {
            console.log(`${checkResponse.data.stalled_tasks}個の停止タスクを検出してエラーステータスに変更しました`);
          }
        } catch (error) {
          console.error('停止タスクチェックエラー:', error);
        }
      }
      
      // タスク一覧取得
      const url = activeOnly 
        ? '/api/admin/scraping/tasks?active_only=true'
        : '/api/admin/scraping/tasks';
      const response = await axios.get(url);
      
      // 実行中のタスクのみの場合
      if (activeOnly) {
        // 現在のタスクを取得
        const currentTasks = tasks;
        const activeTaskIds = new Set(response.data.map((t: ScrapingTask) => t.task_id));
        
        // 完了したタスクを検出（以前はrunning/pendingだったが、今回activeでない）
        const completedTaskIds = currentTasks
          .filter(task => 
            (task.status === 'running' || task.status === 'pending') && 
            !activeTaskIds.has(task.task_id)
          )
          .map(task => task.task_id);
        
        // 完了したタスクの最終状態を取得
        const finalStates = await Promise.all(
          completedTaskIds.map(async taskId => {
            try {
              const finalResponse = await axios.get(`/api/admin/scraping/tasks/${taskId}`);
              return finalResponse.data;
            } catch (error) {
              console.error(`Failed to fetch final state for task ${taskId}:`, error);
              return null;
            }
          })
        );
        
        // タスクリストを更新
        setTasks(prev => {
          // 既存のタスクを更新
          const updatedTasks = prev.map(existingTask => {
            // アクティブなタスクは最新データで更新
            const activeTask = response.data.find((t: ScrapingTask) => t.task_id === existingTask.task_id);
            if (activeTask) {
              return activeTask;
            }
            
            // 完了したタスクは最終状態で更新
            const finalState = finalStates.find(fs => fs && fs.task_id === existingTask.task_id);
            if (finalState) {
              return finalState;
            }
            
            // その他はそのまま保持
            return existingTask;
          });
          
          // 新しいアクティブタスクを追加
          const existingTaskIds = new Set(prev.map(t => t.task_id));
          const newTasks = response.data.filter((t: ScrapingTask) => !existingTaskIds.has(t.task_id));
          
          return [...updatedTasks, ...newTasks];
        });
      } else {
        // 初回または手動更新時は全タスクを取得
        // 並列タスクの詳細情報は既にバックエンドで含まれているため、追加のAPIリクエストは不要
        setTasks(response.data);
      }
    } catch (error: any) {
      console.error('Failed to fetch tasks:', error);
      // エラーの詳細を設定
      if (error.response?.status === 401) {
        setError('認証エラー: 管理画面にログインしてください');
        // ログインページにリダイレクト
        window.location.href = '/admin/login';
      } else if (error.response?.data?.detail) {
        setError(`APIエラー: ${error.response.data.detail}`);
      } else {
        setError(`タスク取得エラー: ${error.message}`);
      }
      // エラー時は空の配列をセット
      setTasks([]);
    }
  };

  const startScraping = async () => {
    if (selectedScrapers.length === 0) {
      alert('少なくとも1つのスクレイパーを選択してください');
      return;
    }
    
    if (selectedAreas.length === 0) {
      alert('少なくとも1つのエリアを選択してください');
      return;
    }

    setLoading(true);
    try {
      // 常に並列実行を使用
      const response = await axios.post('/api/admin/scraping/start-parallel', {
        scrapers: selectedScrapers,
        area_codes: selectedAreas,
        max_properties: maxProperties,
      });
      
      // 新しいタスクを追加
      setTasks(prev => [response.data, ...prev]);
      
      // 展開状態に追加
      setExpandedTasks(prev => new Set([...prev, response.data.task_id]));
    } catch (error) {
      console.error('Failed to start scraping:', error);
      alert('スクレイピングの開始に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  const pauseTask = async (taskId: string) => {
    setLoadingButtons(prev => ({ ...prev, [`pause-${taskId}`]: true }));
    try {
      // APIコールを実行（すべて並列動作）
      const endpoint = `/api/admin/scraping/pause-parallel/${taskId}`;
      await axios.post(endpoint);
      
      // タスク状態が更新されるまでポーリング
      let attempts = 0;
      const maxAttempts = 20; // 最大10秒間チェック
      
      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 500));
        const response = await axios.get('/api/admin/scraping/tasks');
        const updatedTask = response.data.find((t: ScrapingTask) => t.task_id === taskId);
        
        if (updatedTask && updatedTask.status === 'paused') {
          setTasks(response.data);
          break;
        }
        attempts++;
      }
      
      if (attempts >= maxAttempts) {
        console.warn(`Task ${taskId} did not pause within timeout`);
        fetchTasks(); // 最終的に一度更新
      }
    } catch (error: any) {
      console.error('Failed to pause task:', error);
      alert(`タスクの一時停止に失敗しました: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoadingButtons(prev => ({ ...prev, [`pause-${taskId}`]: false }));
    }
  };

  const resumeTask = async (taskId: string) => {
    setLoadingButtons(prev => ({ ...prev, [`resume-${taskId}`]: true }));
    try {
      // APIコールを実行（すべて並列動作）
      const endpoint = `/api/admin/scraping/resume-parallel/${taskId}`;
      await axios.post(endpoint);
      
      // タスク状態が更新されるまでポーリング
      let attempts = 0;
      const maxAttempts = 20; // 最大10秒間チェック
      
      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 500));
        const response = await axios.get('/api/admin/scraping/tasks');
        const updatedTask = response.data.find((t: ScrapingTask) => t.task_id === taskId);
        
        if (updatedTask && updatedTask.status === 'running') {
          setTasks(response.data);
          break;
        }
        attempts++;
      }
      
      if (attempts >= maxAttempts) {
        console.warn(`Task ${taskId} did not resume within timeout`);
        fetchTasks(); // 最終的に一度更新
      }
    } catch (error) {
      console.error('Failed to resume task:', error);
      alert('タスクの再開に失敗しました');
    } finally {
      setLoadingButtons(prev => ({ ...prev, [`resume-${taskId}`]: false }));
    }
  };

  const cancelTask = async (taskId: string) => {
    if (!confirm('タスクをキャンセルしてもよろしいですか？')) {
      return;
    }
    setLoadingButtons(prev => ({ ...prev, [`cancel-${taskId}`]: true }));
    try {
      // APIコールを実行（すべて並列動作）
      const endpoint = `/api/admin/scraping/cancel-parallel/${taskId}`;
      await axios.post(endpoint);
      
      // タスク状態が更新されるまでポーリング
      let attempts = 0;
      const maxAttempts = 20; // 最大10秒間チェック
      
      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 500));
        const tasksResponse = await axios.get('/api/admin/scraping/tasks');
        const updatedTask = tasksResponse.data.find((t: ScrapingTask) => t.task_id === taskId);
        
        if (updatedTask && (updatedTask.status === 'cancelled' || updatedTask.status === 'completed')) {
          setTasks(tasksResponse.data);
          break;
        }
        attempts++;
      }
      
      if (attempts >= maxAttempts) {
        console.warn(`Task ${taskId} did not cancel within timeout`);
        fetchTasks(); // 最終的に一度更新
      }
    } catch (error: any) {
      console.error('Failed to cancel task:', error);
      alert(`タスクのキャンセルに失敗しました: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoadingButtons(prev => ({ ...prev, [`cancel-${taskId}`]: false }));
    }
  };

  const deleteTask = async (taskId: string) => {
    if (!confirm('タスクを削除してもよろしいですか？')) {
      return;
    }
    setLoadingButtons(prev => ({ ...prev, [`delete-${taskId}`]: true }));
    try {
      await axios.delete(`/api/admin/scraping/tasks/${taskId}`);
      
      // タスクリストからすぐに削除
      setTasks(prev => prev.filter(t => t.task_id !== taskId));
      
      // 念のため最新のタスクリストを取得
      await fetchTasks();
      
    } catch (error: any) {
      console.error('Failed to delete task:', error);
      alert(`タスクの削除に失敗しました: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoadingButtons(prev => ({ ...prev, [`delete-${taskId}`]: false }));
    }
  };

  const deleteAllTasks = () => {
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    setDeleteDialogOpen(false);
    setLoading(true);
    
    try {
      const response = await axios.delete('/api/admin/scraping/all-tasks');
      alert(`${response.data.deleted_tasks}件のタスクと${response.data.deleted_progress}件の進捗情報を削除しました`);
      await fetchTasks();
    } catch (error: any) {
      console.error('Failed to delete all tasks:', error);
      alert(`履歴の削除に失敗しました: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteDialogOpen(false);
  };

  const toggleTaskExpansion = (taskId: string) => {
    setExpandedTasks(prev => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  };

  const getStatusColor = (status: string): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' => {
    switch (status) {
      case 'pending': return 'default';
      case 'running': return 'primary';
      case 'paused': return 'warning';
      case 'completed': return 'success';
      case 'failed': return 'error';
      case 'cancelled': return 'secondary';
      default: return 'default';
    }
  };

  const getAreaName = (areaCode: string) => {
    const area = areas.find(a => a.code === areaCode);
    return area ? area.name : areaCode;
  };
  
  const getAreaNames = (areaCodes: string[]) => {
    return areaCodes.map(code => getAreaName(code)).join('、');
  };

  const calculateProgress = (task: ScrapingTask) => {
    // 並列タスクの場合、統計情報から進捗を計算
    if (task.type === 'parallel' && (task as any).statistics) {
      const stats = (task as any).statistics;
      if (task.status === 'completed') return 100;
      if (task.status === 'cancelled') return 100;
      
      // 処理済み数 / 予想総数で計算
      const expectedTotal = task.scrapers.length * task.area_codes.length * task.max_properties;
      const processed = stats.total_processed || 0;
      return Math.min((processed / expectedTotal) * 100, 99);
    }
    
    // 従来の直列タスクの計算
    const progressItems = Object.values(task.progress);
    if (progressItems.length === 0) return 0;
    
    const expectedTotal = task.scrapers.length * task.area_codes.length;

    const totalProgress = progressItems.reduce((sum, progress) => {
      if (progress.status === 'completed') return sum + 100;
      if (progress.status === 'running' || progress.status === 'paused') {
        // 処理予定数（発見数と上限数の小さい方）を分母として使用
        const denominator = progress.properties_processed || progress.properties_found || task.max_properties;
        const attemptedRatio = (progress.properties_attempted || 0) / denominator;
        return sum + Math.min(attemptedRatio * 100, 95);
      }
      return sum;
    }, 0);

    return totalProgress / expectedTotal;
  };
  
  const getTaskStats = (task: ScrapingTask) => {
    // 並列タスクの場合、統計情報から取得
    if (task.type === 'parallel' && (task as any).statistics) {
      const stats = (task as any).statistics;
      return {
        total: stats.total_processed || 0,
        new: stats.total_new || 0,
        price_updated: stats.total_updated || 0,
        other_updates: 0,
        refetched_unchanged: 0,
        skipped: 0,
        save_failed: stats.total_errors || 0
      };
    }
    
    // 従来の直列タスクの計算
    const progressItems = Object.values(task.progress);
    return progressItems.reduce((stats, progress) => ({
      total: stats.total + (progress.properties_scraped || 0),
      new: stats.new + (progress.new_listings || 0),
      price_updated: stats.price_updated + (progress.price_updated || 0),
      other_updates: stats.other_updates + (progress.other_updates || 0),
      refetched_unchanged: stats.refetched_unchanged + (progress.refetched_unchanged || 0),
      skipped: stats.skipped + (progress.skipped_listings || 0),
      save_failed: stats.save_failed + (progress.save_failed || 0)
    }), { total: 0, new: 0, price_updated: 0, other_updates: 0, refetched_unchanged: 0, skipped: 0, save_failed: 0 });
  };

  const [updatingListingStatus, setUpdatingListingStatus] = useState(false);
  const [listingUpdateResult, setListingUpdateResult] = useState<{
    success: boolean;
    message: string;
    inactive_listings?: number;
    sold_properties?: number;
  } | null>(null);

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
    } catch (error) {
      console.error('Failed to update listing status:', error);
      setListingUpdateResult({
        success: false,
        message: '掲載状態の更新に失敗しました',
      });
    } finally {
      setUpdatingListingStatus(false);
    }
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        スクレイピング管理
      </Typography>
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          掲載状態の手動更新
        </Typography>
        <Alert severity="info" sx={{ mb: 2 }}>
          24時間以上確認されていない掲載を終了扱いにし、すべての掲載が終了した物件を販売終了とします。
        </Alert>
        <Box display="flex" alignItems="center" gap={2}>
          <Button
            variant="contained"
            color="secondary"
            onClick={updateListingStatus}
            disabled={updatingListingStatus}
            startIcon={updatingListingStatus ? <CircularProgress size={20} /> : <RefreshIcon />}
          >
            {updatingListingStatus ? '更新中...' : '掲載状態を更新'}
          </Button>
          {listingUpdateResult && (
            <Alert severity={listingUpdateResult.success ? 'success' : 'error'} sx={{ flex: 1 }}>
              {listingUpdateResult.message}
            </Alert>
          )}
        </Box>
      </Paper>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          新規スクレイピング
        </Typography>
        
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <FormControl fullWidth>
              <InputLabel>エリア</InputLabel>
              <Select
                multiple
                value={selectedAreas}
                onChange={(e) => setSelectedAreas(e.target.value as string[])}
                label="エリア"
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {(selected as string[]).map((value) => (
                      <Chip 
                        key={value} 
                        label={areas.find(a => a.code === value)?.name || value}
                        size="small"
                      />
                    ))}
                  </Box>
                )}
              >
                {areas.map(area => (
                  <MenuItem key={area.code} value={area.code}>
                    <Checkbox checked={selectedAreas.includes(area.code)} />
                    <ListItemText primary={area.name} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} md={4}>
            <FormControl fullWidth>
              <InputLabel>スクレイパー</InputLabel>
              <Select
                multiple
                value={selectedScrapers}
                onChange={(e) => setSelectedScrapers(e.target.value as string[])}
                label="スクレイパー"
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {(selected as string[]).map((value) => (
                      <Chip 
                        key={value} 
                        label={scraperOptions.find(opt => opt.value === value)?.label || value}
                        size="small"
                      />
                    ))}
                  </Box>
                )}
              >
                {scraperOptions.map(option => (
                  <MenuItem key={option.value} value={option.value}>
                    <Checkbox checked={selectedScrapers.includes(option.value)} />
                    <ListItemText primary={option.label} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} md={4}>
            <Autocomplete
              freeSolo
              options={[100, 200, 300, 400, 500, 1000, 2000, 3000, 4000, 5000, 10000]}
              value={maxProperties}
              getOptionLabel={(option) => option.toString()}
              onChange={(_, newValue) => {
                if (typeof newValue === 'number') {
                  setMaxProperties(newValue);
                } else if (typeof newValue === 'string') {
                  const value = parseInt(newValue);
                  if (!isNaN(value) && value > 0 && value <= 10000) {
                    setMaxProperties(value);
                  }
                }
              }}
              onInputChange={(_, newInputValue) => {
                const value = parseInt(newInputValue);
                if (!isNaN(value) && value > 0 && value <= 10000) {
                  setMaxProperties(value);
                }
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="処理上限数"
                  type="number"
                  helperText="一覧ページから発見した物件のうち、処理対象とする最大数"
                  InputProps={{
                    ...params.InputProps,
                    inputProps: {
                      ...params.inputProps,
                      min: 1,
                      max: 10000,
                    },
                  }}
                />
              )}
            />
          </Grid>

          <Grid item xs={12}>
            <Button
              variant="contained"
              startIcon={<PlayIcon />}
              onClick={startScraping}
              disabled={loading || selectedScrapers.length === 0}
              fullWidth
            >
              スクレイピング開始
            </Button>
          </Grid>
        </Grid>
      </Paper>

      <Paper sx={{ p: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">実行中のタスク</Typography>
          <Box display="flex" alignItems="center" gap={1}>
            <Button
              variant="outlined"
              color="error"
              size="small"
              startIcon={<DeleteIcon />}
              onClick={deleteAllTasks}
              disabled={loading || tasks.length === 0}
            >
              すべての履歴を削除
            </Button>
            <Tooltip title="タスク一覧を更新（停止タスクも自動チェック）">
              <IconButton 
                onClick={() => fetchTasks(false, true)}
                color="primary"
              >
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {tasks.length === 0 ? (
          <Alert severity="info">実行中のタスクはありません</Alert>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell width={40}></TableCell>
                  <TableCell>エリア</TableCell>
                  <TableCell>スクレイパー</TableCell>
                  <TableCell>処理上限数</TableCell>
                  <TableCell>ステータス</TableCell>
                  <TableCell>進行状況</TableCell>
                  <TableCell>開始時刻</TableCell>
                  <TableCell align="center">操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tasks.map(task => {
                  return (
                  <React.Fragment key={task.task_id}>
                    <TableRow>
                      <TableCell>
                        <IconButton
                          size="small"
                          onClick={() => toggleTaskExpansion(task.task_id)}
                        >
                          {expandedTasks.has(task.task_id) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                        </IconButton>
                      </TableCell>
                      <TableCell>
                        <Box>
                          {task.area_codes && task.area_codes.length > 2 ? (
                            <Tooltip title={getAreaNames(task.area_codes)}>
                              <span>
                                {getAreaName(task.area_codes[0])} 他{task.area_codes.length - 1}件
                              </span>
                            </Tooltip>
                          ) : (
                            <span>
                              {task.area_codes ? getAreaNames(task.area_codes) : 'N/A'}
                            </span>
                          )}
                        </Box>
                      </TableCell>
                      <TableCell>
                        {task.scrapers ? task.scrapers.map(s => (
                          <Chip key={s} label={s} size="small" sx={{ mr: 0.5 }} />
                        )) : null}
                      </TableCell>
                      <TableCell>{task.max_properties}</TableCell>
                      <TableCell>
                        <Box display="flex" gap={0.5} alignItems="center">
                          <Chip
                            label={task.status}
                            color={getStatusColor(task.status)}
                            size="small"
                          />
                        </Box>
                      </TableCell>
                      <TableCell sx={{ minWidth: 200 }}>
                        <Box>
                          <Box display="flex" alignItems="center" mb={0.5}>
                            <LinearProgress
                              variant="determinate"
                              value={calculateProgress(task)}
                              sx={{ flexGrow: 1, mr: 1 }}
                            />
                            <Typography variant="caption">
                              {Math.round(calculateProgress(task))}%
                            </Typography>
                          </Box>
                          <Box display="flex" gap={1} flexWrap="wrap">
                            {(() => {
                              const stats = getTaskStats(task);
                              
                              return (
                                <>
                                  <Typography variant="caption" color="success.main">
                                    新規: {stats.new}
                                  </Typography>
                                  <Typography variant="caption" color="info.main">
                                    価格更新: {stats.price_updated}
                                  </Typography>
                                  <Typography variant="caption" color="primary.main">
                                    その他: {stats.other_updates}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    変更なし: {stats.refetched_unchanged}
                                  </Typography>
                                  {stats.save_failed > 0 && (
                                    <Typography variant="caption" color="error.main">
                                      保存失敗: {stats.save_failed}
                                    </Typography>
                                  )}
                                </>
                              );
                            })()}
                          </Box>
                        </Box>
                      </TableCell>
                      <TableCell>
                        {task.started_at ? new Date(task.started_at).toLocaleString('ja-JP') : 
                         task.created_at ? new Date(task.created_at).toLocaleString('ja-JP') :
                         'N/A'}
                      </TableCell>
                      <TableCell align="center">
                        {task.status === 'running' && (
                          <Tooltip title="一時停止">
                            <span>
                              <IconButton
                                size="small"
                                color="primary"
                                onClick={() => pauseTask(task.task_id)}
                                disabled={loadingButtons[`pause-${task.task_id}`]}
                                sx={{ 
                                  '&:hover': { backgroundColor: 'action.hover' },
                                  transition: 'all 0.3s'
                                }}
                              >
                                {loadingButtons[`pause-${task.task_id}`] ? (
                                  <CircularProgress size={20} />
                                ) : (
                                  <PauseIcon />
                                )}
                              </IconButton>
                            </span>
                          </Tooltip>
                        )}
                        {task.status === 'paused' && (
                          <>
                            <Tooltip title="再開">
                              <span>
                                <IconButton
                                  size="small"
                                  color="primary"
                                  onClick={() => resumeTask(task.task_id)}
                                  disabled={loadingButtons[`resume-${task.task_id}`]}
                                  sx={{ 
                                    '&:hover': { backgroundColor: 'action.hover' },
                                    transition: 'all 0.3s'
                                  }}
                                >
                                  {loadingButtons[`resume-${task.task_id}`] ? (
                                    <CircularProgress size={20} />
                                  ) : (
                                    <PlayIcon />
                                  )}
                                </IconButton>
                              </span>
                            </Tooltip>
                            <Tooltip title="キャンセル">
                              <span>
                                <IconButton
                                  size="small"
                                  color="error"
                                  onClick={() => cancelTask(task.task_id)}
                                  disabled={loadingButtons[`cancel-${task.task_id}`]}
                                  sx={{ 
                                    '&:hover': { backgroundColor: 'action.hover' },
                                    transition: 'all 0.3s'
                                  }}
                                >
                                  {loadingButtons[`cancel-${task.task_id}`] ? (
                                    <CircularProgress size={20} />
                                  ) : (
                                    <StopIcon />
                                  )}
                                </IconButton>
                              </span>
                            </Tooltip>
                          </>
                        )}
                        {(task.status === 'completed' || task.status === 'cancelled' || task.status === 'error') && (
                          <Tooltip title="削除">
                            <span>
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => deleteTask(task.task_id)}
                                disabled={loadingButtons[`delete-${task.task_id}`]}
                                sx={{ 
                                  '&:hover': { backgroundColor: 'action.hover' },
                                  transition: 'all 0.3s'
                                }}
                              >
                                {loadingButtons[`delete-${task.task_id}`] ? (
                                  <CircularProgress size={20} />
                                ) : (
                                  <DeleteIcon />
                                )}
                              </IconButton>
                            </span>
                          </Tooltip>
                        )}
                      </TableCell>
                    </TableRow>
                    
                    <TableRow>
                      <TableCell colSpan={8} sx={{ py: 0 }}>
                        <Collapse in={expandedTasks.has(task.task_id)}>
                          <Box sx={{ p: 2 }}>
                            <Tabs 
                              value={logTabValues[task.task_id] || 0} 
                              onChange={(e, v) => setLogTabValues(prev => ({ ...prev, [task.task_id]: v }))} 
                              sx={{ mb: 2 }}
                            >
                              <Tab label="詳細情報" />
                              <Tab label="ログ" disabled={!task.logs || task.logs.length === 0} />
                              <Tab 
                                label="エラーログ" 
                                disabled={!task.error_logs || task.error_logs.length === 0} 
                              />
                            </Tabs>
                            
                            {(logTabValues[task.task_id] || 0) === 0 && (
                              <Grid container spacing={2}>
                              {(() => {
                                if (!task.progress) {
                                  return <Typography>進捗情報がありません</Typography>;
                                }
                                // スクレイパーの順序を保持するため、task.scrapersの順序でソート
                                const sortedProgress = Object.entries(task.progress).sort(([keyA], [keyB]) => {
                                  const scraperA = keyA.split('_')[0];
                                  const scraperB = keyB.split('_')[0];
                                  const indexA = task.scrapers.indexOf(scraperA);
                                  const indexB = task.scrapers.indexOf(scraperB);
                                  // scrapers配列の順序でソート
                                  if (indexA !== indexB) return indexA - indexB;
                                  // 同じスクレイパーの場合はエリアでソート
                                  return keyA.localeCompare(keyB);
                                });
                                return sortedProgress.map(([key, progress]) => (
                                <Grid item xs={12} md={4} key={key}>
                                  <Paper variant="outlined" sx={{ p: 2 }}>
                                    <Box component="div" fontWeight="medium" fontSize="0.875rem" gutterBottom>
                                      {progress.scraper || 'N/A'} - {progress.area || progress.area_name || 'N/A'}
                                    </Box>
                                    <List dense>
                                      <ListItem>
                                        <ListItemText
                                          primary="ステータス"
                                          secondary={
                                            <Chip
                                              label={
                                                // タスクが一時停止中で、スクレイパーが実行中またはペンディングの場合はpausedを表示
                                                task.status === 'paused' && (progress.status === 'running' || progress.status === 'pending') 
                                                  ? 'paused' 
                                                  // タスクがキャンセル済みで、スクレイパーが実行中の場合はcancelledを表示
                                                  : task.status === 'cancelled' && progress.status === 'running'
                                                  ? 'cancelled'
                                                  : progress.status
                                              }
                                              color={getStatusColor(
                                                task.status === 'paused' && (progress.status === 'running' || progress.status === 'pending')
                                                  ? 'paused'
                                                  : task.status === 'cancelled' && progress.status === 'running'
                                                  ? 'cancelled'
                                                  : progress.status
                                              )}
                                              size="small"
                                            />
                                          }
                                        />
                                      </ListItem>
                                      {/* 詳細統計 */}
                                      {true && (
                                        <>
                                          <ListItem>
                                            <ListItemText
                                              primary="処理進捗"
                                              secondary={
                                                <Box>
                                                  <Box color="text.secondary">
                                                    一覧ページから発見: {progress.properties_found || 0}件
                                                  </Box>
                                                  <Box color="text.secondary">
                                                    処理状況: {progress.properties_attempted || 0} / {progress.properties_processed || progress.properties_found || task.max_properties} 件
                                                    {(progress.properties_processed || progress.properties_found || task.max_properties) > 0 && (
                                                      <span style={{ marginLeft: '8px', color: '#666' }}>
                                                        ({Math.round(((progress.properties_attempted || 0) / (progress.properties_processed || progress.properties_found || task.max_properties)) * 100)}%)
                                                      </span>
                                                    )}
                                                  </Box>
                                                  <Box color="text.secondary">
                                                    詳細取得成功: {progress.detail_fetched || 0}件
                                                  </Box>
                                                  <Box color="text.secondary">
                                                    詳細スキップ: {progress.detail_skipped || progress.skipped_listings || 0}件
                                                  </Box>
                                                  <Box color="text.secondary">
                                                    エラー: {progress.errors || ((progress.detail_fetch_failed || 0) + (progress.save_failed || 0) + (progress.other_errors || 0))}件
                                                  </Box>
                                                </Box>
                                              }
                                            />
                                          </ListItem>
                                          <ListItem>
                                            <ListItemText
                                              primary="詳細取得した物件の内訳"
                                              secondary={
                                                <Box>
                                                  <Box sx={{ pl: 2 }}>
                                                    <Box color="success.main">
                                                      • 新規登録: {progress.new || progress.new_listings || 0}件
                                                    </Box>
                                                    <Box color="info.main">
                                                      • 価格更新: {progress.price_updated || 0}件
                                                    </Box>
                                                    <Box color="primary.main">
                                                      • その他更新: {progress.other_updates || 0}件
                                                    </Box>
                                                    <Box color="text.secondary">
                                                      • 再取得（変更なし）: {progress.refetched_unchanged || 0}件
                                                    </Box>
                                                  </Box>
                                                </Box>
                                              }
                                            />
                                          </ListItem>
                                          {false && progress.new_listings !== undefined && (
                                            <ListItem>
                                              <ListItemText
                                                primary="詳細取得した物件の内訳"
                                                secondary={
                                                  <Box>
                                                    <Box sx={{ pl: 2 }}>
                                                      <Typography variant="body2" color="success.main">
                                                        • 新規登録: {progress.new_listings || 0}件
                                                      </Typography>
                                                      <Typography variant="body2" color="info.main">
                                                        • 価格更新: {progress.price_updated || 0}件
                                                      </Typography>
                                                      <Typography variant="body2" color="primary.main">
                                                      • その他更新: {progress.other_updates || 0}件
                                                    </Typography>
                                                    <Typography variant="body2" color="text.secondary">
                                                      • 再取得（変更なし）: {progress.refetched_unchanged || 0}件
                                                    </Typography>
                                                  </Box>
                                                </Box>
                                              }
                                            />
                                          </ListItem>
                                          )}
                                          {((progress.detail_fetch_failed || 0) > 0 || 
                                            (progress.save_failed || 0) > 0 || 
                                            (progress.price_missing || 0) > 0 || 
                                            (progress.building_info_missing || 0) > 0 || 
                                            (progress.other_errors || 0) > 0) && (
                                            <ListItem>
                                              <ListItemText
                                                primary="エラー情報"
                                                secondary={
                                                  <Box sx={{ pl: 2 }}>
                                                    {(progress.detail_fetch_failed || 0) > 0 && (
                                                      <>
                                                        <Typography variant="body2" color="error">
                                                          • 詳細取得失敗: {progress.detail_fetch_failed}件
                                                        </Typography>
                                                        <Typography variant="caption" color="text.secondary" sx={{ pl: 3, display: 'block' }}>
                                                          （保存処理はスキップされました）
                                                        </Typography>
                                                      </>
                                                    )}
                                                    {(progress.save_failed || 0) > 0 && (
                                                      <>
                                                        <Typography variant="body2" color="error">
                                                          • 保存失敗: {progress.save_failed}件（詳細取得成功後）
                                                        </Typography>
                                                        <Box sx={{ pl: 3 }}>
                                                          {(progress.price_missing || 0) > 0 && (
                                                            <Typography variant="caption" color="error" display="block">
                                                              └ 価格情報なし: {progress.price_missing}件
                                                            </Typography>
                                                          )}
                                                          {(progress.building_info_missing || 0) > 0 && (
                                                            <Typography variant="caption" color="error" display="block">
                                                              └ 建物名なし: {progress.building_info_missing}件
                                                            </Typography>
                                                          )}
                                                          {(progress.other_errors || 0) > 0 && (
                                                            <Typography variant="caption" color="error" display="block">
                                                              └ その他の必須情報不足: {progress.other_errors}件
                                                            </Typography>
                                                          )}
                                                        </Box>
                                                      </>
                                                    )}
                                                    {/* 保存失敗以外のエラー（将来的な拡張用） */}
                                                    {((progress.price_missing || 0) > 0 || 
                                                      (progress.building_info_missing || 0) > 0 || 
                                                      (progress.other_errors || 0) > 0) && 
                                                     (progress.save_failed || 0) === 0 && (
                                                      <Typography variant="caption" color="warning.main" display="block" sx={{ mt: 1 }}>
                                                        ※ 必須情報不足エラーが検出されましたが、保存失敗が0件です
                                                      </Typography>
                                                    )}
                                                  </Box>
                                                }
                                              />
                                            </ListItem>
                                          )}
                                        </>
                                      )}
                                      {progress.error && (
                                        <ListItem>
                                          <ListItemText
                                            primary="エラー"
                                            secondary={
                                              <Typography variant="caption" color="error">
                                                {progress.error}
                                              </Typography>
                                            }
                                          />
                                        </ListItem>
                                      )}
                                      {/* 開始・終了時刻 */}
                                      {(progress.start_time || progress.end_time) && (
                                        <ListItem>
                                          <ListItemText
                                            primary="実行時間"
                                            secondary={
                                              <Box>
                                                {progress.start_time && (
                                                  <Typography variant="caption" color="text.secondary">
                                                    開始: {new Date(progress.start_time).toLocaleString('ja-JP')}
                                                  </Typography>
                                                )}
                                                {progress.end_time && (
                                                  <Typography variant="caption" color="text.secondary">
                                                    終了: {new Date(progress.end_time).toLocaleString('ja-JP')}
                                                  </Typography>
                                                )}
                                              </Box>
                                            }
                                          />
                                        </ListItem>
                                      )}
                                    </List>
                                  </Paper>
                                </Grid>
                              ));
                              })()}
                              </Grid>
                            )}
                            
                            {(logTabValues[task.task_id] || 0) === 1 && task.logs && (
                              <Box sx={{ maxHeight: 400, overflow: 'auto', bgcolor: 'grey.50', p: 1, borderRadius: 1 }}>
                                <List dense>
                                  {task.logs.slice().reverse().map((log, index) => (
                                    <ListItem key={index} sx={{ 
                                      py: 0.5,
                                      borderBottom: '1px solid',
                                      borderColor: 'grey.200'
                                    }}>
                                      <ListItemText
                                        primary={
                                          <Box display="flex" alignItems="center" gap={1}>
                                            <Typography variant="caption" color="text.secondary">
                                              {new Date(log.timestamp).toLocaleTimeString('ja-JP')}
                                            </Typography>
                                            <Chip
                                              label={log.type === 'new' ? '新規' : '更新'}
                                              size="small"
                                              color={log.type === 'new' ? 'success' : 'info'}
                                              sx={{ height: 20 }}
                                            />
                                            <Typography variant="body2">
                                              {log.message}
                                            </Typography>
                                          </Box>
                                        }
                                        secondary={
                                          <Box>
                                            <Typography variant="caption" component="div" color="text.secondary">
                                              {log.scraper} - {log.area}
                                            </Typography>
                                            {log.price_change && (
                                              <Typography variant="caption" component="div" color="warning.main">
                                                価格変更: {log.price_change.old.toLocaleString()}万円 → {log.price_change.new.toLocaleString()}万円
                                              </Typography>
                                            )}
                                          </Box>
                                        }
                                      />
                                    </ListItem>
                                  ))}
                                </List>
                                {task.logs.length === 0 && (
                                  <Typography variant="body2" color="text.secondary" align="center" py={2}>
                                    ログがありません
                                  </Typography>
                                )}
                              </Box>
                            )}
                            
                            {(logTabValues[task.task_id] || 0) === 2 && (
                              <Box sx={{ maxHeight: 400, overflow: 'auto', bgcolor: 'grey.50', p: 1, borderRadius: 1 }}>
                                {task.error_logs && task.error_logs.length > 0 ? (
                                <List dense>
                                  {task.error_logs.slice().reverse().map((log, index) => (
                                    <ListItem key={index} sx={{ 
                                      py: 0.5,
                                      borderBottom: '1px solid',
                                      borderColor: 'grey.200',
                                      bgcolor: 'error.50'
                                    }}>
                                      <ListItemText
                                        primary={
                                          <Box display="flex" alignItems="center" gap={1}>
                                            <Typography variant="caption" color="text.secondary">
                                              {new Date(log.timestamp).toLocaleTimeString('ja-JP')}
                                            </Typography>
                                            <Chip
                                              label={log.reason}
                                              size="small"
                                              color="error"
                                              sx={{ height: 20 }}
                                            />
                                            <Typography variant="body2" color="error">
                                              {log.message}
                                            </Typography>
                                          </Box>
                                        }
                                        secondary={
                                          <Box>
                                            <Typography variant="caption" component="div" color="text.secondary">
                                              {log.scraper} - {log.area_code || log.area}
                                            </Typography>
                                            {log.building_name && (
                                              <Typography variant="caption" component="div">
                                                建物名: {log.building_name} {log.price && `| 価格: ${log.price}`}
                                              </Typography>
                                            )}
                                            {log.url && (
                                              <Typography variant="caption" component="div">
                                                <a href={log.url} target="_blank" rel="noopener noreferrer" 
                                                   style={{ color: '#1976d2', textDecoration: 'none' }}>
                                                  {log.url}
                                                </a>
                                              </Typography>
                                            )}
                                          </Box>
                                        }
                                      />
                                    </ListItem>
                                  ))}
                                </List>
                                ) : (
                                  <Typography variant="body2" color="text.secondary" align="center" py={2}>
                                    エラーログがありません
                                  </Typography>
                                )}
                              </Box>
                            )}

                            {task.errors.length > 0 && (
                              <Box mt={2}>
                                <Alert severity="error">
                                  <Typography variant="subtitle2" gutterBottom>
                                    エラー
                                  </Typography>
                                  <ul>
                                    {task.errors.map((error, index) => (
                                      <li key={index}>
                                        {typeof error === 'string' 
                                          ? error 
                                          : error.error || JSON.stringify(error)}
                                      </li>
                                    ))}
                                  </ul>
                                </Alert>
                              </Box>
                            )}
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  </React.Fragment>
                )})}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      {/* 削除確認ダイアログ */}
      <DeleteConfirmDialog
        open={deleteDialogOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
      />
    </Box>
  );
};

export default AdminScraping;