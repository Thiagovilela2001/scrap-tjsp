import { Button } from "@/components/ui/button";
import React from 'react';
import { Clock3, FileStack, Filter, Trash2, X } from 'lucide-react';
import CourtSelector from './CourtSelector';

export default function Sidebar({ isOpen, onClose, history, onSelectHistory, onClearHistory, onDeleteHistoryItem, results, selectedChamberFilter, onSelectChamberFilter, selectedCount, activeCourtCodes, selectedCourtCodes, onCourtSelectionChange, loading, isMobile = false }) {
  const processos = results?.processos || [];
  const uniqueOrgaos = [...new Set(processos.map((processo) => processo.orgao_julgador).filter(Boolean))];
  const uniqueTribunais = [...new Set(processos.map((processo) => processo.tribunal).filter(Boolean))];
  const avgRelevance = processos.length
    ? Math.round(processos.reduce((total, processo) => total + (processo.relevancia || 0), 0) / processos.length * 100)
    : 0;

  return (
    <aside id="research-sidebar" tabIndex={-1} className={`studio-sidebar ${isOpen ? 'open' : ''}`} aria-label="Arquivo de pesquisa">
      <div className="sidebar-header">
        <div>{isMobile && <span className="sidebar-eyebrow">Suas consultas</span>}<h2 id={isMobile ? 'mobile-view-title' : undefined} tabIndex={isMobile ? -1 : undefined} className="sidebar-title">Arquivo de pesquisa</h2></div>
        <Button variant="ghost" size="icon" type="button" className="sidebar-close-btn" onClick={onClose} aria-label="Fechar arquivo"><X size={17} aria-hidden="true" /></Button>
      </div>
      <div className="sidebar-scrollable">
        {!isMobile && <CourtSelector
          activeCodes={activeCourtCodes}
          selectedCodes={selectedCourtCodes}
          onChange={onCourtSelectionChange}
          disabled={loading}
          compact
        />}
        {processos.length > 0 && (
          <section className="sidebar-section sidebar-analysis" aria-labelledby="analysis-title">
            <div className="sidebar-section-header"><h3 id="analysis-title">Leitura do conjunto</h3><FileStack size={14} aria-hidden="true" /></div>
            <dl className="metrics-grid">
              <div className="metric-box"><dt>Precedentes</dt><dd>{processos.length}</dd></div>
              <div className="metric-box"><dt>Aderência média</dt><dd>{avgRelevance}%</dd></div>
              <div className="metric-box"><dt>Tribunais</dt><dd>{uniqueTribunais.length || 1}</dd></div>
              <div className="metric-box"><dt>Selecionados</dt><dd>{selectedCount}</dd></div>
            </dl>
            {(uniqueTribunais.length > 1 || uniqueOrgaos.length > 0) && (
              <div className="chamber-filter-group">
                <div className="filter-group-label"><Filter size={12} aria-hidden="true" /> Filtrar relatório</div>
                <div className="chamber-tags">
                  <Button variant="ghost" size="default" type="button" className={`chamber-tag-btn ${selectedChamberFilter === 'all' ? 'active' : ''}`} onClick={() => onSelectChamberFilter('all')}>Todos · {processos.length}</Button>
                  {uniqueTribunais.map((tribunal) => <Button variant="ghost" size="default" key={tribunal} type="button" className={`chamber-tag-btn ${selectedChamberFilter === tribunal ? 'active' : ''}`} onClick={() => onSelectChamberFilter(tribunal)}>{tribunal} · {processos.filter((processo) => processo.tribunal === tribunal).length}</Button>)}
                  {uniqueOrgaos.map((orgao) => <Button variant="ghost" size="default" key={orgao} type="button" className={`chamber-tag-btn ${selectedChamberFilter === orgao ? 'active' : ''}`} onClick={() => onSelectChamberFilter(orgao)} title={orgao}>{orgao}</Button>)}
                </div>
              </div>
            )}
          </section>
        )}
        <section className="sidebar-section" aria-labelledby="history-title">
          <div className="sidebar-section-header">
            <h3 id="history-title"><Clock3 size={14} aria-hidden="true" /> Histórico</h3>
            {history.length > 0 && <Button variant="ghost" size="default" type="button" className="clear-history-btn" onClick={onClearHistory}>Limpar</Button>}
          </div>
          {history.length > 0 ? (
            <ol className="history-list">
              {history.map((item, index) => (
                <li key={item} className="history-item">
                  <span className="history-index">{String(index + 1).padStart(2, '0')}</span>
                  <Button variant="ghost" size="default" type="button" className="history-query-btn" onClick={() => onSelectHistory(item)} title={item}><span className="history-text">{item}</span></Button>
                  <Button variant="ghost" size="icon" type="button" className="history-del-btn" onClick={() => onDeleteHistoryItem(item)} aria-label={`Excluir pesquisa: ${item}`}><Trash2 size={13} aria-hidden="true" /></Button>
                </li>
              ))}
            </ol>
          ) : <p className="sidebar-empty-state">Consultas recentes aparecerão aqui.</p>}
        </section>
        <footer className="sidebar-footer-info"><span>Fontes oficiais</span><small>Acórdãos e metadados dos Tribunais de Justiça.</small></footer>
      </div>
    </aside>
  );
}
