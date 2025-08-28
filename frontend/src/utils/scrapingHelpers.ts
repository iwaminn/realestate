/**
 * スクレイピング管理画面で使用するヘルパー関数とタイプ定義
 */

// タスクステータスのマッピング
export const getStatusLabel = (status: string): string => {
  const statusLabels: Record<string, string> = {
    'pending': '待機中',
    'running': '実行中', 
    'completed': '完了',
    'failed': 'エラー',
    'cancelled': 'キャンセル',
    'paused': '一時停止中',
  };
  return statusLabels[status] || status;
};

// ステータスの色を取得
export const getStatusColor = (status: string): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' => {
  const statusColors: Record<string, 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning'> = {
    'pending': 'default',
    'running': 'primary',
    'completed': 'success',
    'failed': 'error',
    'cancelled': 'warning',
    'paused': 'info',
  };
  return statusColors[status] || 'default';
};

// スクレイパー名のマッピング
export const getScraperLabel = (scraper: string): string => {
  const scraperLabels: Record<string, string> = {
    'suumo': 'SUUMO',
    'homes': 'LIFULL HOME\'S',
    'rehouse': '三井のリハウス',
    'nomu': 'ノムコム',
    'livable': '東急リバブル',
  };
  return scraperLabels[scraper] || scraper;
};

// アラートの重要度レベルの色を取得
export const getAlertSeverityColor = (severity: string): 'error' | 'warning' | 'info' => {
  const severityMap: Record<string, 'error' | 'warning' | 'info'> = {
    'critical': 'error',
    'warning': 'warning',
    'info': 'info',
  };
  return severityMap[severity] || 'info';
};

// 日時のフォーマット
export const formatDateTime = (dateString: string | null): string => {
  if (!dateString) return '-';
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date);
};

// 数値を3桁区切りでフォーマット
export const formatNumber = (num: number | undefined | null): string => {
  if (num === undefined || num === null) return '0';
  return num.toLocaleString('ja-JP');
};

// 実行時間の計算
export const calculateDuration = (startedAt: string, completedAt: string | null): string => {
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  const durationMs = end - start;
  
  const hours = Math.floor(durationMs / (1000 * 60 * 60));
  const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((durationMs % (1000 * 60)) / 1000);
  
  if (hours > 0) {
    return `${hours}時間${minutes}分${seconds}秒`;
  } else if (minutes > 0) {
    return `${minutes}分${seconds}秒`;
  } else {
    return `${seconds}秒`;
  }
};

// 進捗率の計算
export const calculateProgressPercentage = (current: number, total: number): number => {
  if (total === 0) return 0;
  return Math.round((current / total) * 100);
};