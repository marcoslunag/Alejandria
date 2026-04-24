import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { mangaApi, comicApi, bookApi } from '../services/api';
import SearchBar from '../components/SearchBar';
import ContentCard from '../components/ContentCard';
import { FaSearch, FaBook, FaMask, FaBookReader, FaExclamationTriangle, FaCheck } from 'react-icons/fa';

// Adapta un resultado de búsqueda al shape de ContentCard
const adaptSearchResult = (item, tab) => {
  if (tab === 'manga') {
    return {
      ...item,
      cover_image: item.cover_image || item.cover,
      in_library: !!item.library_id,
    };
  }
  if (tab === 'comics') {
    return {
      ...item,
      cover_image: item.cover_image,
      in_library: !!item.library_id,
    };
  }
  // books
  return {
    ...item,
    cover_image: item.cover_image || item.thumbnail,
    in_library: !!item.library_id,
  };
};

const TABS = [
  { value: 'books',  label: 'Libros',  icon: FaBookReader, placeholder: 'Buscar libros por título, autor, ISBN...' },
  { value: 'manga',  label: 'Manga',   icon: FaBook,       placeholder: 'Buscar manga por título...' },
  { value: 'comics', label: 'Cómics',  icon: FaMask,       placeholder: 'Buscar cómics por título...' },
];

const Search = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('books');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const initialQuery = searchParams.get('q') || '';
  const [hasSearched, setHasSearched] = useState(!!initialQuery);
  const [lastQuery, setLastQuery] = useState(initialQuery);
  const [duplicateModal, setDuplicateModal] = useState(null);
  const [markedAsRead, setMarkedAsRead] = useState(new Set());

  useEffect(() => {
    if (initialQuery) {
      handleSearch(initialQuery);
    }
  }, []);

  const handleSearch = async (query, tabOverride) => {
    if (!query.trim()) return;
    const tab = tabOverride || activeTab;
    setLastQuery(query);
    try {
      setLoading(true);
      setHasSearched(true);
      let response;
      if (tab === 'manga') {
        response = await mangaApi.search(query);
        setResults(response.data.results || []);
      } else if (tab === 'comics') {
        response = await comicApi.search(query);
        setResults(response.data.results || []);
      } else if (tab === 'books') {
        response = await bookApi.searchGoogleBooks(query);
        setResults(response.data.results || []);
      }
    } catch (error) {
      console.error('Error buscando:', error);
      setResults([]);
      const isTimeout = error.code === 'ECONNABORTED' || error.message?.toLowerCase().includes('timeout');
      const status = error.response?.status;
      if (isTimeout || status === 504 || status === 502) {
        toast.error('La búsqueda tardó demasiado. Inténtalo de nuevo en unos segundos.');
      } else if (status >= 500) {
        toast.error('Error del servidor al buscar. Revisa los logs.');
      } else if (!error.response) {
        toast.error('No se pudo conectar con el servidor.');
      }
    } finally {
      setLoading(false);
    }
  };

  const _doAddManga = async (manga, force = false) => {
    await mangaApi.addFromAnilist({ anilist_id: manga.anilist_id, monitored: true, auto_download: true }, force);
    toast.success(`"${manga.title}" añadido a la biblioteca`);
    if (lastQuery) handleSearch(lastQuery);
  };

  const handleAddManga = async (manga) => {
    try {
      await _doAddManga(manga);
    } catch (error) {
      if (error.response?.status === 409) {
        const detail = error.response.data?.detail || {};
        setDuplicateModal({ matched_id: detail.matched_id, matched_title: detail.matched_title, type: 'manga', forceAdd: () => _doAddManga(manga, true).catch(() => toast.error('Error al añadir')) });
      } else {
        toast.error('Error al añadir el manga');
      }
    }
  };

  const _doAddComic = async (comic, force = false) => {
    if (comic.comicvine_id === 0 && comic.volume_to_add) {
      const volume = comic.volume_to_add;
      await comicApi.addComicFromUrl({ title: volume.title, url: volume.url, source: volume.source, issues: volume.issues, cover: volume.cover });
      toast.success(`"${volume.title}" añadido a la biblioteca`);
    } else {
      const payload = { comicvine_id: comic.comicvine_id };
      if (comic.volume_to_add) payload.volume_to_add = comic.volume_to_add;
      await comicApi.addComic(payload, force);
      const label = comic.volume_to_add ? `${comic.title} Vol ${comic.volume_to_add.number}` : comic.title;
      toast.success(`"${label}" añadido a la biblioteca`);
    }
    if (lastQuery) handleSearch(lastQuery);
  };

  const handleAddComic = async (comic) => {
    try {
      await _doAddComic(comic);
    } catch (error) {
      if (error.response?.status === 409) {
        const detail = error.response.data?.detail || {};
        setDuplicateModal({ matched_id: detail.matched_id, matched_title: detail.matched_title, type: 'comics', forceAdd: () => _doAddComic(comic, true).catch(() => toast.error('Error al añadir')) });
      } else {
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
    if (lastQuery) handleSearch(lastQuery);
  };

  const handleAddBook = async (book) => {
    try {
      await _doAddBook(book);
    } catch (error) {
      if (error.response?.status === 409) {
        const detail = error.response.data?.detail || {};
        setDuplicateModal({ matched_id: detail.matched_id, matched_title: detail.matched_title, type: 'books', forceAdd: () => _doAddBook(book, true).catch(() => toast.error('Error al añadir')) });
      } else {
        toast.error('Error al añadir el libro');
      }
    }
  };

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
    if (lastQuery) {
      handleSearch(lastQuery, tab);
    } else {
      setHasSearched(false);
    }
  };

  const tabInfo = TABS.find(t => t.value === activeTab) || TABS[0];
  const Icon = tabInfo.icon;

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Tabs — gold active style */}
      <div className="flex justify-center gap-3 mb-8">
        {TABS.map((tab) => {
          const TabIcon = tab.icon;
          return (
            <button
              key={tab.value}
              onClick={() => handleTabChange(tab.value)}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors border ${
                activeTab === tab.value
                  ? 'bg-gold/10 border-gold/25 text-gold'
                  : 'border-transparent text-gray-400 hover:text-white hover:bg-dark-lighter'
              }`}
            >
              <TabIcon className="text-sm" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Header */}
      <div className="mb-8 text-center">
        <h1 className="font-serif text-4xl font-bold mb-2">
          {tabInfo.label === 'Manga' ? 'Buscar Manga' : tabInfo.label === 'Cómics' ? 'Buscar Cómics' : 'Buscar Libros'}
        </h1>
        <p className="text-gray-500 mb-6">
          {tabInfo.value === 'manga' ? 'Busca en la base de datos de AniList' : tabInfo.value === 'comics' ? 'Busca en la base de datos de ComicVine' : 'Busca en Google Books y sitios EPUB'}
        </p>
        <SearchBar
          onSearch={handleSearch}
          placeholder={tabInfo.placeholder}
          autoFocus={!initialQuery}
          initialValue={lastQuery}
        />
      </div>

      {/* Loading */}
      {loading && (
        <div className="text-center py-20">
          <div className="w-10 h-10 border-2 border-gold border-t-transparent rounded-full mx-auto mb-4 animate-spin" />
          <p className="text-gray-500">Buscando...</p>
        </div>
      )}

      {/* No results */}
      {!loading && hasSearched && results.length === 0 && (
        <div className="text-center py-20">
          <FaSearch className="text-5xl text-gray-700 mx-auto mb-4" />
          <h3 className="text-xl font-serif font-bold mb-2">Sin resultados</h3>
          <p className="text-gray-500">Prueba con otro término de búsqueda</p>
        </div>
      )}

      {/* Results */}
      {!loading && results.length > 0 && (
        <div>
          <p className="text-sm text-gray-500 mb-6">{results.length} resultado(s)</p>

          {/* Manga — ContentCard unificada */}
          {activeTab === 'manga' && (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {results.map((manga) => {
                const adapted = adaptSearchResult(manga, 'manga');
                const isRead = markedAsRead.has(manga.anilist_id);
                return (
                  <div key={manga.anilist_id} className="flex flex-col gap-1">
                    {/* Scraper badge */}
                    {manga.scraper_sources && manga.scraper_sources.length > 0 && (
                      <div className="flex flex-wrap gap-1 px-1">
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-book/10 border border-book/20 text-book font-semibold">
                          ✓ Encontrado
                        </span>
                        {manga.scraper_tomo_count > 0 && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-manga/10 border border-manga/20 text-manga font-semibold">
                            {manga.scraper_tomo_count} tomos
                          </span>
                        )}
                      </div>
                    )}
                    <ContentCard
                      item={adapted}
                      type="manga"
                      showAddButton={!adapted.in_library && !isRead}
                      onAdd={handleAddManga}
                    />
                    {!isRead && (
                      <button
                        onClick={() => handleMarkMangaAsRead(manga)}
                        className="text-xs text-gray-500 hover:text-book transition-colors text-center py-1"
                        title="Añadir y marcar como leído"
                      >
                        Ya leído
                      </button>
                    )}
                    {isRead && (
                      <div className="text-[10px] text-book text-center flex items-center justify-center gap-1">
                        <FaCheck className="text-[8px]" /> Marcado como leído
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Comics — mantiene lógica de volúmenes con estilo actualizado */}
          {activeTab === 'comics' && (() => {
            const volumeMap = new Map();
            const regularComics = [];
            results.forEach((comic) => {
              if (comic.volumes && comic.volumes.length > 0) {
                comic.volumes.forEach((volume) => {
                  if (!volumeMap.has(volume.url)) volumeMap.set(volume.url, { comic, volume });
                });
              } else {
                regularComics.push(comic);
              }
            });
            const uniqueVolumes = Array.from(volumeMap.values());
            const allItems = [...uniqueVolumes, ...regularComics.map(comic => ({ comic, volume: null }))];

            return (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                {allItems.map(({ comic, volume }) => {
                  if (volume) {
                    return (
                      <div key={`vol-${volume.url}`} className="card overflow-hidden" style={{ borderTop: '2px solid #c07a5a' }}>
                        <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
                          {volume.cover ? (
                            <img src={volume.cover} alt={volume.title} className="w-full h-full object-cover" loading="lazy" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center">
                              <FaMask className="text-6xl text-gray-600" />
                            </div>
                          )}
                          {volume.number > 0 ? (
                            <div className="absolute top-2 right-2 bg-comic/80 text-white px-2 py-0.5 rounded text-xs font-bold">
                              Vol {volume.number}
                            </div>
                          ) : (
                            <div className="absolute top-2 right-2 bg-book/80 text-white px-2 py-0.5 rounded text-xs font-bold">
                              Colección
                            </div>
                          )}
                        </div>
                        <div className="p-3">
                          <h3 className="font-serif font-bold text-sm mb-1 line-clamp-2">{volume.title}</h3>
                          <p className="text-[10px] text-comic font-semibold uppercase tracking-wide mb-2">
                            {volume.issues} issues · {volume.source}
                          </p>
                          <button
                            onClick={() => handleAddComic({ ...comic, volume_to_add: volume })}
                            className="w-full btn bg-comic hover:bg-comic/80 text-white text-xs py-1.5"
                          >
                            {volume.number > 0 ? `Añadir Vol ${volume.number}` : 'Añadir'}
                          </button>
                        </div>
                      </div>
                    );
                  }
                  return (
                    <div key={comic.comicvine_id} className="card overflow-hidden" style={{ borderTop: '2px solid #c07a5a' }}>
                      <div className="relative aspect-[2/3] overflow-hidden bg-gray-800">
                        {comic.cover_image ? (
                          <img src={comic.cover_image} alt={comic.title} className="w-full h-full object-cover" loading="lazy" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <FaMask className="text-6xl text-gray-600" />
                          </div>
                        )}
                      </div>
                      <div className="p-3">
                        <h3 className="font-serif font-bold text-sm mb-1 line-clamp-2">{comic.title}</h3>
                        {comic.publisher && (
                          <p className="text-[10px] text-comic font-semibold uppercase tracking-wide mb-2">{comic.publisher}</p>
                        )}
                        {!comic.in_library ? (
                          <button onClick={() => handleAddComic(comic)} className="w-full btn bg-comic hover:bg-comic/80 text-white text-xs py-1.5">
                            Añadir
                          </button>
                        ) : (
                          <p className="text-xs text-book text-center flex items-center justify-center gap-1">
                            <FaCheck className="text-[8px]" /> En biblioteca
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })()}

          {/* Books — ContentCard unificada */}
          {activeTab === 'books' && (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {results.map((book, idx) => {
                const adapted = adaptSearchResult(book, 'books');
                const scraperSources = book.scraper_sources || [];
                const hasAnyScraper = scraperSources.length > 0 || book.source === 'lectulandia' || book.source === 'epubera';
                const isRead = markedAsRead.has(book.google_books_id || book.source_url);
                return (
                  <div key={book.google_books_id || book.source_url || idx} className="flex flex-col gap-1">
                    {/* Scraper badge */}
                    {hasAnyScraper && (
                      <div className="flex flex-wrap gap-1 px-1">
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-book/10 border border-book/20 text-book font-semibold">
                          ✓ EPUB disponible
                        </span>
                      </div>
                    )}
                    <ContentCard
                      item={adapted}
                      type="book"
                      showAddButton={!adapted.in_library && !isRead}
                      onAdd={handleAddBook}
                    />
                    {!isRead && (
                      <button
                        onClick={() => handleMarkBookAsRead(book)}
                        className="text-xs text-gray-500 hover:text-book transition-colors text-center py-1"
                        title="Añadir y marcar como leído"
                      >
                        Ya leído
                      </button>
                    )}
                    {isRead && (
                      <div className="text-[10px] text-book text-center flex items-center justify-center gap-1">
                        <FaCheck className="text-[8px]" /> Marcado como leído
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!loading && !hasSearched && (
        <div className="text-center py-20">
          <FaSearch className="text-5xl text-gray-700 mx-auto mb-4" />
          <h3 className="font-serif text-2xl font-bold mb-2">Empieza a buscar</h3>
          <p className="text-gray-500">
            Introduce un término para buscar {activeTab === 'manga' ? 'manga' : activeTab === 'comics' ? 'cómics' : 'libros'}
          </p>
        </div>
      )}

      {/* Duplicate detection modal */}
      {duplicateModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="card p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-yellow-500/20 rounded-full">
                <FaExclamationTriangle className="text-yellow-400 text-xl" />
              </div>
              <h3 className="font-serif text-lg font-bold">Posible duplicado</h3>
            </div>
            <p className="text-gray-300 mb-2">
              Ya tienes <strong>"{duplicateModal.matched_title}"</strong> en tu biblioteca, que parece ser el mismo contenido.
            </p>
            <p className="text-sm text-gray-400 mb-6">¿Qué quieres hacer?</p>
            <div className="flex flex-col gap-3">
              <button onClick={() => { navigate(`/${duplicateModal.type}/${duplicateModal.matched_id}`); setDuplicateModal(null); }} className="btn btn-primary w-full">
                Ver en biblioteca
              </button>
              <button onClick={() => { duplicateModal.forceAdd(); setDuplicateModal(null); }} className="btn btn-secondary w-full">
                Añadir igualmente
              </button>
              <button onClick={() => setDuplicateModal(null)} className="text-gray-400 hover:text-gray-200 text-sm text-center">
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
