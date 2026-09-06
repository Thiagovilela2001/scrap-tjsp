import React from 'react';
import { Moon, PanelLeft, Sun } from 'lucide-react';

export default function Header({ theme, toggleTheme, online, toggleSidebar, isSidebarOpen }) {
  return (
    <header className="header">
      <div className="header-left">
        <button
          type="button"
          className={`sidebar-toggle-btn ${isSidebarOpen ? 'active' : ''}`}
          onClick={toggleSidebar}
          aria-label={isSidebarOpen ? 'Fechar arquivo de pesquisa' : 'Abrir arquivo de pesquisa'}
          aria-expanded={isSidebarOpen}
          aria-controls="research-sidebar"
        >
          <PanelLeft size={17} aria-hidden="true" />
        </button>
        <div className="brand" aria-label="Juris">
          <span className="brand-monogram" aria-hidden="true">J.</span>
          <span className="brand-wordmark">Juris</span>
          <span className="brand-divider" aria-hidden="true" />
          <span className="brand-context">Pesquisa de precedentes</span>
        </div>
      </div>
      <div className="header-actions">
        <div className="status-pill" role="status">
          <span className={`status-dot ${online ? 'online' : 'offline'}`} aria-hidden="true" />
          <span>{online ? 'Base disponível' : 'Base indisponível'}</span>
        </div>
        <button
          type="button"
          className="theme-toggle-btn"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Usar tema claro' : 'Usar tema escuro'}
        >
          {theme === 'dark' ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
        </button>
      </div>
    </header>
  );
}
