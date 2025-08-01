import React, { useState, useEffect } from 'react';
import {
  Container,
  Typography,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Box,
  Chip,
  Alert,
  CircularProgress,
  Snackbar,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  IconButton,
  Tooltip,
  Tabs,
  Tab,
} from '@mui/material';
import {
  Logout as LogoutIcon,
} from '@mui/icons-material';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import AdminScraping from '../components/AdminScraping';
import BuildingDuplicateManager from '../components/BuildingDuplicateManager';
import BuildingMergeHistory from '../components/BuildingMergeHistory';
import PropertyMergeHistory from '../components/PropertyMergeHistory';
import ManualBuildingMerger from '../components/ManualBuildingMerger';
import ManualPropertyMerger from '../components/ManualPropertyMerger';
import PropertyDuplicateGroups from '../components/PropertyDuplicateGroups';
import PropertyExclusionHistory from '../components/PropertyExclusionHistory';
import BuildingExclusionHistory from '../components/BuildingExclusionHistory';


const Admin: React.FC = () => {
  const { isAuthenticated, username, isLoading, logout } = useAuth();
  const navigate = useNavigate();
  
  const [activeTab, setActiveTab] = useState(0);
  const [propertySubTab, setPropertySubTab] = useState(0);
  const [buildingSubTab, setBuildingSubTab] = useState(0);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' });

  useEffect(() => {
    // 認証チェック完了後にのみリダイレクト
    if (!isLoading && !isAuthenticated) {
      navigate('/admin/login');
    }
  }, [isAuthenticated, isLoading, navigate]);


  // 認証チェック中はローディング表示
  if (isLoading) {
    return (
      <Container>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="80vh">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">
          管理画面
        </Typography>
        <Box display="flex" alignItems="center" gap={2}>
          <Typography variant="body1" color="text.secondary">
            ログイン中: {username}
          </Typography>
          <Button
            variant="outlined"
            startIcon={<LogoutIcon />}
            onClick={() => {
              logout();
              navigate('/');
            }}
          >
            ログアウト
          </Button>
        </Box>
      </Box>

      <Paper sx={{ mb: 3 }}>
        <Tabs value={activeTab} onChange={(_, value) => setActiveTab(value)}>
          <Tab label="物件重複管理" />
          <Tab label="建物重複管理" />
          <Tab label="スクレイピング" />
        </Tabs>
      </Paper>

      {activeTab === 0 && (
        <Box>
          <Paper sx={{ mb: 2 }}>
            <Tabs value={propertySubTab} onChange={(_, value) => setPropertySubTab(value)}>
              <Tab label="重複グループ" />
              <Tab label="統合履歴" />
              <Tab label="除外履歴" />
            </Tabs>
          </Paper>

          {propertySubTab === 0 && (
            <>
              <ManualPropertyMerger />
              <PropertyDuplicateGroups />
            </>
          )}

          {propertySubTab === 1 && (
            <PropertyMergeHistory />
          )}

          {propertySubTab === 2 && (
            <PropertyExclusionHistory />
          )}
        </Box>
      )}

      {activeTab === 1 && (
        <Box>
          <Paper sx={{ mb: 2 }}>
            <Tabs value={buildingSubTab} onChange={(_, value) => setBuildingSubTab(value)}>
              <Tab label="重複候補" />
              <Tab label="統合履歴" />
              <Tab label="除外履歴" />
            </Tabs>
          </Paper>

          {buildingSubTab === 0 && (
            <>
              <ManualBuildingMerger />
              <BuildingDuplicateManager />
            </>
          )}

          {buildingSubTab === 1 && (
            <BuildingMergeHistory />
          )}

          {buildingSubTab === 2 && (
            <BuildingExclusionHistory />
          )}
        </Box>
      )}

      {activeTab === 2 && (
        <Box>
          <AdminScraping />
        </Box>
      )}

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert 
          onClose={() => setSnackbar({ ...snackbar, open: false })} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default Admin;