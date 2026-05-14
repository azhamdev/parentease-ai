import { useEffect, useState } from 'react';
import { Plus, MessageSquare, Loader2, Trash2 } from 'lucide-react';
import { getSessions, deleteSession } from '../services/api';

const Sidebar = ({ activeSessionId, onSelectSession, onNewSession }) => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      const data = await getSessions();
      setSessions(data);
    } catch (err) {
      console.error("Error loading sessions:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (sessionId, e) => {
    e.stopPropagation(); // Mencegah trigger onSelectSession
    
    const confirmed = window.confirm(
      "Hapus session ini?\nSemua riwayat chat & data anak akan dihapus."
    );
    if (!confirmed) return;
    
    setDeletingId(sessionId);
    try {
      await deleteSession(sessionId);
      
      // Update UI langsung tanpa reload
      setSessions(prev => prev.filter(s => s.session_id !== sessionId));
      
      // Jika yang dihapus adalah session aktif, reset ke new session
      if (sessionId === activeSessionId) {
        onNewSession();
      }
    } catch (err) {
      alert(`Gagal menghapus: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="w-72 bg-bg-main border-r border-border flex flex-col h-full">
      <div className="h-16 p-4 border-b border-border flex items-center justify-between">
        <h2 className="font-semibold text-text-main">Riwayat Chat</h2>
        <button
          onClick={onNewSession}
          className="p-2 hover:bg-primary-light rounded-lg transition text-primary"
          title="Chat Baru"
        >
          <Plus className="w-5 h-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-text-muted">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            Memuat...
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-8 text-text-muted text-sm">
            Belum ada riwayat chat
          </div>
        ) : (
          sessions.map((s) => (
            <div
              key={s.session_id}
              className={`group relative flex items-start gap-3 p-3 rounded-lg transition ${
                activeSessionId === s.session_id
                  ? "bg-primary/10 border border-primary/30 text-primary"
                  : "hover:bg-bg-tertiary text-text-main border border-transparent"
              }`}
            >
              <button
                onClick={() => onSelectSession(s.session_id)}
                className="flex-1 text-left min-w-0"
              >
                <div className="min-w-0">
                  <div className="flex gap-2 jutify-start item-center">
                    <MessageSquare className="w-4 h-4 mt-0.5 flex-shrink-0" />
                    <p className="text-sm font-medium truncate">{s.child_name}</p>
                  </div>
                  <p className="text-xs text-text-muted truncate mt-0.5">
                    {s.last_message_preview}
                  </p>
                </div>
              </button>
              
              {/* Tombol Hapus (muncul saat hover) */}
              <button
                onClick={(e) => handleDelete(s.session_id, e)}
                disabled={deletingId === s.session_id}
                className="p-1.5 text-red-400 text-red-500 bg-red-500/10 rounded transition disabled:opacity-50"
                title="Hapus session"
              >
                {deletingId === s.session_id ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default Sidebar;