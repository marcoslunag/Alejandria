import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { FaHome, FaBook, FaSearch, FaCog, FaDownload, FaMask, FaBookReader, FaSignOutAlt, FaUser, FaUserShield, FaBars, FaTimes, FaCompass, FaBell, FaUpload, FaChartBar } from 'react-icons/fa';
import { useAuth } from '../contexts/AuthContext';
import { notificationsApi } from '../services/api';

const TYPE_PATHS = { manga: '/manga', comic: '/comics', book: '/books' };
const TYPE_LABELS = { manga: 'Manga', comic: 'Cómic', book: 'Libro' };

const Navbar = () => {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [notifCount, setNotifCount] = useState(0);
  const [notifItems, setNotifItems] = useState([]);
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef(null);

  // Notification polling
  useEffect(() => {
    if (isAdmin || !user) return;
    const fetchNotifs = async () => {
      try {
        const { data } = await notificationsApi.getCount();
        setNotifCount(data.total || 0);
        setNotifItems(data.items || []);
      } catch {}
    };
    fetchNotifs();
    const interval = setInterval(fetchNotifs, 60000);
    return () => clearInterval(interval);
  }, [user, isAdmin]);

  // Close notif dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setNotifOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleNotifOpen = async () => {
    setNotifOpen(prev => !prev);
    if (!notifOpen && notifCount > 0) {
      try {
        await notificationsApi.markSeen();
        setNotifCount(0);
        setNotifItems([]);
      } catch {}
    }
  };

  const userNavItems = [
    { to: '/', icon: FaCompass, label: 'Descubrir' },
    { to: '/search', icon: FaSearch, label: 'Buscar' },
    { to: '/library', icon: FaBook, label: 'Manga' },
    { to: '/comics', icon: FaMask, label: 'Comics' },
    { to: '/books', icon: FaBookReader, label: 'Libros' },
    { to: '/queue', icon: FaDownload, label: 'Descargas' },
    { to: '/upload', icon: FaUpload, label: 'Subir' },
    { to: '/dashboard', icon: FaChartBar, label: 'Estadísticas' },
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

            {/* Notification bell (non-admin only) */}
            {!isAdmin && (
              <div className="relative" ref={notifRef}>
                <button
                  onClick={handleNotifOpen}
                  className="relative text-gray-400 hover:text-white p-2 rounded-lg hover:bg-dark-lighter transition-colors"
                  title="Notificaciones"
                >
                  <FaBell />
                  {notifCount > 0 && (
                    <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold rounded-full min-w-[16px] h-4 flex items-center justify-center px-0.5">
                      {notifCount > 99 ? '99+' : notifCount}
                    </span>
                  )}
                </button>

                {/* Dropdown */}
                {notifOpen && (
                  <div className="absolute right-0 top-10 w-72 bg-dark-card border border-gray-700 rounded-xl shadow-xl z-50 overflow-hidden">
                    <div className="px-4 py-2 border-b border-gray-700 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                      Novedades
                    </div>
                    {notifItems.length === 0 ? (
                      <div className="px-4 py-6 text-center text-gray-500 text-sm">
                        Todo al día
                      </div>
                    ) : (
                      <div className="max-h-72 overflow-y-auto divide-y divide-gray-700/50">
                        {notifItems.map((item, i) => (
                          <button
                            key={i}
                            onClick={() => {
                              const path = TYPE_PATHS[item.type];
                              if (path) navigate(`${path}/${item.id}`);
                              setNotifOpen(false);
                            }}
                            className="w-full flex items-center gap-3 px-4 py-3 hover:bg-dark-lighter transition-colors text-left"
                          >
                            {item.cover ? (
                              <img src={item.cover} alt="" className="w-8 h-10 object-cover rounded flex-shrink-0" />
                            ) : (
                              <div className="w-8 h-10 bg-dark-lighter rounded flex-shrink-0" />
                            )}
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium truncate">{item.title}</p>
                              <p className="text-xs text-gray-500">
                                {item.count} {TYPE_LABELS[item.type] || ''} nuevo{item.count !== 1 ? 's' : ''}
                              </p>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
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
