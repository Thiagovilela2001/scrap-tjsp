import React from 'react';
import { 
  History, 
  Trash2, 
  Scale, 
  BarChart3, 
  ChevronRight,
  BookmarkCheck,
  X,
  SlidersHorizontal
} from 'lucide-react';

const TOPIC_PRESETS = [
  { label: 'Negativação indevida & Dano moral in re ipsa', query: 'Negativação indevida por dívida já paga. Cabe indenização por dano moral in re ipsa no TJSP?' },
  { label: 'Atraso de voo internacional & Extravio', query: 'Cancelamento e atraso excessivo de voo internacional gera dano moral presumido no TJSP?' },
  { label: 'Prescrição intercorrente na execução', query: 'Qual o termo inicial da prescrição intercorrente na execução de título extrajudicial segundo o TJSP?' },
  { label: 'Vício construtivo em imóvel & Infiltração', query: 'Prazo prescricional e decadencial para indenização de vício construtivo e infiltração em condomínio.' },
  { label: 'Golpe do PIX & Fortuito interno bancário', query: 'Responsabilidade civil de instituição financeira em golpe do PIX sob a ótica da Súmula 479 do STJ no TJSP.' },
];

export default function Sidebar({
  isOpen,
  onClose,
  history,
  onSelectHistory,
  onClearHistory,
  onDeleteHistoryItem,
  results,
  selectedChamberFilter,
  onSelectChamberFilter,
  selectedCount,
  onSelectPreset,
}) {
  const processos = results?.processos || [];
  const uniqueOrgaos = [...new Set(processos.map((p) => p.orgao_julgador).filter(Boolean))];
  const uniqueTribunais = [...new Set(processos.map((p) => p.tribunal).filter(Boolean))];
  const avgRelevance = processos.length 
    ? Math.round((processos.reduce((acc, p) => acc + (p.relevancia || 0), 0) / processos.length) * 100) 
    : 0;

  return (
    <aside className={`studio-sidebar ${isOpen ? 'open' : ''}`}>
      <div className="sidebar-header">
        <div className="sidebar-title">
          <Scale size={16} />
          <span>Painel Jurídico</span>
        </div>
        <button 
          className="sidebar-close-btn" 
          onClick={onClose}
          aria-label="Fechar painel lateral"
        >
          <X size={16} />
        </button>
      </div>

      <div className="sidebar-scrollable">
        {/* Research Metrics Widget */}
        {results && processos.length > 0 && (
          <section className="sidebar-section">
            <div className="sidebar-section-header">
              <span>Análise da Pesquisa</span>
            </div>
            
            <div className="metrics-grid">
              <div className="metric-box">
                <span className="metric-value">{processos.length}</span>
                <span className="metric-label">Precedentes</span>
              </div>
              <div className="metric-box">
                <span className="metric-value">{avgRelevance}%</span>
                <span className="metric-label">Aderência Média</span>
              </div>
              <div className="metric-box">
                <span className="metric-value">{uniqueTribunais.length || 1}</span>
                <span className="metric-label">Tribunais</span>
              </div>
              <div className="metric-box">
                <span className="metric-value">{selectedCount}</span>
                <span className="metric-label">Para Minuta</span>
              </div>
            </div>

            {uniqueTribunais.length > 1 && (
              <div className="chamber-filter-group" style={{ marginBottom: '8px' }}>
                <label className="filter-group-label">
                  <SlidersHorizontal size={12} /> Filtrar por Tribunal:
                </label>
                <div className="chamber-tags">
                  <button
                    type="button"
                    className={`chamber-tag-btn ${selectedChamberFilter === 'all' ? 'active' : ''}`}
                    onClick={() => onSelectChamberFilter('all')}
                  >
                    Todos os Tribunais ({processos.length})
                  </button>
                  {uniqueTribunais.map((trib, i) => {
                    const count = processos.filter((p) => p.tribunal === trib).length;
                    return (
                      <button
                        key={i}
                        type="button"
                        className={`chamber-tag-btn ${selectedChamberFilter === trib ? 'active' : ''}`}
                        onClick={() => onSelectChamberFilter(trib)}
                        title={trib}
                      >
                        {trib} ({count})
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {uniqueOrgaos.length > 0 && (
              <div className="chamber-filter-group">
                <label className="filter-group-label">
                  <SlidersHorizontal size={12} /> Filtrar por Órgão:
                </label>
                <div className="chamber-tags">
                  <button
                    type="button"
                    className={`chamber-tag-btn ${selectedChamberFilter === 'all' ? 'active' : ''}`}
                    onClick={() => onSelectChamberFilter('all')}
                  >
                    Todos ({processos.length})
                  </button>
                  {uniqueOrgaos.map((org, i) => {
                    const count = processos.filter((p) => p.orgao_julgador === org).length;
                    return (
                      <button
                        key={i}
                        type="button"
                        className={`chamber-tag-btn ${selectedChamberFilter === org ? 'active' : ''}`}
                        onClick={() => onSelectChamberFilter(org)}
                        title={org}
                      >
                        {org} ({count})
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </section>
        )}

        {/* History Section */}
        <section className="sidebar-section">
          <div className="sidebar-section-header">
            <span>Histórico de Pesquisas</span>
            {history && history.length > 0 && (
              <button 
                className="clear-history-btn" 
                onClick={onClearHistory}
                title="Limpar todo o histórico"
              >
                Limpar
              </button>
            )}
          </div>

          {history && history.length > 0 ? (
            <ul className="history-list">
              {history.map((item, idx) => (
                <li key={idx} className="history-item">
                  <button
                    type="button"
                    className="history-query-btn"
                    onClick={() => onSelectHistory(item)}
                    title={item}
                  >
                    <ChevronRight size={12} className="history-arrow" />
                    <span className="history-text">{item}</span>
                  </button>
                  <button
                    type="button"
                    className="history-del-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteHistoryItem(item);
                    }}
                    title="Excluir item"
                  >
                    <Trash2 size={12} />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="sidebar-empty-state">
              <span>Nenhuma pesquisa recente.</span>
            </div>
          )}
        </section>

        {/* Recurrent Legal Topics */}
        <section className="sidebar-section">
          <div className="sidebar-section-header">
            <span>Teses Recorrentes TJSP</span>
          </div>

          <div className="presets-list">
            {TOPIC_PRESETS.map((preset, idx) => (
              <button
                key={idx}
                type="button"
                className="preset-card-btn"
                onClick={() => onSelectPreset(preset.query)}
              >
                <div className="preset-pill-title">{preset.label}</div>
                <div className="preset-pill-snippet">{preset.query}</div>
              </button>
            ))}
          </div>
        </section>

        {/* Footer info */}
        <div className="sidebar-footer-info">
          <div className="court-badge-row">
            <div className="court-dot-live" />
            <span>Repositório Jurisprudencial TJSP</span>
          </div>
          <small>Consultas a acórdãos oficiais de Direito Privado e Público.</small>
        </div>
      </div>
    </aside>
  );
}
