import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { systemApi } from '../services/api';
import {
  FaBook, FaMask, FaBookReader,
  FaExclamationTriangle, FaDownload, FaChartBar,
  FaKindle, FaHdd,
} from 'react-icons/fa';

const TYPE_CONFIG = {
  books:  { label: 'Libros',  color: 'text-green-400', bg: 'bg-green-500/20', icon: FaBookReader, path: '/books'   },
  manga:  { label: 'Manga',   color: 'text-blue-400',  bg: 'bg-blue-500/20',  icon: FaBook,       path: '/library' },
  comics: { label: 'Cómics',  color: 'text-red-400',   bg: 'bg-red-500/20',   icon: FaMask,       path: '/comics'  },
};

const DOWNLOAD_TYPE_CONFIG = {
  book:   { color: 'text-green-400', label: 'Libro'  },
  manga:  { color: 'text-blue-400',  label: 'Manga'  },
  comic:  { color: 'text-red-400',   label: 'Comic'  },
};

const ReadingBar = ({ stats, type }) => {
  const cfg = TYPE_CONFIG[type];
  const Icon = cfg.icon;
  const total = (stats.not_started || 0) + (stats.reading || 0) + (stats.completed || 0);
  if (total === 0) return null;
  const completedPct = Math.round(((stats.completed || 0) / total) * 100);
  const readingPct = Math.round(((stats.reading || 0) / total) * 100);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-gray-400">
        <div className="flex items-center gap-1.5">
          <Icon className={cfg.color} />
          <span>{cfg.label}</span>
        </div>
        <span className="text-gray-500">{total} series</span>
      </div>
      <div className="h-2 rounded-full bg-dark-lighter overflow-hidden flex">
        {completedPct > 0 && (
          <div className="bg-green-500 h-full" style={{ width: `${completedPct}%` }} />
        )}
        {readingPct > 0 && (
          <div className="bg-blue-500 h-full" style={{ width: `${readingPct}%` }} />
        )}
        {(100 - completedPct - readingPct) > 0 && (
          <div className="bg-gray-600 h-full" style={{ width: `${100 - completedPct - readingPct}%` }} />
        )}
      </div>
      <div className="flex gap-3 text-[10px] text-gray-500">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
          Completados {stats.completed || 0}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />
          En curso {stats.reading || 0}
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-gray-600 inline-block" />
          Sin empezar {stats.not_started || 0}
        </span>
      </div>
    </div>
  );
};

const Home = () => {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [loadingDash, setLoadingDash] = useState(true);
  const [kindleHistory, setKindleHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(true);

  useEffect(() => {
    loadDashboard();
    loadKindleHistory();
  }, []);

  const loadDashboard = async () => {
    try {
      const { data } = await systemApi.getDashboard();
      setDashboard(data);
    } catch (err) {
      if (err.response?.status !== 401) console.error('Error cargando dashboard:', err);
    } finally {
      setLoadingDash(false);
    }
  };

  const loadKindleHistory = async () => {
    try {
      const { data } = await systemApi.getKindleHistory(10);
      setKindleHistory(data.history || []);
    } catch {
      // silently ignore
    } finally {
      setLoadingHistory(false);
    }
  };

  const lib = dashboard?.library || {};
  const readingStats = dashboard?.reading_stats || {};
  const recentDownloads = dashboard?.recent_downloads || [];
  const errorCount = dashboard?.error_count || 0;
  const totalItems = (lib.manga || 0) + (lib.comics || 0) + (lib.books || 0);
  const storageByType = dashboard?.storage_by_type || {};
  const totalStorageMb = dashboard?.storage_used_mb || 0;

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl">

      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <FaChartBar className="text-primary text-2xl" />
        <div>
          <h1 className="text-2xl font-bold">Mis Estadísticas</h1>
          <p className="text-gray-400 text-sm">Resumen de tu biblioteca y actividad</p>
        </div>
      </div>

      {/* === Mi Biblioteca === */}
      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-4 text-gray-300">Mi Biblioteca</h2>

        {loadingDash ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            {[0, 1, 2].map(i => (
              <div key={i} className="bg-dark-card rounded-xl p-5 animate-pulse h-20" />
            ))}
          </div>
        ) : totalItems === 0 ? (
          <div className="bg-dark-card rounded-xl p-8 text-center text-gray-500 mb-4">
            <p className="text-lg">Tu biblioteca está vacía</p>
            <p className="text-sm mt-1">Busca y añade contenido para empezar</p>
            <button
              onClick={() => navigate('/search')}
              className="mt-4 px-4 py-2 bg-primary text-white rounded-lg text-sm hover:bg-primary/80 transition-colors"
            >
              Explorar contenido
            </button>
          </div>
        ) : (
          <>
            {/* Stats cards */}
            <div className="grid grid-cols-3 gap-4 mb-4">
              {Object.entries(TYPE_CONFIG).map(([type, cfg]) => {
                const Icon = cfg.icon;
                const count = lib[type] || 0;
                return (
                  <button
                    key={type}
                    onClick={() => navigate(cfg.path)}
                    className="bg-dark-card rounded-xl p-4 text-left hover:ring-1 hover:ring-gray-600 transition-all"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-9 h-9 rounded-lg ${cfg.bg} flex items-center justify-center`}>
                        <Icon className={`${cfg.color} text-base`} />
                      </div>
                      <div>
                        <p className="text-xl font-bold">{count}</p>
                        <p className="text-xs text-gray-400">{cfg.label}</p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Reading progress */}
            {Object.keys(readingStats).length > 0 && (
              <div className="bg-dark-card rounded-xl p-5 mb-4 space-y-4">
                <h3 className="text-sm font-semibold text-gray-300">Progreso de lectura</h3>
                {Object.entries(readingStats).map(([type, stats]) => (
                  <ReadingBar key={type} stats={stats} type={type} />
                ))}
              </div>
            )}
          </>
        )}

        {/* Error badge */}
        {!loadingDash && errorCount > 0 && (
          <button
            onClick={() => navigate('/queue')}
            className="flex items-center gap-2 w-full bg-red-500/10 border border-red-500/30 rounded-xl p-3 text-red-400 hover:bg-red-500/20 transition-colors mb-4"
          >
            <FaExclamationTriangle className="flex-shrink-0 text-sm" />
            <span className="text-sm">{errorCount} error{errorCount !== 1 ? 'es' : ''} en descargas</span>
            <span className="ml-auto text-xs text-red-500 font-medium">Ver cola →</span>
          </button>
        )}

        {/* Recent activity */}
        {!loadingDash && recentDownloads.length > 0 && (
          <div className="bg-dark-card rounded-xl p-5">
            <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <FaDownload className="text-gray-500" />
              Actividad reciente
            </h3>
            <div className="space-y-2">
              {recentDownloads.map((item, i) => {
                const tc = DOWNLOAD_TYPE_CONFIG[item.type] || DOWNLOAD_TYPE_CONFIG.manga;
                const date = item.downloaded_at
                  ? new Date(item.downloaded_at).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
                  : '';
                return (
                  <div key={i} className="flex items-center gap-3 py-1">
                    {item.cover ? (
                      <img src={item.cover} alt="" className="w-8 h-10 object-cover rounded flex-shrink-0" loading="lazy" />
                    ) : (
                      <div className="w-8 h-10 bg-dark-lighter rounded flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{item.title}</p>
                      <p className="text-xs text-gray-500 truncate">{item.item_title}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className={`text-[10px] ${tc.color}`}>{tc.label}</p>
                      <p className="text-[10px] text-gray-600">{date}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* === Almacenamiento === */}
      {!loadingDash && totalStorageMb > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-4 text-gray-300">Almacenamiento</h2>
          <div className="bg-dark-card rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <FaHdd className="text-gray-500" />
                <span>Total en disco</span>
              </div>
              <span className="text-sm font-semibold text-white">
                {totalStorageMb >= 1024
                  ? `${(totalStorageMb / 1024).toFixed(1)} GB`
                  : `${totalStorageMb} MB`}
              </span>
            </div>
            <div className="space-y-2">
              {[
                { type: 'manga',  label: 'Manga',   color: 'bg-blue-500'  },
                { type: 'comics', label: 'Cómics',  color: 'bg-red-500'   },
                { type: 'books',  label: 'Libros',  color: 'bg-green-500' },
              ].map(({ type, label, color }) => {
                const mb = storageByType[type] || 0;
                const pct = totalStorageMb > 0 ? Math.round((mb / totalStorageMb) * 100) : 0;
                if (mb === 0) return null;
                return (
                  <div key={type}>
                    <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                      <span>{label}</span>
                      <span>{mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`} ({pct}%)</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-dark-lighter overflow-hidden">
                      <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}

      {/* === Enviados a Kindle === */}
      {!loadingHistory && kindleHistory.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-4 text-gray-300">Enviados a Kindle</h2>
          <div className="bg-dark-card rounded-xl p-5">
            <div className="space-y-2">
              {kindleHistory.map((item, i) => {
                const tc = DOWNLOAD_TYPE_CONFIG[item.type] || DOWNLOAD_TYPE_CONFIG.manga;
                const date = item.sent_at
                  ? new Date(item.sent_at).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: '2-digit' })
                  : '';
                return (
                  <div key={i} className="flex items-center gap-3 py-1">
                    {item.cover ? (
                      <img src={item.cover} alt="" className="w-8 h-10 object-cover rounded flex-shrink-0" loading="lazy" />
                    ) : (
                      <div className="w-8 h-10 bg-dark-lighter rounded flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{item.title}</p>
                      <p className="text-xs text-gray-500 truncate">{item.item_title}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className={`text-[10px] ${tc.color}`}>{tc.label}</p>
                      <p className="text-[10px] text-gray-600">{date}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}
    </div>
  );
};

export default Home;
