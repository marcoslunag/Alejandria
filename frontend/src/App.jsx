import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import Library from './pages/Library';
import Search from './pages/Search';
import MangaDetails from './pages/MangaDetails';
import Comics from './pages/Comics';
import ComicDetails from './pages/ComicDetails';
import Queue from './pages/Queue';
import Settings from './pages/Settings';

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-dark">
        <Navbar />
        <main>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/library" element={<Library />} />
            <Route path="/search" element={<Search />} />
            <Route path="/manga/:id" element={<MangaDetails />} />
            <Route path="/comics" element={<Comics />} />
            <Route path="/comics/:id" element={<ComicDetails />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
