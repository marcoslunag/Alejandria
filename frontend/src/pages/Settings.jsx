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
  FaAmazon
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
    stk_device_name: null
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
      const [statusRes, statsRes, settingsRes, stkRes] = await Promise.all([
        mangaApi.getSystemStatus().catch(() => null),
        mangaApi.getLibraryStats().catch(() => null),
        mangaApi.getSettings().catch(() => null),
        mangaApi.stkGetStatus().catch(() => null)
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
