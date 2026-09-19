import { useState, useEffect } from 'react';
import { AUTH_EXPIRED_EVENT, api } from './services/api';
import AuthPage from './components/auth/AuthPage';
import Sidebar from './components/Sidebar';
import ChatPanel from './components/ChatPanel';
import { Menu } from 'lucide-react';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem("medirag_token"));
  const [isLogin, setIsLogin] = useState(true);
  const [error, setError] = useState("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  useEffect(() => {
    const handleAuthExpired = () => {
      setIsAuthenticated(false);
      setError("Your session expired. Please sign in again.");
    };

    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
  }, []);

  const handleLogin = async (email: string, password: string) => {
    setError("");
    try {
      await api.login(email, password);
      setIsAuthenticated(true);
    } catch (err: any) {
      setError(err.message || "An error occurred");
      throw err;
    }
  };

  const handleRegister = async (fullName: string, email: string, password: string) => {
    setError("");
    try {
      await api.register(fullName, email, password);
      setIsAuthenticated(true);
    } catch (err: any) {
      setError(err.message || "An error occurred");
      throw err;
    }
  };

  const handleLogout = () => {
    api.logout();
    setIsAuthenticated(false);
  };

  if (!isAuthenticated) {
    return (
      <AuthPage
        mode={isLogin ? "login" : "register"}
        error={error}
        onModeChange={(mode) => {
          setError("");
          setIsLogin(mode === "login");
        }}
        onLogin={handleLogin}
        onRegister={handleRegister}
      />
    );
  }

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden font-sans relative">
      {/* Mobile sidebar overlay */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-20 md:hidden transition-opacity"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}
      
      {/* Sidebar - fixed on mobile, static on desktop */}
      <div className={`fixed inset-y-0 left-0 z-30 transform ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:relative md:translate-x-0 transition duration-300 ease-in-out md:flex md:w-64`}>
        <Sidebar onLogout={handleLogout} onClose={() => setIsSidebarOpen(false)} />
      </div>

      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        {/* Mobile Header */}
        <div className="md:hidden flex items-center justify-between p-4 bg-white shadow-sm border-b border-gray-200 z-10">
          <h1 className="text-lg font-bold text-blue-600">MediRAG AI</h1>
          <button 
            onClick={() => setIsSidebarOpen(true)}
            className="p-2 -mr-2 text-gray-500 hover:bg-gray-100 rounded-lg focus:outline-none"
          >
            <Menu size={24} />
          </button>
        </div>
        
        <div className="flex-1 relative h-full">
          <ChatPanel />
        </div>
      </div>
    </div>
  );
}

export default App;
