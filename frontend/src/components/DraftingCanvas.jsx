import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import React, { useRef, useState } from 'react';
import {
  X,
  Copy,
  Check,
  Send,
  Download,
  FileDown,
  RefreshCw,
  AlignLeft,
} from 'lucide-react';
import { exportDraftToDocx } from '../utils/docxExport';
import { cleanLegalText } from '../utils/cleanLegalText';

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
  const closeButtonRef = useRef(null);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      toast.success('Minuta copiada.');
      setTimeout(() => setCopied(false), 2500);
    } catch {
      toast.error('Não foi possível acessar a área de transferência.');
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
    toast.success('Download do arquivo TXT iniciado.');
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
      toast.success('Download do arquivo Word iniciado.');
    } catch (err) {
      console.error(err);
      toast.error('Erro ao gerar arquivo Word (.docx).');
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
        setDraft(cleanLegalText(data.minuta));
        setChatInput('');
        toast.success('Minuta revisada.');
      } else {
        toast.error(data.detail || 'Erro ao ajustar minuta.');
      }
    } catch {
      toast.error('Falha ao comunicar com o assistente.');
    } finally {
      setRefining(false);
    }
  };

  const wordCount = draft ? draft.trim().split(/\s+/).filter(Boolean).length : 0;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="drafting-modal-wrapper" showCloseButton={false} initialFocus={closeButtonRef}>
        {/* Top Header */}
        <div className="drafting-header">
          <div className="drafting-main-title">
            <DialogTitle>Mesa de Redação</DialogTitle>
            <DialogDescription className="precedents-count-badge">
              {selectedDecisions?.length || 0} precedente{selectedDecisions?.length === 1 ? '' : 's'} no caderno
            </DialogDescription>
          </div>

          <div className="drafting-header-actions">
            <div className="word-count-badge">
              {wordCount} palavras
            </div>

            <Button
              variant="outline"
              size="default"
              type="button"
              className="draft-action-btn"
              onClick={() => setDraft(cleanLegalText(draft))}
              title="Corrigir quebras artificiais de linha e alinhar parágrafos fluidos"
            >
              <AlignLeft size={13} />
              <span>Formatar</span>
            </Button>

            <Button
              variant="outline"
              size="default"
              type="button"
              className="draft-action-btn docx-btn"
              onClick={handleExportDocx}
              disabled={exportingDocx}
              title="Exportar Petição Formatada em Word (.docx)"
            >
              <FileDown size={14} />
              <span>{exportingDocx ? 'Gerando...' : 'Word (.docx)'}</span>
            </Button>

            <Button
              variant="outline"
              size="default"
              type="button"
              className="draft-action-btn"
              onClick={handleDownloadTxt}
              title="Baixar em formato texto simples (.txt)"
            >
              <Download size={13} />
              <span>.txt</span>
            </Button>

            <Button
              variant="outline"
              size="default"
              type="button"
              className={`draft-action-btn primary ${copied ? 'copied' : ''}`}
              onClick={handleCopy}
              title="Copiar texto completo para a área de transferência"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              <span>{copied ? 'Copiado!' : 'Copiar'}</span>
            </Button>

            <Button
              variant="ghost"
              size="icon"
              type="button"
              className="drafting-close-btn"
              onClick={onClose}
              aria-label="Fechar editor de minuta"
              ref={closeButtonRef}
              tooltip={false}
            >
              <X size={16} />
            </Button>
          </div>
        </div>

        {/* Editor Area */}
        <div className="drafting-editor-container">
          <Textarea
            aria-label="Texto da minuta"
            className="drafting-editor-textarea"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="A minuta jurídica estruturada aparecerá aqui..."
            spellCheck="true"
          />
        </div>

        {/* Refinement toolbar */}
        <div className="drafting-footer">
          <div className="quick-refinements-row">
            <span className="quick-refine-label">Ajustes rápidos</span>
            <div className="quick-refine-chips">
              {QUICK_PROMPTS.map((promptText, idx) => (
                <Button
                  variant="ghost"
                  size="default"
                  key={idx}
                  type="button"
                  className="quick-refine-pill"
                  onClick={() => handleRefine(promptText)}
                  disabled={refining}
                >
                  {promptText}
                </Button>
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
            <Input
              aria-label="Instruções para revisar a minuta"
              type="text"
              className="draft-refine-input"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Instrua a IA para calibrar teses, alterar o tom ou acrescentar pedidos..."
              disabled={refining}
            />

            <Button
              variant="default"
              size="default"
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
            </Button>
          </form>
        </div>
      </DialogContent>
    </Dialog>
  );
}
