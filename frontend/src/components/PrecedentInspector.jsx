import React, { useState } from 'react';
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import {
  FileText,
  Copy,
  Check,
  Quote,
  ArrowUpRight,
  AlertTriangle,
} from 'lucide-react';

export default function PrecedentInspector({
  decisao,
  isSelected,
  onToggleSelect,
  onOpenPdf,
}) {
  const [copiedNum, setCopiedNum] = useState(false);
  const [copiedCitation, setCopiedCitation] = useState(false);
  const [activeTab, setActiveTab] = useState('ementa'); // 'ementa' | 'aplicacao'

  if (!decisao) {
    return (
      <aside className="precedent-inspector empty" aria-label="Painel de leitura">
        <div className="inspector-empty-state">
          <span className="inspector-empty-label">Leitura do precedente</span>
          <h3>Selecione um precedente</h3>
          <p>Clique em qualquer acórdão na lista ao lado para inspecionar a íntegra, fundamentos e dados processuais.</p>
        </div>
      </aside>
    );
  }

  const numProcesso = decisao.processo || `Acórdão nº ${decisao.cd_acordao}`;
  const courtSigla = decisao.tribunal || (decisao.orgao_julgador?.startsWith('TJ') ? decisao.orgao_julgador.slice(0, 4) : 'TJSP');
  const relevancia = decisao.relevancia != null ? Math.round(decisao.relevancia * 100) : null;
  const applicationAvailable = Boolean(decisao.argumento || decisao.aderencia_fatica);
  const displayedTab = activeTab === 'aplicacao' && applicationAvailable ? 'aplicacao' : 'ementa';

  const handleTabKeyDown = (event) => {
    const nextTab = {
      ArrowLeft: 'ementa',
      ArrowUp: 'ementa',
      Home: 'ementa',
      ArrowRight: applicationAvailable ? 'aplicacao' : 'ementa',
      ArrowDown: applicationAvailable ? 'aplicacao' : 'ementa',
      End: applicationAvailable ? 'aplicacao' : 'ementa',
    }[event.key];

    if (!nextTab) return;
    event.preventDefault();
    setActiveTab(nextTab);
    document.getElementById(`precedent-tab-${nextTab}`)?.focus();
  };

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
      toast.success('Texto copiado para a área de transferência.');
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Não foi possível copiar o texto.');
      setCopied(false);
    }
  };

  return (
    <aside className="precedent-inspector" aria-label="Inspeção detalhada do precedente">
      {/* Header do Inspetor */}
      <header className="inspector-header">
        <div className="inspector-title-row">
          <div className="inspector-meta-lead">
            <span className="court-pill-badge">{courtSigla}</span>
            <span className="inspector-class-tag">{decisao.classe || 'Acórdão'}</span>
          </div>

          {relevancia != null && (
            <div className={`inspector-score-pill ${relevancia >= 85 ? 'score-high' : 'score-medium'}`}>
              <span>{relevancia}% aderência</span>
            </div>
          )}
        </div>

        <div className="inspector-process-box">
          <label className="inspector-select-toggle" title="Incluir na minuta">
            <Checkbox
              checked={Boolean(isSelected)}
              onCheckedChange={onToggleSelect}
              aria-label={`Incluir processo ${numProcesso} no caderno de minuta`}
            />
            <span className="inspector-process-num">{numProcesso}</span>
          </label>

          <Button
            variant="ghost"
            size="icon"
            className="inspector-copy-btn"
            onClick={() => copyText(numProcesso, setCopiedNum)}
            aria-label="Copiar número do processo"
          >
            {copiedNum ? <Check size={14} /> : <Copy size={14} />}
          </Button>
        </div>

        {/* Metadados resumidos */}
        <div className="inspector-meta-grid">
          {decisao.orgao_julgador && (
            <div className="inspector-meta-item">
              <span className="inspector-meta-label">Órgão julgador</span>
              <span>{decisao.orgao_julgador}</span>
            </div>
          )}
          {decisao.relator && (
            <div className="inspector-meta-item">
              <span className="inspector-meta-label">Relatoria</span>
              <span>{decisao.relator}</span>
            </div>
          )}
          {decisao.data_julgamento && (
            <div className="inspector-meta-item">
              <span className="inspector-meta-label">Julgamento</span>
              <span>{decisao.data_julgamento}</span>
            </div>
          )}
        </div>

        {/* Ações Rápidas do Inspetor */}
        <div className="inspector-action-bar">
          <Button
            variant="default"
            size="sm"
            className="inspector-pdf-btn"
            onClick={() => onOpenPdf(`/documentos/${decisao.cd_acordao}`, numProcesso, decisao.orgao_julgador || 'Documento oficial')}
          >
            <FileText size={14} aria-hidden="true" />
            <span>Ver Inteiro Teor</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="inspector-cite-btn"
            onClick={() => copyText(generateCitation(), setCopiedCitation)}
          >
            {copiedCitation ? <Check size={14} /> : <Quote size={14} />}
            <span>{copiedCitation ? 'Citação Copiada' : 'Copiar Citação'}</span>
          </Button>

          {decisao.inteiro_teor_url && (
            <a
              className="inspector-ext-link"
              href={decisao.inteiro_teor_url}
              target="_blank"
              rel="noreferrer"
              title="Abrir no portal do tribunal"
            >
              <ArrowUpRight size={15} />
            </a>
          )}
        </div>

        {/* Tabs de Conteúdo */}
        <div className="inspector-tab-nav" role="tablist" aria-label="Conteúdo do precedente">
          <button
            id="precedent-tab-ementa"
            type="button"
            role="tab"
            aria-selected={displayedTab === 'ementa'}
            aria-controls="precedent-panel-ementa"
            tabIndex={displayedTab === 'ementa' ? 0 : -1}
            className={`inspector-tab-btn ${displayedTab === 'ementa' ? 'active' : ''}`}
            onClick={() => setActiveTab('ementa')}
            onKeyDown={handleTabKeyDown}
          >
            Ementa Oficial
          </button>
          {applicationAvailable && (
            <button
              id="precedent-tab-aplicacao"
              type="button"
              role="tab"
              aria-selected={displayedTab === 'aplicacao'}
              aria-controls="precedent-panel-aplicacao"
              tabIndex={displayedTab === 'aplicacao' ? 0 : -1}
              className={`inspector-tab-btn ${displayedTab === 'aplicacao' ? 'active' : ''}`}
              onClick={() => setActiveTab('aplicacao')}
              onKeyDown={handleTabKeyDown}
            >
              Subsunção & Aplicação
            </button>
          )}
        </div>
      </header>

      {/* Corpo com scroll */}
      <div className="inspector-body">
        {displayedTab === 'aplicacao' && (
          <section id="precedent-panel-aplicacao" role="tabpanel" aria-labelledby="precedent-tab-aplicacao" className="inspector-fit-section">
            <div className="inspector-fit-card">
              <span className="fit-kicker">Análise de Aderência Fática</span>
              <p className="fit-text">{decisao.argumento || decisao.aderencia_fatica}</p>
              {decisao.ressalva && (
                <div className="fit-warning">
                  <AlertTriangle size={15} aria-hidden="true" />
                  <span><strong>Ressalva jurídica:</strong> {decisao.ressalva}</span>
                </div>
              )}
            </div>
          </section>
        )}

        {displayedTab === 'ementa' && (
          <section id="precedent-panel-ementa" role="tabpanel" aria-labelledby="precedent-tab-ementa" className="inspector-ementa-section">
            <div className="inspector-quote-box">
              <p className="inspector-ementa-text">{decisao.ementa || 'Ementa oficial não disponível.'}</p>
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}
