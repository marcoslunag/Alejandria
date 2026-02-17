import { BrowserRouter as Router, Routes, Route, Outlet } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
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
import Register from './pages/Register';

function ProtectedLayout() {
  return (
    <ProtectedRoute>
      <Navbar />
      <main>
        <Outlet />
      </main>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <Router>
      <AuthProvider>
        <div className="min-h-screen bg-dark">
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* Protected routes */}
            <Route element={<ProtectedLayout />}>
              <Route path="/" element={<Home />} />
              <Route path="/library" element={<Library />} />
              <Route path="/search" element={<Search />} />
              <Route path="/manga/:id" element={<MangaDetails />} />
              <Route path="/comics" element={<Comics />} />
              <Route path="/comics/:id" element={<ComicDetails />} />
              <Route path="/books" element={<Books />} />
              <Route path="/books/:id" element={<BookDetails />} />
              <Route path="/queue" element={<Queue />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
          </Routes>
        </div>
      </AuthProvider>
    </Router>
  );
}

export default App;
