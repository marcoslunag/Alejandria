import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { mangaApi, comicApi, bookApi } from '../services/api';
import SearchBar from '../components/SearchBar';
import MangaCard from '../components/MangaCard';
import BookCard from '../components/BookCard';
import { FaSearch, FaBook, FaMask, FaBookReader } from 'react-icons/fa';

const Search = () => {
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState('manga'); // manga, comics, books
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const initialQuery = searchParams.get('q') || '';
  const [hasSearched, setHasSearched] = useState(!!initialQuery);

  useEffect(() => {
    if (initialQuery) {
      handleSearch(initialQuery);
    }
  }, []);

  const handleSearch = async (query) => {
    if (!query.trim()) return;

    try {
      setLoading(true);
      setHasSearched(true);

      let response;
      if (activeTab === 'manga') {
        response = await mangaApi.search(query);
        setResults(response.data.results);
      } else if (activeTab === 'comics') {
        response = await comicApi.search(query);
        setResults(response.data.results || []);
      } else if (activeTab === 'books') {
        response = await bookApi.searchGoogleBooks(query);
        setResults(response.data.results || []);
      }
    } catch (error) {
      console.error('Error buscando:', error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const handleAddManga = async (manga) => {
    try {
      await mangaApi.addFromAnilist({
        anilist_id: manga.anilist_id,
        monitored: true,
        auto_download: true,
      });
      alert(`"${manga.title}" añadido a la biblioteca!`);
      const query = searchParams.get('q') || initialQuery;
      if (query) handleSearch(query);
    } catch (error) {
      console.error('Error añadiendo manga:', error);
      alert('Error al añadir el manga. Inténtalo de nuevo.');
    }
  };

  const handleAddComic = async (comic) => {
    try {
      // If comicvine_id is 0 (virtual result), add from scraper URL directly
      if (comic.comicvine_id === 0 && comic.volume_to_add) {
        const volume = comic.volume_to_add;
        await comicApi.addComicFromUrl({
          title: volume.title,
          url: volume.url,
          source: volume.source,
          issues: volume.issues,
          cover: volume.cover
        });
        alert(`"${volume.title}" añadido a la biblioteca!`);
      }
      // Normal ComicVine comic
      else {
        const payload = {
          comicvine_id: comic.comicvine_id
        };

        if (comic.volume_to_add) {
          payload.volume_to_add = comic.volume_to_add;
          await comicApi.addComic(payload);
          alert(`"${comic.title} Vol ${comic.volume_to_add.number}" añadido a la biblioteca!`);
        } else {
          await comicApi.addComic(payload);
          alert(`"${comic.title}" añadido a la biblioteca!`);
        }
      }

      const query = searchParams.get('q') || initialQuery;
      if (query) handleSearch(query);
    } catch (error) {
      console.error('Error añadiendo comic:', error);
      alert('Error al añadir el cómic. Inténtalo de nuevo.');
    }
  };

  const handleAddBook = async (book) => {
    try {
      // If book has source_url (from scrapers), use addFromUrl
      // Otherwise use addFromGoogleBooks
      if (book.source_url && !book.google_books_id) {
        await bookApi.addFromUrl({
          source_url: book.source_url,
          monitored: true,
          auto_download: true,
        });
      } else if (book.google_books_id) {
        await bookApi.addFromGoogleBooks({
          google_books_id: book.google_books_id,
          monitored: true,
          auto_download: true,
        });
      } else {
        alert('Este libro no tiene suficiente información para ser añadido.');
        return;
      }

      alert(`"${book.title}" añadido a la biblioteca!`);
      const query = searchParams.get('q') || initialQuery;
      if (query) handleSearch(query);
    } catch (error) {
      console.error('Error añadiendo libro:', error);
      alert('Error al añadir el libro. Inténtalo de nuevo.');
    }
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setResults([]);
    setHasSearched(false);
  };

  const getTabInfo = () => {
    switch (activeTab) {
      case 'manga':
        return {
          title: 'Buscar Manga',
          subtitle: 'Busca en la base de datos de AniList',
          icon: FaBook,
          color: 'text-blue-500',
          placeholder: 'Buscar manga por título...'
        };
      case 'comics':
        return {
          title: 'Buscar Cómics',
          subtitle: 'Busca en la base de datos de ComicVine',
          icon: FaMask,
          color: 'text-red-500',
          placeholder: 'Buscar cómics por título...'
        };
      case 'books':
        return {
          title: 'Buscar Libros',
          subtitle: 'Busca en Google Books y sitios EPUB',
          icon: FaBookReader,
          color: 'text-green-500',
          placeholder: 'Buscar libros por título, autor, ISBN...'
        };
      default:
        return {};
    }
  };

  const tabInfo = getTabInfo();
  const Icon = tabInfo.icon;

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Tabs */}
      <div className="flex justify-center gap-4 mb-8">
        <button
          onClick={() => handleTabChange('manga')}
          className={`px-6 py-3 rounded-lg flex items-center gap-2 transition-colors ${
            activeTab === 'manga'
              ? 'bg-blue-500 text-white'
              : 'bg-dark-lighter text-gray-400 hover:text-white'
          }`}
        >
          <FaBook />
          Manga
        </button>
        <button
          onClick={() => handleTabChange('comics')}
          className={`px-6 py-3 rounded-lg flex items-center gap-2 transition-colors ${
            activeTab === 'comics'
              ? 'bg-red-500 text-white'
              : 'bg-dark-lighter text-gray-400 hover:text-white'
          }`}
        >
          <FaMask />
          Cómics
        </button>
        <button
          onClick={() => handleTabChange('books')}
          className={`px-6 py-3 rounded-lg flex items-center gap-2 transition-colors ${
            activeTab === 'books'
              ? 'bg-green-500 text-white'
              : 'bg-dark-lighter text-gray-400 hover:text-white'
          }`}
        >
          <FaBookReader />
          Libros
        </button>
      </div>

      {/* Header */}
      <div className="mb-8 text-center">
        <h1 className={`text-4xl font-bold mb-2 flex items-center justify-center gap-3 ${tabInfo.color}`}>
          <Icon />
          {tabInfo.title}
        </h1>
        <p className="text-gray-400 mb-6">{tabInfo.subtitle}</p>

        {/* Search Bar */}
        <SearchBar
          onSearch={handleSearch}
          placeholder={tabInfo.placeholder}
          autoFocus={!initialQuery}
        />
      </div>

      {/* Results */}
      {loading && (
        <div className="text-center py-20">
          <div className="spinner border-4 border-primary border-t-transparent rounded-full w-12 h-12 mx-auto mb-4 animate-spin" />
          <p className="text-gray-400">Buscando...</p>
        </div>
      )}

      {!loading && hasSearched && results.length === 0 && (
        <div className="text-center py-20">
          <FaSearch className="text-6xl text-gray-600 mx-auto mb-4" />
          <h3 className="text-2xl font-bold mb-2">Sin resultados</h3>
          <p className="text-gray-400">Prueba con otro término de búsqueda</p>
        </div>
      )}

      {!loading && results.length > 0 && (
        <div>
          <h2 className="text-xl font-bold mb-6 text-gray-400">
            {results.length} resultado(s) encontrado(s)
          </h2>

          {activeTab === 'manga' && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
              {results.map((manga) => (
                <MangaCard
                  key={manga.anilist_id}
                  manga={manga}
                  showAddButton={true}
                  onAdd={handleAddManga}
                />
              ))}
            </div>
          )}

          {activeTab === 'comics' && (() => {
            // Deduplicate volumes across all comics (same volume URL = same volume)
            const volumeMap = new Map();
            const regularComics = [];

            results.forEach((comic) => {
              if (comic.volumes && comic.volumes.length > 0) {
                // Comic has volumes - add each unique volume
                comic.volumes.forEach((volume) => {
                  if (!volumeMap.has(volume.url)) {
                    volumeMap.set(volume.url, { comic, volume });
                  }
                });
              } else {
                // Comic without volumes - show as regular card
                regularComics.push(comic);
              }
            });

            const uniqueVolumes = Array.from(volumeMap.values());
            const allItems = [...uniqueVolumes, ...regularComics.map(comic => ({ comic, volume: null }))];

            return (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
                {allItems.map(({ comic, volume }) => {
                  if (volume) {
                    // Volume card - use volume's own cover and title
                    return (
                      <div key={`vol-${volume.url}`} className="card overflow-hidden">
                      <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
                        {volume.cover ? (
                          <img
                            src={volume.cover}
                            alt={volume.title}
                            className="w-full h-full object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <FaMask className="text-6xl text-gray-600" />
                          </div>
                        )}
                        {/* Volume badge */}
                        {volume.number > 0 ? (
                          <div className="absolute top-2 right-2 bg-red-600 text-white px-3 py-1 rounded-full font-bold text-sm shadow-lg">
                            Vol {volume.number}
                          </div>
                        ) : (
                          <div className="absolute top-2 right-2 bg-green-600 text-white px-3 py-1 rounded-full font-bold text-sm shadow-lg">
                            Colección
                          </div>
                        )}
                      </div>
                      <div className="p-4">
                        <h3 className="font-bold text-lg mb-2 line-clamp-2">{volume.title}</h3>
                        <div className="text-xs text-gray-400 mb-2 space-y-1">
                          <p>📖 {volume.issues} issues</p>
                          <p>🌐 {volume.source}</p>
                        </div>
                        <button
                          onClick={() => handleAddComic({...comic, volume_to_add: volume})}
                          className="w-full btn btn-primary bg-red-500 hover:bg-red-600 mt-2"
                        >
                          {volume.number > 0 ? `Añadir Vol ${volume.number}` : 'Añadir'}
                        </button>
                      </div>
                    </div>
                    );
                  }

                  // Regular comic card (no volume)
                  return (
                    <div key={comic.comicvine_id} className="card overflow-hidden">
                      <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
                        {comic.cover_image ? (
                          <img
                            src={comic.cover_image}
                            alt={comic.title}
                            className="w-full h-full object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <FaMask className="text-6xl text-gray-600" />
                          </div>
                        )}
                      </div>
                      <div className="p-4">
                        <h3 className="font-bold text-lg mb-2 line-clamp-2">{comic.title}</h3>
                        {comic.publisher && (
                          <p className="text-sm text-gray-400 mb-2">{comic.publisher}</p>
                        )}
                        {!comic.in_library && (
                          <button
                            onClick={() => handleAddComic(comic)}
                            className="w-full btn btn-primary bg-red-500 hover:bg-red-600 mt-2"
                          >
                            Añadir
                          </button>
                        )}
                        {comic.in_library && (
                          <div className="text-center text-green-500 mt-2">
                            ✓ En biblioteca
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })()}

          {activeTab === 'books' && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6">
              {results.map((book) => (
                <BookCard
                  key={book.google_books_id}
                  book={book}
                  showAddButton={true}
                  onAdd={handleAddBook}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Empty state (no search yet) */}
      {!loading && !hasSearched && (
        <div className="text-center py-20">
          <Icon className={`text-6xl mx-auto mb-4 ${tabInfo.color}`} />
          <h3 className="text-2xl font-bold mb-2">Empieza a buscar</h3>
          <p className="text-gray-400">
            Introduce un término para buscar {activeTab === 'manga' ? 'manga' : activeTab === 'comics' ? 'cómics' : 'libros'}
          </p>
        </div>
      )}
    </div>
  );
};

export default Search;
