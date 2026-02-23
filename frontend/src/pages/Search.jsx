import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { mangaApi, comicApi, bookApi } from '../services/api';
import SearchBar from '../components/SearchBar';
import ContentCard from '../components/ContentCard';
import { FaSearch, FaBook, FaMask, FaBookReader, FaExclamationTriangle, FaCheck } from 'react-icons/fa';

const Search = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('books'); // books, manga, comics
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const initialQuery = searchParams.get('q') || '';
  const [hasSearched, setHasSearched] = useState(!!initialQuery);
  // Feature 6: Duplicate detection modal
  const [duplicateModal, setDuplicateModal] = useState(null); // { matched_id, matched_title, type, forceAdd }
  // Tracking leídos en esta sesión (por anilist_id / google_books_id)
  const [markedAsRead, setMarkedAsRead] = useState(new Set());

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

  const _doAddManga = async (manga, force = false) => {
    const url = force ? `/manga/add/anilist?force=true` : undefined;
    await mangaApi.addFromAnilist({
      anilist_id: manga.anilist_id,
      monitored: true,
      auto_download: true,
    }, force);
    toast.success(`"${manga.title}" añadido a la biblioteca`);
    const query = searchParams.get('q') || initialQuery;
    if (query) handleSearch(query);
  };

  const handleAddManga = async (manga) => {
    try {
      await _doAddManga(manga);
    } catch (error) {
      if (error.response?.status === 409) {
        const detail = error.response.data?.detail || {};
        setDuplicateModal({
          matched_id: detail.matched_id,
          matched_title: detail.matched_title,
          type: 'manga',
          forceAdd: () => _doAddManga(manga, true).catch(() => toast.error('Error al añadir')),
        });
      } else {
        console.error('Error añadiendo manga:', error);
        toast.error('Error al añadir el manga');
      }
    }
  };

  const _doAddComic = async (comic, force = false) => {
    if (comic.comicvine_id === 0 && comic.volume_to_add) {
      const volume = comic.volume_to_add;
      await comicApi.addComicFromUrl({
        title: volume.title,
        url: volume.url,
        source: volume.source,
        issues: volume.issues,
        cover: volume.cover
      });
      toast.success(`"${volume.title}" añadido a la biblioteca`);
    } else {
      const payload = { comicvine_id: comic.comicvine_id };
      if (comic.volume_to_add) payload.volume_to_add = comic.volume_to_add;
      await comicApi.addComic(payload, force);
      const label = comic.volume_to_add ? `${comic.title} Vol ${comic.volume_to_add.number}` : comic.title;
      toast.success(`"${label}" añadido a la biblioteca`);
    }
    const query = searchParams.get('q') || initialQuery;
    if (query) handleSearch(query);
  };

  const handleAddComic = async (comic) => {
    try {
      await _doAddComic(comic);
    } catch (error) {
      if (error.response?.status === 409) {
        const detail = error.response.data?.detail || {};
        setDuplicateModal({
          matched_id: detail.matched_id,
          matched_title: detail.matched_title,
          type: 'comics',
          forceAdd: () => _doAddComic(comic, true).catch(() => toast.error('Error al añadir')),
        });
      } else {
        console.error('Error añadiendo comic:', error);
        toast.error('Error al añadir el cómic');
      }
    }
  };

  const _doAddBook = async (book, force = false) => {
    if (book.source_url && !book.google_books_id) {
      await bookApi.addFromUrl({ source_url: book.source_url, monitored: true, auto_download: true });
    } else if (book.google_books_id) {
      await bookApi.addFromGoogleBooks({ google_books_id: book.google_books_id, monitored: true, auto_download: true }, force);
    } else {
      toast.error('Este libro no tiene suficiente información para ser añadido');
      return;
    }
    toast.success(`"${book.title}" añadido a la biblioteca`);
    const query = searchParams.get('q') || initialQuery;
    if (query) handleSearch(query);
  };

  const handleAddBook = async (book) => {
    try {
      await _doAddBook(book);
    } catch (error) {
      if (error.response?.status === 409) {
        const detail = error.response.data?.detail || {};
        setDuplicateModal({
          matched_id: detail.matched_id,
          matched_title: detail.matched_title,
          type: 'books',
          forceAdd: () => _doAddBook(book, true).catch(() => toast.error('Error al añadir')),
        });
      } else {
        console.error('Error añadiendo libro:', error);
        toast.error('Error al añadir el libro');
      }
    }
  };

  // Marca un manga como leído: lo añade a biblioteca si es necesario, luego marca como completed
  const handleMarkMangaAsRead = async (manga) => {
    try {
      let libraryId = manga.library_id;
      if (!libraryId) {
        const res = await mangaApi.addFromAnilist({ anilist_id: manga.anilist_id, monitored: false, auto_download: false });
        libraryId = res.data?.id;
      }
      if (!libraryId) { toast.error('No se pudo añadir el manga'); return; }
      await mangaApi.setReadingStatus(libraryId, 'completed');
      setMarkedAsRead(prev => new Set([...prev, manga.anilist_id]));
      toast.success(`"${manga.title}" marcado como leído`);
    } catch (error) {
      if (error.response?.status === 409) {
        // Ya existe — obtener ID del error y marcar
        const detail = error.response.data?.detail || {};
        const existingId = detail.matched_id;
        if (existingId) {
          await mangaApi.setReadingStatus(existingId, 'completed');
          setMarkedAsRead(prev => new Set([...prev, manga.anilist_id]));
          toast.success(`"${manga.title}" marcado como leído`);
        }
      } else {
        toast.error('Error al marcar como leído');
      }
    }
  };

  const handleMarkBookAsRead = async (book) => {
    try {
      let libraryId = book.library_id;
      if (!libraryId) {
        let res;
        if (book.google_books_id) {
          res = await bookApi.addFromGoogleBooks({ google_books_id: book.google_books_id, monitored: false, auto_download: false });
        } else if (book.source_url) {
          res = await bookApi.addFromUrl({ source_url: book.source_url, monitored: false, auto_download: false });
        } else { toast.error('Sin información suficiente'); return; }
        libraryId = res.data?.id;
      }
      if (!libraryId) { toast.error('No se pudo añadir el libro'); return; }
      await bookApi.setReadingStatus(libraryId, 'completed');
      setMarkedAsRead(prev => new Set([...prev, book.google_books_id || book.source_url]));
      toast.success(`"${book.title}" marcado como leído`);
    } catch (error) {
      if (error.response?.status === 409) {
        const detail = error.response.data?.detail || {};
        const existingId = detail.matched_id;
        if (existingId) {
          await bookApi.setReadingStatus(existingId, 'completed');
          setMarkedAsRead(prev => new Set([...prev, book.google_books_id || book.source_url]));
          toast.success(`"${book.title}" marcado como leído`);
        }
      } else {
        toast.error('Error al marcar como leído');
      }
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
                <div key={manga.anilist_id} className="card overflow-hidden flex flex-col">
                  <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
                    {manga.cover ? (
                      <img
                        src={manga.cover}
                        alt={manga.title}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <FaBook className="text-6xl text-gray-600" />
                      </div>
                    )}
                    {/* Scraper availability badge */}
                    {manga.scraper_sources && manga.scraper_sources.length > 0 ? (
                      <div className="absolute top-2 left-2 bg-green-600 text-white px-2 py-0.5 rounded-full text-xs font-bold shadow">
                        ✓ Encontrado
                      </div>
                    ) : (
                      <div className="absolute top-2 left-2 bg-gray-700 text-gray-300 px-2 py-0.5 rounded-full text-xs shadow">
                        Sin fuentes
                      </div>
                    )}
                  </div>
                  <div className="p-3 flex flex-col flex-1">
                    <h3 className="font-bold text-sm mb-1 line-clamp-2">{manga.title}</h3>
                    {manga.average_score > 0 && (
                      <p className="text-xs text-yellow-400 mb-1">⭐ {manga.average_score / 10}/10</p>
                    )}
                    {/* Scraper info */}
                    {manga.scraper_sources && manga.scraper_sources.length > 0 && (
                      <div className="text-xs text-gray-400 mb-2 space-y-0.5">
                        {manga.scraper_tomo_count > 0 && (
                          <p>📚 {manga.scraper_tomo_count} tomos</p>
                        )}
                        <p>🌐 {manga.scraper_sources.join(', ')}</p>
                      </div>
                    )}
                    <div className="mt-auto space-y-1">
                      {markedAsRead.has(manga.anilist_id) ? (
                        <div className="text-center text-green-500 text-sm mt-2 flex items-center justify-center gap-1">
                          <FaCheck /> Leído
                        </div>
                      ) : manga.in_library ? (
                        <div className="text-center text-green-500 text-sm mt-2">✓ En biblioteca</div>
                      ) : (
                        <button
                          onClick={() => handleAddManga(manga)}
                          className="w-full btn btn-primary bg-blue-500 hover:bg-blue-600 text-sm mt-2"
                        >
                          Añadir
                        </button>
                      )}
                      {!markedAsRead.has(manga.anilist_id) && (
                        <button
                          onClick={() => handleMarkMangaAsRead(manga)}
                          className="w-full btn bg-gray-700 hover:bg-green-700 text-gray-300 hover:text-white text-xs mt-1"
                          title="Añadir a biblioteca y marcar como leído"
                        >
                          Ya leído
                        </button>
                      )}
                    </div>
                  </div>
                </div>
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
              {results.map((book, idx) => {
                const scraperSources = book.scraper_sources || [];
                const isLectulandia = book.source === 'lectulandia' || scraperSources.includes('lectulandia');
                const isEpubera = book.source === 'epubera' || scraperSources.includes('epubera');
                const hasAnyScraper = isLectulandia || isEpubera;

                return (
                  <div key={book.google_books_id || book.source_url || idx} className="card overflow-hidden flex flex-col">
                    <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
                      {(book.cover_image || book.thumbnail) ? (
                        <img
                          src={book.cover_image || book.thumbnail}
                          alt={book.title}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center">
                          <FaBookReader className="text-6xl text-gray-600" />
                        </div>
                      )}
                      {/* EPUB availability badge */}
                      {hasAnyScraper ? (
                        <div className="absolute top-2 left-2 bg-green-600 text-white px-2 py-0.5 rounded-full text-xs font-bold shadow">
                          ✓ EPUB disponible
                        </div>
                      ) : book.source === 'google_books' ? (
                        <div className="absolute top-2 left-2 bg-gray-700 text-gray-300 px-2 py-0.5 rounded-full text-xs shadow">
                          Sin EPUB conocido
                        </div>
                      ) : null}
                    </div>
                    <div className="p-3 flex flex-col flex-1">
                      <h3 className="font-bold text-sm mb-1 line-clamp-2">{book.title}</h3>
                      {book.authors && book.authors.length > 0 && (
                        <p className="text-xs text-gray-400 mb-1 line-clamp-1">{book.authors.join(', ')}</p>
                      )}
                      {/* Scraper sources */}
                      {hasAnyScraper && (
                        <div className="text-xs text-gray-400 mb-2 space-y-0.5">
                          {isLectulandia && <p>🌐 Lectulandia</p>}
                          {isEpubera && <p>🌐 Epubera</p>}
                        </div>
                      )}
                      <div className="mt-auto space-y-1">
                        {markedAsRead.has(book.google_books_id || book.source_url) ? (
                          <div className="text-center text-green-500 text-sm mt-2 flex items-center justify-center gap-1">
                            <FaCheck /> Leído
                          </div>
                        ) : book.in_library ? (
                          <div className="text-center text-green-500 text-sm mt-2">✓ En biblioteca</div>
                        ) : (
                          <button
                            onClick={() => handleAddBook(book)}
                            className="w-full btn btn-primary bg-green-500 hover:bg-green-600 text-sm mt-2"
                          >
                            Añadir
                          </button>
                        )}
                        {!markedAsRead.has(book.google_books_id || book.source_url) && (
                          <button
                            onClick={() => handleMarkBookAsRead(book)}
                            className="w-full btn bg-gray-700 hover:bg-green-700 text-gray-300 hover:text-white text-xs mt-1"
                            title="Añadir a biblioteca y marcar como leído"
                          >
                            Ya leído
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
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

      {/* Feature 6: Duplicate detection modal */}
      {duplicateModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="card p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-yellow-500/20 rounded-full">
                <FaExclamationTriangle className="text-yellow-400 text-xl" />
              </div>
              <h3 className="text-lg font-bold">Posible duplicado</h3>
            </div>
            <p className="text-gray-300 mb-2">
              Ya tienes <strong>"{duplicateModal.matched_title}"</strong> en tu biblioteca, que parece ser el mismo contenido.
            </p>
            <p className="text-sm text-gray-400 mb-6">¿Qué quieres hacer?</p>
            <div className="flex flex-col gap-3">
              <button
                onClick={() => {
                  navigate(`/${duplicateModal.type}/${duplicateModal.matched_id}`);
                  setDuplicateModal(null);
                }}
                className="btn btn-primary w-full"
              >
                Ver en biblioteca
              </button>
              <button
                onClick={() => {
                  duplicateModal.forceAdd();
                  setDuplicateModal(null);
                }}
                className="btn btn-secondary w-full"
              >
                Añadir igualmente
              </button>
              <button
                onClick={() => setDuplicateModal(null)}
                className="text-gray-400 hover:text-gray-200 text-sm text-center"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Search;
