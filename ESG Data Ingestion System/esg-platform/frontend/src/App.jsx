import React from 'react';
import { Routes, Route, NavLink, Navigate } from 'react-router-dom';
import UploadPage from './pages/UploadPage';
import DashboardPage from './pages/DashboardPage';

function Sidebar() {
  return (
    <nav className="sidebar" aria-label="Main navigation">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">🌿</div>
        <div className="sidebar-logo-text">
          <strong>ESG Platform</strong>
          <span>Data Ingestion</span>
        </div>
      </div>

      <NavLink
        id="nav-upload"
        to="/upload"
        className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
      >
        <span className="nav-icon">⬆️</span>
        Upload Data
      </NavLink>

      <NavLink
        id="nav-dashboard"
        to="/dashboard"
        className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
      >
        <span className="nav-icon">📊</span>
        Review Dashboard
      </NavLink>

      <div style={{ marginTop: 'auto', paddingTop: 'var(--space-6)', borderTop: '1px solid var(--border-subtle)' }}>
        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>GHG Protocol Scopes</div>
          <div>🟠 Scope 1 — Direct combustion</div>
          <div>🔵 Scope 2 — Purchased electricity</div>
          <div>🟣 Scope 3 — Indirect value chain</div>
        </div>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <div className="layout">
      <Sidebar />
      <main className="main-content" id="main-content">
        <Routes>
          <Route path="/" element={<Navigate to="/upload" replace />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </main>
    </div>
  );
}
