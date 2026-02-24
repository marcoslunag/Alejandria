import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { FaLock } from 'react-icons/fa';
import toast from 'react-hot-toast';

const ChangePassword = () => {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { changePassword, mustChangePassword } = useAuth();
  const navigate = useNavigate();
  // Guardar si era "primer cambio" antes de que changePassword lo ponga a false
  const isFirstChange = mustChangePassword;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (newPassword !== confirmPassword) {
      setError('Las contrasenas no coinciden');
      return;
    }

    if (newPassword.length < 6) {
      setError('La nueva contrasena debe tener al menos 6 caracteres');
      return;
    }

    setLoading(true);

    try {
      await changePassword(currentPassword, newPassword);
      toast.success('Contrasena actualizada correctamente');
      // Primera vez → configurar dispositivo; admin reset → inicio normal
      navigate(isFirstChange ? '/device-setup' : '/');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || 'Error al cambiar la contrasena');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="text-6xl mb-4">🔑</div>
          <h1 className="text-3xl font-bold text-primary">Cambiar contrasena</h1>
          {mustChangePassword && (
            <p className="text-yellow-400 mt-2">
              Debes cambiar tu contrasena antes de continuar
            </p>
          )}
        </div>

        <div className="card p-8">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-3 rounded-lg mb-4">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Contrasena actual</label>
              <div className="relative">
                <FaLock className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="input pl-10 w-full"
                  placeholder="Tu contrasena actual"
                  required
                  autoFocus
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Nueva contrasena</label>
              <div className="relative">
                <FaLock className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="input pl-10 w-full"
                  placeholder="Minimo 6 caracteres"
                  required
                  minLength={6}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Confirmar nueva contrasena</label>
              <div className="relative">
                <FaLock className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="input pl-10 w-full"
                  placeholder="Repite la nueva contrasena"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full py-3 flex items-center justify-center gap-2"
            >
              {loading ? (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
              ) : (
                'Cambiar contrasena'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default ChangePassword;
