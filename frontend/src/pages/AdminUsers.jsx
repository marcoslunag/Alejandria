import { useState, useEffect, useCallback } from 'react';
import {
  FaPlus, FaTrash, FaKey, FaUserShield, FaBan, FaCheck,
  FaBook, FaBookOpen, FaImage, FaTimes, FaDatabase, FaExclamationTriangle,
  FaDownload, FaBookReader,
} from 'react-icons/fa';
import toast from 'react-hot-toast';
import api from '../services/api';
import ConfirmModal from '../components/ConfirmModal';

const FORMAT_BYTES = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

const TYPE_CONFIG = {
  manga: { label: 'Manga', icon: FaBookOpen, color: 'text-blue-400', countKey: 'manga_count' },
  comic: { label: 'Cómics', icon: FaImage, color: 'text-red-400', countKey: 'comic_count' },
  book: { label: 'Libros', icon: FaBook, color: 'text-green-400', countKey: 'book_count' },
};

// ── Library Modal ─────────────────────────────────────────────────────────────

const LibraryModal = ({ user, onClose }) => {
  const [activeTab, setActiveTab] = useState('manga');
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const fetchItems = useCallback(async (type) => {
    setLoadingItems(true);
    setItems([]);
    try {
      const res = await api.get(`/auth/users/${user.id}/library`, { params: { type } });
      setItems(res.data);
    } catch {
      toast.error('Error al cargar biblioteca');
    } finally {
      setLoadingItems(false);
    }
  }, [user.id]);

  useEffect(() => {
    fetchItems(activeTab);
  }, [activeTab, fetchItems]);

  const handleDeleteItem = (item) => {
    setConfirmDelete({
      title: `Eliminar ${TYPE_CONFIG[activeTab].label.toLowerCase()}`,
      message: `¿Eliminar "${item.title}" de la biblioteca de ${user.username}? Esta acción no se puede deshacer.`,
      onConfirm: async () => {
        try {
          await api.delete(`/auth/users/${user.id}/library/${activeTab}/${item.id}`);
          toast.success(`"${item.title}" eliminado`);
          setItems(prev => prev.filter(i => i.id !== item.id));
        } catch (err) {
          toast.error(err.response?.data?.detail || 'Error al eliminar');
        }
        setConfirmDelete(null);
      },
    });
  };

  const totalStorage = items.reduce((s, i) => s + (i.storage_bytes || 0), 0);
  const cfg = TYPE_CONFIG[activeTab];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
      <div className="bg-dark-lighter border border-gray-700 rounded-xl w-full max-w-4xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-700">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <FaBookReader className="text-primary" />
              Biblioteca de {user.username}
            </h2>
            <p className="text-gray-400 text-sm mt-0.5">{user.email}</p>
          </div>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-white">
            <FaTimes size={20} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700 px-5">
          {Object.entries(TYPE_CONFIG).map(([type, c]) => {
            const Icon = c.icon;
            const count = user[c.countKey] ?? 0;
            return (
              <button
                key={type}
                onClick={() => setActiveTab(type)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === type
                    ? `border-primary ${c.color}`
                    : 'border-transparent text-gray-400 hover:text-white'
                }`}
              >
                <Icon />
                {c.label}
                <span className="ml-1 bg-gray-700 text-gray-300 text-xs px-1.5 py-0.5 rounded-full">
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Stats bar */}
        {!loadingItems && items.length > 0 && (
          <div className="flex items-center gap-6 px-5 py-2.5 bg-dark/50 text-sm text-gray-400">
            <span className="flex items-center gap-1.5">
              <FaDatabase className="text-gray-500" />
              Almacenamiento: <span className="text-white font-medium">{FORMAT_BYTES(totalStorage)}</span>
            </span>
            <span>{items.length} títulos</span>
            <span>{items.reduce((s, i) => s + (i.downloaded_count || 0), 0)} archivos descargados</span>
            {items.some(i => i.error_count > 0) && (
              <span className="text-red-400 flex items-center gap-1">
                <FaExclamationTriangle />
                {items.reduce((s, i) => s + (i.error_count || 0), 0)} errores
              </span>
            )}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {loadingItems ? (
            <div className="flex items-center justify-center h-40">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-gray-500">
              <cfg.icon size={32} className="mb-2 opacity-40" />
              <p>No hay {cfg.label.toLowerCase()} en la biblioteca</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-dark-lighter">
                <tr className="border-b border-gray-700 text-left">
                  <th className="px-4 py-2.5 text-gray-400 font-medium">Título</th>
                  <th className="px-4 py-2.5 text-gray-400 font-medium text-center">
                    {activeTab === 'comic' ? 'Issues' : 'Capítulos'}
                  </th>
                  <th className="px-4 py-2.5 text-gray-400 font-medium text-center">Descargados</th>
                  <th className="px-4 py-2.5 text-gray-400 font-medium text-center">Errores</th>
                  <th className="px-4 py-2.5 text-gray-400 font-medium text-right">Tamaño</th>
                  <th className="px-4 py-2.5 text-gray-400 font-medium text-center">Estado</th>
                  <th className="px-4 py-2.5 text-gray-400 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-gray-800 hover:bg-dark/50">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        {item.cover_url && (
                          <img
                            src={item.cover_url}
                            alt=""
                            className="w-8 h-10 object-cover rounded opacity-80"
                            onError={(e) => { e.target.style.display = 'none'; }}
                          />
                        )}
                        <div>
                          <p className="text-white font-medium leading-tight line-clamp-1">{item.title}</p>
                          {item.monitored && (
                            <span className="text-xs text-blue-400">Monitoreado</span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-center text-gray-300">
                      {item.chapter_count ?? item.issue_count ?? 0}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <span className="flex items-center justify-center gap-1 text-gray-300">
                        <FaDownload className="text-gray-500" size={10} />
                        {item.downloaded_count || 0}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      {item.error_count > 0 ? (
                        <span className="text-red-400 flex items-center justify-center gap-1">
                          <FaExclamationTriangle size={10} />
                          {item.error_count}
                        </span>
                      ) : (
                        <span className="text-gray-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right text-gray-300">
                      {item.storage_bytes > 0 ? FORMAT_BYTES(item.storage_bytes) : <span className="text-gray-600">—</span>}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      {item.reading_status && item.reading_status !== 'not_started' ? (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          item.reading_status === 'completed'
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-yellow-500/20 text-yellow-400'
                        }`}>
                          {item.reading_status === 'completed' ? 'Leído' : 'Leyendo'}
                        </span>
                      ) : (
                        <span className="text-gray-600 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        onClick={() => handleDeleteItem(item)}
                        className="p-1.5 text-gray-600 hover:text-red-400 transition-colors"
                        title="Eliminar"
                      >
                        <FaTrash size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <ConfirmModal
        isOpen={!!confirmDelete}
        title={confirmDelete?.title}
        message={confirmDelete?.message}
        onConfirm={confirmDelete?.onConfirm}
        onCancel={() => setConfirmDelete(null)}
        variant="danger"
      />
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────────

const AdminUsers = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '' });
  const [creating, setCreating] = useState(false);
  const [resetPassword, setResetPassword] = useState(null);
  const [libraryUser, setLibraryUser] = useState(null);

  const fetchUsers = async () => {
    try {
      const res = await api.get('/auth/admin/overview');
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
      message: `¿Eliminar a "${user.username}"? Se eliminará todo su contenido. Esta acción no se puede deshacer.`,
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
      toast.success(`Contraseña de ${user.username} reseteada`);
      fetchUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Error al resetear contraseña');
    }
  };

  const totalStorage = (user) => {
    // Storage is shown per-library; here we just show counts
    return (user.manga_count || 0) + (user.comic_count || 0) + (user.book_count || 0);
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
            Gestión de Usuarios
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
              <label className="block text-sm text-gray-400 mb-1">Contraseña</label>
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
            El usuario deberá cambiar la contraseña en su primer inicio de sesión.
          </p>
        </div>
      )}

      {/* Reset password display */}
      {resetPassword && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 mb-6">
          <p className="text-yellow-400 font-semibold mb-1">
            Nueva contraseña para {resetPassword.username}:
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
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700 text-left">
              <th className="px-4 py-3 text-gray-400 font-medium">Usuario</th>
              <th className="px-4 py-3 text-gray-400 font-medium">Email</th>
              <th className="px-4 py-3 text-gray-400 font-medium text-center">
                <span className="text-blue-400">Manga</span>
              </th>
              <th className="px-4 py-3 text-gray-400 font-medium text-center">
                <span className="text-red-400">Cómics</span>
              </th>
              <th className="px-4 py-3 text-gray-400 font-medium text-center">
                <span className="text-green-400">Libros</span>
              </th>
              <th className="px-4 py-3 text-gray-400 font-medium">Estado</th>
              <th className="px-4 py-3 text-gray-400 font-medium">Dispositivo</th>
              <th className="px-4 py-3 text-gray-400 font-medium">Creado</th>
              <th className="px-4 py-3 text-gray-400 font-medium text-right">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className="border-b border-gray-800 hover:bg-dark-lighter/50">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {user.is_admin && <FaUserShield className="text-purple-400" size={12} />}
                    <span className="text-white font-medium">{user.username}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-gray-400">{user.email}</td>

                {/* Library counts — clickable for non-admin users */}
                {['manga', 'comic', 'book'].map((type) => {
                  const cfg = TYPE_CONFIG[type];
                  const count = user[cfg.countKey] || 0;
                  return (
                    <td key={type} className="px-4 py-3 text-center">
                      {!user.is_admin && count > 0 ? (
                        <button
                          onClick={() => setLibraryUser({ ...user, _tab: type })}
                          className={`font-semibold ${cfg.color} hover:underline`}
                        >
                          {count}
                        </button>
                      ) : (
                        <span className="text-gray-600">{count || '—'}</span>
                      )}
                    </td>
                  );
                })}

                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      user.is_active
                        ? 'bg-green-500/20 text-green-400'
                        : 'bg-red-500/20 text-red-400'
                    }`}>
                      {user.is_active ? 'Activo' : 'Inactivo'}
                    </span>
                    {user.must_change_password && (
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-yellow-500/20 text-yellow-400">
                        Cambio pwd
                      </span>
                    )}
                  </div>
                </td>

                <td className="px-4 py-3 text-gray-400 text-xs capitalize">
                  {user.ereader_type || '—'}
                </td>

                <td className="px-4 py-3 text-gray-400 text-xs">
                  {new Date(user.created_at).toLocaleDateString('es-ES')}
                </td>

                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-1">
                    {!user.is_admin && (
                      <>
                        <button
                          onClick={() => setLibraryUser(user)}
                          className="p-2 text-gray-400 hover:text-primary transition-colors"
                          title="Ver biblioteca"
                        >
                          <FaBookOpen size={13} />
                        </button>
                        <button
                          onClick={() => handleResetPassword(user)}
                          className="p-2 text-gray-400 hover:text-yellow-400 transition-colors"
                          title="Resetear contraseña"
                        >
                          <FaKey size={13} />
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
                          {user.is_active ? <FaBan size={13} /> : <FaCheck size={13} />}
                        </button>
                        <button
                          onClick={() => handleDelete(user)}
                          className="p-2 text-gray-400 hover:text-red-400 transition-colors"
                          title="Eliminar usuario"
                        >
                          <FaTrash size={13} />
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Library modal */}
      {libraryUser && (
        <LibraryModal
          user={libraryUser}
          onClose={() => setLibraryUser(null)}
        />
      )}

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
