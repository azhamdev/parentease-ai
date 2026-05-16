import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import WelcomeForm from './components/WelcomeForm';
import ChatInterface from './components/ChatInterface';
import { createSession } from './services/api';

const fetchChildProfile = async (sessionId) => {
  // Nanti disambung ke endpoint backend: GET /sessions/{sessionId}/profile
  // Untuk sekarang, return null dulu
  return null; 
};

function App() {
  const [sessionId, setSessionId] = useState(localStorage.getItem('parentease_session') || null);
  const [babyData, setBabyData] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [theme, setTheme] = useState(() => {
    const storedTheme = localStorage.getItem('parentease_theme');
    if (storedTheme === 'light' || storedTheme === 'dark') return storedTheme;
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('parentease_theme', theme);
  }, [theme]);

  // Jika user baru, tampilkan form
  useEffect(() => {
    if (!sessionId) {
      setShowForm(true);
    } else {
      setShowForm(false);
      // Fetch baby data saat sessionId aktif
      loadBabyData(sessionId);
    }
  }, [sessionId]);

  // Load baby data dari backend untuk session tertentu
  const loadBabyData = async (sid) => {
    if (!sid) return;
    setIsLoadingSession(true);
    try {
      const data = await fetchChildProfile(sid);
      if (data) setBabyData(data);
    } catch (err) {
      console.error("Failed to load baby data:", err);
      setBabyData(null);
    } finally {
      setIsLoadingSession(false);
    }
  };

  const handleSessionCreated = (newSessionId, data) => {
    setSessionId(newSessionId);
    setBabyData(data);
    setShowForm(false);
    localStorage.setItem('parentease_session', newSessionId);
  };

  // Handle klik session di sidebar
  const handleSelectSession = async (selectedSessionId) => {
    if (selectedSessionId === sessionId) return;
    
    setSessionId(selectedSessionId);
    localStorage.setItem('parentease_session', selectedSessionId);
    setShowForm(false);
  };

  const handleNewSession = () => {
    setSessionId(null);
    setBabyData(null);
    setShowForm(true);
    localStorage.removeItem('parentease_session');
  };

  const handleCloseForm = () => {
    setShowForm(false);
  };

  const handleEditBabyData = () => {
    if (!sessionId) return;
    setShowForm(true);
  };

  const handleFormSuccess = (newSessionIdOrData, data) => {
    const isEdit = typeof newSessionIdOrData !== 'string';
    
    if (isEdit) {
      setBabyData(prev => ({ ...prev, ...data }));
    } else {
      setSessionId(newSessionIdOrData);
      setBabyData(data);
      localStorage.setItem('parentease_session', newSessionIdOrData);
    }
    setShowForm(false);
  };

  return (
    <div className="flex h-[100dvh] min-h-[100dvh] flex-col overflow-hidden bg-[var(--app-bg)] p-2 text-text-main sm:p-3 lg:flex-row lg:p-4">
      {/* Sidebar History */}
      <Sidebar 
        activeSessionId={sessionId}  // untuk highlight session aktif
        onSelectSession={handleSelectSession}  // untuk handle klik
        onNewSession={handleNewSession}  // Ganti nama prop agar konsisten
        theme={theme}
        onToggleTheme={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
      />

      {/* Main Content */}
      <div className="flex min-h-0 flex-1 flex-col lg:pl-3">
        {isLoadingSession ? (
          <div className="liquid-panel flex flex-1 items-center justify-center rounded-xl text-text-muted">
            Memuat data...
          </div>
        ) : showForm ? (
          <WelcomeForm 
            onSessionCreated={handleSessionCreated} 
            onClose={handleCloseForm}
            initialData={babyData}
            sessionId={sessionId}
            onSuccess={handleFormSuccess}
          />
        ) : (
          <ChatInterface 
            sessionId={sessionId} 
            babyData={babyData}
            onEditBabyData={handleEditBabyData}
          />
        )}
      </div>
    </div>
  );
}

export default App;
