import React, { useRef, useState } from 'react';
import { Check, ChevronDown, ChevronUp, Minus } from 'lucide-react';
import { COURT_GROUPS } from '../data/courts';

export default function CourtSelector({ activeCodes, selectedCodes, onChange, disabled, compact = false }) {
  const [activeGroup, setActiveGroup] = useState('estaduais');
  const [collapsed, setCollapsed] = useState(false);
  const tabRefs = useRef([]);
  const group = COURT_GROUPS.find((item) => item.id === activeGroup) || COURT_GROUPS[2];
  const available = group.courts.filter((court) => activeCodes.has(court.code));
  const selectedAvailable = available.filter((court) => selectedCodes.has(court.code));
  const allSelected = available.length > 0 && selectedAvailable.length === available.length;

  const toggleCourt = (code) => {
    const next = new Set(selectedCodes);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    onChange(next);
  };

  const toggleAll = () => {
    const next = new Set(selectedCodes);
    available.forEach((court) => {
      if (allSelected) next.delete(court.code);
      else next.add(court.code);
    });
    onChange(next);
  };

  const handleTabKeyDown = (event, index) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    let nextIndex = index;
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % COURT_GROUPS.length;
    if (event.key === 'ArrowLeft') nextIndex = (index - 1 + COURT_GROUPS.length) % COURT_GROUPS.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = COURT_GROUPS.length - 1;
    setActiveGroup(COURT_GROUPS[nextIndex].id);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <section className={`court-selector ${compact ? 'court-selector-compact' : ''} ${collapsed ? 'collapsed' : ''}`} aria-labelledby="court-selector-title">
      <div className="court-selector-heading">
        <div><span className="search-kicker">Escopo</span><h3 id="court-selector-title">Onde pesquisar</h3></div>
        <span className="court-selection-summary" aria-live="polite">
          {selectedCodes.size} {selectedCodes.size === 1 ? 'tribunal selecionado' : 'tribunais selecionados'}
        </span>
        {compact && (
          <button
            type="button"
            className="court-selector-toggle"
            onClick={() => setCollapsed((current) => !current)}
            aria-expanded={!collapsed}
            aria-controls={`court-selector-content court-panel-${group.id}`}
            aria-label={collapsed ? 'Expandir Onde pesquisar' : 'Minimizar Onde pesquisar'}
            title={collapsed ? 'Expandir' : 'Minimizar'}
          >
            {collapsed ? <ChevronDown size={17} aria-hidden="true" /> : <ChevronUp size={17} aria-hidden="true" />}
          </button>
        )}
      </div>

      <div id="court-selector-content" className="court-tabs" role="tablist" aria-label="Competência dos tribunais">
        {COURT_GROUPS.map((item, index) => {
          const activeCount = item.courts.filter((court) => activeCodes.has(court.code)).length;
          const selected = item.id === activeGroup;
          return (
            <button key={item.id} ref={(node) => { tabRefs.current[index] = node; }}
              id={`court-tab-${item.id}`} type="button" role="tab" aria-selected={selected}
              aria-controls={`court-panel-${item.id}`} tabIndex={selected ? 0 : -1}
              className={`court-tab ${selected ? 'active' : ''}`} onClick={() => setActiveGroup(item.id)}
              onKeyDown={(event) => handleTabKeyDown(event, index)}>
              <span>{item.shortLabel}</span><small>{activeCount}/{item.courts.length}</small>
            </button>
          );
        })}
      </div>

      <div id={`court-panel-${group.id}`} role="tabpanel" aria-labelledby={`court-tab-${group.id}`} className="court-panel">
        <div className="court-panel-toolbar">
          <span>{group.label}</span>
          <button type="button" className="court-select-all" onClick={toggleAll} disabled={disabled || !available.length}>
            {allSelected ? <Minus size={13} aria-hidden="true" /> : <Check size={13} aria-hidden="true" />}
            {allSelected ? 'Limpar seleção' : 'Selecionar todos disponíveis'}
          </button>
        </div>

        <div className="court-grid">
          {group.courts.map((court) => {
            const availableCourt = activeCodes.has(court.code);
            const checked = selectedCodes.has(court.code);
            return (
              <label key={court.code} className={`court-option ${availableCourt ? '' : 'unavailable'}`}>
                <input type="checkbox" checked={checked} disabled={disabled || !availableCourt}
                  onChange={() => toggleCourt(court.code)} />
                <span className="court-option-check" aria-hidden="true">{checked && <Check size={12} />}</span>
                <span className="court-option-copy"><strong>{court.acronym}</strong><small>{court.name}</small></span>
                <span className="court-option-status">{availableCourt ? 'Ativo' : 'Em integração'}</span>
              </label>
            );
          })}
        </div>
        {!available.length && <p className="court-empty-note" role="status">Adaptadores desta competência ainda não estão ativos. Catálogo pronto para próximas integrações.</p>}
      </div>
    </section>
  );
}
