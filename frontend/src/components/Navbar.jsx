import { Link, NavLink } from 'react-router-dom';
import { FaHome, FaBook, FaSearch, FaCog, FaDownload, FaMask } from 'react-icons/fa';

const Navbar = () => {
  const navItems = [
    { to: '/', icon: FaHome, label: 'Inicio' },
    { to: '/library', icon: FaBook, label: 'Manga' },
    { to: '/comics', icon: FaMask, label: 'Cómics' },
    { to: '/search', icon: FaSearch, label: 'Buscar' },
    { to: '/queue', icon: FaDownload, label: 'Descargas' },
    { to: '/settings', icon: FaCog, label: 'Ajustes' },
  ];

  return (
    <nav className="bg-dark-card border-b border-gray-700 sticky top-0 z-50">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-3">
            <div className="text-3xl">📚</div>
            <div>
              <h1 className="text-xl font-bold text-primary">Alejandría</h1>
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
          </div>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
