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
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import {
  ArrowBack,
  CheckCircleOutline,
  Warning,
  Info,
} from '@mui/icons-material';
import { APP_CONFIG } from '../config/app';

const DisclaimerPage: React.FC = () => {
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
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
          <Warning sx={{ mr: 2, fontSize: 32, color: 'warning.main' }} />
          <Typography variant="h4" component="h1">
            免責事項
          </Typography>
        </Box>

        <Typography variant="body1" sx={{ mb: 4, lineHeight: 1.8 }}>
          {APP_CONFIG.APP_NAME}（以下、「本サイト」といいます）をご利用いただく前に、以下の免責事項をよくお読みください。
          本サイトをご利用いただいた場合、これらの免責事項に同意したものとみなされます。
        </Typography>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          1. 情報の正確性について
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本サイトに掲載されている物件情報は、各不動産情報サイトから自動的に収集したものです。
            情報の正確性、完全性、有用性、安全性等について、いかなる保証も行いません。
          </Typography>
          <List>
            <ListItem>
              <ListItemIcon>
                <CheckCircleOutline color="primary" />
              </ListItemIcon>
              <ListItemText
                primary="物件情報は収集時点のものであり、最新の状況とは異なる場合があります"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <CheckCircleOutline color="primary" />
              </ListItemIcon>
              <ListItemText
                primary="価格、間取り、面積等の情報は変更されている可能性があります"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <CheckCircleOutline color="primary" />
              </ListItemIcon>
              <ListItemText
                primary="物件がすでに成約済みである可能性があります"
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          2. 本サイトの位置づけ
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本サイトは物件情報の検索・閲覧サービスを提供するものであり、以下の点にご注意ください：
          </Typography>
          <List>
            <ListItem>
              <ListItemIcon>
                <Info color="info" />
              </ListItemIcon>
              <ListItemText
                primary="本サイトは不動産の売買・賃貸の仲介業務は行っておりません"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <Info color="info" />
              </ListItemIcon>
              <ListItemText
                primary="宅地建物取引業法に基づく免許を有しておりません"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon>
                <Info color="info" />
              </ListItemIcon>
              <ListItemText
                primary="物件の詳細や取引については、必ず掲載元の不動産会社にお問い合わせください"
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          3. 損害賠償責任
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本サイトの利用により生じたいかなる損害についても、本サイトの運営者は一切の責任を負いません。
            これには以下が含まれますが、これらに限定されません：
          </Typography>
          <List>
            <ListItem>
              <ListItemText
                primary="誤った情報に基づく意思決定による損害"
                sx={{ pl: 4 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="物件情報の変更・削除による損害"
                sx={{ pl: 4 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="本サイトの利用不能による損害"
                sx={{ pl: 4 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="第三者サイトへのリンクから生じる損害"
                sx={{ pl: 4 }}
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          4. 外部リンクについて
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本サイトから各不動産サイトへのリンクを提供していますが、リンク先のウェブサイトの内容について、
            本サイトは一切の責任を負いません。リンク先のご利用は、利用者ご自身の責任において行ってください。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          5. 著作権・知的財産権
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本サイトに掲載されている物件情報の著作権は、元の情報提供者に帰属します。
            本サイトのシステム・デザイン等の著作権は、本サイトの運営者に帰属します。
            無断での転載・複製を禁じます。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          6. 免責事項の変更
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本免責事項は、予告なく変更される場合があります。
            変更後の免責事項は、本サイトに掲載した時点から効力を生じるものとします。
          </Typography>
        </Box>

        <Paper sx={{ p: 3, backgroundColor: '#fff3e0', border: '1px solid #ffb74d' }}>
          <Box sx={{ display: 'flex', alignItems: 'flex-start' }}>
            <Warning sx={{ color: '#f57c00', mr: 2, mt: 0.5 }} />
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1 }}>
                物件のご検討にあたって
              </Typography>
              <Typography variant="body2" sx={{ lineHeight: 1.8 }}>
                実際に物件を検討される際は、必ず不動産会社に最新の情報をご確認ください。
                物件の内覧、契約等は、宅地建物取引業の免許を持つ不動産会社を通じて行ってください。
              </Typography>
            </Box>
          </Box>
        </Paper>

        <Box sx={{ mt: 4, pt: 3, borderTop: '1px solid #e0e0e0' }}>
          <Typography variant="body2" color="text.secondary" align="center">
            最終更新日: 2025年1月24日
          </Typography>
        </Box>
      </Paper>
    </Container>
  );
};

export default DisclaimerPage;