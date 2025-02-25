import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import Login from './components/Login';
import Dashboard from './components/Dashboard';

const AuthWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const navigate = useNavigate();
  const token = localStorage.getItem('token');

  useEffect(() => {
    console.log('AuthWrapper - token:', token);
    if (!token) {
      console.log('No token found, redirecting to login...');
      navigate('/login', { replace: true });
    }
  }, [token, navigate]);

  return token ? <>{children}</> : null;
};

const App: React.FC = () => {
  const isAuthenticated = () => {
    const token = localStorage.getItem('token');
    console.log('Checking authentication - token:', token);
    return !!token;
  };

  return (
    <Router>
      <Routes>
        <Route path="/login" element={
          isAuthenticated() ? <Navigate to="/dashboard" replace /> : <Login />
        } />
        <Route path="/dashboard" element={
          <AuthWrapper>
            <Dashboard />
          </AuthWrapper>
        } />
        <Route path="/" element={<Navigate to="/login" replace />} />
      </Routes>
    </Router>
  );
};

export default App; 