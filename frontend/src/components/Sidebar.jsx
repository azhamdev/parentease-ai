import { useEffect, useState } from 'react';
import { Plus, MessageSquare, Loader2, Trash2, Moon, Sun } from 'lucide-react';
import { getSessions, deleteSession } from '../services/api';

const Sidebar = ({ activeSessionId, onSelectSession, onNewSession, theme, onToggleTheme }) => {
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
    <aside className="liquid-panel-strong mb-2 flex max-h-44 w-full shrink-0 flex-col overflow-hidden rounded-xl lg:mb-0 lg:h-full lg:max-h-none lg:w-72">
      <div className="flex min-h-14 items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h2 className="font-semibold text-text-main">Riwayat Chat</h2>
          <p className="hidden text-xs text-text-muted sm:block lg:hidden">Geser untuk melihat session lainnya</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onToggleTheme}
            className="rounded-lg border border-border bg-bg-tertiary p-2 text-text-muted transition hover:border-primary-border hover:text-primary"
            aria-label={theme === 'dark' ? 'Aktifkan light mode' : 'Aktifkan dark mode'}
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
          >
            {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
          <button
            onClick={onNewSession}
            className="rounded-lg border border-primary-border bg-primary-light p-2 text-primary transition hover:bg-primary/15"
            title="Chat Baru"
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="glass-scrollbar flex flex-1 gap-2 overflow-x-auto overflow-y-hidden p-2 lg:block lg:space-y-1 lg:overflow-y-auto">
        {loading ? (
          <div className="flex min-w-48 items-center justify-center py-8 text-text-muted">
            <Loader2 className="w-5 h-5 animate-spin mr-2" />
            Memuat...
          </div>
        ) : sessions.length === 0 ? (
          <div className="min-w-48 py-8 text-center text-sm text-text-muted">
            Belum ada riwayat chat
          </div>
        ) : (
          sessions.map((s) => (
            <div
              key={s.session_id}
              className={`group relative flex min-w-64 items-start gap-3 rounded-lg p-3 transition lg:min-w-0 ${
                activeSessionId === s.session_id
                  ? "border border-primary/30 bg-primary/10 text-primary shadow-sm"
                  : "border border-transparent text-text-main hover:bg-bg-tertiary"
              }`}
            >
              <button
                onClick={() => onSelectSession(s.session_id)}
                className="flex-1 text-left min-w-0"
              >
                <div className="min-w-0">
                  <div className="flex items-center justify-start gap-2">
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
                className="rounded p-1.5 text-red-500 transition hover:bg-red-500/10 disabled:opacity-50"
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
    </aside>
  );
};

export default Sidebar;
