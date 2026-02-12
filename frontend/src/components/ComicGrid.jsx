import ComicCard from './ComicCard';

const ComicGrid = ({ comics, loading, onAdd, showAddButton = false }) => {
  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
        {[...Array(12)].map((_, i) => (
          <div key={i} className="card animate-pulse">
            <div className="aspect-[2/3] bg-gray-700" />
            <div className="p-4">
              <div className="h-4 bg-gray-700 rounded mb-2" />
              <div className="h-3 bg-gray-700 rounded w-2/3" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!comics || comics.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-400 text-lg">No se encontraron comics</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
      {comics.map((comic) => (
        <ComicCard
          key={comic.id || comic.library_id || comic.comicvine_id}
          comic={comic}
          onAdd={onAdd}
          showAddButton={showAddButton}
        />
      ))}
    </div>
  );
};

export default ComicGrid;
