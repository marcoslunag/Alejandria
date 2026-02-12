import { Link } from 'react-router-dom';
import { FaMask, FaCheck, FaPlus, FaBuilding, FaCalendarAlt } from 'react-icons/fa';
import { useState } from 'react';

const ComicCard = ({ comic, onAdd, showAddButton = false }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isAdding, setIsAdding] = useState(false);

  const handleAdd = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsAdding(true);
    try {
      await onAdd(comic);
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
        borderTop: '4px solid #EF4444'
      }}
    >
      <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
        {comic.cover_image ? (
          <img
            src={comic.cover_image}
            alt={comic.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <FaMask className="text-6xl text-gray-600" />
          </div>
        )}

        {isHovered && comic.description && (
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/70 to-transparent flex flex-col justify-end p-4 animate-fade-in">
            <p className="text-sm text-gray-300 line-clamp-3">
              {comic.description.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '')}
            </p>
          </div>
        )}

        {comic.downloaded_issues > 0 && (
          <div className="absolute top-2 right-2 px-2 py-1 rounded text-xs font-medium bg-red-500">
            Descargado
          </div>
        )}

        {comic.in_library && (
          <div className="absolute top-2 left-2 bg-red-500 rounded-full p-2">
            <FaCheck className="text-white text-xs" />
          </div>
        )}
      </div>

      <div className="p-4">
        <h3 className="font-bold text-lg mb-2 line-clamp-2 group-hover:text-red-500 transition-colors">
          {comic.title}
        </h3>

        <div className="flex items-center gap-2 text-sm text-gray-400 mb-2">
          {comic.publisher && (
            <div className="flex items-center gap-1">
              <FaBuilding className="text-xs" />
              <span>{comic.publisher}</span>
            </div>
          )}
          {comic.start_year && (
            <div className="flex items-center gap-1">
              <FaCalendarAlt className="text-xs" />
              <span>{comic.start_year}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 text-sm text-gray-400 mb-2">
          <span className="text-red-400">
            {comic.downloaded_issues || 0}/{comic.count_of_issues || comic.total_issues || '?'} issues
          </span>
        </div>

        {comic.in_library && (comic.count_of_issues || comic.total_issues) > 0 && (
          <div className="mt-2">
            <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
              <span>Descargados</span>
              <span>{comic.downloaded_issues || 0}/{comic.count_of_issues || comic.total_issues}</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-1.5">
              <div
                className="bg-red-500 h-1.5 rounded-full transition-all"
                style={{
                  width: `${((comic.downloaded_issues || 0) / (comic.count_of_issues || comic.total_issues || 1)) * 100}%`
                }}
              />
            </div>
          </div>
        )}

        {showAddButton && !comic.in_library && (
          <button
            onClick={handleAdd}
            disabled={isAdding}
            className="w-full mt-3 btn bg-red-500 hover:bg-red-600 text-white flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <FaPlus />
            {isAdding ? 'Agregando...' : 'Añadir a biblioteca'}
          </button>
        )}
      </div>
    </div>
  );

  const comicId = comic.library_id || comic.id;
  if (comicId) {
    return (
      <Link to={`/comics/${comicId}`}>
        <CardContent />
      </Link>
    );
  }

  return <CardContent />;
};

export default ComicCard;
