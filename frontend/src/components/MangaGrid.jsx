import MangaCard from './MangaCard';

const MangaGrid = ({ manga, onAdd, showAddButton = false, loading = false }) => {
  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
        {[...Array(12)].map((_, i) => (
          <div key={i} className="animate-pulse">
            <div className="aspect-[2/3] bg-dark-lighter rounded-lg mb-3" />
            <div className="h-4 bg-dark-lighter rounded mb-2" />
            <div className="h-3 bg-dark-lighter rounded w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  if (!manga || manga.length === 0) {
    return (
      <div className="text-center py-20">
        <p className="text-gray-400 text-lg">No se encontraron manga</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
      {manga.map((item) => (
        <MangaCard
          key={item.anilist_id || item.id || item.slug}
          manga={item}
          onAdd={onAdd}
          showAddButton={showAddButton}
        />
      ))}
    </div>
  );
};

export default MangaGrid;
