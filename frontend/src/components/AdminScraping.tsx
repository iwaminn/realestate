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
  ListItemSecondaryAction,
  Tabs,
  Tab,
  Autocomplete,
  CircularProgress,
  Pagination,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Pause as PauseIcon,
  Refresh as RefreshIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Delete as DeleteIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import axios from 'axios';
import '../utils/axiosConfig';
import DeleteConfirmDialog from './DeleteConfirmDialog';

interface Area {
  code: string;
  name: string;
}

interface ScraperAlert {
  id: number;
  scraper_name?: string;  // 新しいAPIレスポンス用
  source_site?: string;   // 後方互換性のため残す
  alert_type: string;
  severity?: string;
  message: string;
  details: {
    task_id?: string;
    status?: string;
    error_message?: string;
    field_name?: string;
    error_count?: number;
    error_rate?: number;
    threshold?: any;
  } | null;
  is_active?: boolean;
  resolved_at: string | null;
  resolved_by?: string | null;
  created_at: string;
  updated_at?: string | null;
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
  // 並列タスクの統計情報（task直下）
  total_processed?: number;
  total_new?: number;
  total_updated?: number;
  total_errors?: number;
  properties_found?: number;
  detail_fetched?: number;
  detail_skipped?: number;
  price_missing?: number;
  building_info_missing?: number;
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
      refetched_unchanged?: number;  // 変更なし
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
    type: 'new' | 'update' | 'price_updated' | 'other_updates' | 'refetched_unchanged';
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
    update_details?: string;
  }>;
  error_logs?: Array<{
    timestamp: string;
    scraper: string;
    area?: string;
    area_code?: string;
    url?: string;
    reason: string;
    building_name?: string;
    price?: string;
  }>;
  warning_logs?: Array<{
    timestamp: string;
    scraper: string;
    area?: string;
    area_code?: string;
    url?: string;
    reason?: string;
    building_name?: string;
    price?: string;
    site_property_id?: string;
    message?: string;
  }>;
}

const AdminScraping: React.FC = () => {
  const [areas, setAreas] = useState<Area[]>([]);
  const [selectedAreas, setSelectedAreas] = useState<string[]>(['13103']); // 港区
  const [selectedScrapers, setSelectedScrapers] = useState<string[]>(['suumo']);
  const [maxProperties, setMaxProperties] = useState(100);
  const [detailRefetchHours, setDetailRefetchHours] = useState<number>(2160); // デフォルト90日（2160時間）
  const [useCustomRefetch, setUseCustomRefetch] = useState(false);
  const [ignoreErrorHistory, setIgnoreErrorHistory] = useState(false); // 404/検証エラー履歴を無視するオプション
  const [tasks, setTasks] = useState<ScrapingTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [selectedTaskLog, setSelectedTaskLog] = useState<string | null>(null);
  const [logTabValues, setLogTabValues] = useState<{ [taskId: string]: number }>({});
  const [loadingButtons, setLoadingButtons] = useState<{ [key: string]: boolean }>({});
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteDialogMessage, setDeleteDialogMessage] = useState('');
  const [alerts, setAlerts] = useState<ScraperAlert[]>([]);
  const [logPages, setLogPages] = useState<{ [taskId: string]: number }>({});  // 各タスクのログページ番号

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
        await fetchAlerts();
      } catch (error) {
        // エラーは既にsetErrorで処理されている
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
      // エラーは既にsetErrorで処理されている
      if (error.response?.status === 401) {
        setError('認証エラー: 管理画面にログインしてください');
        window.location.href = '/admin/login';
      } else {
        setError(`エリア取得エラー: ${error.message}`);
      }
    }
  };

  const fetchAlerts = async () => {
    try {
      // 未解決のアラートのみを取得
      const response = await axios.get('/api/admin/scraper-alerts?resolved=false');
      // APIが配列を直接返す場合とオブジェクトでラップされた場合の両方に対応
      const alertData = Array.isArray(response.data) ? response.data : response.data.alerts || [];
      // 未解決のアラートのみをフィルタリング（念のため）
      const unresolvedAlerts = alertData.filter((alert: ScraperAlert) => !alert.resolved_at);
      setAlerts(unresolvedAlerts);
    } catch (error) {
      // エラーハンドリング済み
    }
  };

  const resolveAlert = async (alertId: number) => {
    try {
      await axios.put(`/api/admin/scraper-alerts/${alertId}/resolve`);
      await fetchAlerts();
    } catch (error) {
      setError('アラートの解決に失敗しました');
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
      
          }
        } catch (error) {
          // エラーは無視（次回の定期更新で取得）
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
              // エラーは無視（最終状態の取得に失敗）
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
      // エラーは既にsetErrorで処理されている
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
      const requestData: any = {
        scrapers: selectedScrapers,
        area_codes: selectedAreas,
        max_properties: maxProperties,
      };
      
      // カスタム再取得期間が有効な場合
      if (useCustomRefetch && detailRefetchHours >= 0) {
        requestData.detail_refetch_hours = detailRefetchHours;
        // 0時間の場合は強制詳細取得モードを有効にする
        if (detailRefetchHours === 0) {
          requestData.force_detail_fetch = true;
        }
      }
      
      // 404/検証エラー履歴を無視するオプション
      if (ignoreErrorHistory) {
        requestData.ignore_error_history = true;
      }
      
      const response = await axios.post('/api/admin/scraping/start-parallel', requestData);
      
      // 新しいタスクを追加
      setTasks(prev => [response.data, ...prev]);
      
      // 展開状態に追加
      setExpandedTasks(prev => new Set([...prev, response.data.task_id]));
    } catch (error) {
      // エラーは既にsetErrorで処理されている
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
        setError('タスクの一時停止がタイムアウトしました');
        fetchTasks(); // 最終的に一度更新
      }
    } catch (error: any) {
      // エラーは既にsetErrorで処理されている
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
        setError('タスクの再開がタイムアウトしました');
        fetchTasks(); // 最終的に一度更新
      }
    } catch (error) {
      // エラーは既にsetErrorで処理されている
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
        setError('タスクのキャンセルがタイムアウトしました');
        fetchTasks(); // 最終的に一度更新
      }
    } catch (error: any) {
      // エラーは既にsetErrorで処理されている
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
      // エラーは既にsetErrorで処理されている
      alert(`タスクの削除に失敗しました: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoadingButtons(prev => ({ ...prev, [`delete-${taskId}`]: false }));
    }
  };

  const deleteAllTasks = () => {
    // 実行中のタスクがあるか確認
    const runningTasks = tasks.filter(task => task.status === 'running' || task.status === 'paused');
    if (runningTasks.length > 0) {
      setDeleteDialogMessage(
        `${runningTasks.length}件のタスクが実行中または一時停止中です。\n` +
        `これらのタスクを除いて、完了したタスクの履歴のみを削除しますか？`
      );
    } else {
      setDeleteDialogMessage('すべてのスクレイピング履歴を削除しますか？\nこの操作は取り消せません。');
    }
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    setDeleteDialogOpen(false);
    setLoading(true);
    
    try {
      const response = await axios.delete('/api/admin/scraping/all-tasks');
      alert(`${response.data.deleted_count}件のタスクを削除しました`);
      await fetchTasks();
    } catch (error: any) {
      // エラーは既にsetErrorで処理されている
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
    // 詳細再取得タスクの特別な識別子
    if (areaCode === 'single_url') {
      return '詳細再取得';
    }
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
    // 並列タスクの場合
    if (task.type === 'parallel') {
      // 各進捗から集計する
      const progressItems = Object.values(task.progress || {});
      

      
      // 各進捗の合計を計算
      const aggregated = progressItems.reduce((stats, progress: any) => ({
        total: stats.total + (progress.processed || 0),
        new: stats.new + (progress.new_listings || progress.new || 0),
        price_updated: stats.price_updated + (progress.price_updated || progress.updated || 0),
        other_updates: stats.other_updates + (progress.other_updates || 0),
        refetched_unchanged: stats.refetched_unchanged + (progress.refetched_unchanged || 0),
        skipped: stats.skipped + (progress.skipped || 0),
        save_failed: stats.save_failed + (progress.errors || 0)
      }), { total: 0, new: 0, price_updated: 0, other_updates: 0, refetched_unchanged: 0, skipped: 0, save_failed: 0 });
      
      // statisticsフィールドがある場合は優先的に使用
      const stats = (task as any).statistics;
      if (stats) {
        return {
          total: stats.total_processed || aggregated.total,
          new: stats.total_new || aggregated.new,
          price_updated: stats.total_updated || aggregated.price_updated,
          other_updates: aggregated.other_updates,
          refetched_unchanged: aggregated.refetched_unchanged,
          skipped: aggregated.skipped,
          save_failed: stats.total_errors || aggregated.save_failed
        };
      }
      
      return aggregated;
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
      setError('掲載ステータスの更新に失敗しました');
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
      
      {/* スクレイパーアラート - シンプルなデザイン */}
      {alerts.length > 0 && (
        <Alert 
          severity="warning" 
          sx={{ 
            mb: 3,
            '& .MuiAlert-icon': { fontSize: 28 }
          }}
          icon={<WarningIcon />}
        >
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2 }}>
              スクレイパーアラート ({alerts.length}件)
            </Typography>
            {alerts.map((alert) => (
              <Box 
                key={alert.id}
                sx={{ 
                  pl: 2,
                  pr: 2,
                  py: 1.5,
                  mb: 1.5,
                  borderLeft: `3px solid ${
                    (alert.severity === 'high' || alert.severity === 'critical') ? '#d32f2f' :
                    (alert.severity === 'medium' || alert.severity === 'warning') ? '#ed6c02' : '#0288d1'
                  }`,
                  backgroundColor: 'rgba(255, 255, 255, 0.9)',
                  borderRadius: '4px'
                }}
              >
                <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                  <Box flex={1}>
                    <Box display="flex" alignItems="center" gap={1} mb={0.5}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                        {alert.scraper_name || alert.source_site || '不明'}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        - {alert.alert_type}
                      </Typography>
                    </Box>
                    <Typography variant="body2" sx={{ mb: 0.5 }}>
                      {alert.message}
                    </Typography>
                    <Box display="flex" gap={2}>
                      {alert.details && alert.details.error_count !== undefined && (
                        <Typography variant="caption" color="text.secondary">
                          エラー: {alert.details.error_count}件 ({(alert.details.error_rate * 100).toFixed(0)}%)
                        </Typography>
                      )}
                      <Typography variant="caption" color="text.secondary">
                        {new Date(alert.created_at).toLocaleString('ja-JP', {
                          month: 'numeric',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </Typography>
                    </Box>
                  </Box>
                  <Button
                    size="small"
                    variant="text"
                    onClick={() => resolveAlert(alert.id)}
                    sx={{ minWidth: 'auto', ml: 2 }}
                  >
                    解決
                  </Button>
                </Box>
              </Box>
            ))}
          </Box>
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
                MenuProps={{
                  PaperProps: {
                    style: {
                      maxHeight: 400,
                    },
                  },
                }}
              >
                <Box sx={{ px: 2, py: 1, borderBottom: '1px solid rgba(0, 0, 0, 0.12)' }}>
                  <Button
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedScrapers(scraperOptions.map(opt => opt.value));
                    }}
                    sx={{ mr: 1 }}
                  >
                    全選択
                  </Button>
                  <Button
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedScrapers([]);
                    }}
                  >
                    全解除
                  </Button>
                </Box>
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
            <Box sx={{ mb: 2 }}>
              <FormGroup>
                <FormControlLabel
                    control={
                      <Checkbox
                        checked={useCustomRefetch}
                        onChange={(e) => {
                          setUseCustomRefetch(e.target.checked);
                          // カスタマイズを無効にした場合、エラー履歴無視もリセット
                          if (!e.target.checked) {
                            setIgnoreErrorHistory(false);
                          }
                        }}
                        color="warning"
                      />
                    }
                    label="詳細ページの再取得範囲をカスタマイズ"
                  />
                </FormGroup>
                {!useCustomRefetch && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                    デフォルト: 価格変更があった物件と、90日以上詳細を取得していない物件のみ更新
                  </Typography>
                )}
                {useCustomRefetch && (
                  <Box sx={{ mt: 2 }}>
                    <TextField
                      fullWidth
                      label="詳細ページ再取得期間"
                      type="number"
                      value={detailRefetchHours}
                      onChange={(e) => {
                        const value = parseInt(e.target.value);
                        if (!isNaN(value) && value >= 0) {
                          setDetailRefetchHours(value);
                        }
                      }}
                      InputProps={{
                        inputProps: { min: 0, max: 10000 },
                        endAdornment: detailRefetchHours === 0 
                          ? <Typography variant="caption" color="warning.main">すべて再取得</Typography>
                          : detailRefetchHours < 24 
                          ? <Typography variant="caption" color="text.secondary">{detailRefetchHours}時間</Typography>
                          : <Typography variant="caption" color="text.secondary">{Math.round(detailRefetchHours / 24)}日</Typography>
                      }}
                      helperText={detailRefetchHours === 0 
                        ? "すべての物件の詳細ページを再取得します" 
                        : `${detailRefetchHours}時間（${Math.round(detailRefetchHours / 24)}日）以上経過した物件の詳細を再取得します`
                      }
                      size="small"
                    />
                    <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      <Button size="small" variant="outlined" onClick={() => setDetailRefetchHours(0)}>すべて</Button>
                      <Button size="small" variant="outlined" onClick={() => setDetailRefetchHours(24)}>1日</Button>
                      <Button size="small" variant="outlined" onClick={() => setDetailRefetchHours(72)}>3日</Button>
                      <Button size="small" variant="outlined" onClick={() => setDetailRefetchHours(168)}>1週間</Button>
                      <Button size="small" variant="outlined" onClick={() => setDetailRefetchHours(720)}>30日</Button>
                      <Button size="small" variant="outlined" onClick={() => setDetailRefetchHours(2160)}>90日</Button>
                    </Box>
                    {detailRefetchHours < 168 && (
                      <Alert severity="warning" sx={{ mt: 1 }} icon={false}>
                        <Typography variant="caption">
                          短い期間を設定すると、処理時間が大幅に増加します
                        </Typography>
                      </Alert>
                    )}
                  </Box>
                )}
                
                {useCustomRefetch && (
                  <>
                    <FormGroup sx={{ mt: 2 }}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={ignoreErrorHistory}
                            onChange={(e) => setIgnoreErrorHistory(e.target.checked)}
                            color="error"
                          />
                        }
                        label="エラー履歴を無視して再取得"
                      />
                    </FormGroup>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', ml: 3.5, mt: 0.5 }}>
                      404エラーや検証エラー（面積超過等）の履歴を無視して再取得を試みます
                    </Typography>
                    {ignoreErrorHistory && (
                      <Alert severity="warning" sx={{ mt: 1, ml: 3.5 }} icon={false}>
                        <Typography variant="caption">
                          同じエラーが再発する可能性があります
                        </Typography>
                      </Alert>
                    )}
                  </>
                )}
            </Box>
            <Button
              variant="contained"
              startIcon={<PlayIcon />}
              onClick={startScraping}
              disabled={loading || selectedScrapers.length === 0}
              fullWidth
              color={ignoreErrorHistory ? "error" : useCustomRefetch && detailRefetchHours < 168 ? "warning" : "primary"}
            >
              {useCustomRefetch && detailRefetchHours === 0 
                ? "スクレイピング開始（強制再取得）" 
                : useCustomRefetch && detailRefetchHours < 24
                ? `スクレイピング開始（${detailRefetchHours}時間以上経過で再取得）`
                : useCustomRefetch && detailRefetchHours < 168
                ? `スクレイピング開始（${Math.round(detailRefetchHours / 24)}日以上経過で再取得）`
                : "スクレイピング開始"}
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
                              <Tab label="進捗状況" />
                              <Tab label="物件更新履歴" disabled={!task.logs || task.logs.length === 0} />
                              <Tab 
                                label="エラーログ" 
                                disabled={!task.error_logs || task.error_logs.length === 0} 
                              />
                              <Tab 
                                label="警告ログ" 
                                disabled={!task.warning_logs || task.warning_logs.length === 0} 
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
                                    <Box component="div" fontWeight="medium" fontSize="0.875rem" sx={{ mb: 1 }}>
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
                                                      • 変更なし: {progress.refetched_unchanged || 0}件
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
                                                      • 変更なし: {progress.refetched_unchanged || 0}件
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
                              <Box sx={{ bgcolor: 'grey.50', p: 1, borderRadius: 1 }}>
                                {/* ページネーション */}
                                {task.logs.length > 30 && (
                                  <Box sx={{ mb: 1 }}>
                                    <Typography variant="caption" color="text.secondary" align="center" display="block" sx={{ mb: 0.5 }}>
                                      全{task.logs.length}件 (1ページ = 最新、{Math.ceil(task.logs.length / 30)}ページ = 最古)
                                    </Typography>
                                    <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                                      <Pagination
                                        count={Math.ceil(task.logs.length / 30)}
                                        page={logPages[task.task_id] || 1}
                                        onChange={(_, page) => setLogPages({ ...logPages, [task.task_id]: page })}
                                        size="small"
                                        color="primary"
                                      />
                                    </Box>
                                  </Box>
                                )}
                                <Box sx={{ maxHeight: 400, overflow: 'auto' }}>
                                  <List dense>
                                    {(() => {
                                      const currentPage = logPages[task.task_id] || 1;
                                      const itemsPerPage = 30;
                                      const reversedLogs = task.logs.slice().reverse();
                                      const startIndex = (currentPage - 1) * itemsPerPage;
                                      const endIndex = startIndex + itemsPerPage;
                                      const paginatedLogs = reversedLogs.slice(startIndex, endIndex);
                                      
                                      return paginatedLogs.map((log, index) => (
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
                                              label={(() => {
                                                switch(log.type) {
                                                  case 'new': return '新規';
                                                  case 'price_updated': return '価格更新';
                                                  case 'other_updates': return 'その他更新';
                                                  case 'refetched_unchanged': return '変更なし';
                                                  default: return '更新';
                                                }
                                              })()}
                                              size="small"
                                              color={(() => {
                                                switch(log.type) {
                                                  case 'new': return 'success';
                                                  case 'price_updated': return 'warning';
                                                  case 'other_updates': return 'info';
                                                  case 'refetched_unchanged': return 'default';
                                                  default: return 'info';
                                                }
                                              })()}
                                              sx={{ height: 20 }}
                                            />
                                            <Typography variant="body2">
                                              {(() => {
                                                // メッセージから建物名、物件詳細、価格を抽出して整形
                                                const message = log.message;
                                                
                                                // 新規登録の場合
                                                if (message.includes('新規登録:')) {
                                                  // パターン: "新規登録: 建物名 階数 / 面積 / 間取り / 方角 - 価格万円 - URL"
                                                  const match = message.match(/新規登録:\s*([^-]+?)\s*-\s*(\d+)万円/);
                                                  if (match) {
                                                    const details = match[1].trim();
                                                    const price = match[2];
                                                    return `新規物件登録: ${details} (${price}万円)`;
                                                  }
                                                }
                                                
                                                // 価格更新の場合
                                                if (message.includes('価格更新:')) {
                                                  // パターン: "価格更新: 建物名 階数 / 面積 / 間取り / 方角 - 旧価格万円 → 新価格万円 - URL"
                                                  const match = message.match(/価格更新:\s*([^-]+?)\s*-\s*(\d+)万円\s*→\s*(\d+)万円/);
                                                  if (match) {
                                                    const details = match[1].trim();
                                                    const oldPrice = match[2];
                                                    const newPrice = match[3];
                                                    return `価格更新: ${details} (${oldPrice}万円 → ${newPrice}万円)`;
                                                  }
                                                }
                                                
                                                // その他更新の場合
                                                if (message.includes('その他更新:')) {
                                                  // パターン: "その他更新: 建物名 階数 / 面積 / 間取り / 方角 - 詳細: 更新内容 - URL"
                                                  const match = message.match(/その他更新:\s*([^-]+?)(?:\s*-\s*詳細:\s*([^-]+))?\s*-\s*https?:/);
                                                  if (match) {
                                                    const details = match[1].trim();
                                                    const updateDetails = match[2] ? match[2].trim() : '';
                                                    return updateDetails 
                                                      ? `その他更新: ${details} (${updateDetails})`
                                                      : `その他更新: ${details}`;
                                                  }
                                                }
                                                
                                                // デフォルトはそのまま表示
                                                return log.message;
                                              })()}
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
                                            {log.update_details && (
                                              <Typography variant="caption" component="div" color="info.main">
                                                更新内容: {log.update_details}
                                              </Typography>
                                            )}
                                          </Box>
                                        }
                                      />
                                    </ListItem>
                                  ));
                                })()}
                              </List>
                            </Box>
                            {task.logs.length === 0 && (
                              <Typography variant="body2" color="text.secondary" align="center" py={2}>
                                物件更新履歴がありません
                              </Typography>
                            )}
                            {/* 下部にもページネーション */}
                            {task.logs.length > 30 && (
                              <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1 }}>
                                <Pagination
                                  count={Math.ceil(task.logs.length / 30)}
                                  page={logPages[task.task_id] || 1}
                                  onChange={(_, page) => setLogPages({ ...logPages, [task.task_id]: page })}
                                  size="small"
                                  color="primary"
                                />
                              </Box>
                            )}
                          </Box>
                            )}
                            
                            {(logTabValues[task.task_id] || 0) === 2 && (
                              <Box sx={{ 
                                maxHeight: 400, 
                                overflow: 'auto', 
                                bgcolor: 'grey.50', 
                                p: 1, 
                                borderRadius: 1,
                                width: '100%',
                                overflowX: 'hidden'
                              }}>
                                {task.error_logs && task.error_logs.length > 0 ? (
                                <List dense sx={{ width: '100%' }}>
                                  {task.error_logs.slice().reverse().map((log, index) => (
                                    <ListItem key={index} sx={{ 
                                      py: 0.5,
                                      borderBottom: '1px solid',
                                      borderColor: 'grey.200',
                                      bgcolor: 'error.50',
                                      display: 'block',
                                      width: '100%',
                                      maxWidth: '100%'
                                    }}>
                                      <ListItemText
                                        sx={{ overflow: 'hidden' }}
                                        primary={
                                          <Box>
                                            <Box display="flex" alignItems="center" gap={1} sx={{ mb: 0.5 }}>
                                              <Typography variant="caption" color="text.secondary">
                                                {new Date(log.timestamp).toLocaleTimeString('ja-JP')}
                                              </Typography>
                                              <Chip
                                                label={log.reason?.includes('システムエラー') ? 'システムエラー' : log.reason?.split(':')[0] || log.reason}
                                                size="small"
                                                color="error"
                                                sx={{ height: 20, flexShrink: 0 }}
                                              />
                                            </Box>
                                            {log.reason?.includes(':') && (
                                              <Typography 
                                                variant="body2" 
                                                color="error" 
                                                component="div"
                                                sx={{ 
                                                  wordBreak: 'break-all',
                                                  overflowWrap: 'break-word',
                                                  whiteSpace: 'pre-wrap',
                                                  maxWidth: '100%'
                                                }}
                                              >
                                                {log.reason.substring(log.reason.indexOf(':') + 1).trim()}
                                              </Typography>
                                            )}
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
                                              <Typography 
                                                variant="caption" 
                                                component="div"
                                                sx={{ 
                                                  wordBreak: 'break-all',
                                                  overflow: 'hidden'
                                                }}
                                              >
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

                            {(logTabValues[task.task_id] || 0) === 3 && (
                              <Box sx={{ maxHeight: 400, overflow: 'auto', bgcolor: 'grey.50', p: 1, borderRadius: 1 }}>
                                {task.warning_logs && task.warning_logs.length > 0 ? (
                                <List dense>
                                  {task.warning_logs.slice().reverse().map((log, index) => (
                                    <ListItem key={index} sx={{ 
                                      py: 0.5,
                                      borderBottom: '1px solid',
                                      borderColor: 'grey.200',
                                      bgcolor: 'warning.50'
                                    }}>
                                      <ListItemText 
                                        primary={
                                          <Box>
                                            <Typography variant="body2" component="span" fontWeight="medium">
                                              [{new Date(log.timestamp).toLocaleTimeString()}] {log.scraper}
                                            </Typography>
                                            <Typography variant="body2" component="div" color="warning.main">
                                              {log.reason || '警告'}
                                            </Typography>
                                          </Box>
                                        }
                                        secondary={
                                          <Box>
                                            {(log.building_name || log.price || log.site_property_id) && (
                                              <Typography variant="caption" component="div" color="text.secondary">
                                                {log.building_name && `建物名: ${log.building_name}`}
                                                {log.price && ` | 価格: ${log.price}`}
                                                {log.site_property_id && ` | 掲載情報ID: ${log.site_property_id}`}
                                              </Typography>
                                            )}
                                            {log.url && (
                                              <Typography 
                                                variant="caption" 
                                                component="div"
                                                sx={{ 
                                                  wordBreak: 'break-all',
                                                  overflow: 'hidden'
                                                }}
                                              >
                                                <a href={log.url} target="_blank" rel="noopener noreferrer" 
                                                   style={{ color: '#ed6c02', textDecoration: 'none' }}>
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
                                    警告ログがありません
                                  </Typography>
                                )}
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
        message={deleteDialogMessage}
      />
    </Box>
  );
};

export default AdminScraping;