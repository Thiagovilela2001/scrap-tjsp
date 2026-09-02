import React, { useState } from 'react';
import { 
  X, 
  Copy, 
  Check, 
  Sparkles, 
  Send, 
  FileText, 
  Download, 
  FileDown,
  RefreshCw
} from 'lucide-react';
import { exportDraftToDocx } from '../utils/docxExport';

const QUICK_PROMPTS = [
  'Adicionar pedido de tutela de urgência / liminar',
  'Tornar a fundamentação mais direta e concisa',
  'Enfatizar o dano moral in re ipsa e quantificação',
  'Destacar responsabilidade objetiva e CDC',
  'Incluir síntese dos acórdãos em tópicos com negrito',
];

export default function DraftingCanvas({
  isOpen,
  onClose,
  draft,
  setDraft,
  selectedDecisions,
  originalQuery,
  topic,
}) {
  const [copied, setCopied] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [refining, setRefining] = useState(false);
  const [exportingDocx, setExportingDocx] = useState(false);

  if (!isOpen) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      alert('Não foi possível acessar a área de transferência.');
    }
  };

  const handleDownloadTxt = () => {
    const blob = new Blob([draft], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `minuta_jurisprudencia_tjsp_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportDocx = async () => {
    if (!draft || !draft.trim() || exportingDocx) return;
    setExportingDocx(true);
    try {
      await exportDraftToDocx({
        title: 'Minuta de Jurisprudência — TJSP',
        topic: topic || originalQuery,
        draftText: draft,
        selectedDecisions,
      });
    } catch (err) {
      console.error(err);
      alert('Erro ao gerar arquivo Word (.docx).');
    } finally {
      setExportingDocx(false);
    }
  };

  const handleRefine = async (instructionText) => {
    const textToSend = instructionText || chatInput;
    if (!textToSend || !textToSend.trim() || refining) return;

    setRefining(true);
    try {
      const res = await fetch('/tjsp/gerar-minuta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tema: topic || originalQuery,
          pergunta: originalQuery,
          acordaos_selecionados: selectedDecisions,
          instrucao: textToSend.trim(),
        }),
      });
      const data = await res.json();
      if (res.ok && data.minuta) {
        setDraft(data.minuta);
        setChatInput('');
      } else {
        alert(data.detail || 'Erro ao ajustar minuta.');
      }
    } catch {
      alert('Falha ao comunicar com o assistente.');
    } finally {
      setRefining(false);
    }
  };

  const wordCount = draft ? draft.trim().split(/\s+/).length : 0;

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drafting-modal-wrapper" role="dialog" aria-modal="true">
        {/* Studio Top Header */}
        <div className="drafting-header">
          <div className="drafting-title-group">
            <div className="drafting-icon-badge">
              <FileText size={16} />
            </div>
            <div>
              <div className="drafting-main-title">
                <h2>Minuta Jurídica com Precedentes TJSP</h2>
                <span className="precedents-count-badge">
                  {selectedDecisions.length} precedente(s) vinculado(s)
                </span>
              </div>
              <p className="drafting-subtitle">
                {topic ? `Tema: ${topic}` : 'Argumentação estruturada e pronta para petição.'}
              </p>
            </div>
          </div>

          <div className="drafting-header-actions">
            <div className="word-count-badge">
              {wordCount} palavras
            </div>

            <button
              type="button"
              className="draft-action-btn docx-btn"
              onClick={handleExportDocx}
              disabled={exportingDocx}
              title="Exportar Petição Formatada em Word (.docx)"
            >
              <FileDown size={14} />
              <span>{exportingDocx ? 'Gerando Word...' : 'Exportar .docx'}</span>
            </button>

            <button
              type="button"
              className="draft-action-btn"
              onClick={handleDownloadTxt}
              title="Baixar em formato texto simples (.txt)"
            >
              <Download size={13} />
              <span>.txt</span>
            </button>

            <button
              type="button"
              className={`draft-action-btn primary ${copied ? 'copied' : ''}`}
              onClick={handleCopy}
              title="Copiar texto completo para a área de transferência"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              <span>{copied ? 'Copiado!' : 'Copiar Petição'}</span>
            </button>

            <button
              type="button"
              className="drafting-close-btn"
              onClick={onClose}
              aria-label="Fechar editor de minuta"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Studio Editor Area */}
        <div className="drafting-editor-container">
          <textarea
            className="drafting-editor-textarea"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="A minuta jurídica estruturada aparecerá aqui..."
            spellCheck="true"
          />
        </div>

        {/* AI Co-Pilot Refinement Toolbar */}
        <div className="drafting-footer">
          <div className="quick-refinements-row">
            <span className="quick-refine-label">
              <Sparkles size={12} /> Ajustar com IA:
            </span>
            <div className="quick-refine-chips">
              {QUICK_PROMPTS.map((promptText, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="quick-refine-pill"
                  onClick={() => handleRefine(promptText)}
                  disabled={refining}
                >
                  {promptText}
                </button>
              ))}
            </div>
          </div>

          <form
            className="draft-refine-input-row"
            onSubmit={(e) => {
              e.preventDefault();
              handleRefine();
            }}
          >
            <input
              type="text"
              className="draft-refine-input"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Instrua a IA para calibrar teses, alterar o tom ou acrescentar pedidos..."
              disabled={refining}
            />

            <button
              type="submit"
              className="draft-refine-send-btn"
              disabled={refining || !chatInput.trim()}
              title="Enviar comando para a IA"
            >
              {refining ? (
                <RefreshCw size={14} className="spin-icon" />
              ) : (
                <>
                  <Send size={13} />
                  <span>Refinar</span>
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
