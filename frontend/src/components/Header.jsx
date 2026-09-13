import { Button } from "@/components/ui/button";
import React from 'react';
import { Moon, PanelLeft, Sun } from 'lucide-react';

export default function Header({ theme, toggleTheme, online, toggleSidebar, isSidebarOpen }) {
  return (
    <header className="header">
      <div className="header-left">
        <Button
          variant="ghost"
          size="icon"
          type="button"
          className={`sidebar-toggle-btn ${isSidebarOpen ? 'active' : ''}`}
          onClick={toggleSidebar}
          aria-label={isSidebarOpen ? 'Fechar arquivo de pesquisa' : 'Abrir arquivo de pesquisa'}
          aria-expanded={isSidebarOpen}
          aria-controls="research-sidebar"
        >
          <PanelLeft size={17} aria-hidden="true" />
        </Button>

        <div className="brand" aria-label="Juris">
          <span className="brand-wordmark">Juris</span>
          <span className="brand-divider" aria-hidden="true" />
          <span className="brand-context">Pesquisa de precedentes</span>
        </div>
      </div>

      <div className="header-actions">
        <div className="status-pill" role="status" title="Estado da conexão">
          <span className={`status-dot ${online ? 'online' : 'offline'}`} aria-hidden="true" />
          <span>{online ? 'Conectado' : 'Sem conexão'}</span>
        </div>

        <Button
          variant="ghost"
          size="icon"
          type="button"
          className="theme-toggle-btn"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Usar tema claro' : 'Usar tema escuro'}
        >
          {theme === 'dark' ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
        </Button>
      </div>
    </header>
  );
}
