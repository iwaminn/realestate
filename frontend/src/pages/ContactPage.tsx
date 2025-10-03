import React, { useState } from 'react';
import {
  Container,
  Typography,
  Paper,
  TextField,
  Button,
  Box,
  Alert,
  CircularProgress,
} from '@mui/material';
import { Send as SendIcon } from '@mui/icons-material';
import axios from '../utils/axiosConfig';

const ContactPage: React.FC = () => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    subject: '',
    message: '',
  });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      await axios.post('/contact', formData);
      setSuccess(true);
      setFormData({
        name: '',
        email: '',
        subject: '',
        message: '',
      });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'お問い合わせの送信に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="md" sx={{ py: 4, px: { xs: 0.5, sm: 2, md: 3 } }}>
      <Typography variant="h4" gutterBottom>
        お問い合わせ
      </Typography>

      <Paper elevation={2} sx={{ p: 3, mt: 3 }}>
        <Typography variant="body1" paragraph>
          ご質問やご要望がございましたら、以下のフォームからお気軽にお問い合わせください。
        </Typography>

        {success && (
          <Alert severity="success" sx={{ mb: 3 }}>
            お問い合わせを受け付けました。ご連絡ありがとうございます。
          </Alert>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        <Box component="form" onSubmit={handleSubmit}>
          <TextField
            fullWidth
            label="お名前"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            margin="normal"
          />

          <TextField
            fullWidth
            label="メールアドレス"
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            required
            margin="normal"
          />

          <TextField
            fullWidth
            label="件名"
            name="subject"
            value={formData.subject}
            onChange={handleChange}
            required
            margin="normal"
          />

          <TextField
            fullWidth
            label="お問い合わせ内容"
            name="message"
            value={formData.message}
            onChange={handleChange}
            required
            multiline
            rows={6}
            margin="normal"
          />

          <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              type="submit"
              variant="contained"
              color="primary"
              size="large"
              disabled={loading}
              startIcon={loading ? <CircularProgress size={20} /> : <SendIcon />}
            >
              {loading ? '送信中...' : '送信'}
            </Button>
          </Box>
        </Box>
      </Paper>
    </Container>
  );
};

export default ContactPage;
