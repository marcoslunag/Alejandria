import { Link, NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { FaHome, FaBook, FaSearch, FaCog, FaDownload, FaMask, FaBookReader, FaSignOutAlt, FaUser, FaUserShield, FaBars, FaTimes, FaCompass, FaBell, FaUpload, FaChartBar } from 'react-icons/fa';
import { useAuth } from '../contexts/AuthContext';
import { notificationsApi } from '../services/api';

const TYPE_PATHS = { manga: '/manga', comic: '/comics', book: '/books' };
const TYPE_LABELS = { manga: 'Manga', comic: 'Cómic', book: 'Libro' };

const Navbar = () => {
  const { user, logout, isAdmin, token } = useAuth();
  const location = useLocation();
  // Library section includes /library, /comics, /books
  const LIBRARY_PATHS = ['/library', '/comics', '/books'];
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [notifCount, setNotifCount] = useState(0);
  const [notifErrors, setNotifErrors] = useState(0);
  const [notifItems, setNotifItems] = useState([]);
  const [notifOpen, setNotifOpen] = useState(false);
  const [stkAuthenticated, setStkAuthenticated] = useState(true); // assume OK until first check
  const notifRef = useRef(null);

  // SSE-based notification stream (replaces 60s polling)
  useEffect(() => {
    if (isAdmin || !user || !token) return;
    if (typeof EventSource === 'undefined') {
      // Fallback to polling if SSE not supported
      const fetchNotifs = async () => {
        try {
          const { data } = await notificationsApi.getCount();
          setNotifCount(data.total || 0);
          setNotifErrors(data.errors || 0);
          setNotifItems(data.items || []);
          if (data.stk_authenticated !== undefined) setStkAuthenticated(data.stk_authenticated);
        } catch {}
      };
      fetchNotifs();
      const interval = setInterval(fetchNotifs, 60000);
      return () => clearInterval(interval);
    }

    const apiBase = import.meta.env.VITE_API_URL || '/api/v1';
    const url = `${apiBase}/notifications/stream?token=${encodeURIComponent(token)}`;
    let es = null;
    let reconnectTimer = null;

    const connect = () => {
      es = new EventSource(url);
      es.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          setNotifCount(data.total || 0);
          setNotifErrors(data.errors || 0);
          setNotifItems(data.items || []);
          if (data.stk_authenticated !== undefined) {
            setStkAuthenticated(data.stk_authenticated);
          }
        } catch {}
      };
      es.onerror = () => {
        es.close();
        // Reconnect after 15s on error
        reconnectTimer = setTimeout(connect, 15000);
      };
    };

    connect();
    return () => {
      es.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  }, [user, isAdmin, token]);

  useEffect(() => {
    const handler = async (e) => {
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        if (notifOpen && notifCount > 0) {
          try {
            await notificationsApi.markSeen();
            setNotifCount(0);
          } catch {}
        }
        setNotifOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [notifOpen, notifCount]);

  const handleNotifOpen = async () => {
    const wasOpen = notifOpen;
    setNotifOpen(prev => !prev);
    if (wasOpen && notifCount > 0) {
      try {
        await notificationsApi.markSeen();
        setNotifCount(0);
      } catch {}
    }
  };

  const userNavItems = [
    { to: '/', icon: FaCompass, label: 'Descubrir' },
    { to: '/search', icon: FaSearch, label: 'Buscar' },
    { to: '/library', icon: FaBook, label: 'Biblioteca' },
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
    `flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm border ${
      isActive
        ? 'bg-gold/10 border-gold/25 text-gold font-semibold'
        : 'text-gray-400 hover:text-white hover:bg-dark-lighter border-transparent'
    }`;

  return (
    <nav className="bg-dark-card border-b border-gray-700 sticky top-0 z-50">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to={isAdmin ? '/admin/users' : '/'} className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-gold to-gold-light rounded-lg flex items-center justify-center flex-shrink-0">
              <span className="font-serif font-black text-dark-base text-lg leading-none">A</span>
            </div>
            <div>
              <h1 className="font-serif text-lg font-bold text-white leading-tight">Alejandría</h1>
              <p className="text-[10px] text-gray-500 leading-tight">
                {isAdmin ? 'Administración' : 'Tu biblioteca digital'}
              </p>
            </div>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-6">
            {isAdmin ? (
              <NavLink
                to="/admin/users"
                className={({ isActive }) =>
                  `flex items-center gap-2 px-3 py-2 rounded-lg transition-colors text-sm border ${
                    isActive
                      ? 'bg-gold/10 border-gold/25 text-gold font-semibold'
                      : 'text-gray-400 hover:text-white hover:bg-dark-lighter border-transparent'
                  }`
                }
              >
                <FaUserShield />
                <span className="hidden md:inline">Usuarios</span>
              </NavLink>
            ) : (
              userNavItems.map((item) => {
                // "Biblioteca" is active when on any library-related path
                const isLibraryItem = item.to === '/library';
                const isLibraryActive = isLibraryItem && LIBRARY_PATHS.some(p => location.pathname.startsWith(p));
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    className={isLibraryActive
                      ? () => navLinkClass({ isActive: true })
                      : navLinkClass
                    }
                  >
                    <span className="relative">
                      <item.icon />
                      {/* Warning dot on Settings when STK is not configured */}
                      {item.to === '/settings' && !stkAuthenticated && (
                        <span className="absolute -top-1 -right-1 w-2 h-2 bg-orange-500 rounded-full" title="Kindle no configurado — ve a Ajustes" />
                      )}
                    </span>
                    <span className="hidden md:inline">{item.label}</span>
                  </NavLink>
                );
              })
            )}

            {/* Notification bell (non-admin only) */}
            {!isAdmin && (
              <div className="relative" ref={notifRef}>
                <button
                  onClick={handleNotifOpen}
                  className="relative text-gray-400 hover:text-white p-2 rounded-lg hover:bg-dark-lighter transition-colors"
                  title={notifErrors > 0 ? `${notifErrors} error${notifErrors !== 1 ? 'es' : ''} de descarga` : 'Notificaciones'}
                >
                  <FaBell className={notifErrors > 0 ? 'text-red-400' : ''} />
                  {notifCount > 0 && (
                    <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold rounded-full min-w-[16px] h-4 flex items-center justify-center px-0.5">
                      {notifCount > 99 ? '99+' : notifCount}
                    </span>
                  )}
                  {notifCount === 0 && notifErrors > 0 && (
                    <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold rounded-full min-w-[16px] h-4 flex items-center justify-center px-0.5">
                      !
                    </span>
                  )}
                </button>

                {/* Dropdown */}
                {notifOpen && (
                  <div className="absolute right-0 top-10 w-72 bg-dark-card border border-gray-700 rounded-xl shadow-xl z-50 overflow-hidden">
                    <div className="px-4 py-2 border-b border-gray-700 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                      Novedades
                    </div>
                    {notifErrors > 0 && (
                      <button
                        onClick={() => { navigate('/queue'); setNotifOpen(false); }}
                        className="w-full flex items-center gap-3 px-4 py-3 bg-red-500/10 hover:bg-red-500/20 transition-colors text-left border-b border-gray-700/50"
                      >
                        <span className="text-red-400 text-lg">⚠</span>
                        <div>
                          <p className="text-sm font-medium text-red-400">
                            {notifErrors} descarga{notifErrors !== 1 ? 's' : ''} con error
                          </p>
                          <p className="text-xs text-gray-500">Click para ver la cola</p>
                        </div>
                      </button>
                    )}
                    {notifItems.length === 0 && notifErrors === 0 ? (
                      <div className="px-4 py-6 text-center text-gray-500 text-sm">
                        Todo al día
                      </div>
                    ) : notifItems.length > 0 && (
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
                `flex items-center gap-3 px-3 py-3 rounded-lg transition-colors border ${
                  isActive ? 'bg-gold/10 border-gold/25 text-gold font-semibold' : 'text-gray-400 hover:text-white hover:bg-dark-lighter border-transparent'
                }`
              }
            >
              <FaUserShield />
              Usuarios
            </NavLink>
          ) : (
            userNavItems.map((item) => {
              const isLibraryItem = item.to === '/library';
              const isLibraryActive = isLibraryItem && LIBRARY_PATHS.some(p => location.pathname.startsWith(p));
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  onClick={() => setMenuOpen(false)}
                  className={isLibraryActive
                    ? `flex items-center gap-3 px-3 py-3 rounded-lg transition-colors border bg-gold/10 border-gold/25 text-gold font-semibold`
                    : ({ isActive }) =>
                        `flex items-center gap-3 px-3 py-3 rounded-lg transition-colors border ${
                          isActive ? 'bg-gold/10 border-gold/25 text-gold font-semibold' : 'text-gray-400 hover:text-white hover:bg-dark-lighter border-transparent'
                        }`
                  }
                >
                  <item.icon />
                  {item.label}
                </NavLink>
              );
            })
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
      {/* Gold accent line */}
      <div className="h-px bg-gradient-to-r from-transparent via-gold/20 to-transparent" />
    </nav>
  );
};

export default Navbar;
