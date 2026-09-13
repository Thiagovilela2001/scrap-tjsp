import React from 'react';
import { Search, Files, History } from 'lucide-react';

export default function MobileNavigation({ view, onChange, resultCount, loading }) {
  const items = [
    { id: 'search', label: 'Pesquisa', Icon: Search },
    { id: 'results', label: 'Resultados', Icon: Files, count: resultCount },
    { id: 'archive', label: 'Arquivo', Icon: History },
  ];
  return (
    <nav className="mobile-navigation" aria-label="Navegação principal">
      {items.map(({ id, label, Icon, count }) => (
        <button key={id} type="button" aria-current={view === id ? 'page' : undefined}
          onClick={() => onChange(id)}>
          <span className="mobile-nav-icon"><Icon size={20} aria-hidden="true" />
            {count > 0 && <span className="mobile-nav-count">{count}</span>}
          </span>
          <span>{id === 'results' && loading ? 'Pesquisando…' : label}</span>
        </button>
      ))}
    </nav>
  );
}
