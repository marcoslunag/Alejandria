import { useEffect, useState } from 'react';
import { mangaApi } from '../services/api';
import {
  FaCog,
  FaServer,
  FaDatabase,
  FaCheckCircle,
  FaExclamationCircle,
  FaBook,
  FaEnvelope,
  FaTabletAlt,
  FaKey,
  FaQuestionCircle,
  FaSpinner,
  FaExternalLinkAlt,
  FaSave,
  FaCheck,
  FaTimes,
  FaBookReader,
  FaAmazon
} from 'react-icons/fa';

const Settings = () => {
  const [systemStatus, setSystemStatus] = useState(null);
  const [libraryStats, setLibraryStats] = useState(null);
  const [loading, setLoading] = useState(true);

  // Settings state
  const [settings, setSettings] = useState({
    kindle_email: '',
    smtp_server: 'smtp.gmail.com',
    smtp_port: 587,
    smtp_user: '',
    smtp_password: '',
    smtp_from_email: '',
    auto_send_to_kindle: false,
    amazon_email: '',
    amazon_password: '',
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
  const [testStatus, setTestStatus] = useState(null);
  const [testMessage, setTestMessage] = useState('');
  const [showGuide, setShowGuide] = useState(false);

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
          ...settingsRes.data,
          smtp_password: ''
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
      const dataToSave = { ...settings };
      if (!dataToSave.smtp_password) {
        delete dataToSave.smtp_password;
      }
      if (!dataToSave.amazon_password) {
        delete dataToSave.amazon_password;
      }
      await mangaApi.saveSettings(dataToSave);
      setSaveStatus('success');
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (error) {
      console.error('Error guardando configuración:', error);
      setSaveStatus('error');
      setTimeout(() => setSaveStatus(null), 3000);
    }
  };

  const handleTestSmtp = async () => {
    try {
      setTestStatus('testing');
      setTestMessage('');
      const response = await mangaApi.testSmtp();
      setTestStatus('success');
      setTestMessage(response.data.message || 'Conexión exitosa');
      setTimeout(() => {
        setTestStatus(null);
        setTestMessage('');
      }, 5000);
    } catch (error) {
      setTestStatus('error');
      setTestMessage(error.response?.data?.detail || 'Error de conexión');
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
      setStkMessage({ type: 'success', text: 'Autorizacion exitosa! Ya puedes enviar archivos grandes a Kindle.' });
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
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Email del Kindle
                </label>
                <input
                  type="email"
                  value={settings.kindle_email}
                  onChange={(e) => handleInputChange('kindle_email', e.target.value)}
                  placeholder="tu_usuario@kindle.com"
                  className="w-full px-4 py-3 bg-white rounded-lg border border-gray-700 focus:border-primary focus:outline-none text-gray-900"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Encuentra tu email de Kindle en Amazon → Gestionar contenido y dispositivos → Preferencias → Configuración de documentos personales
                </p>
              </div>

              {/* Selector de modelo Kindle */}
              <div className="mt-6">
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

          {/* Configuración SMTP / Gmail */}
          <section>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <FaEnvelope className="text-red-500" />
              Configuración de Email (Gmail)
            </h2>
            <div className="card p-6 space-y-4">
              <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 mb-4">
                <p className="text-sm text-yellow-300">
                  <strong>Nota:</strong> El envío por email tiene un límite de 25MB por archivo.
                  Para archivos de manga más grandes, usa <strong>Calibre-Web</strong> (ver abajo).
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Email de Gmail
                  </label>
                  <input
                    type="email"
                    value={settings.smtp_user}
                    onChange={(e) => {
                      handleInputChange('smtp_user', e.target.value);
                      handleInputChange('smtp_from_email', e.target.value);
                    }}
                    placeholder="tu_email@gmail.com"
                    className="w-full px-4 py-3 bg-white rounded-lg border border-gray-700 focus:border-primary focus:outline-none text-gray-900"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2 flex items-center gap-2">
                    App Password
                    <button
                      onClick={() => setShowGuide(!showGuide)}
                      className="text-primary hover:text-primary-light"
                      title="¿Cómo obtener App Password?"
                    >
                      <FaQuestionCircle />
                    </button>
                  </label>
                  <input
                    type="password"
                    value={settings.smtp_password}
                    onChange={(e) => handleInputChange('smtp_password', e.target.value)}
                    placeholder="••••••••••••••••"
                    className="w-full px-4 py-3 bg-white rounded-lg border border-gray-700 focus:border-primary focus:outline-none text-gray-900"
                  />
                </div>
              </div>

              {/* Guía de App Password */}
              {showGuide && (
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mt-4">
                  <h3 className="font-bold text-blue-400 mb-3 flex items-center gap-2">
                    <FaKey />
                    Cómo obtener App Password de Gmail
                  </h3>
                  <ol className="list-decimal list-inside space-y-2 text-gray-300 text-sm">
                    <li>
                      Ve a{' '}
                      <a
                        href="https://myaccount.google.com/security"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline inline-flex items-center gap-1"
                      >
                        myaccount.google.com/security
                        <FaExternalLinkAlt className="text-xs" />
                      </a>
                    </li>
                    <li>
                      En <strong>"Cómo inicias sesión en Google"</strong>, activa la{' '}
                      <strong>Verificación en 2 pasos</strong> si aún no está activa
                    </li>
                    <li>
                      Después de activarla, busca{' '}
                      <a
                        href="https://myaccount.google.com/apppasswords"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline inline-flex items-center gap-1"
                      >
                        Contraseñas de aplicaciones
                        <FaExternalLinkAlt className="text-xs" />
                      </a>
                    </li>
                    <li>
                      Crea una nueva contraseña de aplicación con nombre <strong>"Alejandria"</strong>
                    </li>
                    <li>
                      Copia la contraseña de <strong>16 caracteres</strong> (sin espacios) y pégala arriba
                    </li>
                  </ol>
                  <div className="mt-3 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded text-xs text-yellow-300">
                    Esta contraseña es diferente a tu contraseña de Google. Guárdala en un lugar seguro.
                  </div>
                </div>
              )}

              {/* Botón de probar conexión */}
              <div className="flex flex-wrap gap-3 mt-4">
                <button
                  onClick={handleTestSmtp}
                  disabled={testStatus === 'testing' || !settings.smtp_user}
                  className="btn btn-secondary flex items-center gap-2"
                >
                  {testStatus === 'testing' ? (
                    <>
                      <FaSpinner className="animate-spin" />
                      Probando...
                    </>
                  ) : testStatus === 'success' ? (
                    <>
                      <FaCheck className="text-green-500" />
                      Conexión exitosa
                    </>
                  ) : testStatus === 'error' ? (
                    <>
                      <FaTimes className="text-red-500" />
                      Error
                    </>
                  ) : (
                    <>
                      <FaEnvelope />
                      Probar conexión SMTP
                    </>
                  )}
                </button>
              </div>

              {testMessage && (
                <p className={`text-sm mt-2 ${testStatus === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                  {testMessage}
                </p>
              )}
            </div>
          </section>

          {/* Amazon Send to Kindle (STK - OAuth2) */}
          <section>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <FaAmazon className="text-orange-400" />
              Amazon Send to Kindle (Archivos grandes)
            </h2>
            <div className="card p-6 space-y-4">
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 mb-4">
                <p className="text-sm text-green-300">
                  <strong>Recomendado para manga grande.</strong> Soporta archivos hasta 200MB.
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

          {/* Calibre-Web para archivos grandes */}
          <section>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
              <FaBookReader className="text-blue-500" />
              Calibre-Web (Alternativa manual)
            </h2>
            <div className="card p-6">
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mb-4">
                <p className="text-sm text-blue-300">
                  <strong>Recomendado para manga.</strong> Los archivos de manga suelen ser muy grandes (100-400MB).
                  Calibre-Web te permite descargar los EPUB directamente y enviarlos a tu Kindle.
                </p>
              </div>

              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-surface-light rounded-lg">
                  <div>
                    <h3 className="font-bold">Calibre-Web</h3>
                    <p className="text-sm text-gray-400">Accede a tu biblioteca de manga convertido</p>
                  </div>
                  <a
                    href="http://localhost:8383"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-primary flex items-center gap-2"
                  >
                    Abrir Calibre-Web
                    <FaExternalLinkAlt />
                  </a>
                </div>

                <div className="text-sm text-gray-400 space-y-2">
                  <p><strong>Cómo usar:</strong></p>
                  <ol className="list-decimal list-inside space-y-1">
                    <li>Abre Calibre-Web en <code className="bg-surface-light px-1 rounded">localhost:8383</code></li>
                    <li>Configura tu cuenta la primera vez (usuario: <strong>admin</strong>, password: <strong>admin123</strong>)</li>
                    <li>Ve a Admin → Email Server y configura el SMTP igual que arriba</li>
                    <li>Ve a Admin → Kindle Email y añade tu email de Kindle</li>
                    <li>Los manga convertidos aparecerán automáticamente en la biblioteca</li>
                    <li>Desde cada libro puedes enviarlo directamente a tu Kindle</li>
                  </ol>
                </div>
              </div>
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
                      Guardar toda la configuración
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
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
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

                {/* Email Kindle */}
                <div className="flex items-center gap-4">
                  <div className={`p-3 rounded-full ${settings.kindle_email ? 'bg-green-500/20' : 'bg-yellow-500/20'}`}>
                    {settings.kindle_email ? (
                      <FaCheckCircle className="text-green-500 text-xl" />
                    ) : (
                      <FaExclamationCircle className="text-yellow-500 text-xl" />
                    )}
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Email Kindle</p>
                    <p className="font-bold">{settings.kindle_email ? 'Configurado' : 'No configurado'}</p>
                    {settings.kindle_email && (
                      <p className="text-xs text-gray-500 truncate max-w-[150px]">{settings.kindle_email}</p>
                    )}
                  </div>
                </div>

                {/* SMTP/Gmail */}
                <div className="flex items-center gap-4">
                  <div className={`p-3 rounded-full ${settings.smtp_user && settings.smtp_password ? 'bg-green-500/20' : 'bg-gray-500/20'}`}>
                    {settings.smtp_user && settings.smtp_password ? (
                      <FaCheckCircle className="text-green-500 text-xl" />
                    ) : (
                      <FaExclamationCircle className="text-gray-500 text-xl" />
                    )}
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Email (SMTP)</p>
                    <p className="font-bold">{settings.smtp_user ? 'Configurado' : 'No configurado'}</p>
                    {settings.smtp_user && (
                      <p className="text-xs text-gray-500">Limite: 25MB</p>
                    )}
                  </div>
                </div>

                {/* Estado General */}
                <div className="flex items-center gap-4">
                  <div className={`p-3 rounded-full ${stkStatus.authenticated && settings.kindle_email ? 'bg-green-500/20' : 'bg-yellow-500/20'}`}>
                    {stkStatus.authenticated && settings.kindle_email ? (
                      <FaCheckCircle className="text-green-500 text-xl" />
                    ) : (
                      <FaExclamationCircle className="text-yellow-500 text-xl" />
                    )}
                  </div>
                  <div>
                    <p className="text-gray-400 text-sm">Envio a Kindle</p>
                    <p className="font-bold">
                      {stkStatus.authenticated && settings.kindle_email
                        ? 'Listo'
                        : stkStatus.authenticated
                        ? 'Falta email Kindle'
                        : 'Falta Amazon STK'}
                    </p>
                    {stkStatus.authenticated && (
                      <p className="text-xs text-gray-500">Hasta 200MB/archivo</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Mensaje de estado */}
              {!stkStatus.authenticated && (
                <div className="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                  <p className="text-sm text-yellow-300">
                    <strong>Importante:</strong> Para enviar archivos grandes de manga (hasta 200MB),
                    necesitas conectar tu cuenta de Amazon en la seccion "Amazon Send to Kindle" de arriba.
                  </p>
                </div>
              )}

              {stkStatus.authenticated && !settings.kindle_email && (
                <div className="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                  <p className="text-sm text-yellow-300">
                    <strong>Falta:</strong> Introduce tu email de Kindle (@kindle.com) en la seccion de arriba
                    para poder recibir los manga en tu dispositivo.
                  </p>
                </div>
              )}

              {stkStatus.authenticated && settings.kindle_email && (
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

          {/* Información adicional */}
          <section>
            <div className="card p-6 bg-surface-light/50">
              <h3 className="font-bold mb-2 flex items-center gap-2">
                <FaTabletAlt className="text-orange-500" />
                Información importante sobre Kindle
              </h3>
              <ul className="text-sm text-gray-400 space-y-1 list-disc list-inside">
                <li>El email de envío (Gmail) debe estar en la lista de emails aprobados de tu Kindle</li>
                <li>Ve a Amazon → Gestionar contenido → Preferencias → Configuración de documentos personales</li>
                <li>Añade tu email de Gmail a "Lista de email de envío a Kindle aprobados"</li>
                <li>Los archivos EPUB se envían directamente. Amazon los convierte automáticamente</li>
                <li>Para archivos grandes (+25MB), usa Calibre-Web o transfiere por USB</li>
              </ul>
            </div>
          </section>

          {/* Espacio extra para el botón sticky */}
          <div className="h-20"></div>
        </div>
      )}
    </div>
  );
};

export default Settings;
