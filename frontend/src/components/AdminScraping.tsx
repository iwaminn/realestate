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
      updated_listings: number;
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
  const [logTabValue, setLogTabValue] = useState(0);

  const scraperOptions = [
    { value: 'suumo', label: 'SUUMO' },
    { value: 'homes', label: "LIFULL HOME'S" },
    { value: 'athome', label: 'AtHome' },
    { value: 'nomu', label: 'ノムコム' },
  ];

  useEffect(() => {
    fetchAreas();
    fetchTasks();
    // 定期的にタスクの状態を更新
    const interval = setInterval(fetchTasks, 3000);
    return () => clearInterval(interval);
  }, []);

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
    try {
      await axios.post(`/api/admin/scraping/pause/${taskId}`);
      fetchTasks();
    } catch (error) {
      console.error('Failed to pause task:', error);
      alert('タスクの一時停止に失敗しました');
    }
  };

  const resumeTask = async (taskId: string) => {
    try {
      await axios.post(`/api/admin/scraping/resume/${taskId}`);
      fetchTasks();
    } catch (error) {
      console.error('Failed to resume task:', error);
      alert('タスクの再開に失敗しました');
    }
  };

  const cancelTask = async (taskId: string) => {
    try {
      await axios.post(`/api/admin/scraping/cancel/${taskId}`);
      fetchTasks();
    } catch (error) {
      console.error('Failed to cancel task:', error);
      alert('タスクのキャンセルに失敗しました');
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

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending': return 'default';
      case 'running': return 'primary';
      case 'paused': return 'warning';
      case 'completed': return 'success';
      case 'failed': return 'error';
      case 'cancelled': return 'warning';
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
      if (progress.status === 'running') {
        return sum + Math.min((progress.properties_scraped / task.max_properties) * 100, 90);
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
      updated: stats.updated + (progress.updated_listings || 0)
    }), { total: 0, new: 0, updated: 0 });
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        スクレイピング管理
      </Typography>

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
            <TextField
              fullWidth
              label="取得件数"
              type="number"
              value={maxProperties}
              onChange={(e) => setMaxProperties(parseInt(e.target.value) || 100)}
              inputProps={{ min: 1, max: 1000 }}
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
                  <TableCell>取得件数</TableCell>
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
                                    合計: {stats.total}
                                  </Typography>
                                  <Typography variant="caption" color="success.main">
                                    新規: {stats.new}
                                  </Typography>
                                  <Typography variant="caption" color="info.main">
                                    更新: {stats.updated}
                                  </Typography>
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
                            <IconButton
                              size="small"
                              color="primary"
                              onClick={() => pauseTask(task.task_id)}
                            >
                              <PauseIcon />
                            </IconButton>
                          </Tooltip>
                        )}
                        {task.status === 'paused' && (
                          <>
                            <Tooltip title="再開">
                              <IconButton
                                size="small"
                                color="primary"
                                onClick={() => resumeTask(task.task_id)}
                              >
                                <PlayIcon />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="キャンセル">
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => cancelTask(task.task_id)}
                              >
                                <StopIcon />
                              </IconButton>
                            </Tooltip>
                          </>
                        )}
                      </TableCell>
                    </TableRow>
                    
                    <TableRow>
                      <TableCell colSpan={8} sx={{ py: 0 }}>
                        <Collapse in={expandedTasks.has(task.task_id)}>
                          <Box sx={{ p: 2 }}>
                            <Tabs value={logTabValue} onChange={(e, v) => setLogTabValue(v)} sx={{ mb: 2 }}>
                              <Tab label="詳細情報" />
                              <Tab label="ログ" disabled={!task.logs || task.logs.length === 0} />
                            </Tabs>
                            
                            {logTabValue === 0 && (
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
                                              label={progress.status}
                                              color={getStatusColor(progress.status)}
                                              size="small"
                                            />
                                          }
                                        />
                                      </ListItem>
                                      <ListItem>
                                        <ListItemText
                                          primary="取得件数"
                                          secondary={`${progress.properties_scraped}件`}
                                        />
                                      </ListItem>
                                      <ListItem>
                                        <ListItemText
                                          primary="新規登録"
                                          secondary={
                                            <Typography variant="body2" color="success.main">
                                              {progress.new_listings || 0}件
                                            </Typography>
                                          }
                                        />
                                      </ListItem>
                                      <ListItem>
                                        <ListItemText
                                          primary="更新"
                                          secondary={
                                            <Typography variant="body2" color="info.main">
                                              {progress.updated_listings || 0}件
                                            </Typography>
                                          }
                                        />
                                      </ListItem>
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
                            
                            {logTabValue === 1 && task.logs && (
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