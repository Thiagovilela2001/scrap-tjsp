import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible } from '@base-ui/react/collapsible';
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import React, { useState } from 'react';
import { AlertTriangle, ArrowUpRight, Check, ChevronDown, Copy, FileText, Quote } from 'lucide-react';

export default function DecisionCard({
  decisao,
  onOpenPdf,
  isSelected,
  onToggleSelect,
  index = 0,
  isActive = false,
  onInspect,
}) {
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
      toast.success('Texto copiado.');
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Não foi possível copiar. Tente novamente.');
      setCopied(false);
    }
  };

  const handleCardClick = (e) => {
    // If the click is on an interactive element, do not trigger inspect
    if (e.target.closest('button, a, input, [role="checkbox"]')) {
      return;
    }
    if (onInspect) {
      onInspect(decisao);
    }
  };

  const handleCardKeyDown = (event) => {
    if (!onInspect || event.target !== event.currentTarget) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onInspect(decisao);
    }
  };

  return (
    <article
      className={`precedent-card ${isSelected ? 'selected' : ''} ${isActive ? 'active-inspected' : ''}`}
      onClick={handleCardClick}
      onKeyDown={handleCardKeyDown}
      tabIndex={onInspect ? 0 : undefined}
      aria-label={onInspect ? `Analisar precedente ${numProcesso}` : undefined}
    >
      <div className="precedent-index" aria-hidden="true">
        <span>{String(index + 1).padStart(2, '0')}</span>
        <span className="precedent-index-line" />
      </div>

      <div className="precedent-content">
        <header className="card-top-row">
          <div className="card-identity">
            <label className="custom-checkbox-wrapper">
              <Checkbox checked={Boolean(isSelected)} onCheckedChange={onToggleSelect} aria-label={`Selecionar ${numProcesso} para minuta`} />
              <span className="sr-only">Selecionar {numProcesso} para minuta</span>
            </label>
            <div className="process-id-wrap">
              <span className="court-prefix-tag">{courtSigla}</span>
              <h3 className="process-number-text">{numProcesso}</h3>
              <Button variant="ghost" size="icon" type="button" className="action-icon-btn" onClick={() => copyText(numProcesso, setCopiedNum)} aria-label="Copiar número do processo">
                {copiedNum ? <Check size={14} /> : <Copy size={14} />}
              </Button>
            </div>
          </div>
          {relevancia != null && (
            <div className={`relevance-score ${relevancia >= 85 ? 'high-score' : 'mid-score'}`} aria-label={`${relevancia}% de aderência`}>
              <div className="relevance-labels">
                <span className="relevance-label">Aderência</span>
                <span className="relevance-number">{relevancia}%</span>
              </div>
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
          <Collapsible.Root open={expanded} onOpenChange={setExpanded} render={<section />} className={`ementa-section ${expanded ? 'expanded' : ''}`}>
            <Collapsible.Trigger render={<Button variant="ghost" size="default" />} type="button" className="ementa-toggle-btn">
              <span>{expanded ? 'Recolher ementa' : 'Ler ementa oficial'}</span>
              <ChevronDown size={15} aria-hidden="true" />
            </Collapsible.Trigger>
            <Collapsible.Panel className="ementa-reveal"><blockquote className="ementa-content-box"><p className="ementa-text">{decisao.ementa}</p></blockquote></Collapsible.Panel>
          </Collapsible.Root>
        )}

        <footer className="card-action-footer">
          <Button variant="outline" size="default" className="btn-read-pdf" type="button" onClick={() => onOpenPdf(`/documentos/${decisao.cd_acordao}`, numProcesso, decisao.orgao_julgador || 'Documento oficial')}>
            <FileText size={15} aria-hidden="true" /> Inteiro teor
          </Button>
          <Button variant="outline" size="default" type="button" className="citation-quick-btn" onClick={() => copyText(generateCitation(), setCopiedCitation)}>
            {copiedCitation ? <Check size={14} aria-hidden="true" /> : <Quote size={14} aria-hidden="true" />}
            {copiedCitation ? 'Citação copiada' : 'Copiar citação'}
          </Button>
          {decisao.inteiro_teor_url && <a className="btn-tribunal-ext" href={decisao.inteiro_teor_url} target="_blank" rel="noreferrer">Portal do tribunal <ArrowUpRight size={14} aria-hidden="true" /></a>}
        </footer>
      </div>
    </article>
  );
}
