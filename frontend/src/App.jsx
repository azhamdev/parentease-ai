import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import WelcomeForm from './components/WelcomeForm';
import ChatInterface from './components/ChatInterface';

// Mock function to simulate fetching child profile from backend
const fetchChildProfile = async (sessionId) => {
  // Nanti disambung ke endpoint backend
  return null; 
};

function App() {
  const [sessionId, setSessionId] = useState(localStorage.getItem('parentease_session') || null);
  const [babyData, setBabyData] = useState(null);
  const [showForm, setShowForm] = useState(false);

  // Jika user baru, tampilkan form
  useEffect(() => {
    if (!sessionId) {
      setShowForm(true);
    } else {
      setShowForm(false);
      // Fetch baby data logic here
    }
  }, [sessionId]);

  const handleSessionCreated = (newSessionId, data) => {
    setSessionId(newSessionId);
    setBabyData(data);
    setShowForm(false);
    localStorage.setItem('parentease_session', newSessionId);
  };

  const handleEditBabyData = () => {
    setShowForm(true);
  };

  const handleCloseForm = () => {
    setShowForm(false);
  };

  return (
    <div className="flex h-screen bg-[#F4F6F9]">
      {/* Sidebar History */}
      <Sidebar 
        sessionId={sessionId} 
        onNewSession={() => {
          setSessionId(null);
          setBabyData(null);
          setShowForm(true);
          localStorage.removeItem('parentease_session');
        }}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {showForm ? (
          <WelcomeForm 
            onSessionCreated={handleSessionCreated} 
            onClose={handleCloseForm}
            initialData={babyData}
            sessionId={sessionId}
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