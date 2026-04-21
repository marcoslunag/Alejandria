import ContentCard from './ContentCard';

/**
 * ContentGrid - Grid unificado para manga, cómics y libros.
 *
 * Props:
 *   items          - Array de items a mostrar
 *   type           - 'manga' | 'comic' | 'book'
 *   loading        - Boolean
 *   onAdd          - Callback para añadir
 *   showAddButton  - Mostrar botón de añadir
 *   emptyMessage   - Mensaje cuando no hay items
 *   keyExtractor   - Función para extraer key de cada item
 *   onToggleMonitor - Callback para toggle monitored (item) => void
 */
const ContentGrid = ({
  items,
  type = 'manga',
  loading = false,
  onAdd,
  showAddButton = false,
  emptyMessage,
  keyExtractor,
  onToggleMonitor,
}) => {
  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
        {[...Array(12)].map((_, i) => (
          <div key={i} className="rounded-xl overflow-hidden bg-dark-card">
            <div className="aspect-[2/3] skeleton-shimmer" />
            <div className="p-4 space-y-2">
              <div className="h-4 skeleton-shimmer rounded w-3/4" />
              <div className="h-3 skeleton-shimmer rounded w-1/2" />
              <div className="h-3 skeleton-shimmer rounded w-2/3" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-400 text-lg">
          {emptyMessage || `No se encontraron ${type === 'manga' ? 'manga' : type === 'comic' ? 'comics' : 'libros'}`}
        </p>
      </div>
    );
  }

  const defaultKeyExtractor = (item) => {
    if (type === 'manga') return item.anilist_id || item.id || item.slug;
    if (type === 'comic') return item.id || item.library_id || item.comicvine_id;
    return item.id || item.google_books_id || item.openlibrary_id;
  };

  const getKey = keyExtractor || defaultKeyExtractor;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
      {items.map((item) => (
        <ContentCard
          key={getKey(item)}
          item={item}
          type={type}
          onAdd={onAdd}
          showAddButton={showAddButton}
          onToggleMonitor={onToggleMonitor}
        />
      ))}
    </div>
  );
};

export default ContentGrid;
