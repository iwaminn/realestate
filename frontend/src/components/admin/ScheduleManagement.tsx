import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Switch,
  FormControlLabel,
  Grid,
  Alert,
  Tooltip,
  List,
  ListItem,
  ListItemText,
  Divider,
  Autocomplete,
  Checkbox,
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  PlayArrow as PlayIcon,
  Schedule as ScheduleIcon,
  History as HistoryIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';
import { ja } from 'date-fns/locale';
import axios from 'axios';
import '../../utils/axiosConfig';
import {
  AVAILABLE_SCRAPERS,
  AVAILABLE_AREAS,
  AVAILABLE_MAX_PROPERTIES,
  getScraperDisplayName,
} from '../../constants/scraperConstants';

interface Schedule {
  id: number;
  name: string;
  description?: string;
  scrapers: string[];
  areas?: string[];
  schedule_type: string;  // 'interval' or 'daily'
  interval_minutes?: number;
  daily_hour?: number;
  daily_minute?: number;
  max_properties: number;
  is_active: boolean;
  last_run_at?: string;
  next_run_at?: string;
  last_task_id?: number;
  created_by?: string;
  created_at: string;
  updated_at: string;
  last_status?: string;
  last_error?: string;
}

interface ScheduleHistory {
  id: number;
  task_id?: number;
  started_at: string;
  completed_at?: string;
  status: string;
  error_message?: string;
}

interface ScheduleDetail extends Schedule {
  history: ScheduleHistory[];
}

export const ScheduleManagement: React.FC = () => {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // ダイアログ状態
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedSchedule, setSelectedSchedule] = useState<ScheduleDetail | null>(null);
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null);

  // フォーム状態
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    scrapers: [] as string[],
    areas: [] as string[],
    schedule_type: 'daily' as 'interval' | 'daily',
    interval_minutes: 60,
    daily_hour: 9,
    daily_minute: 0,
    max_properties: 100,
    is_active: true,
  });

  // 共通定数を使用
  const availableScrapers = AVAILABLE_SCRAPERS;
  const availableMaxProperties = AVAILABLE_MAX_PROPERTIES;
  const availableAreas = AVAILABLE_AREAS;

  useEffect(() => {
    fetchSchedules();
  }, []);

  const fetchSchedules = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get('/admin/schedules');
      setSchedules(response.data.schedules);
    } catch (err: any) {
      setError('スケジュール一覧の取得に失敗しました: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    try {
      // エリアコードをエリア名に変換してAPIに送信
      const convertedFormData = {
        ...formData,
        areas: formData.areas.map(areaCode => {
          const area = availableAreas.find(a => a.code === areaCode);
          return area ? area.name : areaCode; // 見つからない場合は元の値を使用
        })
      };
      
      await axios.post('/admin/schedules', convertedFormData);
      setSuccess('スケジュールを作成しました');
      setCreateDialogOpen(false);
      resetForm();
      fetchSchedules();
    } catch (err: any) {
      setError('スケジュールの作成に失敗しました: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleUpdate = async () => {
    if (!editingSchedule) return;
    
    try {
      // エリアコードをエリア名に変換してAPIに送信
      const convertedFormData = {
        ...formData,
        areas: formData.areas.map(areaCode => {
          const area = availableAreas.find(a => a.code === areaCode);
          return area ? area.name : areaCode; // 見つからない場合は元の値を使用
        })
      };
      
      await axios.put(`/admin/schedules/${editingSchedule.id}`, convertedFormData);
      setSuccess('スケジュールを更新しました');
      setEditDialogOpen(false);
      resetForm();
      fetchSchedules();
    } catch (err: any) {
      setError('スケジュールの更新に失敗しました: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDelete = async () => {
    if (!editingSchedule) return;
    
    try {
      await axios.delete(`/admin/schedules/${editingSchedule.id}`);
      setSuccess('スケジュールを削除しました');
      setDeleteDialogOpen(false);
      setEditingSchedule(null);
      fetchSchedules();
    } catch (err: any) {
      setError('スケジュールの削除に失敗しました: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleRunNow = async (scheduleId: number) => {
    try {
      await axios.post(`/admin/schedules/${scheduleId}/run`);
      setSuccess('スケジュールの実行を開始しました');
      fetchSchedules();
    } catch (err: any) {
      setError('スケジュールの実行に失敗しました: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleViewDetail = async (schedule: Schedule) => {
    try {
      const response = await axios.get(`/admin/schedules/${schedule.id}`);
      setSelectedSchedule(response.data);
      setDetailDialogOpen(true);
    } catch (err: any) {
      setError('スケジュール詳細の取得に失敗しました: ' + (err.response?.data?.detail || err.message));
    }
  };

  const openEditDialog = (schedule: Schedule) => {
    setEditingSchedule(schedule);
    
    // エリア名からエリアコードに変換
    const convertedAreas = (schedule.areas || []).map(areaName => {
      const area = availableAreas.find(a => a.name === areaName);
      return area ? area.code : areaName; // 見つからない場合は元の値を使用
    });
    
    setFormData({
      name: schedule.name,
      description: schedule.description || '',
      scrapers: schedule.scrapers,
      areas: convertedAreas,
      schedule_type: schedule.schedule_type as 'interval' | 'daily',
      interval_minutes: schedule.interval_minutes || 60,
      daily_hour: schedule.daily_hour || 9,
      daily_minute: schedule.daily_minute || 0,
      max_properties: schedule.max_properties,
      is_active: schedule.is_active,
    });
    setEditDialogOpen(true);
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      scrapers: [],
      areas: [],
      schedule_type: 'interval',
      interval_minutes: 60,
      daily_hour: 9,
      daily_minute: 0,
      max_properties: 100,
      is_active: true,
    });
    setEditingSchedule(null);
  };

  const formatInterval = (minutes: number) => {
    if (minutes < 60) {
      return `${minutes}分`;
    } else if (minutes < 1440) {
      return `${Math.floor(minutes / 60)}時間${minutes % 60 ? `${minutes % 60}分` : ''}`;
    } else {
      const days = Math.floor(minutes / 1440);
      const hours = Math.floor((minutes % 1440) / 60);
      return `${days}日${hours ? `${hours}時間` : ''}`;
    }
  };

  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'completed': return 'success';
      case 'running': return 'info';
      case 'error': return 'error';
      default: return 'default';
    }
  };

  const getAreaName = (areaCode: string) => {
    const area = availableAreas.find(a => a.code === areaCode);
    return area ? area.name : areaCode;
  };

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h2">
          スケジュール管理
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateDialogOpen(true)}
        >
          新規作成
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <Paper>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell sx={{ minWidth: 150 }}>名前</TableCell>
                <TableCell>スクレイパー</TableCell>
                <TableCell>エリア</TableCell>
                <TableCell>実行間隔</TableCell>
                <TableCell>処理上限数</TableCell>
                <TableCell>状態</TableCell>
                <TableCell>最終実行</TableCell>
                <TableCell>次回実行</TableCell>
                <TableCell>ステータス</TableCell>
                <TableCell align="center" sx={{ minWidth: 120 }}>操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {schedules.map((schedule) => (
                <TableRow key={schedule.id}>
                  <TableCell>
                    <Box>
                      <Typography variant="subtitle2">{schedule.name}</Typography>
                      {schedule.description && (
                        <Typography variant="caption" color="text.secondary">
                          {schedule.description}
                        </Typography>
                      )}
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Box display="flex" flexWrap="wrap" gap={0.5}>
                      {schedule.scrapers.map((scraper) => (
                        <Chip key={scraper} label={getScraperDisplayName(scraper)} size="small" />
                      ))}
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Box display="flex" flexWrap="wrap" gap={0.5}>
                      {schedule.areas?.slice(0, 3).map((area) => (
                        <Chip key={area} label={getAreaName(area)} size="small" variant="outlined" />
                      ))}
                      {schedule.areas && schedule.areas.length > 3 && (
                        <Chip label={`+${schedule.areas.length - 3}`} size="small" variant="outlined" />
                      )}
                      {!schedule.areas?.length && (
                        <Typography variant="caption" color="text.secondary">全エリア</Typography>
                      )}
                    </Box>
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    {schedule.schedule_type === 'interval' 
                      ? formatInterval(schedule.interval_minutes || 0)
                      : `毎日 ${schedule.daily_hour?.toString().padStart(2, '0')}:${schedule.daily_minute?.toString().padStart(2, '0')}`
                    }
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    <Typography variant="body2">
                      {schedule.max_properties}件
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={schedule.is_active}
                      size="small"
                      onChange={async (e) => {
                        try {
                          await axios.put(`/admin/schedules/${schedule.id}`, {
                            is_active: e.target.checked
                          });
                          fetchSchedules();
                        } catch (err: any) {
                          setError('状態の更新に失敗しました');
                        }
                      }}
                    />
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    {schedule.last_run_at ? (
                      <Typography variant="caption" noWrap>
                        {format(new Date(schedule.last_run_at), 'MM/dd HH:mm', { locale: ja })}
                      </Typography>
                    ) : (
                      <Typography variant="caption" color="text.secondary" noWrap>未実行</Typography>
                    )}
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    {schedule.next_run_at ? (
                      <Typography variant="caption" noWrap>
                        {format(new Date(schedule.next_run_at), 'MM/dd HH:mm', { locale: ja })}
                      </Typography>
                    ) : (
                      <Typography variant="caption" color="text.secondary" noWrap>-</Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    {schedule.last_status && (
                      <Chip 
                        label={schedule.last_status} 
                        size="small" 
                        color={getStatusColor(schedule.last_status) as any}
                      />
                    )}
                  </TableCell>
                  <TableCell align="center" sx={{ minWidth: 120, whiteSpace: 'nowrap' }}>
                    <Tooltip title="今すぐ実行">
                      <span>
                        <IconButton
                          size="small"
                          onClick={() => handleRunNow(schedule.id)}
                          disabled={!schedule.is_active}
                        >
                          <PlayIcon />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="履歴表示">
                      <IconButton size="small" onClick={() => handleViewDetail(schedule)}>
                        <HistoryIcon />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="編集">
                      <IconButton size="small" onClick={() => openEditDialog(schedule)}>
                        <EditIcon />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="削除">
                      <IconButton
                        size="small"
                        onClick={() => {
                          setEditingSchedule(schedule);
                          setDeleteDialogOpen(true);
                        }}
                      >
                        <DeleteIcon />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
              {schedules.length === 0 && !loading && (
                <TableRow>
                  <TableCell colSpan={10} align="center">
                    <Typography color="text.secondary">
                      スケジュールが登録されていません
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {/* 作成ダイアログ */}
      <Dialog open={createDialogOpen} onClose={() => setCreateDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>新しいスケジュール</DialogTitle>
        <DialogContent>
          <Grid container spacing={3} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="スケジュール名"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="未入力時は自動生成されます"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="説明"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                multiline
                rows={2}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <Autocomplete
                multiple
                disableCloseOnSelect
                options={availableScrapers}
                value={formData.scrapers}
                onChange={(_, newValue) => setFormData({ ...formData, scrapers: newValue })}
                getOptionLabel={(option) => getScraperDisplayName(option)}
                renderInput={(params) => (
                  <TextField {...params} label="スクレイパー" required />
                )}
                renderOption={(props, option, { selected }) => (
                  <li {...props}>
                    <Checkbox
                      style={{ marginRight: 8 }}
                      checked={selected}
                    />
                    {getScraperDisplayName(option)}
                  </li>
                )}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => (
                    <Chip {...getTagProps({ index })} key={option} label={getScraperDisplayName(option)} size="small" />
                  ))
                }
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <Autocomplete
                multiple
                disableCloseOnSelect
                options={availableAreas.map(area => area.code)}
                getOptionLabel={(option) => availableAreas.find(a => a.code === option)?.name || option}
                isOptionEqualToValue={(option, value) => option === value}
                value={formData.areas}
                onChange={(_, newValue) => setFormData({ ...formData, areas: Array.from(new Set(newValue)) })}
                renderInput={(params) => (
                  <TextField {...params} label="エリア" helperText="未選択の場合は全エリア" />
                )}
                renderOption={(props, option, { selected }) => (
                  <li {...props}>
                    <Checkbox
                      style={{ marginRight: 8 }}
                      checked={selected}
                    />
                    {availableAreas.find(a => a.code === option)?.name || option}
                  </li>
                )}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => (
                    <Chip 
                      {...getTagProps({ index })} 
                      key={option} 
                      label={availableAreas.find(a => a.code === option)?.name || option}
                      size="small" 
                    />
                  ))
                }
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth required>
                <InputLabel>スケジュールタイプ</InputLabel>
                <Select
                  value={formData.schedule_type}
                  label="スケジュールタイプ"
                  onChange={(e) => setFormData({ ...formData, schedule_type: e.target.value as 'interval' | 'daily' })}
                >
                  <MenuItem value="daily">毎日指定時刻</MenuItem>
                  <MenuItem value="interval">間隔指定</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            {formData.schedule_type === 'interval' && (
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  type="number"
                  label="実行間隔（分）"
                  value={formData.interval_minutes}
                  onChange={(e) => setFormData({ ...formData, interval_minutes: parseInt(e.target.value) || 60 })}
                  required
                  inputProps={{ min: 1 }}
                />
              </Grid>
            )}
{formData.schedule_type === 'daily' && (
              <>
                <Grid item xs={12} sm={3}>
                  <FormControl fullWidth required>
                    <InputLabel>時</InputLabel>
                    <Select
                      value={formData.daily_hour}
                      label="時"
                      onChange={(e) => setFormData({ ...formData, daily_hour: Number(e.target.value) })}
                    >
                      {Array.from({ length: 24 }, (_, i) => (
                        <MenuItem key={i} value={i}>
                          {i.toString().padStart(2, '0')}時
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <FormControl fullWidth required>
                    <InputLabel>分</InputLabel>
                    <Select
                      value={formData.daily_minute}
                      label="分"
                      onChange={(e) => setFormData({ ...formData, daily_minute: Number(e.target.value) })}
                    >
                      {Array.from({ length: 12 }, (_, i) => i * 5).map((minute) => (
                        <MenuItem key={minute} value={minute}>
                          {minute.toString().padStart(2, '0')}分
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
              </>
            )}
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth required>
                <InputLabel>処理上限数</InputLabel>
                <Select
                  value={formData.max_properties}
                  label="処理上限数"
                  onChange={(e) => setFormData({ ...formData, max_properties: Number(e.target.value) })}
                >
                  {availableMaxProperties.map((count) => (
                    <MenuItem key={count} value={count}>
                      {count}件
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  />
                }
                label="アクティブ"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>キャンセル</Button>
          <Button 
            onClick={handleCreate} 
            variant="contained"
            disabled={formData.scrapers.length === 0}
          >
            作成
          </Button>
        </DialogActions>
      </Dialog>

      {/* 編集ダイアログ */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>スケジュール編集</DialogTitle>
        <DialogContent>
          <Grid container spacing={3} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="スケジュール名"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="未入力時は自動生成されます"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="説明"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                multiline
                rows={2}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <Autocomplete
                multiple
                disableCloseOnSelect
                options={availableScrapers}
                value={formData.scrapers}
                onChange={(_, newValue) => setFormData({ ...formData, scrapers: newValue })}
                getOptionLabel={(option) => getScraperDisplayName(option)}
                renderInput={(params) => (
                  <TextField {...params} label="スクレイパー" required />
                )}
                renderOption={(props, option, { selected }) => (
                  <li {...props}>
                    <Checkbox
                      style={{ marginRight: 8 }}
                      checked={selected}
                    />
                    {getScraperDisplayName(option)}
                  </li>
                )}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => (
                    <Chip {...getTagProps({ index })} key={option} label={getScraperDisplayName(option)} size="small" />
                  ))
                }
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <Autocomplete
                multiple
                disableCloseOnSelect
                options={availableAreas.map(area => area.code)}
                getOptionLabel={(option) => availableAreas.find(a => a.code === option)?.name || option}
                isOptionEqualToValue={(option, value) => option === value}
                value={formData.areas}
                onChange={(_, newValue) => setFormData({ ...formData, areas: Array.from(new Set(newValue)) })}
                renderInput={(params) => (
                  <TextField {...params} label="エリア" helperText="未選択の場合は全エリア" />
                )}
                renderOption={(props, option, { selected }) => (
                  <li {...props}>
                    <Checkbox
                      style={{ marginRight: 8 }}
                      checked={selected}
                    />
                    {availableAreas.find(a => a.code === option)?.name || option}
                  </li>
                )}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => (
                    <Chip 
                      {...getTagProps({ index })} 
                      key={option} 
                      label={availableAreas.find(a => a.code === option)?.name || option}
                      size="small" 
                    />
                  ))
                }
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth required>
                <InputLabel>スケジュールタイプ</InputLabel>
                <Select
                  value={formData.schedule_type}
                  label="スケジュールタイプ"
                  onChange={(e) => setFormData({ ...formData, schedule_type: e.target.value as 'interval' | 'daily' })}
                >
                  <MenuItem value="daily">毎日指定時刻</MenuItem>
                  <MenuItem value="interval">間隔指定</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            {formData.schedule_type === 'interval' && (
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  type="number"
                  label="実行間隔（分）"
                  value={formData.interval_minutes}
                  onChange={(e) => setFormData({ ...formData, interval_minutes: parseInt(e.target.value) || 60 })}
                  required
                  inputProps={{ min: 1 }}
                />
              </Grid>
            )}
{formData.schedule_type === 'daily' && (
              <>
                <Grid item xs={12} sm={3}>
                  <FormControl fullWidth required>
                    <InputLabel>時</InputLabel>
                    <Select
                      value={formData.daily_hour}
                      label="時"
                      onChange={(e) => setFormData({ ...formData, daily_hour: Number(e.target.value) })}
                    >
                      {Array.from({ length: 24 }, (_, i) => (
                        <MenuItem key={i} value={i}>
                          {i.toString().padStart(2, '0')}時
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <FormControl fullWidth required>
                    <InputLabel>分</InputLabel>
                    <Select
                      value={formData.daily_minute}
                      label="分"
                      onChange={(e) => setFormData({ ...formData, daily_minute: Number(e.target.value) })}
                    >
                      {Array.from({ length: 12 }, (_, i) => i * 5).map((minute) => (
                        <MenuItem key={minute} value={minute}>
                          {minute.toString().padStart(2, '0')}分
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
              </>
            )}
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth required>
                <InputLabel>処理上限数</InputLabel>
                <Select
                  value={formData.max_properties}
                  label="処理上限数"
                  onChange={(e) => setFormData({ ...formData, max_properties: Number(e.target.value) })}
                >
                  {availableMaxProperties.map((count) => (
                    <MenuItem key={count} value={count}>
                      {count}件
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  />
                }
                label="アクティブ"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>キャンセル</Button>
          <Button 
            onClick={handleUpdate} 
            variant="contained"
            disabled={formData.scrapers.length === 0}
          >
            更新
          </Button>
        </DialogActions>
      </Dialog>

      {/* 詳細・履歴ダイアログ */}
      <Dialog open={detailDialogOpen} onClose={() => setDetailDialogOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>実行履歴</DialogTitle>
        <DialogContent>
          {selectedSchedule && (
            <Box>
              <Typography variant="h6" gutterBottom>
                {selectedSchedule.name}
              </Typography>
              {selectedSchedule.description && (
                <Typography color="text.secondary" paragraph>
                  {selectedSchedule.description}
                </Typography>
              )}
              
              <Divider sx={{ my: 2 }} />
              
              <List>
                {selectedSchedule.history.map((item) => (
                  <ListItem key={item.id} divider>
                    <ListItemText
                      primary={
                        <Box display="flex" alignItems="center" gap={1}>
                          <Typography variant="subtitle2">
                            {format(new Date(item.started_at), 'yyyy/MM/dd HH:mm:ss', { locale: ja })}
                          </Typography>
                          <Chip 
                            label={item.status} 
                            size="small" 
                            color={getStatusColor(item.status) as any}
                          />
                          {item.task_id && (
                            <Typography variant="caption" color="text.secondary">
                              Task ID: {item.task_id}
                            </Typography>
                          )}
                        </Box>
                      }
                      secondary={
                        <Box>
                          {item.completed_at && (
                            <Typography variant="caption" color="text.secondary" display="block">
                              完了: {format(new Date(item.completed_at), 'yyyy/MM/dd HH:mm:ss', { locale: ja })}
                            </Typography>
                          )}
                          {item.error_message && (
                            <Typography variant="caption" color="error" display="block">
                              エラー: {item.error_message}
                            </Typography>
                          )}
                        </Box>
                      }
                    />
                  </ListItem>
                ))}
                {selectedSchedule.history.length === 0 && (
                  <ListItem>
                    <ListItemText
                      primary={
                        <Typography color="text.secondary" align="center">
                          実行履歴がありません
                        </Typography>
                      }
                    />
                  </ListItem>
                )}
              </List>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailDialogOpen(false)}>閉じる</Button>
        </DialogActions>
      </Dialog>

      {/* 削除確認ダイアログ */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>スケジュール削除</DialogTitle>
        <DialogContent>
          <Typography>
            「{editingSchedule?.name}」を削除しますか？この操作は取り消せません。
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>キャンセル</Button>
          <Button onClick={handleDelete} color="error" variant="contained">
            削除
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};