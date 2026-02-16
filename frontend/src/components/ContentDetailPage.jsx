import { Link } from 'react-router-dom';
import {
  FaStar,
  FaSync,
  FaTrash,
  FaExternalLinkAlt,
  FaSpinner,
  FaBook,
} from 'react-icons/fa';

/**
 * ContentDetailPage - Componente unificado para páginas de detalle.
 * Usado por MangaDetails, ComicDetails y BookDetails.
 *
 * Props:
 *   accentColor       - Color hex para acentos (ej: "#3B82F6" azul, "#EF4444" rojo, "#10B981" verde)
 *   bannerImage       - URL de banner real (si existe)
 *   coverImage        - URL de portada
 *   title             - Título principal
 *   subtitles         - Array de strings para subtítulos (ej: [title_romaji, title_native])
 *   badges            - Array de { label, color?, className? } para mostrar como badges
 *   score             - Número (puntuación, ej: 8.5)
 *   scoreMax          - Número máximo para la escala (default 10)
 *   description       - Texto de descripción (HTML se limpia)
 *   translatedDescription - Descripción traducida (opcional)
 *   translating       - Boolean si está traduciendo
 *   genres            - Array de strings
 *   infoGrid          - Array de { label, value, icon? } para grid de info adicional
 *   creators          - Array of { role, names } (ej: [{ role: 'Autor', names: ['Oda'] }])
 *   externalLinks     - Array of { label, url, icon? }
 *   actions           - Array of { label, onClick, className, icon?, disabled?, title? }
 *   stats             - Array of { label, value, color } para stats cards
 *   progress          - { current, total, color? } para barra de progreso
 *   loading           - Boolean
 *   notFoundMessage   - String para cuando no se encuentra
 *   backLink          - { to, label } para botón de volver
 *   children          - Contenido después del detalle (chapter list, issue list, etc.)
 */
const ContentDetailPage = ({
  accentColor = '#3B82F6',
  bannerImage,
  coverImage,
  title,
  subtitles = [],
  badges = [],
  score,
  scoreMax = 10,
  description,
  translatedDescription,
  translating = false,
  genres = [],
  infoGrid = [],
  creators = [],
  externalLinks = [],
  actions = [],
  stats = [],
  progress,
  loading = false,
  notFoundMessage = 'No encontrado',
  backLink,
  children,
}) => {
  // Loading state
  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="animate-pulse space-y-4">
          <div className="h-64 bg-dark-lighter rounded-lg" />
          <div className="h-8 bg-dark-lighter rounded w-1/2" />
          <div className="h-4 bg-dark-lighter rounded w-3/4" />
        </div>
      </div>
    );
  }

  // Not found state
  if (!title) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <p className="text-gray-400">{notFoundMessage}</p>
        {backLink && (
          <Link to={backLink.to} className="btn btn-primary mt-4 inline-block">
            {backLink.label}
          </Link>
        )}
      </div>
    );
  }

  const cleanHtml = (text) => {
    if (!text) return '';
    return text.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '');
  };

  // Accent color classes for genres
  const accentBg = `${accentColor}33`; // 20% opacity hex

  return (
    <div className="min-h-screen">
      {/* Banner */}
      {coverImage && (
        <div className="w-full h-64 relative overflow-hidden">
          {bannerImage ? (
            // Real banner image (like manga from AniList)
            <div
              className="absolute inset-0 bg-cover bg-center"
              style={{ backgroundImage: `url(${bannerImage})` }}
            />
          ) : (
            // Blurred cover as banner (books, comics)
            <div
              className="absolute inset-0 bg-cover bg-center"
              style={{
                backgroundImage: `url(${coverImage})`,
                filter: 'blur(8px)',
                transform: 'scale(1.1)',
              }}
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-dark/50 to-dark" />
        </div>
      )}

      <div
        className="container mx-auto px-4 pb-8"
        style={{ marginTop: coverImage ? '-8rem' : '2rem' }}
      >
        <div className="flex flex-col md:flex-row gap-8">
          {/* Cover */}
          <div className="flex-shrink-0">
            {coverImage ? (
              <img
                src={coverImage}
                alt={title}
                className="w-64 rounded-lg shadow-2xl"
                style={{ borderTop: `4px solid ${accentColor}` }}
              />
            ) : (
              <div
                className="w-64 h-96 rounded-lg shadow-2xl bg-dark-lighter flex items-center justify-center"
                style={{ borderTop: `4px solid ${accentColor}` }}
              >
                <FaBook className="text-6xl text-gray-600" />
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1">
            {/* Title */}
            <h1 className="text-4xl font-bold mb-2">{title}</h1>
            {subtitles.filter(Boolean).map((sub, i) => (
              <p
                key={i}
                className={`${i === 0 ? 'text-xl text-gray-400' : 'text-lg text-gray-500'} mb-${i === subtitles.filter(Boolean).length - 1 ? '4' : '2'}`}
              >
                {sub}
              </p>
            ))}

            {/* Meta - Score + Badges */}
            <div className="flex flex-wrap gap-4 mb-6">
              {score != null && (
                <div className="flex items-center gap-2">
                  <FaStar className="text-yellow-400" />
                  <span className="font-bold">
                    {typeof score === 'number' && scoreMax > 10
                      ? (score / (scoreMax / 10)).toFixed(1)
                      : typeof score === 'number'
                        ? score.toFixed(1)
                        : score}
                  </span>
                </div>
              )}
              {badges.map((badge, i) => (
                <span
                  key={i}
                  className={badge.className || 'px-3 py-1 bg-dark-lighter rounded'}
                >
                  {badge.label}
                </span>
              ))}
            </div>

            {/* Genres / Categories */}
            {genres.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-6">
                {genres.map((genre, i) => (
                  <span
                    key={i}
                    className="px-3 py-1 rounded-full text-sm"
                    style={{
                      backgroundColor: accentBg,
                      color: accentColor,
                    }}
                  >
                    {genre}
                  </span>
                ))}
              </div>
            )}

            {/* Description */}
            {description && (
              <div className="mb-6">
                <h3 className="text-lg font-bold mb-2">Sinopsis</h3>
                {translating ? (
                  <div className="flex items-center gap-2 text-gray-400">
                    <FaSpinner className="animate-spin" />
                    <span>Traduciendo...</span>
                  </div>
                ) : (
                  <p className="text-gray-300 leading-relaxed">
                    {translatedDescription || cleanHtml(description)}
                  </p>
                )}
              </div>
            )}

            {/* Info Grid */}
            {infoGrid.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
                {infoGrid.map((item, i) => (
                  <div key={i}>
                    <p className="text-gray-400 text-sm mb-1">{item.label}</p>
                    <p className="flex items-center gap-2 font-medium">
                      {item.icon && item.icon}
                      {item.value}
                    </p>
                  </div>
                ))}
              </div>
            )}

            {/* Creators */}
            {creators.length > 0 && (
              <div className="mb-6 space-y-1">
                {creators.map((creator, i) => (
                  <p key={i}>
                    <span className="text-gray-400">{creator.role}:</span>{' '}
                    {Array.isArray(creator.names) ? creator.names.join(', ') : creator.names}
                  </p>
                ))}
              </div>
            )}

            {/* External Links */}
            {externalLinks.length > 0 && (
              <div className="flex gap-4 mb-6">
                {externalLinks.map((link, i) => (
                  <a
                    key={i}
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-secondary flex items-center gap-2"
                  >
                    {link.icon || <FaExternalLinkAlt />}
                    {link.label}
                  </a>
                ))}
              </div>
            )}

            {/* Actions */}
            {actions.length > 0 && (
              <div className="flex flex-wrap gap-4">
                {actions.map((action, i) => (
                  <div key={i} className="relative group">
                    <button
                      onClick={action.onClick}
                      disabled={action.disabled}
                      className={action.className || 'btn btn-secondary flex items-center gap-2'}
                      title={action.title}
                    >
                      {action.icon && action.icon}
                      {action.label}
                    </button>
                    {action.tooltip && (
                      <div className="absolute bottom-full left-0 mb-2 hidden group-hover:block bg-dark-lighter text-sm text-gray-300 p-2 rounded shadow-lg w-64 z-10">
                        {action.tooltip}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Stats */}
        {stats.length > 0 && (
          <div className="mt-12">
            <h2 className="text-2xl font-bold mb-6">Estadisticas de Descarga</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              {stats.map((stat, i) => (
                <div key={i} className="card p-4">
                  <p className="text-gray-400 text-sm">{stat.label}</p>
                  <p className={`text-2xl font-bold ${stat.color || ''}`}>{stat.value}</p>
                </div>
              ))}
            </div>

            {/* Progress bar */}
            {progress && progress.total > 0 && (
              <div className="mt-6">
                <div className="flex justify-between text-sm text-gray-400 mb-2">
                  <span>Progreso general</span>
                  <span>
                    {progress.current} / {progress.total} ({Math.round((progress.current / progress.total) * 100)}%)
                  </span>
                </div>
                <div className="w-full bg-dark-lighter rounded-full h-3">
                  <div
                    className="h-3 rounded-full transition-all"
                    style={{
                      width: `${(progress.current / progress.total) * 100}%`,
                      backgroundColor: progress.color || accentColor,
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Children (chapter lists, issue lists, etc.) */}
        {children}
      </div>
    </div>
  );
};

export default ContentDetailPage;
