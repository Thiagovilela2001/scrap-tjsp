import React from 'react';
import { Sun, Moon, PanelLeft, Scale } from 'lucide-react';

export default function Header({ 
  theme, 
  toggleTheme, 
  online, 
  toggleSidebar, 
  isSidebarOpen 
}) {
  return (
    <header className="header">
      <div className="header-left">
        <button
          className={`sidebar-toggle-btn ${isSidebarOpen ? 'active' : ''}`}
          onClick={toggleSidebar}
          aria-label="Alternar painel lateral"
          title="Alternar painel lateral (Histórico e Filtros)"
        >
          <PanelLeft size={16} />
        </button>

        <div className="brand">
          <div className="brand-badge">
            <Scale size={18} strokeWidth={2.2} />
          </div>
          <div className="brand-info">
            <div className="brand-title-row">
              <h1>Juris TJSP</h1>
              <span className="brand-tier-tag">Inteligência Judicial</span>
            </div>
            <span className="brand-subtitle">Tribunal de Justiça de São Paulo • Pesquisa & Minutas</span>
          </div>
        </div>
      </div>

      <div className="header-actions">
        <div className="status-pill" title={online ? 'Servidor de Jurisprudência Conectado' : 'Conectando...'}>
          <span className={`status-dot ${online ? 'online' : 'offline'}`} />
          <span>{online ? 'TJSP Conectado' : 'Conectando...'}</span>
        </div>

        <button
          className="theme-toggle-btn"
          onClick={toggleTheme}
          aria-label="Alternar tema claro e escuro"
          title={theme === 'dark' ? 'Alternar para tema claro' : 'Alternar para tema escuro'}
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  );
}
