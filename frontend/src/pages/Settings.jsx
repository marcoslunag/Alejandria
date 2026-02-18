import { useEffect, useState } from 'react';
import { mangaApi } from '../services/api';
import {
  FaCog,
  FaServer,
  FaDatabase,
  FaCheckCircle,
  FaExclamationCircle,
  FaBook,
  FaTabletAlt,
  FaSpinner,
  FaExternalLinkAlt,
  FaSave,
  FaCheck,
  FaTimes,
  FaAmazon,
  FaDownload,
  FaFilter,
  FaInbox,
  FaSync,
  FaRedo,
  FaCheckSquare,
  FaTimesCircle
} from 'react-icons/fa';

const Settings = () => {
  const [systemStatus, setSystemStatus] = useState(null);
  const [libraryStats, setLibraryStats] = useState(null);
  const [loading, setLoading] = useState(true);

  // Settings state
  const [settings, setSettings] = useState({
    auto_send_to_kindle: false,
    kcc_profile: 'KPW5',
    stk_device_serial: null,
    stk_device_name: null,
    preferred_quality: 'hq',
    preferred_format: 'auto',
    max_file_size_mb: 0,
    preferred_hosts: '[]',
  });

  // Kindle device profiles for KCC
  const kindleProfiles = [
    { value: 'KPW5', label: 'Kindle Paperwhite 5 / Signature', resolution: '1236 x 1648' },
    { value: 'KO', label: 'Kindle Oasis 2/3 / Paperwhite 12', resolution: '1264 x 1680' },
    { value: 'KS', label: 'Kindle Scribe 1/2', resolution: '1860 x 2480' },
    { value: 'KCS', label: 'Kindle Colorsoft', resolution: '1264 x 1680' },
    { value: 'K11', label: 'Kindle 11 (2022)', resolution: '1072 x 1448' },
    { value: 'KV', label: 'Kindle Voyage', resolution: '1072 x 1448' },
    { value: 'KPW34', label: 'Kindle Paperwhite 3/4', resolution: '1072 x 1448' },
    { value: 'KPW', label: 'Kindle Paperwhite 1/2', resolution: '758 x 1024' },
    { value: 'K810', label: 'Kindle 8/10', resolution: '600 x 800' },
    { value: 'K57', label: 'Kindle 5/7', resolution: '600 x 800' },
  ];
  const [saveStatus, setSaveStatus] = useState(null);

  // Import folder state (Feature 5)
  const [importStatus, setImportStatus] = useState(null);
  const [importProcessing, setImportProcessing] = useState(false);

  // STK (Send to Kindle) OAuth state
  const [stkStatus, setStkStatus] = useState({ authenticated: false, devices: [] });
  const [stkSigninUrl, setStkSigninUrl] = useState('');
  const [stkRedirectUrl, setStkRedirectUrl] = useState('');
  const [stkLoading, setStkLoading] = useState(false);
  const [stkMessage, setStkMessage] = useState({ type: '', text: '' });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [statusRes, statsRes, settingsRes, stkRes, importRes] = await Promise.all([
        mangaApi.getSystemStatus().catch(() => null),
        mangaApi.getLibraryStats().catch(() => null),
        mangaApi.getSettings().catch(() => null),
        mangaApi.stkGetStatus().catch(() => null),
        mangaApi.getImportStatus().catch(() => null),
      ]);
      if (statusRes) setSystemStatus(statusRes.data);
      if (statsRes) setLibraryStats(statsRes.data);
      if (settingsRes?.data) {
        setSettings(prev => ({
          ...prev,
          ...settingsRes.data
        }));
      }
      if (stkRes?.data) {
        setStkStatus(stkRes.data);
      }
      if (importRes?.data) {
        setImportStatus(importRes.data);
      }
    } catch (error) {
      console.error('Error cargando datos:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveSettings = async () => {
    try {
      setSaveStatus('saving');
      await mangaApi.saveSettings(settings);
      setSaveStatus('success');
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (error) {
      console.error('Error guardando configuración:', error);
      setSaveStatus('error');
      setTimeout(() => setSaveStatus(null), 3000);
    }
  };

  // STK (Send to Kindle) handlers
  const handleStkGetSigninUrl = async () => {
    try {
      setStkLoading(true);
      setStkMessage({ type: '', text: '' });
      const response = await mangaApi.stkGetSigninUrl();
      setStkSigninUrl(response.data.signin_url);
      setStkMessage({ type: 'info', text: 'Abre el enlace de arriba en tu navegador y autoriza la aplicacion' });
    } catch (error) {
      setStkMessage({ type: 'error', text: error.response?.data?.detail || 'Error obteniendo URL' });
    } finally {
      setStkLoading(false);
    }
  };

  const handleStkAuthorize = async () => {
    if (!stkRedirectUrl) {
      setStkMessage({ type: 'error', text: 'Pega la URL de redireccion del navegador' });
      return;
    }
    try {
      setStkLoading(true);
      setStkMessage({ type: '', text: '' });
      const response = await mangaApi.stkAuthorize(stkRedirectUrl);
      setStkStatus({ authenticated: true, devices: response.data.devices || [] });
      setStkSigninUrl('');
      setStkRedirectUrl('');
      setStkMessage({ type: 'success', text: 'Autorizacion exitosa! Ya puedes enviar archivos a Kindle.' });
    } catch (error) {
      setStkMessage({ type: 'error', text: error.response?.data?.detail || 'Error de autorizacion' });
    } finally {
      setStkLoading(false);
    }
  };

  const handleStkLogout = async () => {
    try {
      await mangaApi.stkLogout();
      setStkStatus({ authenticated: false, devices: [] });
      setStkMessage({ type: 'info', text: 'Sesion cerrada' });
    } catch (error) {
      console.error('Error logout STK:', error);
    }
  };

  const handleInputChange = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold flex items-center gap-3">
          <FaCog className="text-primary" />
          Ajustes
        </h1>
        <p className="text-gray-400 mt-2">
          Configuración del sistema y envío a Kindle
        </p>
      </div>

      {loading ? (
        <div className="text-center py-20">
          <div className="spinner border-4 border-primary border-t-transparent rounded-full w-12 h-12 mx-auto mb-4 animate-spin" />
          <p className="text-gray-400">Cargando información...</p>
        </div>
      ) : (
        <div className="space-y-8">
          {/* Configuración de Kindle */}
          <section>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <FaTabletAlt className="text-orange-500" />
              Configuración de Kindle
            </h2>
            <div className="card p-6">
              {/* Selector de modelo Kindle */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Modelo de Kindle (para optimización)
                </label>
                <select
                  value={settings.kcc_profile || 'KPW5'}
                  onChange={(e) => handleInputChange('kcc_profile', e.target.value)}
                  className="w-full px-4 py-3 bg-white rounded-lg border border-gray-700 focus:border-primary focus:outline-none text-gray-900"
                >
                  {kindleProfiles.map((profile) => (
                    <option key={profile.value} value={profile.value}>
                      {profile.label} ({profile.resolution})
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  Selecciona tu modelo de Kindle para optimizar la conversión de manga.
                  KCC ajustará la resolución y calidad de imagen según tu dispositivo.
                </p>
              </div>

              <div className="flex items-center gap-3 mt-4">
                <input
                  type="checkbox"
                  id="autoSend"
                  checked={settings.auto_send_to_kindle}
                  onChange={(e) => handleInputChange('auto_send_to_kindle', e.target.checked)}
                  className="w-5 h-5 rounded bg-surface-light border-gray-700 text-primary focus:ring-primary"
                />
                <label htmlFor="autoSend" className="text-gray-300">
                  Enviar automáticamente a Kindle después de convertir
                </label>
              </div>
            </div>
          </section>

          {/* Preferencias de Descarga */}
          <section>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <FaDownload className="text-blue-500" />
              Preferencias de Descarga
            </h2>
            <div className="card p-6 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Calidad preferida */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Calidad preferida
                  </label>
                  <select
                    value={settings.preferred_quality || 'hq'}
                    onChange={(e) => handleInputChange('preferred_quality', e.target.value)}
                    className="w-full px-4 py-3 bg-white rounded-lg border border-gray-700 focus:border-primary focus:outline-none text-gray-900"
                  >
                    <option value="hq">Alta calidad (HQ)</option>
                    <option value="lq">Baja calidad (LQ, archivos más pequeños)</option>
                    <option value="any">Cualquiera</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    Prioriza fuentes de alta o baja calidad según tu preferencia.
                  </p>
                </div>

                {/* Formato preferido */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Formato preferido
                  </label>
                  <select
                    value={settings.preferred_format || 'auto'}
                    onChange={(e) => handleInputChange('preferred_format', e.target.value)}
                    className="w-full px-4 py-3 bg-white rounded-lg border border-gray-700 focus:border-primary focus:outline-none text-gray-900"
                  >
                    <option value="auto">Auto-detectar</option>
                    <option value="epub">EPUB nativo</option>
                    <option value="cbz">CBZ/CBR (cómic)</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    Formato preferido para descargas. "Auto" deja que el sistema decida.
                  </p>
                </div>
              </div>

              {/* Tamaño máximo */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Tamaño máximo por archivo (MB) — 0 = sin límite
                </label>
                <input
                  type="number"
                  min="0"
                  value={settings.max_file_size_mb || 0}
                  onChange={(e) => handleInputChange('max_file_size_mb', parseInt(e.target.value) || 0)}
                  className="w-full md:w-48 px-4 py-3 bg-white rounded-lg border border-gray-700 focus:border-primary focus:outline-none text-gray-900"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Filtra fuentes por tamaño. Útil si tienes espacio limitado en el Kindle.
                </p>
              </div>

              {/* Hosts preferidos */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3 flex items-center gap-2">
                  <FaFilter className="text-blue-400" />
                  Hosts de descarga preferidos
                </label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {[
                    { id: 'mediafire', label: 'MediaFire', color: 'text-blue-400' },
                    { id: 'mega', label: 'MEGA', color: 'text-red-400' },
                    { id: 'google_drive', label: 'Google Drive', color: 'text-green-400' },
                    { id: 'fireload', label: 'Fireload', color: 'text-orange-400' },
                    { id: '1fichier', label: '1fichier', color: 'text-purple-400' },
                    { id: 'dropbox', label: 'Dropbox', color: 'text-sky-400' },
                  ].map(({ id, label, color }) => {
                    let hosts = [];
                    try { hosts = JSON.parse(settings.preferred_hosts || '[]'); } catch {}
                    const checked = hosts.includes(id);
                    return (
                      <label
                        key={id}
                        className={`flex items-center gap-2 p-3 rounded-lg cursor-pointer transition-colors ${
                          checked ? 'bg-primary/10 border border-primary/30' : 'bg-surface-light hover:bg-surface-lighter border border-transparent'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            let current = [];
                            try { current = JSON.parse(settings.preferred_hosts || '[]'); } catch {}
                            const updated = checked ? current.filter(h => h !== id) : [...current, id];
                            handleInputChange('preferred_hosts', JSON.stringify(updated));
                          }}
                          className="w-4 h-4 text-primary rounded"
                        />
                        <span className={`text-sm font-medium ${color}`}>{label}</span>
                        {checked && <FaCheck className="ml-auto text-primary text-xs" />}
                      </label>
                    );
                  })}
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  Si marcas hosts, el sistema los priorizará al elegir el enlace de descarga. Si ninguno está disponible, usará el mejor disponible automáticamente.
                </p>
              </div>
            </div>
          </section>

          {/* Amazon Send to Kindle (STK - OAuth2) */}
          <section>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <FaAmazon className="text-orange-400" />
              Amazon Send to Kindle
            </h2>
            <div className="card p-6 space-y-4">
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 mb-4">
                <p className="text-sm text-green-300">
                  <strong>Método recomendado.</strong> Soporta archivos hasta 200MB.
                  Usa OAuth2 - solo necesitas autorizar una vez en tu navegador. Funciona con 2FA.
                </p>
              </div>

              {/* Estado de conexion */}
              <div className={`flex items-center gap-3 p-4 rounded-lg ${stkStatus.authenticated ? 'bg-green-500/10 border border-green-500/30' : 'bg-gray-500/10 border border-gray-500/30'}`}>
                <div className={`p-2 rounded-full ${stkStatus.authenticated ? 'bg-green-500/20' : 'bg-gray-500/20'}`}>
                  {stkStatus.authenticated ? (
                    <FaCheckCircle className="text-green-500 text-xl" />
                  ) : (
                    <FaExclamationCircle className="text-gray-500 text-xl" />
                  )}
                </div>
                <div className="flex-1">
                  <p className="font-bold">{stkStatus.authenticated ? 'Conectado a Amazon' : 'No conectado'}</p>
                  {stkStatus.authenticated && stkStatus.devices?.length > 0 && (
                    <p className="text-sm text-gray-400">
                      {stkStatus.devices.length} dispositivo(s) Kindle disponible(s)
                    </p>
                  )}
                </div>
                {stkStatus.authenticated && (
                  <button
                    onClick={handleStkLogout}
                    className="btn btn-secondary text-sm"
                  >
                    Desconectar
                  </button>
                )}
              </div>

              {/* Flujo de autorizacion */}
              {!stkStatus.authenticated && (
                <div className="space-y-4">
                  {!stkSigninUrl ? (
                    <button
                      onClick={handleStkGetSigninUrl}
                      disabled={stkLoading}
                      className="btn btn-primary flex items-center gap-2"
                    >
                      {stkLoading ? (
                        <FaSpinner className="animate-spin" />
                      ) : (
                        <FaAmazon />
                      )}
                      Conectar con Amazon
                    </button>
                  ) : (
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          Paso 1: Abre este enlace en tu navegador
                        </label>
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={stkSigninUrl}
                            readOnly
                            className="flex-1 px-4 py-2 bg-surface-light rounded-lg border border-gray-700 text-gray-300 text-sm"
                          />
                          <a
                            href={stkSigninUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn btn-primary flex items-center gap-2"
                          >
                            Abrir
                            <FaExternalLinkAlt />
                          </a>
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          Paso 2: Despues de autorizar, copia la URL completa del navegador y pegala aqui
                        </label>
                        <input
                          type="text"
                          value={stkRedirectUrl}
                          onChange={(e) => setStkRedirectUrl(e.target.value)}
                          placeholder="https://www.amazon.com/..."
                          className="w-full px-4 py-3 bg-white rounded-lg border border-gray-700 focus:border-primary focus:outline-none text-gray-900"
                        />
                      </div>

                      <button
                        onClick={handleStkAuthorize}
                        disabled={stkLoading || !stkRedirectUrl}
                        className="btn btn-primary flex items-center gap-2"
                      >
                        {stkLoading ? (
                          <FaSpinner className="animate-spin" />
                        ) : (
                          <FaCheck />
                        )}
                        Completar autorizacion
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Mensaje de estado */}
              {stkMessage.text && (
                <p className={`text-sm ${
                  stkMessage.type === 'success' ? 'text-green-400' :
                  stkMessage.type === 'error' ? 'text-red-400' :
                  'text-blue-400'
                }`}>
                  {stkMessage.text}
                </p>
              )}

              {/* Selector de dispositivo destino */}
              {stkStatus.authenticated && stkStatus.devices?.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-300 mb-2">Enviar a dispositivo:</h4>
                  <div className="space-y-2">
                    {/* Opción: Todos los dispositivos */}
                    <label className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                      !settings.stk_device_serial ? 'bg-orange-500/20 border border-orange-500/50' : 'bg-surface-light hover:bg-surface-lighter'
                    }`}>
                      <input
                        type="radio"
                        name="stk_device"
                        checked={!settings.stk_device_serial}
                        onChange={() => {
                          handleInputChange('stk_device_serial', null);
                          handleInputChange('stk_device_name', null);
                        }}
                        className="w-4 h-4 text-orange-500 focus:ring-orange-500"
                      />
                      <FaTabletAlt className="text-gray-400" />
                      <span className="text-gray-300">Todos los dispositivos ({stkStatus.devices.length})</span>
                    </label>

                    {/* Opciones: Dispositivos individuales */}
                    {stkStatus.devices.map((device, index) => (
                      <label
                        key={index}
                        className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                          settings.stk_device_serial === device.serial ? 'bg-orange-500/20 border border-orange-500/50' : 'bg-surface-light hover:bg-surface-lighter'
                        }`}
                      >
                        <input
                          type="radio"
                          name="stk_device"
                          checked={settings.stk_device_serial === device.serial}
                          onChange={() => {
                            handleInputChange('stk_device_serial', device.serial);
                            handleInputChange('stk_device_name', device.name || device.serial);
                          }}
                          className="w-4 h-4 text-orange-500 focus:ring-orange-500"
                        />
                        <FaTabletAlt className="text-orange-400" />
                        <span className="text-gray-300">{device.name || device.serial}</span>
                        {settings.stk_device_serial === device.serial && (
                          <span className="ml-auto text-xs bg-orange-500/30 text-orange-300 px-2 py-1 rounded">Seleccionado</span>
                        )}
                      </label>
                    ))}
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Selecciona a qué Kindle quieres enviar los manga. "Todos" enviará a todos tus dispositivos.
                  </p>
                </div>
              )}
            </div>
          </section>

          {/* BOTÓN GUARDAR - Al final de todas las configuraciones */}
          <section className="sticky bottom-4 z-10">
            <div className="card p-4 bg-dark-card/95 backdrop-blur border border-gray-700 shadow-lg">
              <div className="flex items-center justify-between">
                <p className="text-gray-400 text-sm">
                  Recuerda guardar los cambios antes de salir
                </p>
                <button
                  onClick={handleSaveSettings}
                  disabled={saveStatus === 'saving'}
                  className="btn btn-primary flex items-center gap-2 px-8 py-3"
                >
                  {saveStatus === 'saving' ? (
                    <>
                      <FaSpinner className="animate-spin" />
                      Guardando...
                    </>
                  ) : saveStatus === 'success' ? (
                    <>
                      <FaCheck />
                      Guardado correctamente
                    </>
                  ) : saveStatus === 'error' ? (
                    <>
                      <FaTimes />
                      Error al guardar
                    </>
                  ) : (
                    <>
                      <FaSave />
                      Guardar configuración
                    </>
                  )}
                </button>
              </div>
            </div>
          </section>

          {/* Estado de Kindle */}
          <section>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <FaTabletAlt className="text-orange-500" />
              Estado de Kindle
            </h2>
            <div className="card p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Amazon STK */}
                <div className="flex items-center gap-4">
                  <div className={`p-3 rounded-full ${stkStatus.authenticated ? 'bg-green-500/20' : 'bg-red-500/20'}`}>
                    {stkStatus.authenticated ? (
                      <FaCheckCircle className="text-green-500 text-xl" />
                    ) : (
                      <FaExclamationCircle className="text-red-500 text-xl" />
                    )}
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Amazon STK</p>
                    <p className="font-bold">{stkStatus.authenticated ? 'Conectado' : 'No conectado'}</p>
                    {stkStatus.authenticated && stkStatus.devices?.length > 0 && (
                      <p className="text-xs text-gray-500">{stkStatus.devices.length} dispositivo(s)</p>
                    )}
                  </div>
                </div>

                {/* Dispositivo seleccionado */}
                <div className="flex items-center gap-4">
                  <div className={`p-3 rounded-full ${settings.stk_device_serial ? 'bg-green-500/20' : 'bg-yellow-500/20'}`}>
                    {settings.stk_device_serial ? (
                      <FaCheckCircle className="text-green-500 text-xl" />
                    ) : (
                      <FaExclamationCircle className="text-yellow-500 text-xl" />
                    )}
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Dispositivo destino</p>
                    <p className="font-bold">
                      {settings.stk_device_name || (stkStatus.devices?.length > 0 ? 'Todos los dispositivos' : 'No configurado')}
                    </p>
                  </div>
                </div>
              </div>

              {/* Mensaje de estado */}
              {!stkStatus.authenticated && (
                <div className="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                  <p className="text-sm text-yellow-300">
                    <strong>Importante:</strong> Para enviar archivos de manga (hasta 200MB),
                    necesitas conectar tu cuenta de Amazon en la seccion "Amazon Send to Kindle" de arriba.
                  </p>
                </div>
              )}

              {stkStatus.authenticated && (
                <div className="mt-4 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                  <p className="text-sm text-green-300">
                    Todo listo para enviar manga a tu Kindle. Los archivos se dividiran automaticamente
                    si superan 180MB para cumplir el limite de Amazon.
                  </p>
                </div>
              )}
            </div>
          </section>

          {/* Bandeja de Entrada (/imports) */}
          <section>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <FaInbox className="text-yellow-500" />
              Bandeja de Entrada (/imports)
            </h2>
            <div className="card p-6 space-y-4">
              <p className="text-sm text-gray-400">
                Coloca archivos CBZ, CBR, EPUB o PDF en la carpeta <code className="bg-surface-light px-1 rounded">/imports</code> y el sistema los
                detectará automáticamente cada 5 minutos. Los archivos se moverán a <code className="bg-surface-light px-1 rounded">/imports/processed</code> si se procesan correctamente.
              </p>

              {/* Stats row */}
              {importStatus && (
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-yellow-400">{importStatus.pending_count}</p>
                    <p className="text-xs text-gray-400">Pendientes</p>
                  </div>
                  <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-green-400">{importStatus.processed_count}</p>
                    <p className="text-xs text-gray-400">Procesados</p>
                  </div>
                  <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-red-400">{importStatus.failed_count}</p>
                    <p className="text-xs text-gray-400">Fallidos</p>
                  </div>
                </div>
              )}

              {/* Pending files */}
              {importStatus?.pending?.length > 0 && (
                <div>
                  <p className="text-sm font-medium text-yellow-400 mb-2">En cola:</p>
                  <div className="space-y-1">
                    {importStatus.pending.map(f => (
                      <div key={f} className="flex items-center gap-2 text-sm text-gray-300 bg-surface-light rounded px-3 py-1.5">
                        <FaSpinner className="text-yellow-400 animate-spin text-xs" />
                        {f}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Failed files */}
              {importStatus?.failed?.length > 0 && (
                <div>
                  <p className="text-sm font-medium text-red-400 mb-2">Fallidos (sin coincidencia en biblioteca):</p>
                  <div className="space-y-1">
                    {importStatus.failed.map(f => (
                      <div key={f} className="flex items-center gap-2 text-sm text-gray-300 bg-surface-light rounded px-3 py-1.5">
                        <FaTimesCircle className="text-red-400 text-xs flex-shrink-0" />
                        <span className="flex-1 truncate">{f}</span>
                        <button
                          onClick={async () => {
                            await mangaApi.retryFailedImport(f).catch(() => {});
                            const res = await mangaApi.getImportStatus().catch(() => null);
                            if (res?.data) setImportStatus(res.data);
                          }}
                          className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 flex-shrink-0"
                        >
                          <FaRedo className="text-[10px]" /> Reintentar
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={async () => {
                    setImportProcessing(true);
                    try {
                      await mangaApi.triggerImportProcess();
                      const res = await mangaApi.getImportStatus().catch(() => null);
                      if (res?.data) setImportStatus(res.data);
                    } finally {
                      setImportProcessing(false);
                    }
                  }}
                  disabled={importProcessing}
                  className="btn btn-secondary flex items-center gap-2 text-sm"
                >
                  {importProcessing ? <FaSpinner className="animate-spin" /> : <FaSync />}
                  Procesar ahora
                </button>
                <button
                  onClick={async () => {
                    const res = await mangaApi.getImportStatus().catch(() => null);
                    if (res?.data) setImportStatus(res.data);
                  }}
                  className="btn btn-secondary flex items-center gap-2 text-sm"
                >
                  <FaSync />
                  Actualizar
                </button>
              </div>

              <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
                <p className="text-xs text-blue-300">
                  <strong>Formato del nombre:</strong> <code>Titulo #01.cbz</code> (cómic) ·
                  <code> Titulo Vol.01.cbz</code> (manga) ·
                  <code> Autor - Titulo.epub</code> (libro).
                  El título debe coincidir con una serie ya en tu biblioteca.
                </p>
              </div>
            </div>
          </section>

          {/* Estado del Sistema */}
          <section>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <FaServer />
              Estado del Sistema
            </h2>
            <div className="card p-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="flex items-center gap-4">
                  <div className={`p-3 rounded-full ${systemStatus ? 'bg-green-500/20' : 'bg-red-500/20'}`}>
                    {systemStatus ? (
                      <FaCheckCircle className="text-green-500 text-xl" />
                    ) : (
                      <FaExclamationCircle className="text-red-500 text-xl" />
                    )}
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Backend</p>
                    <p className="font-bold">{systemStatus ? 'Conectado' : 'Desconectado'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="p-3 rounded-full bg-blue-500/20">
                    <FaDatabase className="text-blue-500 text-xl" />
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Base de Datos</p>
                    <p className="font-bold">{systemStatus?.database || 'PostgreSQL'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="p-3 rounded-full bg-purple-500/20">
                    <FaCog className="text-purple-500 text-xl" />
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Version</p>
                    <p className="font-bold">{systemStatus?.version || '1.0.0'}</p>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Estadísticas de la Biblioteca */}
          {libraryStats && (
            <section>
              <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
                <FaBook />
                Biblioteca
              </h2>
              <div className="card p-6">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                  <div>
                    <p className="text-gray-400 text-sm">Total Manga</p>
                    <p className="text-3xl font-bold">{libraryStats.total_manga || 0}</p>
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Monitorizados</p>
                    <p className="text-3xl font-bold text-primary">{libraryStats.monitored_manga || 0}</p>
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Total Tomos</p>
                    <p className="text-3xl font-bold">{libraryStats.total_chapters || 0}</p>
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Descargados</p>
                    <p className="text-3xl font-bold text-green-500">{libraryStats.downloaded_chapters || 0}</p>
                  </div>
                </div>
              </div>
            </section>
          )}

          {/* Espacio extra para el botón sticky */}
          <div className="h-20"></div>
        </div>
      )}
    </div>
  );
};

export default Settings;
