import { NavLink } from 'react-router-dom';
import { FaBook, FaMask, FaBookReader } from 'react-icons/fa';

const TABS = [
  { to: '/library', icon: FaBook,      label: 'Manga',   color: 'text-blue-400',  activeColor: 'bg-blue-500'  },
  { to: '/comics',  icon: FaMask,      label: 'Cómics',  color: 'text-red-400',   activeColor: 'bg-red-500'   },
  { to: '/books',   icon: FaBookReader,label: 'Libros',  color: 'text-green-400', activeColor: 'bg-green-500' },
];

/**
 * Shared tab bar shown at the top of Library, Comics, and Books pages.
 * Clicking a tab navigates to the respective page, giving the appearance of
 * a single unified library view.
 */
const LibraryTabs = () => (
  <div className="flex gap-1 mb-6 bg-dark-card rounded-xl p-1 w-fit">
    {TABS.map(({ to, icon: Icon, label, color, activeColor }) => (
      <NavLink
        key={to}
        to={to}
        end
        className={({ isActive }) =>
          `flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            isActive
              ? `${activeColor} text-white`
              : `text-gray-400 hover:text-white hover:bg-dark-lighter`
          }`
        }
      >
        <Icon className="text-base" />
        {label}
      </NavLink>
    ))}
  </div>
);

export default LibraryTabs;
