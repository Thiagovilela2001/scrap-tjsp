import React, { useState } from 'react';
import { 
  FileText, 
  ExternalLink, 
  ChevronDown, 
  ChevronUp, 
  Copy, 
  Check, 
  Quote, 
  Scale, 
  UserCheck, 
  Calendar,
  AlertTriangle
} from 'lucide-react';

export default function DecisionCard({
  decisao,
  onOpenPdf,
  isSelected,
  onToggleSelect,
}) {
  const [expanded, setExpanded] = useState(false);
  const [copiedNum, setCopiedNum] = useState(false);
  const [copiedCitation, setCopiedCitation] = useState(false);

  const numProcesso = decisao.processo || `Acórdão nº ${decisao.cd_acordao}`;
  const relevancia = decisao.relevancia != null ? Math.round(decisao.relevancia * 100) : null;

  const courtSigla = decisao.tribunal || (decisao.orgao_julgador && decisao.orgao_julgador.startsWith('TJ') ? decisao.orgao_julgador.slice(0, 4) : 'TJSP');

  // Format standard Brazilian judicial citation (ABNT / CPC)
  const generateAbntCitation = () => {
    const comarca = decisao.comarca ? `${decisao.comarca}, ` : '';
    const orgao = decisao.orgao_julgador || courtSigla;
    const relator = decisao.relator ? `Relator: ${decisao.relator}` : '';
    const data = decisao.data_julgamento ? `j. em ${decisao.data_julgamento}` : '';
    const details = [comarca, orgao, relator, data].filter(Boolean).join(', ');
    return `${courtSigla}; Processo nº ${numProcesso}; ${details}; Disponível em: ${decisao.inteiro_teor_url || 'https://esaj.tjsp.jus.br'}.`;
  };

  const handleCopyProcess = (e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(numProcesso);
    setCopiedNum(true);
    setTimeout(() => setCopiedNum(false), 2000);
  };

  const handleCopyCitation = (e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(generateAbntCitation());
    setCopiedCitation(true);
    setTimeout(() => setCopiedCitation(false), 2000);
  };

  return (
    <article className={`precedent-card ${isSelected ? 'selected' : ''}`}>
      {/* Top Header - Jusbrasil Style */}
      <div className="card-top-row">
        <div className="card-identity">
          <label className="custom-checkbox-wrapper" title="Selecionar precedente para a minuta">
            <input
              type="checkbox"
              checked={!!isSelected}
              onChange={onToggleSelect}
              className="custom-checkbox"
            />
            <span className="checkbox-box" />
          </label>

          <div className="process-id-wrap">
            <span className="court-prefix-tag">{courtSigla}</span>
            <span className="process-number-text">{numProcesso}</span>
            <button
              type="button"
              className="action-icon-btn"
              onClick={handleCopyProcess}
              title="Copiar número do processo"
            >
              {copiedNum ? <Check size={13} className="text-green" /> : <Copy size={13} />}
            </button>
          </div>
        </div>

        <div className="card-top-actions">
          <button
            type="button"
            className="citation-quick-btn"
            onClick={handleCopyCitation}
            title="Copiar citação formatada para petição"
          >
            {copiedCitation ? (
              <>
                <Check size={12} className="text-green" />
                <span>Citação Copiada</span>
              </>
            ) : (
              <>
                <Quote size={12} />
                <span>Copiar Citação</span>
              </>
            )}
          </button>

          {relevancia != null && (
            <div className={`relevance-badge ${relevancia >= 85 ? 'high' : relevancia >= 70 ? 'medium' : 'normal'}`}>
              <div className="relevance-dot" />
              <span>{relevancia}% Aderência</span>
            </div>
          )}
        </div>
      </div>

      {/* Metadata Line with Bullet Separators */}
      <div className="metadata-chips-row">
        {decisao.orgao_julgador && (
          <span className="meta-chip">
            <Scale size={12} /> {decisao.orgao_julgador}
          </span>
        )}
        {decisao.relator && (
          <>
            <span className="metadata-divider">•</span>
            <span className="meta-chip">
              <UserCheck size={12} /> Rel. <strong>{decisao.relator}</strong>
            </span>
          </>
        )}
        {decisao.data_julgamento && (
          <>
            <span className="metadata-divider">•</span>
            <span className="meta-chip">
              <Calendar size={12} /> Julgado em {decisao.data_julgamento}
            </span>
          </>
        )}
        {decisao.classe && (
          <>
            <span className="metadata-divider">•</span>
            <span className="meta-chip">{decisao.classe}</span>
          </>
        )}
      </div>

      {/* Case Fit Analysis / Legal Thesis Callout */}
      {(decisao.argumento || decisao.aderencia_fatica) && (
        <div className="case-fit-panel">
          <div className="case-fit-header">
            <strong>Destaque da Tese & Aplicação ao Caso</strong>
          </div>
          <p className="case-fit-body">{decisao.argumento || decisao.aderencia_fatica}</p>
          {decisao.ressalva && (
            <div className="case-fit-caveat">
              <AlertTriangle size={13} />
              <span><strong>Observação:</strong> {decisao.ressalva}</span>
            </div>
          )}
        </div>
      )}

      {/* Official Court Ementa Accordion */}
      {decisao.ementa && (
        <div className="ementa-section">
          <button
            type="button"
            className="ementa-toggle-btn"
            onClick={() => setExpanded(!expanded)}
          >
            <span>{expanded ? 'Ocultar Ementa Completa' : 'Exibir Ementa Oficial do Acórdão'}</span>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {expanded && (
            <div className="ementa-content-box">
              <p className="ementa-text">{decisao.ementa}</p>
            </div>
          )}
        </div>
      )}

      {/* Card Action Footer */}
      <div className="card-action-footer">
        <button
          className="btn-read-pdf"
          type="button"
          onClick={() =>
            onOpenPdf(
              `/documentos/${decisao.cd_acordao}`,
              numProcesso,
              decisao.orgao_julgador || 'Acórdão Oficial TJSP'
            )
          }
        >
          <FileText size={14} />
          <span>Visualizar Inteiro Teor (PDF)</span>
        </button>

        {decisao.inteiro_teor_url && (
          <a
            className="btn-tribunal-ext"
            href={decisao.inteiro_teor_url}
            target="_blank"
            rel="noreferrer"
          >
            <span>Consultar no e-SAJ TJSP</span>
            <ExternalLink size={12} />
          </a>
        )}
      </div>
    </article>
  );
}
