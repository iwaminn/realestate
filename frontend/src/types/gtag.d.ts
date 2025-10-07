// Google Analytics gtag.jsの型定義
interface Window {
  dataLayer: any[];
  gtag: (
    command: 'config' | 'set' | 'event' | 'js',
    targetId: string | Date,
    config?: { [key: string]: any }
  ) => void;
}
