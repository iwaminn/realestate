import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  DialogContentText,
  TextField,
  Button,
} from '@mui/material';

interface DeleteConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  message?: string;
}

const DeleteConfirmDialog: React.FC<DeleteConfirmDialogProps> = ({
  open,
  onClose,
  onConfirm,
  message,
}) => {
  // ローカル状態で管理（親コンポーネントの再レンダリングを回避）
  const [confirmText, setConfirmText] = React.useState('');

  const handleClose = () => {
    setConfirmText('');
    onClose();
  };

  const handleConfirm = () => {
    if (confirmText !== '削除') {
      alert('確認テキストが正しくありません。「削除」と入力してください。');
      return;
    }
    setConfirmText('');
    onConfirm();
  };

  // ダイアログが閉じたときにテキストをリセット
  React.useEffect(() => {
    if (!open) {
      setConfirmText('');
    }
  }, [open]);

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>スクレイピング履歴の削除</DialogTitle>
      <DialogContent>
        <DialogContentText style={{ whiteSpace: 'pre-wrap' }}>
          {message || 'この操作は取り消すことができません。\nすべてのスクレイピング履歴が完全に削除されます。'}
        </DialogContentText>
        <DialogContentText sx={{ mt: 2, fontWeight: 'bold' }}>
          続行するには、下のテキストフィールドに「削除」と入力してください。
        </DialogContentText>
        <TextField
          autoFocus
          margin="dense"
          fullWidth
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="削除"
          sx={{ mt: 2 }}
          inputProps={{
            autoComplete: 'off',
            spellCheck: false,
          }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} color="primary">
          キャンセル
        </Button>
        <Button 
          onClick={handleConfirm} 
          color="error"
          variant="contained"
          disabled={confirmText !== '削除'}
        >
          削除を実行
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default React.memo(DeleteConfirmDialog);