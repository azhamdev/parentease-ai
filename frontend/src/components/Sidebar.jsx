// frontend/src/components/Sidebar.jsx
import { useEffect, useState } from 'react';
import { Plus, MessageSquare, Loader2 } from 'lucide-react';
import { getSessions } from '../services/api';

const Sidebar = ({ activeSessionId, onSelectSession, onNewSession }) => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

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
            <button
              key={s.session_id}
              onClick={() => onSelectSession(s.session_id)}
              className={`w-full text-left p-3 rounded-lg transition flex items-start gap-3 ${
                activeSessionId === s.session_id
                  ? "bg-primary/10 border border-primary/30 text-primary"
                  : "hover:bg-bg-tertiary text-text-main border border-transparent"
              }`}
            >
              <MessageSquare className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{s.child_name}</p>
                <p className="text-xs text-text-muted truncate mt-0.5">
                  {s.last_message_preview}
                </p>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
};

export default Sidebar;