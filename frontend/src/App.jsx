import { BrowserRouter as Router, Routes, Route, Outlet, Navigate, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import ErrorBoundary from './components/ErrorBoundary';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import Library from './pages/Library';
import Search from './pages/Search';
import MangaDetails from './pages/MangaDetails';
import Comics from './pages/Comics';
import ComicDetails from './pages/ComicDetails';
import Books from './pages/Books';
import BookDetails from './pages/BookDetails';
import Queue from './pages/Queue';
import Settings from './pages/Settings';
import Login from './pages/Login';
import ChangePassword from './pages/ChangePassword';
import AdminUsers from './pages/AdminUsers';
import Discover from './pages/Discover';
import MangaReader from './pages/MangaReader';
import Upload from './pages/Upload';
import DeviceSetup from './pages/DeviceSetup';

const LoadingSpinner = () => (
  <div className="min-h-screen flex items-center justify-center">
    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
  </div>
);

function ProtectedLayout() {
  const { mustChangePassword, isAdmin, deviceSetupCompleted, loading } = useAuth();
  const location = useLocation();

  if (loading) return <LoadingSpinner />;
  if (isAdmin) return <Navigate to="/admin/users" replace />;
  if (mustChangePassword) return <Navigate to="/change-password" replace />;
  if (!deviceSetupCompleted) return <Navigate to="/device-setup" replace />;

  return (
    <ProtectedRoute>
      <Navbar />
      <main key={location.key} className="animate-page-in">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </ProtectedRoute>
  );
}

function AdminLayout() {
  const { isAdmin, mustChangePassword, loading } = useAuth();
  const location = useLocation();

  if (loading) return <LoadingSpinner />;
  if (mustChangePassword) return <Navigate to="/change-password" replace />;
  if (!isAdmin) return <Navigate to="/" replace />;

  return (
    <ProtectedRoute>
      <Navbar />
      <main key={location.key} className="animate-page-in">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: '#161b22',
              color: '#f3f4f6',
              border: '1px solid rgba(201,168,76,0.2)',
              fontFamily: 'Outfit, system-ui, sans-serif',
            },
            success: {
              iconTheme: { primary: '#7aa67a', secondary: '#f3f4f6' },
            },
            error: {
              duration: 5000,
              iconTheme: { primary: '#ef4444', secondary: '#f3f4f6' },
            },
          }}
        />
        <div className="min-h-screen bg-dark-base">
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />

            {/* Authenticated but may need password change */}
            <Route path="/change-password" element={
              <ProtectedRoute>
                <ChangePassword />
              </ProtectedRoute>
            } />

            {/* Device setup wizard (after first password change) */}
            <Route path="/device-setup" element={
              <ProtectedRoute>
                <DeviceSetup />
              </ProtectedRoute>
            } />

            {/* Protected routes (non-admin users) */}
            <Route element={<ProtectedLayout />}>
              <Route path="/" element={<Discover />} />
              <Route path="/dashboard" element={<Home />} />
              <Route path="/library" element={<Library />} />
              <Route path="/search" element={<Search />} />
              <Route path="/manga/:id" element={<MangaDetails />} />
              <Route path="/comics" element={<Comics />} />
              <Route path="/comics/:id" element={<ComicDetails />} />
              <Route path="/books" element={<Books />} />
              <Route path="/books/:id" element={<BookDetails />} />
              <Route path="/queue" element={<Queue />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/upload" element={<Upload />} />
              <Route path="/discover" element={<Navigate to="/" replace />} />
            </Route>

            {/* Fullscreen reader (no Navbar) */}
            <Route path="/manga/:mangaId/chapters/:chapterId/read" element={
              <ProtectedRoute>
                <MangaReader />
              </ProtectedRoute>
            } />

            {/* Admin routes */}
            <Route element={<AdminLayout />}>
              <Route path="/admin/users" element={<AdminUsers />} />
            </Route>
          </Routes>
        </div>
      </AuthProvider>
    </Router>
  );
}

export default App;
