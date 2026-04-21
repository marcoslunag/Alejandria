import { Link } from 'react-router-dom';
import { sanitizeUrl } from '../utils/sanitizeUrl';
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
 *   accentColor       - Color hex para acentos (ej: "#6b9bd2" manga, "#c07a5a" comic, "#7aa67a" book)
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
  accentColor = '#6b9bd2',
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
      <div className="min-h-screen">
        <div className="h-56 skeleton-shimmer" />
        <div className="container mx-auto px-4 py-8 space-y-4">
          <div className="h-10 skeleton-shimmer rounded w-1/2" />
          <div className="h-5 skeleton-shimmer rounded w-1/3" />
          <div className="h-4 skeleton-shimmer rounded w-3/4" />
          <div className="h-4 skeleton-shimmer rounded w-2/3" />
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

  return (
    <div className="min-h-screen">
      {/* Banner — always rendered, cinematographic overlay */}
      <div className="w-full h-56 relative overflow-hidden">
        {bannerImage ? (
          <div
            className="absolute inset-0 bg-cover bg-center"
            style={{ backgroundImage: `url(${sanitizeUrl(bannerImage)})` }}
          />
        ) : coverImage ? (
          <div
            className="absolute inset-0 bg-cover bg-center"
            style={{
              backgroundImage: `url(${sanitizeUrl(coverImage)})`,
              filter: 'blur(12px)',
              transform: 'scale(1.15)',
            }}
          />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-dark-card to-dark" />
        )}
        {/* Dark overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-dark-base/30 via-dark/60 to-dark" />
        {/* Bottom gradient */}
        <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-dark to-transparent" />
      </div>

      <div className="container mx-auto px-4 pb-8" style={{ marginTop: '-8rem' }}>
        <div className="flex flex-col md:flex-row gap-8">
          {/* Cover */}
          <div className="flex-shrink-0">
            {coverImage ? (
              <img
                src={coverImage}
                alt={title}
                className="w-64 rounded-lg shadow-[0_8px_32px_rgba(0,0,0,0.6)]"
                style={{ borderTop: `2px solid ${accentColor}` }}
              />
            ) : (
              <div
                className="w-64 h-96 rounded-lg shadow-[0_8px_32px_rgba(0,0,0,0.6)] bg-dark-lighter flex items-center justify-center"
                style={{ borderTop: `2px solid ${accentColor}` }}
              >
                <FaBook className="text-6xl text-gray-600" />
              </div>
            )}
          </div>

          {/* Info */}
          <div className="flex-1">
            {/* Title — Playfair Display */}
            <h1 className="font-serif text-4xl font-bold mb-2 text-white/95">{title}</h1>
            {subtitles.filter(Boolean).map((sub, i) => (
              <p
                key={i}
                className={`${i === 0 ? 'text-xl text-gray-400' : 'text-lg text-gray-500'} mb-${i === subtitles.filter(Boolean).length - 1 ? '4' : '2'}`}
              >
                {sub}
              </p>
            ))}

            {/* Meta — Score + Badges */}
            <div className="flex flex-wrap gap-4 mb-6">
              {score != null && (
                <div className="flex items-center gap-2">
                  <FaStar className="text-gold" />
                  <span className="font-bold text-gold">
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
                  className={badge.className || 'px-3 py-1 bg-dark-lighter rounded text-sm'}
                >
                  {badge.label}
                </span>
              ))}
            </div>

            {/* Genres — pill style with border */}
            {genres.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-6">
                {genres.map((genre, i) => (
                  <span
                    key={i}
                    className="px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wide border"
                    style={{
                      backgroundColor: `${accentColor}18`,
                      color: accentColor,
                      borderColor: `${accentColor}35`,
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
                    href={sanitizeUrl(link.url)}
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

            {/* Actions — first action gets btn-primary by default */}
            {actions.length > 0 && (
              <div className="flex flex-wrap gap-3 mt-2">
                {actions.map((action, i) => (
                  <div key={i} className="relative group">
                    <button
                      onClick={action.onClick}
                      disabled={action.disabled}
                      className={action.className || (i === 0 ? 'btn btn-primary flex items-center gap-2' : 'btn btn-secondary flex items-center gap-2')}
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

        {/* Stats row */}
        {stats.length > 0 && (
          <div className="mt-8">
            <div className="flex flex-wrap gap-4 bg-dark-card rounded-xl p-5 border border-white/5">
              {stats.map((stat, i) => (
                <div key={i} className="flex-1 min-w-[80px] text-center">
                  <p
                    className="text-2xl font-bold mb-1"
                    style={{ color: stat.color || '#f8f4ef' }}
                  >
                    {stat.value}
                  </p>
                  <p className="text-xs text-gray-500 uppercase tracking-widest font-light">{stat.label}</p>
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
                <div className="w-full bg-dark-lighter rounded-full h-[3px]">
                  <div
                    className="h-[3px] rounded-full transition-all"
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
