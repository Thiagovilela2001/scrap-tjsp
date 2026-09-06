import React, { useState } from 'react';
import { AlertTriangle, ArrowUpRight, Check, ChevronDown, Copy, FileText, Quote } from 'lucide-react';

export default function DecisionCard({ decisao, onOpenPdf, isSelected, onToggleSelect, index = 0 }) {
  const [expanded, setExpanded] = useState(false);
  const [copiedNum, setCopiedNum] = useState(false);
  const [copiedCitation, setCopiedCitation] = useState(false);

  const numProcesso = decisao.processo || `Acórdão nº ${decisao.cd_acordao}`;
  const relevancia = decisao.relevancia != null ? Math.round(decisao.relevancia * 100) : null;
  const courtSigla = decisao.tribunal || (decisao.orgao_julgador?.startsWith('TJ') ? decisao.orgao_julgador.slice(0, 4) : 'TJSP');

  const generateCitation = () => {
    const details = [
      decisao.comarca,
      decisao.orgao_julgador || courtSigla,
      decisao.relator ? `Rel. ${decisao.relator}` : '',
      decisao.data_julgamento ? `j. ${decisao.data_julgamento}` : '',
    ].filter(Boolean).join(', ');
    return `${courtSigla}, ${numProcesso}, ${details}. Disponível em: ${decisao.inteiro_teor_url || 'portal oficial do tribunal'}.`;
  };

  const copyText = async (text, setCopied) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <article className={`precedent-card ${isSelected ? 'selected' : ''}`}>
      <div className="precedent-index" aria-hidden="true">
        <span>{String(index + 1).padStart(2, '0')}</span>
        <span className="precedent-index-line" />
      </div>

      <div className="precedent-content">
        <header className="card-top-row">
          <div className="card-identity">
            <label className="custom-checkbox-wrapper">
              <input type="checkbox" checked={Boolean(isSelected)} onChange={onToggleSelect} className="custom-checkbox" />
              <span className="checkbox-box" aria-hidden="true">{isSelected && <Check size={12} />}</span>
              <span className="sr-only">Selecionar {numProcesso} para minuta</span>
            </label>
            <div className="process-id-wrap">
              <span className="court-prefix-tag">{courtSigla}</span>
              <h3 className="process-number-text">{numProcesso}</h3>
              <button type="button" className="action-icon-btn" onClick={() => copyText(numProcesso, setCopiedNum)} aria-label="Copiar número do processo">
                {copiedNum ? <Check size={14} /> : <Copy size={14} />}
              </button>
            </div>
          </div>
          {relevancia != null && (
            <div className="relevance-score" aria-label={`${relevancia}% de aderência`}>
              <span className="relevance-number">{relevancia}</span><span className="relevance-percent">%</span>
              <span className="relevance-label">aderência</span>
            </div>
          )}
        </header>

        <dl className="metadata-chips-row">
          {decisao.orgao_julgador && <div className="meta-chip"><dt>Órgão</dt><dd>{decisao.orgao_julgador}</dd></div>}
          {decisao.relator && <div className="meta-chip"><dt>Relatoria</dt><dd>{decisao.relator}</dd></div>}
          {decisao.data_julgamento && <div className="meta-chip"><dt>Julgamento</dt><dd>{decisao.data_julgamento}</dd></div>}
          {decisao.classe && <div className="meta-chip"><dt>Classe</dt><dd>{decisao.classe}</dd></div>}
        </dl>

        {(decisao.argumento || decisao.aderencia_fatica) && (
          <section className="case-fit-panel" aria-label="Aplicação ao caso">
            <span className="case-fit-header">Aplicação ao caso</span>
            <p className="case-fit-body">{decisao.argumento || decisao.aderencia_fatica}</p>
            {decisao.ressalva && <div className="case-fit-caveat"><AlertTriangle size={14} aria-hidden="true" /><span><strong>Ressalva:</strong> {decisao.ressalva}</span></div>}
          </section>
        )}

        {decisao.ementa && (
          <section className={`ementa-section ${expanded ? 'expanded' : ''}`}>
            <button type="button" className="ementa-toggle-btn" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
              <span>{expanded ? 'Recolher ementa' : 'Ler ementa oficial'}</span>
              <ChevronDown size={15} aria-hidden="true" />
            </button>
            {expanded && <blockquote className="ementa-content-box"><p className="ementa-text">{decisao.ementa}</p></blockquote>}
          </section>
        )}

        <footer className="card-action-footer">
          <button className="btn-read-pdf" type="button" onClick={() => onOpenPdf(`/documentos/${decisao.cd_acordao}`, numProcesso, decisao.orgao_julgador || 'Documento oficial')}>
            <FileText size={15} aria-hidden="true" /> Inteiro teor
          </button>
          <button type="button" className="citation-quick-btn" onClick={() => copyText(generateCitation(), setCopiedCitation)}>
            {copiedCitation ? <Check size={14} aria-hidden="true" /> : <Quote size={14} aria-hidden="true" />}
            {copiedCitation ? 'Citação copiada' : 'Copiar citação'}
          </button>
          {decisao.inteiro_teor_url && <a className="btn-tribunal-ext" href={decisao.inteiro_teor_url} target="_blank" rel="noreferrer">Portal do tribunal <ArrowUpRight size={14} aria-hidden="true" /></a>}
        </footer>
      </div>
    </article>
  );
}
