import { useState, useEffect } from 'react';
import { FaPlus, FaTrash, FaKey, FaUserShield, FaBan, FaCheck } from 'react-icons/fa';
import toast from 'react-hot-toast';
import api from '../services/api';
import ConfirmModal from '../components/ConfirmModal';

const AdminUsers = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '' });
  const [creating, setCreating] = useState(false);
  const [resetPassword, setResetPassword] = useState(null);

  const fetchUsers = async () => {
    try {
      const res = await api.get('/auth/users');
      setUsers(res.data);
    } catch {
      toast.error('Error al cargar usuarios');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);

    try {
      await api.post('/auth/users', newUser);
      toast.success(`Usuario ${newUser.username} creado`);
      setNewUser({ username: '', email: '', password: '' });
      setShowCreate(false);
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Error al crear usuario');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = (user) => {
    setConfirmAction({
      title: 'Eliminar usuario',
      message: `Estas seguro de eliminar a "${user.username}"? Esta accion no se puede deshacer.`,
      onConfirm: async () => {
        try {
          await api.delete(`/auth/users/${user.id}`);
          toast.success(`Usuario ${user.username} eliminado`);
          fetchUsers();
        } catch (err) {
          toast.error(err.response?.data?.detail || 'Error al eliminar');
        }
      },
    });
  };

  const handleToggleActive = async (user) => {
    try {
      const res = await api.patch(`/auth/users/${user.id}/toggle-active`);
      toast.success(res.data.message);
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Error al cambiar estado');
    }
  };

  const handleResetPassword = async (user) => {
    try {
      const res = await api.patch(`/auth/users/${user.id}/reset-password`);
      setResetPassword({ username: user.username, password: res.data.new_password });
      toast.success(`Contrasena de ${user.username} reseteada`);
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Error al resetear contrasena');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <FaUserShield className="text-primary" />
            Gestion de Usuarios
          </h1>
          <p className="text-gray-400 mt-1">{users.length} usuarios registrados</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="btn-primary flex items-center gap-2"
        >
          <FaPlus /> Nuevo Usuario
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="card p-6 mb-6">
          <h3 className="text-lg font-semibold text-white mb-4">Crear nuevo usuario</h3>
          <form onSubmit={handleCreate} className="flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm text-gray-400 mb-1">Usuario</label>
              <input
                type="text"
                value={newUser.username}
                onChange={(e) => setNewUser(p => ({ ...p, username: e.target.value }))}
                className="input w-full"
                placeholder="nombre_usuario"
                required
              />
            </div>
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm text-gray-400 mb-1">Email</label>
              <input
                type="email"
                value={newUser.email}
                onChange={(e) => setNewUser(p => ({ ...p, email: e.target.value }))}
                className="input w-full"
                placeholder="email@ejemplo.com"
                required
              />
            </div>
            <div className="flex-1 min-w-[200px]">
              <label className="block text-sm text-gray-400 mb-1">Contrasena</label>
              <input
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser(p => ({ ...p, password: e.target.value }))}
                className="input w-full"
                placeholder="Min. 6 caracteres"
                required
                minLength={6}
              />
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={creating} className="btn-primary px-6">
                {creating ? 'Creando...' : 'Crear'}
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="btn-secondary px-4"
              >
                Cancelar
              </button>
            </div>
          </form>
          <p className="text-sm text-gray-500 mt-2">
            El usuario debera cambiar la contrasena en su primer inicio de sesion.
          </p>
        </div>
      )}

      {/* Reset password display */}
      {resetPassword && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 mb-6">
          <p className="text-yellow-400 font-semibold mb-1">
            Nueva contrasena para {resetPassword.username}:
          </p>
          <code className="text-white text-lg bg-dark-lighter px-3 py-1 rounded select-all">
            {resetPassword.password}
          </code>
          <button
            onClick={() => setResetPassword(null)}
            className="ml-4 text-gray-400 hover:text-white text-sm"
          >
            Cerrar
          </button>
        </div>
      )}

      {/* Users table */}
      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-700 text-left">
              <th className="px-4 py-3 text-gray-400 text-sm font-medium">Usuario</th>
              <th className="px-4 py-3 text-gray-400 text-sm font-medium">Email</th>
              <th className="px-4 py-3 text-gray-400 text-sm font-medium">Estado</th>
              <th className="px-4 py-3 text-gray-400 text-sm font-medium">Rol</th>
              <th className="px-4 py-3 text-gray-400 text-sm font-medium">Creado</th>
              <th className="px-4 py-3 text-gray-400 text-sm font-medium text-right">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className="border-b border-gray-800 hover:bg-dark-lighter/50">
                <td className="px-4 py-3 text-white font-medium">{user.username}</td>
                <td className="px-4 py-3 text-gray-400">{user.email}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    user.is_active
                      ? 'bg-green-500/20 text-green-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {user.is_active ? 'Activo' : 'Inactivo'}
                  </span>
                  {user.must_change_password && (
                    <span className="ml-2 px-2 py-1 rounded text-xs font-medium bg-yellow-500/20 text-yellow-400">
                      Cambio pendiente
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    user.is_admin
                      ? 'bg-purple-500/20 text-purple-400'
                      : 'bg-gray-500/20 text-gray-400'
                  }`}>
                    {user.is_admin ? 'Admin' : 'Usuario'}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-400 text-sm">
                  {new Date(user.created_at).toLocaleDateString('es-ES')}
                </td>
                <td className="px-4 py-3 text-right">
                  {!user.is_admin && (
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleResetPassword(user)}
                        className="p-2 text-gray-400 hover:text-yellow-400 transition-colors"
                        title="Resetear contrasena"
                      >
                        <FaKey />
                      </button>
                      <button
                        onClick={() => handleToggleActive(user)}
                        className={`p-2 transition-colors ${
                          user.is_active
                            ? 'text-gray-400 hover:text-orange-400'
                            : 'text-gray-400 hover:text-green-400'
                        }`}
                        title={user.is_active ? 'Desactivar' : 'Activar'}
                      >
                        {user.is_active ? <FaBan /> : <FaCheck />}
                      </button>
                      <button
                        onClick={() => handleDelete(user)}
                        className="p-2 text-gray-400 hover:text-red-400 transition-colors"
                        title="Eliminar"
                      >
                        <FaTrash />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmModal
        isOpen={!!confirmAction}
        title={confirmAction?.title}
        message={confirmAction?.message}
        onConfirm={() => {
          confirmAction?.onConfirm();
          setConfirmAction(null);
        }}
        onCancel={() => setConfirmAction(null)}
        variant="danger"
      />
    </div>
  );
};

export default AdminUsers;
