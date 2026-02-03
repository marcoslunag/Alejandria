import { Link } from 'react-router-dom';
import { FaStar, FaBook, FaCheck, FaPlus } from 'react-icons/fa';
import { useState } from 'react';
import clsx from 'clsx';

const MangaCard = ({ manga, onAdd, showAddButton = false }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isAdding, setIsAdding] = useState(false);

  const handleAdd = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsAdding(true);
    try {
      await onAdd(manga);
    } finally {
      setIsAdding(false);
    }
  };

  const CardContent = () => (
    <div
      className="card group cursor-pointer transition-all duration-300 hover:scale-105 hover:shadow-2xl relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        borderTop: manga.cover_color ? `4px solid ${manga.cover_color}` : 'none'
      }}
    >
      {/* Cover Image */}
      <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
        {manga.cover_image || manga.cover ? (
          <img
            src={manga.cover_image || manga.cover}
            alt={manga.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <FaBook className="text-6xl text-gray-600" />
          </div>
        )}

        {/* Overlay on hover */}
        {isHovered && (
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/70 to-transparent flex flex-col justify-end p-4 animate-fade-in">
            <p className="text-sm text-gray-300 line-clamp-3">
              {manga.description ? manga.description.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '') : 'Sin descripción disponible'}
            </p>
          </div>
        )}

        {/* Status badge */}
        {manga.status && (
          <div className={clsx(
            "absolute top-2 right-2 px-2 py-1 rounded text-xs font-medium",
            manga.status === 'RELEASING' ? 'bg-green-500' :
            manga.status === 'FINISHED' ? 'bg-blue-500' :
            'bg-gray-500'
          )}>
            {manga.status}
          </div>
        )}

        {/* In Library indicator */}
        {manga.in_library && (
          <div className="absolute top-2 left-2 bg-primary rounded-full p-2">
            <FaCheck className="text-white text-xs" />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-4">
        <h3 className="font-bold text-lg mb-2 line-clamp-2 group-hover:text-primary transition-colors">
          {manga.title}
        </h3>

        {/* Genres */}
        {manga.genres && manga.genres.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {manga.genres.slice(0, 3).map((genre) => (
              <span
                key={genre}
                className="text-xs bg-dark-lighter px-2 py-1 rounded"
              >
                {genre}
              </span>
            ))}
          </div>
        )}

        {/* Stats */}
        <div className="flex items-center justify-between text-sm text-gray-400">
          {/* Score */}
          {manga.average_score && (
            <div className="flex items-center gap-1">
              <FaStar className="text-yellow-400" />
              <span>{(manga.average_score / 10).toFixed(1)}</span>
            </div>
          )}

          {/* Tomos */}
          {manga.chapters_total && (
            <div className="flex items-center gap-1">
              <FaBook />
              <span>{manga.chapters_total} tomos</span>
            </div>
          )}

          {/* Format */}
          {manga.format && (
            <span className="text-xs uppercase">{manga.format}</span>
          )}
        </div>

        {/* Download progress (if in library) */}
        {manga.in_library && manga.downloaded_chapters !== undefined && (
          <div className="mt-3">
            <div className="flex justify-between text-xs text-gray-400 mb-1">
              <span>Descargados</span>
              <span>{manga.downloaded_chapters}/{manga.chapters_total || '?'}</span>
            </div>
            <div className="w-full bg-dark-lighter rounded-full h-1.5">
              <div
                className="bg-primary h-1.5 rounded-full transition-all"
                style={{
                  width: `${manga.chapters_total
                    ? (manga.downloaded_chapters / manga.chapters_total) * 100
                    : 0}%`
                }}
              />
            </div>
          </div>
        )}

        {/* Add button */}
        {showAddButton && !manga.in_library && (
          <button
            onClick={handleAdd}
            disabled={isAdding}
            className="mt-3 w-full btn btn-primary flex items-center justify-center gap-2"
          >
            {isAdding ? (
              <>
                <div className="spinner border-2 border-white border-t-transparent rounded-full w-4 h-4" />
                <span>Añadiendo...</span>
              </>
            ) : (
              <>
                <FaPlus />
                <span>Añadir a Biblioteca</span>
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );

  // Wrap in Link if manga has a valid ID (meaning it's in the library)
  // Check for library_id first (when coming from discovery), then regular id (when coming from library list)
  const mangaId = manga.library_id || (manga.id && manga.id > 0 ? manga.id : null);

  if (mangaId) {
    return (
      <Link to={`/manga/${mangaId}`}>
        <CardContent />
      </Link>
    );
  }

  return <CardContent />;
};

export default MangaCard;
