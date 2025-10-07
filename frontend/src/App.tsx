import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { Container } from '@mui/material';
import { AuthProvider } from './contexts/AuthContext';
import { UserAuthProvider } from './contexts/UserAuthContext';
import Header from './components/Header';
import { APP_CONFIG } from './config/app';
import AreaSelectionPage from './pages/AreaSelectionPage';
import PropertyListPage from './pages/PropertyListPage';
import PropertyDetailPage from './pages/PropertyDetailPage';
import BuildingPropertiesPage from './pages/BuildingPropertiesPage';
import Admin from './pages/Admin';
import AdminLogin from './components/AdminLogin';
import PropertyUpdatesPage from './pages/PropertyUpdatesPage';
import RedirectToUpdates from './components/RedirectToUpdates';
import { BookmarksPage } from './pages/BookmarksPage';
import { VerifyEmailPage } from './pages/VerifyEmailPage';
import { AuthCallbackPage } from './pages/AuthCallbackPage';
import { AccountSettingsPage } from './pages/AccountSettingsPage';
import { VerifyPasswordSetPage } from './pages/VerifyPasswordSetPage';
import { RequestPasswordResetPage } from './pages/RequestPasswordResetPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { VerifyEmailChangePage } from './pages/VerifyEmailChangePage';
import Footer from './components/Footer';
import ScrollToTop from './components/ScrollToTop';
import DisclaimerPage from './pages/DisclaimerPage';
import TermsPage from './pages/TermsPage';
import PrivacyPage from './pages/PrivacyPage';
import TransactionPricesPage from './pages/TransactionPricesPage';
import ContactPage from './pages/ContactPage';
import './utils/axiosConfig'; // Axiosの設定を読み込む

// Google Analyticsのページビュートラッキングコンポーネント
function GoogleAnalyticsTracker() {
  const location = useLocation();

  useEffect(() => {
    // 管理画面（/admin）の場合はトラッキングしない
    if (location.pathname.startsWith('/admin')) {
      return;
    }

    // Google Analyticsのgtagが存在する場合のみトラッキング
    if (typeof window.gtag === 'function') {
      window.gtag('config', 'G-C985LS1W3F', {
        page_path: location.pathname + location.search,
      });
    }
  }, [location]);

  return null;
}

const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
    },
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
  },
});

function App() {
  // HTMLタイトルを設定
  useEffect(() => {
    document.title = APP_CONFIG.HTML_TITLE;
  }, []);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AuthProvider>
        <Router future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
          <UserAuthProvider>
            <GoogleAnalyticsTracker />
            <ScrollToTop />
            <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
              <Header />
              <Container maxWidth="lg" sx={{ mt: 4, mb: 4, flex: 1 }}>
                <Routes>
                  <Route path="/" element={<AreaSelectionPage />} />
                  <Route path="/properties" element={<PropertyListPage />} />
                  <Route path="/properties/:id" element={<PropertyDetailPage />} />
                  <Route path="/buildings/:buildingId/properties" element={<BuildingPropertiesPage />} />
                  <Route path="/bookmarks" element={<BookmarksPage />} />
                  <Route path="/account/settings" element={<AccountSettingsPage />} />
                  <Route path="/verify-password-set" element={<VerifyPasswordSetPage />} />
                  <Route path="/request-password-reset" element={<RequestPasswordResetPage />} />
                  <Route path="/reset-password" element={<ResetPasswordPage />} />
                  <Route path="/verify-email-change" element={<VerifyEmailChangePage />} />
                  <Route path="/updates" element={<PropertyUpdatesPage />} />
                  <Route path="/verify-email" element={<VerifyEmailPage />} />
                  <Route path="/auth/callback" element={<AuthCallbackPage />} />
                  <Route path="/transaction-prices" element={<TransactionPricesPage />} />
                  <Route path="/contact" element={<ContactPage />} />
                  {/* 法的ページ */}
                  <Route path="/terms/disclaimer" element={<DisclaimerPage />} />
                  <Route path="/terms" element={<TermsPage />} />
                  <Route path="/privacy" element={<PrivacyPage />} />
                  {/* 旧URLは新しいURLにリダイレクト */}
                  <Route path="/price-changes" element={<RedirectToUpdates defaultTab={0} />} />
                  <Route path="/new-listings" element={<RedirectToUpdates defaultTab={1} />} />
                  <Route path="/admin" element={<Admin />} />
                  <Route path="/admin/login" element={<AdminLogin />} />
                </Routes>
              </Container>
              <Footer />
            </div>
          </UserAuthProvider>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;