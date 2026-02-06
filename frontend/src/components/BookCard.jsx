import { Link } from 'react-router-dom';
import { FaStar, FaBookReader, FaCheck, FaPlus } from 'react-icons/fa';
import { useState } from 'react';
import clsx from 'clsx';

const BookCard = ({ book, onAdd, showAddButton = false }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isAdding, setIsAdding] = useState(false);

  const handleAdd = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsAdding(true);
    try {
      await onAdd(book);
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
        borderTop: '4px solid #10B981' // Green color for books
      }}
    >
      {/* Cover Image */}
      <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
        {book.cover_image || book.thumbnail ? (
          <img
            src={book.cover_image || book.thumbnail}
            alt={book.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <FaBookReader className="text-6xl text-gray-600" />
          </div>
        )}

        {/* Overlay on hover */}
        {isHovered && book.description && (
          <div className="absolute inset-0 bg-gradient-to-t from-black via-black/70 to-transparent flex flex-col justify-end p-4 animate-fade-in">
            <p className="text-sm text-gray-300 line-clamp-3">
              {book.description.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, '')}
            </p>
          </div>
        )}

        {/* Downloaded badge */}
        {book.downloaded_chapters > 0 && (
          <div className="absolute top-2 right-2 px-2 py-1 rounded text-xs font-medium bg-green-500">
            Descargado
          </div>
        )}

        {/* In Library indicator */}
        {book.in_library && (
          <div className="absolute top-2 left-2 bg-green-500 rounded-full p-2">
            <FaCheck className="text-white text-xs" />
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-4">
        <h3 className="font-bold text-lg mb-2 line-clamp-2 group-hover:text-green-500 transition-colors">
          {book.title}
        </h3>

        {/* Authors */}
        {book.authors && book.authors.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {book.authors.slice(0, 2).map((author, idx) => (
              <span
                key={idx}
                className="text-xs px-2 py-1 bg-dark-lighter rounded text-gray-300"
              >
                {author}
              </span>
            ))}
          </div>
        )}

        {/* Stats */}
        <div className="flex items-center gap-3 text-sm text-gray-400 mb-2">
          {/* Rating */}
          {book.average_rating && (
            <div className="flex items-center gap-1">
              <FaStar className="text-yellow-400 text-xs" />
              <span>{book.average_rating.toFixed(1)}</span>
            </div>
          )}

          {/* Pages */}
          {book.page_count && (
            <div className="flex items-center gap-1">
              <FaBookReader className="text-xs" />
              <span>{book.page_count}p</span>
            </div>
          )}

          {/* Language */}
          {book.language && (
            <span className="text-xs uppercase">{book.language}</span>
          )}
        </div>

        {/* Download progress (if in library) */}
        {book.in_library && book.total_chapters > 0 && (
          <div className="mt-2">
            <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
              <span>Descargados</span>
              <span>{book.downloaded_chapters || 0}/{book.total_chapters}</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-1.5">
              <div
                className="bg-green-500 h-1.5 rounded-full transition-all"
                style={{
                  width: `${((book.downloaded_chapters || 0) / book.total_chapters) * 100}%`
                }}
              />
            </div>
          </div>
        )}

        {/* Add button */}
        {showAddButton && !book.in_library && (
          <button
            onClick={handleAdd}
            disabled={isAdding}
            className="w-full mt-3 btn btn-primary flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <FaPlus />
            {isAdding ? 'Agregando...' : 'Añadir a biblioteca'}
          </button>
        )}
      </div>
    </div>
  );

  // If book has valid ID and is in library, wrap with Link
  if (book.id || book.library_id) {
    return (
      <Link to={`/books/${book.library_id || book.id}`}>
        <CardContent />
      </Link>
    );
  }

  return <CardContent />;
};

export default BookCard;
