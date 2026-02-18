import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { FaHome, FaBook, FaSearch, FaCog, FaDownload, FaMask, FaBookReader, FaSignOutAlt, FaUser, FaUserShield, FaBars, FaTimes } from 'react-icons/fa';
import { useAuth } from '../contexts/AuthContext';

const Navbar = () => {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const userNavItems = [
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
    setMenuOpen(false);
  };

  const navLinkClass = ({ isActive }) =>
    `flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
      isActive
        ? 'bg-primary text-white'
        : 'text-gray-400 hover:text-white hover:bg-dark-lighter'
    }`;

  return (
    <nav className="bg-dark-card border-b border-gray-700 sticky top-0 z-50">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to={isAdmin ? '/admin/users' : '/'} className="flex items-center gap-3">
            <div className="text-3xl">📚</div>
            <div>
              <h1 className="text-xl font-bold text-primary">Alejandría</h1>
              <p className="text-xs text-gray-400">
                {isAdmin ? 'Panel de administración' : 'Tu biblioteca digital'}
              </p>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-6">
            {isAdmin ? (
              <NavLink
                to="/admin/users"
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-purple-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-dark-lighter'
                  }`
                }
              >
                <FaUserShield />
                <span className="hidden md:inline">Usuarios</span>
              </NavLink>
            ) : (
              userNavItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={navLinkClass}
                >
                  <item.icon />
                  <span className="hidden lg:inline">{item.label}</span>
                </NavLink>
              ))
            )}

            {/* User menu */}
            <div className="flex items-center gap-3 ml-4 pl-4 border-l border-gray-700">
              <div className="flex items-center gap-2 text-gray-400">
                <FaUser className="text-sm" />
                <span className="hidden lg:inline text-sm">{user?.username}</span>
              </div>
              <button
                onClick={handleLogout}
                className="text-gray-400 hover:text-red-400 transition-colors p-2 rounded-lg hover:bg-dark-lighter"
                title="Cerrar sesión"
              >
                <FaSignOutAlt />
              </button>
            </div>
          </div>

          {/* Mobile hamburger */}
          <button
            className="md:hidden text-gray-400 hover:text-white p-2 rounded-lg hover:bg-dark-lighter"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Toggle menu"
          >
            {menuOpen ? <FaTimes size={20} /> : <FaBars size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="md:hidden bg-dark-card border-t border-gray-700 px-4 py-3 flex flex-col gap-1">
          {isAdmin ? (
            <NavLink
              to="/admin/users"
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-3 rounded-lg transition-colors ${
                  isActive ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white hover:bg-dark-lighter'
                }`
              }
            >
              <FaUserShield />
              Usuarios
            </NavLink>
          ) : (
            userNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-3 rounded-lg transition-colors ${
                    isActive ? 'bg-primary text-white' : 'text-gray-400 hover:text-white hover:bg-dark-lighter'
                  }`
                }
              >
                <item.icon />
                {item.label}
              </NavLink>
            ))
          )}
          <div className="flex items-center justify-between px-3 py-3 mt-1 border-t border-gray-700">
            <div className="flex items-center gap-2 text-gray-400 text-sm">
              <FaUser />
              {user?.username}
            </div>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 text-gray-400 hover:text-red-400 transition-colors"
            >
              <FaSignOutAlt />
              Salir
            </button>
          </div>
        </div>
      )}
    </nav>
  );
};

export default Navbar;
