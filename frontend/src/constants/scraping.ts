/**
 * スクレイピング管理画面で使用する定数
 */

// スクレイパーの定義
export const SCRAPERS = [
  { value: 'suumo', label: 'SUUMO' },
  { value: 'homes', label: 'LIFULL HOME\'S' },
  { value: 'rehouse', label: '三井のリハウス' },
  { value: 'nomu', label: 'ノムコム' },
  { value: 'livable', label: '東急リバブル' },
] as const;

// タスクステータス
export const TASK_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
  PAUSED: 'paused',
} as const;

// タスクステータスのラベル
export const TASK_STATUS_LABELS: Record<string, string> = {
  [TASK_STATUS.PENDING]: '待機中',
  [TASK_STATUS.RUNNING]: '実行中',
  [TASK_STATUS.COMPLETED]: '完了',
  [TASK_STATUS.FAILED]: 'エラー',
  [TASK_STATUS.CANCELLED]: 'キャンセル',
  [TASK_STATUS.PAUSED]: '一時停止中',
};

// タスクステータスの色
export const TASK_STATUS_COLORS: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'> = {
  [TASK_STATUS.PENDING]: 'default',
  [TASK_STATUS.RUNNING]: 'primary',
  [TASK_STATUS.COMPLETED]: 'success',
  [TASK_STATUS.FAILED]: 'error',
  [TASK_STATUS.CANCELLED]: 'warning',
  [TASK_STATUS.PAUSED]: 'info',
};

// アラートの重要度
export const ALERT_SEVERITY = {
  CRITICAL: 'critical',
  WARNING: 'warning',
  INFO: 'info',
} as const;

// アラートタイプ
export const ALERT_TYPES = {
  CRITICAL_ERROR_RATE: 'critical_error_rate',
  CONSECUTIVE_ERRORS: 'consecutive_errors',
  SUSPICIOUS_UPDATE: 'suspicious_update',
  VALIDATION_ERROR: 'validation_error',
} as const;

// ポーリング間隔（ミリ秒）
export const POLLING_INTERVAL = 2000;

// タスクのタイムアウト時間（ミリ秒）
export const TASK_TIMEOUT = 10000;

// デフォルトの詳細再取得時間（時間）
export const DEFAULT_DETAIL_REFETCH_HOURS = 2160; // 90日

// 詳細再取得時間のプリセット
export const DETAIL_REFETCH_PRESETS = [
  { label: '常に更新', hours: 0 },
  { label: '24時間', hours: 24 },
  { label: '3日', hours: 72 },
  { label: '1週間', hours: 168 },
  { label: '30日', hours: 720 },
  { label: '90日', hours: 2160 },
];