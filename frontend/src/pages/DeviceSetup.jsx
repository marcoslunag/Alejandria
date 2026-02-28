import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaBook, FaTabletAlt, FaMobileAlt, FaQuestion, FaArrowRight } from 'react-icons/fa';
import { useAuth } from '../contexts/AuthContext';
import api from '../services/api';

const DEVICES = [
  {
    id: 'kindle',
    icon: <FaBook className="text-4xl text-orange-400" />,
    label: 'Kindle',
    description: 'Amazon Kindle Paperwhite, Oasis, Scribe…',
    features: ['Envío automático vía Send to Kindle', 'Conversión CBZ → EPUB optimizada', 'Perfiles de pantalla Kindle'],
    color: 'border-orange-500 bg-orange-500/10',
  },
  {
    id: 'kobo',
    icon: <FaBook className="text-4xl text-blue-400" />,
    label: 'Kobo',
    description: 'Kobo Libra, Clara, Sage, Elipsa…',
    features: ['Catálogo OPDS integrado', 'Descarga directa de CBZ y EPUB', 'Compatible con KOReader'],
    color: 'border-blue-500 bg-blue-500/10',
  },
  {
    id: 'pocketbook',
    icon: <FaTabletAlt className="text-4xl text-green-400" />,
    label: 'PocketBook',
    description: 'PocketBook InkPad, Touch, Era…',
    features: ['Catálogo OPDS nativo en firmware', 'Soporte CBZ/CBR sin conversión', 'Descarga directa'],
    color: 'border-green-500 bg-green-500/10',
  },
  {
    id: 'android',
    icon: <FaMobileAlt className="text-4xl text-purple-400" />,
    label: 'Android',
    description: 'Moon+ Reader, Librera, KOReader, Onyx Boox…',
    features: ['Catálogo OPDS vía app lectora', 'Descarga CBZ/EPUB desde el navegador', 'Compatible con todas las apps Android'],
    color: 'border-purple-500 bg-purple-500/10',
  },
  {
    id: 'other',
    icon: <FaQuestion className="text-4xl text-gray-400" />,
    label: 'Otro',
    description: 'Cualquier otro dispositivo o lector web',
    features: ['Lector web integrado para manga', 'Descarga directa de archivos', 'Catálogo OPDS disponible'],
    color: 'border-gray-500 bg-gray-500/10',
  },
];

export default function DeviceSetup() {
  const [selected, setSelected] = useState(null);
  const [saving, setSaving] = useState(false);
  const { updateEreaderType, markDeviceSetupCompleted } = useAuth();
  const navigate = useNavigate();

  const handleContinue = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await api.post('/settings', { ereader_type: selected, device_setup_completed: true });
      updateEreaderType(selected);
      markDeviceSetupCompleted();
      navigate('/');
    } catch (err) {
      console.error('Error saving device type:', err);
      // Still mark as done locally so we don't loop
      markDeviceSetupCompleted();
      navigate('/');
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = async () => {
    try {
      await api.post('/settings', { device_setup_completed: true });
    } catch (err) {
      console.error('Error marking device setup complete:', err);
    }
    markDeviceSetupCompleted();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-gray-900 flex flex-col items-center justify-center px-4 py-12">
      <div className="max-w-3xl w-full">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-white mb-2">¿Qué dispositivo de lectura tienes?</h1>
          <p className="text-gray-400">
            Ajustaremos Alejandría para mostrarte solo las opciones relevantes para tu dispositivo.
            Podrás cambiarlo en cualquier momento desde Ajustes.
          </p>
        </div>

        {/* Device grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          {DEVICES.map(device => (
            <button
              key={device.id}
              onClick={() => setSelected(device.id)}
              className={`text-left p-5 rounded-xl border-2 transition-all ${
                selected === device.id
                  ? device.color
                  : 'border-gray-700 bg-gray-800 hover:border-gray-500'
              }`}
            >
              <div className="flex items-center gap-3 mb-3">
                {device.icon}
                <span className="text-lg font-bold text-white">{device.label}</span>
              </div>
              <p className="text-sm text-gray-400 mb-3">{device.description}</p>
              <ul className="space-y-1">
                {device.features.map((f, i) => (
                  <li key={i} className="text-xs text-gray-300 flex items-start gap-1">
                    <span className="text-green-400 mt-0.5">✓</span>
                    {f}
                  </li>
                ))}
              </ul>
            </button>
          ))}
        </div>

        {/* Continue button */}
        <div className="flex justify-center">
          <button
            onClick={handleContinue}
            disabled={!selected || saving}
            className="flex items-center gap-2 px-8 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors text-lg"
          >
            {saving ? 'Guardando…' : 'Continuar'}
            <FaArrowRight />
          </button>
        </div>

        {/* Skip link */}
        <div className="text-center mt-4">
          <button
            onClick={handleSkip}
            className="text-sm text-gray-500 hover:text-gray-400 underline"
          >
            Omitir por ahora
          </button>
        </div>
      </div>
    </div>
  );
}
