import React, { useState, useEffect } from 'react';
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
} from '@mui/icons-material';
import axios from 'axios';

interface Area {
  code: string;
  name: string;
}

interface ScrapingTask {
  task_id: string;
  status: string;
  scrapers: string[];
  area_codes: string[];
  max_properties: number;
  started_at: string;
  completed_at: string | null;
  progress: {
    [key: string]: {
      scraper: string;
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
      // 詳細統計
      properties_found?: number;
      properties_processed?: number;
      properties_attempted?: number;
      detail_fetched?: number;  // 詳細取得成功数
      detail_fetch_failed?: number;
      save_failed?: number;
      price_missing?: number;
      building_info_missing?: number;
      other_errors?: number;
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

  const scraperOptions = [
    { value: 'suumo', label: 'SUUMO' },
    { value: 'homes', label: "LIFULL HOME'S" },
    { value: 'rehouse', label: '三井のリハウス' },
    { value: 'nomu', label: 'ノムコム' },
    { value: 'livable', label: '東急リバブル' },
  ];

  useEffect(() => {
    fetchAreas();
    fetchTasks();
  }, []);

  // 自動更新の制御
  useEffect(() => {
    if (autoRefreshEnabled) {
      const interval = setInterval(fetchTasks, 3000);
      return () => clearInterval(interval);
    }
  }, [autoRefreshEnabled]);

  // ボタン操作中は自動更新を停止
  useEffect(() => {
    const isAnyButtonLoading = Object.values(loadingButtons).some(loading => loading);
    setAutoRefreshEnabled(!isAnyButtonLoading);
  }, [loadingButtons]);

  const fetchAreas = async () => {
    try {
      const response = await axios.get('/api/admin/areas');
      setAreas(response.data.areas);
    } catch (error) {
      console.error('Failed to fetch areas:', error);
    }
  };

  const fetchTasks = async () => {
    try {
      const response = await axios.get('/api/admin/scraping/tasks');
      console.log('Fetched tasks:', response.data); // デバッグ用ログ
      // error_logsの存在を確認
      response.data.forEach((task: any) => {
        if (task.error_logs && task.error_logs.length > 0) {
          console.log(`Task ${task.task_id} has ${task.error_logs.length} error logs`);
        }
      });
      setTasks(response.data);
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
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
      const response = await axios.post('/api/admin/scraping/start', {
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
    console.log(`Pausing task ${taskId}...`);
    console.log('Current axios headers:', axios.defaults.headers);
    setLoadingButtons(prev => ({ ...prev, [`pause-${taskId}`]: true }));
    try {
      // APIコールを実行
      console.log(`Making POST request to /api/admin/scraping/pause/${taskId}`);
      const response = await axios.post(`/api/admin/scraping/pause/${taskId}`);
      console.log('Pause response:', response.data);
      
      // タスク状態が更新されるまでポーリング
      let attempts = 0;
      const maxAttempts = 20; // 最大10秒間チェック
      
      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 500));
        const response = await axios.get('/api/admin/scraping/tasks');
        const updatedTask = response.data.find((t: ScrapingTask) => t.task_id === taskId);
        
        if (updatedTask && updatedTask.status === 'paused') {
          console.log(`Task ${taskId} is now paused`);
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
      console.error('Error details:', {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      });
      alert(`タスクの一時停止に失敗しました: ${error.response?.data?.detail || error.message}`);
    } finally {
      setLoadingButtons(prev => ({ ...prev, [`pause-${taskId}`]: false }));
    }
  };

  const resumeTask = async (taskId: string) => {
    console.log(`Resuming task ${taskId}...`);
    setLoadingButtons(prev => ({ ...prev, [`resume-${taskId}`]: true }));
    try {
      // APIコールを実行
      await axios.post(`/api/admin/scraping/resume/${taskId}`);
      
      // タスク状態が更新されるまでポーリング
      let attempts = 0;
      const maxAttempts = 20; // 最大10秒間チェック
      
      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 500));
        const response = await axios.get('/api/admin/scraping/tasks');
        const updatedTask = response.data.find((t: ScrapingTask) => t.task_id === taskId);
        
        if (updatedTask && updatedTask.status === 'running') {
          console.log(`Task ${taskId} is now running`);
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
    console.log(`Cancelling task ${taskId}...`);
    setLoadingButtons(prev => ({ ...prev, [`cancel-${taskId}`]: true }));
    try {
      const response = await axios.post(`/api/admin/scraping/cancel/${taskId}`);
      console.log('Cancel response:', response.data);
      
      // タスク状態が更新されるまでポーリング
      let attempts = 0;
      const maxAttempts = 20; // 最大10秒間チェック
      
      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 500));
        const tasksResponse = await axios.get('/api/admin/scraping/tasks');
        const updatedTask = tasksResponse.data.find((t: ScrapingTask) => t.task_id === taskId);
        
        if (updatedTask && (updatedTask.status === 'cancelled' || updatedTask.status === 'completed')) {
          console.log(`Task ${taskId} is now ${updatedTask.status}`);
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
    const progressItems = Object.values(task.progress);
    if (progressItems.length === 0) return 0;
    
    const expectedTotal = task.scrapers.length * task.area_codes.length;

    const totalProgress = progressItems.reduce((sum, progress) => {
      if (progress.status === 'completed') return sum + 100;
      if (progress.status === 'running' || progress.status === 'paused') {
        // 常に処理上限数を分母として使用
        const attemptedRatio = (progress.properties_attempted || 0) / task.max_properties;
        return sum + Math.min(attemptedRatio * 100, 95);
      }
      return sum;
    }, 0);

    return totalProgress / expectedTotal;
  };
  
  const getTaskStats = (task: ScrapingTask) => {
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
              onChange={(_, newValue) => {
                if (typeof newValue === 'number') {
                  setMaxProperties(newValue);
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
          <IconButton onClick={fetchTasks}>
            <RefreshIcon />
          </IconButton>
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
                {tasks.map(task => (
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
                          {task.area_codes.length > 2 ? (
                            <Tooltip title={getAreaNames(task.area_codes)}>
                              <Typography variant="body2">
                                {getAreaName(task.area_codes[0])} 他{task.area_codes.length - 1}件
                              </Typography>
                            </Tooltip>
                          ) : (
                            <Typography variant="body2">
                              {getAreaNames(task.area_codes)}
                            </Typography>
                          )}
                        </Box>
                      </TableCell>
                      <TableCell>
                        {task.scrapers.map(s => (
                          <Chip key={s} label={s} size="small" sx={{ mr: 0.5 }} />
                        ))}
                      </TableCell>
                      <TableCell>{task.max_properties}</TableCell>
                      <TableCell>
                        <Chip
                          label={task.status}
                          color={getStatusColor(task.status)}
                          size="small"
                        />
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
                          <Box display="flex" gap={1}>
                            {(() => {
                              const stats = getTaskStats(task);
                              return (
                                <>
                                  <Typography variant="caption" color="text.secondary">
                                    詳細取得: {stats.total}
                                  </Typography>
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
                        {new Date(task.started_at).toLocaleString('ja-JP')}
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
                              {Object.entries(task.progress).map(([key, progress]) => (
                                <Grid item xs={12} md={4} key={key}>
                                  <Paper variant="outlined" sx={{ p: 2 }}>
                                    <Typography variant="subtitle2" gutterBottom>
                                      {progress.scraper} - {progress.area_name}
                                    </Typography>
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
                                                  <Typography variant="body2" color="text.secondary">
                                                    一覧ページから発見: {progress.properties_found || 0}件
                                                  </Typography>
                                                  <Typography variant="body2" color="text.secondary">
                                                    処理状況: {progress.properties_attempted || 0} / {progress.properties_found || 0} 件
                                                    {(progress.properties_found || 0) > 0 && (
                                                      <span style={{ marginLeft: '8px', color: '#666' }}>
                                                        ({Math.round(((progress.properties_attempted || 0) / (progress.properties_found || 0)) * 100)}%)
                                                      </span>
                                                    )}
                                                  </Typography>
                                                  <Typography variant="body2" color="text.secondary">
                                                    詳細取得成功: {progress.detail_fetched || 0}件
                                                  </Typography>
                                                  <Typography variant="body2" color="text.secondary">
                                                    詳細スキップ: {progress.skipped_listings || 0}件
                                                  </Typography>
                                                  <Typography variant="body2" color="text.secondary">
                                                    エラー: {(progress.detail_fetch_failed || 0) + (progress.save_failed || 0)}件
                                                  </Typography>
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
                                    </List>
                                  </Paper>
                                </Grid>
                              ))}
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
                                      <li key={index}>{error}</li>
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
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </Box>
  );
};

export default AdminScraping;