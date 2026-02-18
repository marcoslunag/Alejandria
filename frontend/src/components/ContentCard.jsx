import { Link } from 'react-router-dom';
import { FaStar, FaBook, FaBookReader, FaMask, FaCheck, FaPlus, FaEye, FaEyeSlash } from 'react-icons/fa';
import { useState } from 'react';

/**
 * ContentCard - Tarjeta unificada para manga, cómics y libros.
 *
 * Props:
 *   item             - El objeto de datos (manga, comic o book)
 *   type             - 'manga' | 'comic' | 'book'
 *   onAdd            - Callback para añadir a biblioteca
 *   showAddButton    - Mostrar botón de añadir
 */
const ContentCard = ({ item, type = 'manga', onAdd, showAddButton = false, onToggleMonitor }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [isTogglingMonitor, setIsTogglingMonitor] = useState(false);

  const config = {
    manga: {
      accentColor: item.cover_color || '#3B82F6',
      icon: FaBook,
      hoverTextClass: 'group-hover:text-primary',
      badgeClass: 'bg-primary',
      addBtnClass: 'btn btn-primary',
      progressBarClass: 'bg-primary',
      detailPath: '/manga',
      getLink: () => {
        const id = item.library_id || (item.id && item.id > 0 ? item.id : null);
        return id ? `/manga/${id}` : null;
      },
      getCover: () => item.cover_image || item.cover,
      getScore: () => item.average_score ? (item.average_score / 10).toFixed(1) : null,
      getSubInfo: () => item.genres?.slice(0, 3).map(g => ({ key: g, label: g })) || [],
      getStats: () => {
        const parts = [];
        if (item.average_score) parts.push({ type: 'score', value: (item.average_score / 10).toFixed(1) });
        if (item.chapters_total) parts.push({ type: 'count', label: `${item.chapters_total} tomos` });
        if (item.format) parts.push({ type: 'text', label: item.format });
        return parts;
      },
      getProgress: () => ({
        current: item.downloaded_chapters || 0,
        total: item.chapters_total || 0,
        show: item.in_library && item.downloaded_chapters !== undefined,
      }),
      getStatusBadge: () => item.status ? {
        label: item.status,
        className: item.status === 'RELEASING' ? 'bg-green-500' : item.status === 'FINISHED' ? 'bg-blue-500' : 'bg-gray-500',
      } : null,
    },
    comic: {
      accentColor: '#EF4444',
      icon: FaMask,
      hoverTextClass: 'group-hover:text-red-500',
      badgeClass: 'bg-red-500',
      addBtnClass: 'btn bg-red-500 hover:bg-red-600 text-white',
      progressBarClass: 'bg-red-500',
      detailPath: '/comics',
      getLink: () => {
        const id = item.library_id || item.id;
        return id ? `/comics/${id}` : null;
      },
      getCover: () => item.cover_image,
      getScore: () => null,
      getSubInfo: () => {
        const parts = [];
        if (item.publisher) parts.push({ key: 'pub', label: item.publisher });
        if (item.start_year) parts.push({ key: 'year', label: `${item.start_year}` });
        return parts;
      },
      getStats: () => {
        const total = item.count_of_issues || item.total_issues || '?';
        return [{ type: 'count', label: `${item.downloaded_issues || 0}/${total} issues`, className: 'text-red-400' }];
      },
      getProgress: () => ({
        current: item.downloaded_issues || 0,
        total: item.count_of_issues || item.total_issues || 0,
        show: item.in_library && (item.count_of_issues || item.total_issues) > 0,
      }),
      getStatusBadge: () => item.downloaded_issues > 0 ? { label: 'Descargado', className: 'bg-red-500' } : null,
    },
    book: {
      accentColor: '#10B981',
      icon: FaBookReader,
      hoverTextClass: 'group-hover:text-green-500',
      badgeClass: 'bg-green-500',
      addBtnClass: 'btn btn-primary',
      progressBarClass: 'bg-green-500',
      detailPath: '/books',
      getLink: () => {
        const id = item.library_id || item.id;
        return id ? `/books/${id}` : null;
      },
      getCover: () => item.cover_image || item.thumbnail,
      getScore: () => item.average_rating ? item.average_rating.toFixed(1) : null,
      getSubInfo: () => item.authors?.slice(0, 2).map((a, i) => ({ key: i, label: a })) || [],
      getStats: () => {
        const parts = [];
        if (item.average_rating) parts.push({ type: 'score', value: item.average_rating.toFixed(1) });
        if (item.page_count) parts.push({ type: 'count', label: `${item.page_count}p` });
        if (item.language) parts.push({ type: 'text', label: item.language.toUpperCase() });
        return parts;
      },
      getProgress: () => ({
        current: item.downloaded_chapters || 0,
        total: item.total_chapters || 0,
        show: item.in_library && item.total_chapters > 0,
      }),
      getStatusBadge: () => item.downloaded_chapters > 0 ? { label: 'Descargado', className: 'bg-green-500' } : null,
    },
  };

  const c = config[type];
  const coverUrl = c.getCover();
  const link = c.getLink();
  const score = c.getScore();
  const subInfo = c.getSubInfo();
  const statsList = c.getStats();
  const progress = c.getProgress();
  const statusBadge = c.getStatusBadge();
  const IconComponent = c.icon;

  const handleAdd = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsAdding(true);
    try {
      await onAdd(item);
    } finally {
      setIsAdding(false);
    }
  };

  const handleToggleMonitor = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!onToggleMonitor || isTogglingMonitor) return;
    setIsTogglingMonitor(true);
    try {
      await onToggleMonitor(item);
    } finally {
      setIsTogglingMonitor(false);
    }
  };

  const CardContent = () => (
    <div
      className="card group cursor-pointer transition-all duration-300 hover:scale-105 hover:shadow-2xl relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        borderTop: type === 'manga' && item.cover_color
          ? `4px solid ${item.cover_color}`
          : `4px solid ${c.accentColor}`,
      }}
    >
      {/* Cover Image */}
      <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
        {coverUrl ? (
          <img
            src={coverUrl}
            alt={item.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <IconComponent className="text-6xl text-gray-600" />
          </div>
        )}

        {/* Hover overlay with description */}
        {isHovered && item.description && (
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/70 to-transparent flex flex-col justify-end p-4 animate-fade-in">
            <p className="text-sm text-gray-300 line-clamp-3">
              {item.description.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '')}
            </p>
          </div>
        )}

        {/* Status badge */}
        {statusBadge && (
          <div className={`absolute top-2 right-2 px-2 py-1 rounded text-xs font-medium ${statusBadge.className}`}>
            {statusBadge.label}
          </div>
        )}

        {/* Reading status badge */}
        {item.in_library && item.reading_status === 'completed' && (
          <div className="absolute bottom-2 left-0 right-0 flex justify-center pointer-events-none">
            <span className="bg-green-600/90 text-white text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
              <FaEye className="text-[8px]" /> Leído
            </span>
          </div>
        )}

        {/* In Library / Watchlist indicator */}
        {item.in_library && (
          <div className="absolute top-2 left-2 flex flex-col gap-1">
            <div className={`${c.badgeClass} rounded-full p-1.5`}>
              <FaCheck className="text-white text-xs" />
            </div>
            {onToggleMonitor ? (
              <button
                onClick={handleToggleMonitor}
                disabled={isTogglingMonitor}
                title={item.monitored ? 'Siguiendo — Click para dejar de seguir' : 'No siguiendo — Click para seguir'}
                className={`rounded-full p-1.5 transition-colors ${
                  item.monitored
                    ? `${c.badgeClass} text-white opacity-90 hover:opacity-100`
                    : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                }`}
              >
                {item.monitored
                  ? <FaEye className="text-xs" />
                  : <FaEyeSlash className="text-xs" />
                }
              </button>
            ) : item.monitored !== undefined && (
              <div
                title={item.monitored ? 'Siguiendo' : 'No siguiendo'}
                className={`rounded-full p-1.5 ${
                  item.monitored ? `${c.badgeClass} opacity-80` : 'bg-gray-700'
                }`}
              >
                {item.monitored
                  ? <FaEye className="text-white text-xs" />
                  : <FaEyeSlash className="text-gray-400 text-xs" />
                }
              </div>
            )}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-4">
        <h3 className={`font-bold text-lg mb-2 line-clamp-2 ${c.hoverTextClass} transition-colors`}>
          {item.title}
        </h3>

        {/* Sub info (genres for manga, publisher/year for comics, authors for books) */}
        {subInfo.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {subInfo.map((info) => (
              <span
                key={info.key}
                className="text-xs px-2 py-1 bg-dark-lighter rounded text-gray-300"
              >
                {info.label}
              </span>
            ))}
          </div>
        )}

        {/* Stats row */}
        <div className="flex items-center gap-3 text-sm text-gray-400 mb-2">
          {statsList.map((stat, i) => {
            if (stat.type === 'score') {
              return (
                <div key={i} className="flex items-center gap-1">
                  <FaStar className="text-yellow-400 text-xs" />
                  <span>{stat.value}</span>
                </div>
              );
            }
            if (stat.type === 'count') {
              return (
                <span key={i} className={stat.className || ''}>
                  {stat.label}
                </span>
              );
            }
            return (
              <span key={i} className="text-xs uppercase">{stat.label}</span>
            );
          })}
        </div>

        {/* Progress bar */}
        {progress.show && progress.total > 0 && (
          <div className="mt-2">
            <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
              <span>Descargados</span>
              <span>{progress.current}/{progress.total}</span>
            </div>
            <div className="w-full bg-dark-lighter rounded-full h-1.5">
              <div
                className={`${c.progressBarClass} h-1.5 rounded-full transition-all`}
                style={{ width: `${(progress.current / progress.total) * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* Add button */}
        {showAddButton && !item.in_library && (
          <button
            onClick={handleAdd}
            disabled={isAdding}
            className={`w-full mt-3 ${c.addBtnClass} flex items-center justify-center gap-2 disabled:opacity-50`}
          >
            <FaPlus />
            {isAdding ? 'Agregando...' : 'Añadir a biblioteca'}
          </button>
        )}
      </div>
    </div>
  );

  if (link) {
    return (
      <Link to={link}>
        <CardContent />
      </Link>
    );
  }

  return <CardContent />;
};

export default ContentCard;
