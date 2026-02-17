import { Link, NavLink, useNavigate } from 'react-router-dom';
import { FaHome, FaBook, FaSearch, FaCog, FaDownload, FaMask, FaBookReader, FaSignOutAlt, FaUser } from 'react-icons/fa';
import { useAuth } from '../contexts/AuthContext';

const Navbar = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const navItems = [
    { to: '/', icon: FaHome, label: 'Inicio' },
    { to: '/search', icon: FaSearch, label: 'Buscar' },
    { to: '/library', icon: FaBook, label: 'Manga' },
    { to: '/comics', icon: FaMask, label: 'Comics' },
    { to: '/books', icon: FaBookReader, label: 'Libros' },
    { to: '/queue', icon: FaDownload, label: 'Descargas' },
    { to: '/settings', icon: FaCog, label: 'Ajustes' },
  ];

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <nav className="bg-dark-card border-b border-gray-700 sticky top-0 z-50">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-3">
            <div className="text-3xl">📚</div>
            <div>
              <h1 className="text-xl font-bold text-primary">Alejandria</h1>
              <p className="text-xs text-gray-400">Tu biblioteca digital</p>
            </div>
          </Link>

          {/* Navigation */}
          <div className="flex items-center gap-6">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-primary text-white'
                      : 'text-gray-400 hover:text-white hover:bg-dark-lighter'
                  }`
                }
              >
                <item.icon />
                <span className="hidden md:inline">{item.label}</span>
              </NavLink>
            ))}

            {/* User menu */}
            <div className="flex items-center gap-3 ml-4 pl-4 border-l border-gray-700">
              <div className="flex items-center gap-2 text-gray-400">
                <FaUser className="text-sm" />
                <span className="hidden lg:inline text-sm">{user?.username}</span>
              </div>
              <button
                onClick={handleLogout}
                className="text-gray-400 hover:text-red-400 transition-colors p-2 rounded-lg hover:bg-dark-lighter"
                title="Cerrar sesion"
              >
                <FaSignOutAlt />
              </button>
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
