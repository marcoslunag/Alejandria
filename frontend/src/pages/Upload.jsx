import { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  FaUpload, FaBook, FaMask, FaBookReader, FaSearch,
  FaCheck, FaTimes, FaSpinner, FaFileAlt, FaArrowLeft
} from 'react-icons/fa';
import { mangaApi, comicApi, bookApi, uploadApi } from '../services/api';

// ─── Type configuration ───────────────────────────────────────────────────
const TYPE_CONFIG = {
  manga: {
    label: 'Manga',
    icon: FaBook,
    color: 'blue',
    accentClass: 'border-blue-500 bg-blue-500/10',
    badgeClass: 'bg-blue-500/20 text-blue-400 border border-blue-500/30',
    btnClass: 'bg-blue-600 hover:bg-blue-500',
    search: (q) => mangaApi.search(q, 1, 8),
    getResults: (data) => data.data?.results || [],
    getId: (item) => String(item.anilist_id || item.id),
    getTitle: (item) => item.title,
    getCover: (item) => item.cover_image || item.cover,
    getSub: (item) => item.authors?.[0] || item.format || '',
    idLabel: 'AniList ID',
    idField: 'anilist_id',
    detailPath: '/manga',
    accept: '.cbz,.cbr,.zip',
    acceptHint: 'CBZ, CBR, ZIP',
  },
  comic: {
    label: 'Cómic',
    icon: FaMask,
    color: 'red',
    accentClass: 'border-red-500 bg-red-500/10',
    badgeClass: 'bg-red-500/20 text-red-400 border border-red-500/30',
    btnClass: 'bg-red-600 hover:bg-red-500',
    search: (q) => comicApi.search(q, 1, 8),
    getResults: (data) => data.data?.results || [],
    getId: (item) => String(item.comicvine_id || item.id),
    getTitle: (item) => item.title,
    getCover: (item) => item.cover_image || item.image,
    getSub: (item) => item.publisher || item.start_year || '',
    idLabel: 'ComicVine ID',
    idField: 'comicvine_id',
    detailPath: '/comics',
    accept: '.cbz,.cbr,.zip',
    acceptHint: 'CBZ, CBR, ZIP',
  },
  book: {
    label: 'Libro',
    icon: FaBookReader,
    color: 'green',
    accentClass: 'border-green-500 bg-green-500/10',
    badgeClass: 'bg-green-500/20 text-green-400 border border-green-500/30',
    btnClass: 'bg-green-600 hover:bg-green-500',
    search: (q) => bookApi.searchGoogleBooks(q, 1, 8),
    getResults: (data) => data.data?.results || [],
    getId: (item) => item.google_books_id || item.id,
    getTitle: (item) => item.title,
    getCover: (item) => item.thumbnail || item.cover_image,
    getSub: (item) => item.authors?.[0] || item.publisher || '',
    idLabel: 'Google Books ID',
    idField: 'google_books_id',
    detailPath: '/books',
    accept: '.epub,.pdf',
    acceptHint: 'EPUB, PDF',
  },
};

// ─── Step indicator ────────────────────────────────────────────────────────
const Steps = ({ current }) => (
  <div className="flex items-center gap-2 mb-8">
    {['Tipo', 'Buscar', 'Subir'].map((label, i) => {
      const step = i + 1;
      const done = step < current;
      const active = step === current;
      return (
        <div key={step} className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
            done ? 'bg-primary border-primary text-white' :
            active ? 'border-primary text-primary' :
            'border-gray-600 text-gray-600'
          }`}>
            {done ? <FaCheck className="text-[10px]" /> : step}
          </div>
          <span className={`text-sm ${active ? 'text-white' : done ? 'text-primary' : 'text-gray-600'}`}>
            {label}
          </span>
          {i < 2 && <div className="w-8 h-px bg-gray-700 mx-1" />}
        </div>
      );
    })}
  </div>
);

// ─── Main Component ────────────────────────────────────────────────────────
const Upload = () => {
  const navigate = useNavigate();

  // Step 1 state
  const [step, setStep] = useState(1);
  const [selectedType, setSelectedType] = useState(null);

  // Step 2 state
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);
  const searchTimer = useRef(null);

  // Step 3 state
  const [file, setFile] = useState(null);
  const [itemNumber, setItemNumber] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadResult, setUploadResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  const fileInputRef = useRef(null);
  const cfg = selectedType ? TYPE_CONFIG[selectedType] : null;

  // ── Step 1: select type ──────────────────────────────────────────────────
  const handleSelectType = (type) => {
    setSelectedType(type);
    setStep(2);
  };

  // ── Step 2: search ───────────────────────────────────────────────────────
  const handleQueryChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    clearTimeout(searchTimer.current);
    if (val.trim().length < 2) { setSearchResults([]); return; }
    searchTimer.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await cfg.search(val.trim());
        setSearchResults(cfg.getResults(res));
      } catch {
        toast.error('Error buscando');
      } finally {
        setSearching(false);
      }
    }, 400);
  };

  const handleSelectItem = (item) => {
    setSelectedItem(item);
    setSearchResults([]);
    setQuery(cfg.getTitle(item));
    setStep(3);
  };

  // ── Step 3: file upload ──────────────────────────────────────────────────
  const handleFileChange = (f) => {
    if (!f) return;
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    const allowed = cfg.accept.split(',');
    if (!allowed.includes(ext)) {
      toast.error(`Tipo no permitido. Usa: ${cfg.acceptHint}`);
      return;
    }
    setFile(f);
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFileChange(f);
  }, [cfg]);

  const handleSubmit = async () => {
    if (!file || !selectedItem || !selectedType) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('content_type', selectedType);
    formData.append('external_id', cfg.getId(selectedItem));
    if (itemNumber.trim()) formData.append('item_number', itemNumber.trim());

    setUploading(true);
    setUploadProgress(0);
    try {
      const res = await uploadApi.upload(formData, (progressEvent) => {
        if (progressEvent.total) {
          setUploadProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100));
        }
      });
      setUploadResult(res.data);
      toast.success(`"${res.data.item_title}" subido correctamente`);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Error al subir el archivo';
      toast.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setStep(1);
    setSelectedType(null);
    setSelectedItem(null);
    setQuery('');
    setSearchResults([]);
    setFile(null);
    setItemNumber('');
    setUploadProgress(0);
    setUploadResult(null);
  };

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="container mx-auto px-4 py-8 max-w-2xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <FaUpload className="text-primary text-2xl" />
        <div>
          <h1 className="text-2xl font-bold">Subir archivo</h1>
          <p className="text-gray-400 text-sm">Añade un CBZ, EPUB o PDF a tu biblioteca</p>
        </div>
      </div>

      <Steps current={step} />

      {/* ── STEP 1: Type selection ── */}
      {step === 1 && (
        <div className="grid grid-cols-3 gap-4">
          {Object.entries(TYPE_CONFIG).map(([type, c]) => {
            const Icon = c.icon;
            return (
              <button
                key={type}
                onClick={() => handleSelectType(type)}
                className={`flex flex-col items-center gap-3 p-6 rounded-xl border-2 border-gray-700 hover:${c.accentClass} transition-all hover:scale-105`}
              >
                <Icon className="text-4xl text-gray-400" />
                <span className="font-semibold">{c.label}</span>
                <span className="text-xs text-gray-500">{c.acceptHint}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* ── STEP 2: Search ── */}
      {step === 2 && cfg && (
        <div>
          <button
            onClick={() => { setStep(1); setSelectedType(null); setQuery(''); setSearchResults([]); }}
            className="flex items-center gap-1.5 text-gray-400 hover:text-white mb-4 text-sm"
          >
            <FaArrowLeft className="text-xs" /> Cambiar tipo
          </button>

          <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm mb-4 ${cfg.badgeClass}`}>
            <cfg.icon className="text-xs" /> {cfg.label}
          </div>

          <div className="relative">
            <div className="relative">
              <FaSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm" />
              <input
                type="text"
                value={query}
                onChange={handleQueryChange}
                placeholder={`Buscar ${cfg.label.toLowerCase()}...`}
                className="w-full pl-9 pr-4 py-3 bg-dark-card border border-gray-700 rounded-lg focus:outline-none focus:border-primary text-sm"
                autoFocus
              />
              {searching && <FaSpinner className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 animate-spin" />}
            </div>

            {/* Results dropdown */}
            {searchResults.length > 0 && (
              <div className="absolute top-full mt-1 left-0 right-0 bg-dark-card border border-gray-700 rounded-lg shadow-xl z-50 max-h-72 overflow-y-auto">
                {searchResults.map((item, i) => (
                  <button
                    key={i}
                    onClick={() => handleSelectItem(item)}
                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-dark-lighter transition-colors text-left"
                  >
                    {cfg.getCover(item) ? (
                      <img src={cfg.getCover(item)} alt="" className="w-9 h-12 object-cover rounded flex-shrink-0" />
                    ) : (
                      <div className="w-9 h-12 bg-dark-lighter rounded flex-shrink-0 flex items-center justify-center">
                        <cfg.icon className="text-gray-600" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{cfg.getTitle(item)}</p>
                      {cfg.getSub(item) && (
                        <p className="text-xs text-gray-500 truncate">{cfg.getSub(item)}</p>
                      )}
                    </div>
                    <FaCheck className="text-xs text-gray-600 flex-shrink-0" />
                  </button>
                ))}
              </div>
            )}
          </div>

          {query.trim().length < 2 && (
            <p className="text-gray-500 text-sm mt-3">Escribe al menos 2 caracteres para buscar</p>
          )}
        </div>
      )}

      {/* ── STEP 3: File upload ── */}
      {step === 3 && cfg && selectedItem && !uploadResult && (
        <div>
          <button
            onClick={() => { setStep(2); setSelectedItem(null); setQuery(''); setFile(null); }}
            className="flex items-center gap-1.5 text-gray-400 hover:text-white mb-4 text-sm"
          >
            <FaArrowLeft className="text-xs" /> Cambiar selección
          </button>

          {/* Selected item card */}
          <div className="flex items-center gap-3 p-3 bg-dark-card border border-gray-700 rounded-lg mb-6">
            {cfg.getCover(selectedItem) ? (
              <img src={cfg.getCover(selectedItem)} alt="" className="w-12 h-16 object-cover rounded flex-shrink-0" />
            ) : (
              <div className="w-12 h-16 bg-dark-lighter rounded flex-shrink-0 flex items-center justify-center">
                <cfg.icon className="text-gray-600 text-xl" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="font-semibold truncate">{cfg.getTitle(selectedItem)}</p>
              {cfg.getSub(selectedItem) && (
                <p className="text-xs text-gray-500">{cfg.getSub(selectedItem)}</p>
              )}
              <span className={`inline-block mt-1 text-[10px] px-2 py-0.5 rounded-full ${cfg.badgeClass}`}>
                {cfg.label}
              </span>
            </div>
          </div>

          {/* Drag & drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center gap-3 cursor-pointer transition-all ${
              dragOver ? 'border-primary bg-primary/10' :
              file ? 'border-green-500 bg-green-500/10' :
              'border-gray-600 hover:border-gray-400'
            }`}
          >
            {file ? (
              <>
                <FaFileAlt className="text-4xl text-green-400" />
                <p className="font-medium text-green-400">{file.name}</p>
                <p className="text-xs text-gray-500">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                <button
                  onClick={(e) => { e.stopPropagation(); setFile(null); }}
                  className="text-xs text-gray-500 hover:text-red-400 flex items-center gap-1"
                >
                  <FaTimes className="text-[9px]" /> Quitar
                </button>
              </>
            ) : (
              <>
                <FaUpload className="text-4xl text-gray-500" />
                <p className="text-gray-400 font-medium">Arrastra un archivo aquí</p>
                <p className="text-xs text-gray-600">o haz clic para seleccionar</p>
                <p className="text-xs text-gray-600">{cfg.acceptHint}</p>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept={cfg.accept}
              className="hidden"
              onChange={(e) => handleFileChange(e.target.files[0])}
            />
          </div>

          {/* Optional number field */}
          <div className="mt-4">
            <label className="block text-sm text-gray-400 mb-1">
              Número de tomo / capítulo <span className="text-gray-600">(opcional)</span>
            </label>
            <input
              type="text"
              value={itemNumber}
              onChange={(e) => setItemNumber(e.target.value)}
              placeholder="Ej: 1, 2, 2.5"
              className="w-full px-3 py-2 bg-dark-card border border-gray-700 rounded-lg focus:outline-none focus:border-primary text-sm"
            />
          </div>

          {/* Upload button */}
          <button
            onClick={handleSubmit}
            disabled={!file || uploading}
            className={`w-full mt-5 py-3 rounded-lg font-semibold flex items-center justify-center gap-2 transition-all ${
              !file || uploading
                ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                : `${cfg.btnClass} text-white`
            }`}
          >
            {uploading ? (
              <>
                <FaSpinner className="animate-spin" />
                Subiendo... {uploadProgress}%
              </>
            ) : (
              <>
                <FaUpload />
                Subir archivo
              </>
            )}
          </button>

          {/* Progress bar */}
          {uploading && (
            <div className="mt-3 w-full bg-dark-lighter rounded-full h-2">
              <div
                className="bg-primary h-2 rounded-full transition-all"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          )}
        </div>
      )}

      {/* ── SUCCESS ── */}
      {uploadResult && (
        <div className="text-center py-8">
          <div className="w-16 h-16 rounded-full bg-green-500/20 border border-green-500/40 flex items-center justify-center mx-auto mb-4">
            <FaCheck className="text-green-400 text-2xl" />
          </div>
          <h2 className="text-xl font-bold mb-1">¡Subido correctamente!</h2>
          <p className="text-gray-400 text-sm mb-6">
            "{uploadResult.item_title}" ha sido añadido a tu biblioteca.
            El archivo será convertido automáticamente.
          </p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={() => navigate(`${cfg.detailPath}/${uploadResult.item_id}`)}
              className={`px-4 py-2 rounded-lg text-white text-sm font-medium ${cfg.btnClass}`}
            >
              Ver en biblioteca
            </button>
            <button
              onClick={handleReset}
              className="px-4 py-2 rounded-lg bg-dark-card border border-gray-700 text-gray-300 text-sm hover:bg-dark-lighter"
            >
              Subir otro
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Upload;
