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
} from '@mui/material';
import {
  ArrowBack,
  Gavel,
} from '@mui/icons-material';
import { APP_CONFIG } from '../config/app';

const TermsPage: React.FC = () => {
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
          <Gavel sx={{ mr: 2, fontSize: 32, color: 'primary.main' }} />
          <Typography variant="h4" component="h1">
            利用規約
          </Typography>
        </Box>

        <Typography variant="body1" sx={{ mb: 4, lineHeight: 1.8 }}>
          この利用規約（以下、「本規約」といいます）は、{APP_CONFIG.APP_NAME}（以下、「本サービス」といいます）の利用条件を定めるものです。
          利用者の皆様には、本規約に従って本サービスをご利用いただきます。
        </Typography>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第1条（適用）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本規約は、利用者と本サービス運営者との間の本サービスの利用に関わる一切の関係に適用されるものとします。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第2条（サービス内容）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本サービスは、以下のサービスを提供します：
          </Typography>
          <List>
            <ListItem>
              <ListItemText
                primary="1. 不動産物件情報の検索・閲覧機能"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="2. 物件情報の比較機能"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="3. 価格推移の表示機能"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="4. 外部不動産サイトへのリンク提供"
                sx={{ pl: 2 }}
              />
            </ListItem>
          </List>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本サービスは情報提供のみを目的としており、不動産の売買・賃貸の仲介、代理、媒介等の取引行為は一切行いません。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第3条（利用料金）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            本サービスの利用は無料です。ただし、本サービスの利用に必要なインターネット接続料金等の通信費用は、
            利用者の負担となります。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第4条（禁止事項）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            利用者は、本サービスの利用にあたり、以下の行為をしてはなりません：
          </Typography>
          <List>
            <ListItem>
              <ListItemText
                primary="1. 法令または公序良俗に違反する行為"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="2. 本サービスのサーバーまたはネットワークの機能を破壊したり、妨害したりする行為"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="3. 本サービスの運営を妨害するおそれのある行為"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="4. 他の利用者に関する個人情報等を収集または蓄積する行為"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="5. 自動化された手段（スクレイピング、ボット等）による過度なアクセス"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="6. 本サービスの情報を商業目的で無断転載・複製する行為"
                sx={{ pl: 2 }}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="7. その他、運営者が不適切と判断する行為"
                sx={{ pl: 2 }}
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第5条（知的財産権）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            1. 本サービスのシステム、プログラム、デザイン等に関する著作権その他の知的財産権は、
            本サービス運営者に帰属します。
          </Typography>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            2. 本サービスに掲載される物件情報の著作権は、各情報提供元に帰属します。
          </Typography>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            3. 利用者は、本サービスの利用により得られる一切の情報について、
            運営者および情報提供元の事前の書面による承諾を得ることなく、
            転載、複製、出版、放送、公衆送信等その他の方法により利用してはなりません。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第6条（免責事項）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            1. 運営者は、本サービスに掲載される情報の正確性、完全性、有用性等について、いかなる保証も行いません。
          </Typography>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            2. 運営者は、利用者が本サービスを利用したことにより生じた損害、
            または第三者との間で生じたトラブルについて、一切の責任を負いません。
          </Typography>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            3. 運営者は、本サービスの提供の中断、停止、終了、利用不能または変更、
            利用者が本サービスに送信したメッセージまたは情報の削除または消失、
            その他本サービスに関して利用者が被った損害について、一切の責任を負いません。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第7条（サービス内容の変更等）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            運営者は、利用者に通知することなく、本サービスの内容を変更しまたは本サービスの提供を中止することができるものとし、
            これによって利用者に生じた損害について一切の責任を負いません。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第8条（利用規約の変更）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            1. 運営者は、必要と判断した場合には、利用者に通知することなくいつでも本規約を変更することができるものとします。
          </Typography>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            2. 変更後の本規約は、本サービス上に掲載した時点から効力を生じるものとします。
          </Typography>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            3. 本規約の変更後、本サービスの利用を継続した場合、利用者は変更後の本規約に同意したものとみなされます。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第9条（個人情報の取扱い）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            運営者は、本サービスの利用によって取得する個人情報については、
            別途定める「プライバシーポリシー」に従い適切に取り扱うものとします。
          </Typography>
        </Box>

        <Typography variant="h5" sx={{ mb: 2, fontWeight: 'bold' }}>
          第10条（準拠法・裁判管轄）
        </Typography>
        <Box sx={{ mb: 4, pl: 2 }}>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            1. 本規約の解釈にあたっては、日本法を準拠法とします。
          </Typography>
          <Typography variant="body1" paragraph sx={{ lineHeight: 1.8 }}>
            2. 本サービスに関して紛争が生じた場合には、東京地方裁判所を第一審の専属的合意管轄裁判所とします。
          </Typography>
        </Box>

        <Paper sx={{ p: 3, backgroundColor: '#e3f2fd', border: '1px solid #90caf9' }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1 }}>
            お問い合わせ
          </Typography>
          <Typography variant="body2" sx={{ lineHeight: 1.8 }}>
            本規約に関するお問い合わせは、本サービス内のお問い合わせフォームよりご連絡ください。
            なお、物件に関する具体的なお問い合わせは、各物件の掲載元不動産会社に直接お願いいたします。
          </Typography>
        </Paper>

        <Box sx={{ mt: 4, pt: 3, borderTop: '1px solid #e0e0e0' }}>
          <Typography variant="body2" color="text.secondary" align="center">
            制定日: 2025年1月24日<br />
            最終更新日: 2025年1月24日
          </Typography>
        </Box>
      </Paper>
    </Container>
  );
};

export default TermsPage;