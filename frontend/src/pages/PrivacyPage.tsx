import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  Paper,
  Button,
  List,
  ListItem,
  ListItemText,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import {
  ArrowBack,
  Security,
  Cookie,
  Storage,
} from '@mui/icons-material';
import { APP_CONFIG } from '../config/app';

const PrivacyPage: React.FC = () => {
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <Container maxWidth="md" sx={{ py: 4, px: { xs: 0.5, sm: 2, md: 3 } }}>
      <Button
        component={Link}
        to="/"
        startIcon={<ArrowBack />}
        sx={{ mb: 3 }}
      >
        トップページに戻る
      </Button>

      <Paper elevation={1} sx={{ p: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
          <Security sx={{ mr: 2, fontSize: 32, color: 'success.main' }} />
          <Typography variant="h4" component="h1">
            プライバシーポリシー
          </Typography>
        </Box>

        <Typography variant="body1" sx={{ mb: 4, lineHeight: 1.8 }}>
          {APP_CONFIG.APP_NAME}（以下、「当サービス」といいます）は、利用者のプライバシーを尊重し、
          個人情報の保護に努めます。本プライバシーポリシーは、当サービスにおける個人情報の取扱いについて説明します。
        </Typography>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          1. 収集する情報
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            当サービスは、以下の情報を収集する場合があります：
          </Typography>

          <Typography variant="h6" sx={{ mb: 1, fontWeight: 'bold', fontSize: '1.1rem' }}>
            （1）自動的に収集される情報
          </Typography>
          <List>
            <ListItem>
              <ListItemText
                primary="アクセスログ情報（IPアドレス、ブラウザ種類、アクセス日時等）"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Cookie情報（サイトの利用状況、設定情報等）"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="デバイス情報（OS、画面サイズ等）"
                sx={{ pl: 2 }}
              />
            </ListItem>
          </List>

          <Typography variant="h6" sx={{ mb: 1, fontWeight: 'bold', fontSize: '1.1rem', mt: 2 }}>
            （2）利用者が提供する情報
          </Typography>
          <List>
            <ListItem>
              <ListItemText
                primary="ユーザー登録情報（メールアドレス、パスワード等）"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="ブックマークした物件情報（サーバーのデータベースに保存）"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="検索条件、並び順等の設定情報（URLパラメータ経由）"
                sx={{ pl: 2 }}
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          2. 情報の利用目的
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            収集した情報は、以下の目的で利用します：
          </Typography>
          <List>
            <ListItem>
              <ListItemText
                primary="1. サービスの提供・運営"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="2. サービスの改善・新機能の開発"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="3. アクセス解析・統計データの作成"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="4. セキュリティの向上・不正利用の防止"
                sx={{ pl: 2 }}
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          3. Cookieの使用について
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 2 }}>
            <Cookie sx={{ mr: 1, mt: 0.5, color: 'text.secondary' }} />
            <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
              当サービスでは、利用者の利便性向上のためCookieを使用しています。
              Cookieは、以下の目的で使用されます：
            </Typography>
          </Box>
          <TableContainer component={Paper} variant="outlined" sx={{ mb: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Cookie名</TableCell>
                  <TableCell>用途</TableCell>
                  <TableCell>保存期間</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <TableRow>
                  <TableCell>セッションCookie</TableCell>
                  <TableCell>一時的な情報の保存</TableCell>
                  <TableCell>ブラウザ終了時まで</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>設定Cookie</TableCell>
                  <TableCell>表示設定、並び順の保存</TableCell>
                  <TableCell>1年間</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>分析Cookie</TableCell>
                  <TableCell>利用状況の分析</TableCell>
                  <TableCell>2年間</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
          <Typography variant="body2" sx={{ lineHeight: 1.8 }}>
            ※ブラウザの設定により、Cookieの受け入れを拒否することができますが、
            その場合、一部の機能が正常に動作しない可能性があります。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          4. ローカルストレージの使用
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 2 }}>
            <Storage sx={{ mr: 1, mt: 0.5, color: 'text.secondary' }} />
            <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
              当サービスでは、ブラウザのローカルストレージを使用して以下の情報を保存します：
            </Typography>
          </Box>
          <List>
            <ListItem>
              <ListItemText
                primary="認証トークン"
                secondary="ログイン状態を維持するため"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="表示設定・並び順"
                secondary="次回訪問時の利便性向上のため"
                sx={{ pl: 2 }}
              />
            </ListItem>
          </List>
          <Typography variant="body2" sx={{ lineHeight: 1.8, mb: 1 }}>
            これらの情報は利用者のブラウザにのみ保存されます。
          </Typography>
          <Typography variant="body2" sx={{ lineHeight: 1.8, fontWeight: 'bold' }}>
            ※ブックマーク情報や物件データは、ローカルストレージではなくサーバーのデータベースに安全に保管されます。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          5. 第三者への情報提供
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            当サービスは、以下の場合を除き、収集した情報を第三者に提供することはありません：
          </Typography>
          <List>
            <ListItem>
              <ListItemText
                primary="1. 利用者の同意がある場合"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="2. 法令に基づく開示請求があった場合"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="3. 利用者や公共の安全を守るために必要な場合"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="4. サービス向上のための統計データとして、個人を特定できない形で利用する場合"
                sx={{ pl: 2 }}
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          6. 外部サービスとの連携
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            当サービスには、以下の外部サービスへのリンクが含まれています：
          </Typography>
          <List>
            <ListItem>
              <ListItemText
                primary="各不動産情報サイト（SUUMO、LIFULL HOME'S等）"
                secondary="物件詳細情報の閲覧のため"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Google Maps"
                secondary="物件の位置情報表示のため"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="ハザードマップポータルサイト"
                secondary="防災情報の確認のため"
                sx={{ pl: 2 }}
              />
            </ListItem>
          </List>
          <Typography variant="body2" sx={{ lineHeight: 1.8 }}>
            これらの外部サービスには、各サービス独自のプライバシーポリシーが適用されます。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          7. セキュリティ対策
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            当サービスは、収集した情報を適切に管理し、以下のセキュリティ対策を実施しています：
          </Typography>
          <List>
            <ListItem>
              <ListItemText
                primary="SSL/TLSによる通信の暗号化"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="アクセス権限の適切な管理"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="定期的なセキュリティ更新"
                sx={{ pl: 2 }}
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          8. プライバシーポリシーの変更
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            当サービスは、必要に応じて本プライバシーポリシーを変更することがあります。
            変更後のプライバシーポリシーは、本ページに掲載した時点から効力を生じるものとします。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          9. お問い合わせ
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本プライバシーポリシーに関するお問い合わせは、サービス内のお問い合わせフォームよりご連絡ください。
          </Typography>
        </Box>

        <Paper sx={{ p: 3, backgroundColor: '#e8f5e9', border: '1px solid #66bb6a' }}>
          <Box sx={{ display: 'flex', alignItems: 'flex-start' }}>
            <Security sx={{ color: '#2e7d32', mr: 2, mt: 0.5 }} />
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1 }}>
                利用者の権利
              </Typography>
              <Typography variant="body2" sx={{ lineHeight: 1.8 }}>
                利用者は、自身の個人情報について、開示、訂正、削除等を求める権利を有しています。
                これらの請求については、お問い合わせフォームよりご連絡ください。
                本人確認のうえ、法令に従い適切に対応いたします。
              </Typography>
            </Box>
          </Box>
        </Paper>

        <Box sx={{ mt: 4, pt: 3, borderTop: '1px solid #e0e0e0' }}>
          <Typography variant="body2" color="text.secondary" align="center">
            制定日: 2025年1月24日<br />
            最終更新日: 2025年10月1日
          </Typography>
        </Box>
      </Paper>
    </Container>
  );
};

export default PrivacyPage;