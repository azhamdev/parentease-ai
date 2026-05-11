import { MessageSquare, Plus, Settings, User } from 'lucide-react';

const Sidebar = ({ sessionId, onNewSession }) => {
  const history = [
    { id: '1', title: 'Kapan mulai MPASI?' },
    { id: '2', title: 'Jadwal vaksinasi bayi' },
  ];

  return (
    <div className="w-[280px] bg-bg-main border-r border-border flex flex-col hidden md:flex shadow-sm">
      <div className="p-4 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-2 font-bold text-text-main">
          <div className="w-7 h-7 bg-primary-light rounded-lg flex items-center justify-center">
            <MessageSquare className="text-primary w-4 h-4" />
          </div>
          ParentEase
        </div>
        <button 
          onClick={onNewSession}
          className="p-1.5 hover:bg-primary-light rounded-lg text-text-muted hover:text-primary transition"
        >
          <Plus className="w-5 h-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        <div className="px-3 py-2 text-xs font-semibold text-text-muted uppercase tracking-wider">
          Riwayat Chat
        </div>
        {history.map((item) => (
          <button
            key={item.id}
            className="w-full text-left px-3 py-2.5 text-sm text-text-main hover:bg-primary-light rounded-lg transition flex items-center gap-3"
          >
            <MessageSquare className="w-4 h-4 text-text-light" />
            <span className="truncate">{item.title}</span>
          </button>
        ))}
      </div>

      {/* <div className="p-3 border-t border-border">
        <button className="flex items-center gap-3 w-full px-3 py-2 hover:bg-primary-light rounded-lg transition">
          <div className="w-8 h-8 bg-bg-tertiary rounded-full flex items-center justify-center text-text-muted">
            <User className="w-4 h-4" />
          </div>
          <div className="text-sm font-medium text-text-main">
            Orangtua Baru
          </div>
        </button>
      </div> */}
    </div>
  );
};

export default Sidebar;