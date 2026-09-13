import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import React, { useEffect, useRef } from 'react';
import { ArrowRight, CornerDownLeft, SlidersHorizontal, X } from 'lucide-react';

const QUICK_QUERIES = [
  'Dano moral in re ipsa',
  'Prescrição intercorrente',
  'Golpe do PIX',
  'Vício construtivo',
];

export default function PromptBox({
  prompt,
  setPrompt,
  onSubmit,
  loading,
  onSelectQuickTag,
  onOpenSemanticAssistant,
  selectedCourtCodes,
  isMobile = false,
}) {
  const textareaRef = useRef(null);

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = 'auto';
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 176)}px`;
  }, [prompt]);

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !isMobile && !event.nativeEvent.isComposing) {
      event.preventDefault();
      onSubmit();
    }
  };

  const handleClear = () => {
    setPrompt('');
    textareaRef.current?.focus();
  };

  return (
    <section className="search-console" aria-labelledby="search-title">
      <div className="search-console-box">
        <div className="search-console-top">
          <div>
            <span className="search-kicker">Consulta 01</span>
            <h2 id="search-title" className="search-title">Questão jurídica</h2>
          </div>
        </div>
        <div className="search-input-wrapper">
          <label className="sr-only" htmlFor="legal-query">Descreva fatos, controvérsia e tese jurídica</label>
          <Textarea
            id="legal-query"
            ref={textareaRef}
            className="search-textarea"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ex.: instituição financeira responde por transferência via PIX realizada após engenharia social?"
            rows={3}
            disabled={loading}
          />
          {prompt && (
            <Button variant="ghost" size="icon" type="button" className="clear-query-btn" onClick={handleClear} aria-label="Limpar questão jurídica">
              <X size={15} aria-hidden="true" />
            </Button>
          )}
        </div>
        <div className="search-console-footer">
          <Button variant="outline" size="default" type="button" className="semantic-assistant-btn" onClick={onOpenSemanticAssistant}>
            <SlidersHorizontal size={14} aria-hidden="true" /> Delimitar caso
          </Button>
          <div className="search-submit-wrap">
            <span className="search-shortcut"><CornerDownLeft size={12} aria-hidden="true" /> Enter</span>
            <Button variant="default" size="default" type="button" className="search-submit-btn" onClick={onSubmit} disabled={loading || !prompt.trim() || selectedCourtCodes.size === 0}>
              <span>{loading ? 'Pesquisando' : 'Pesquisar'}</span>
              {loading ? <span className="btn-spinner" aria-hidden="true" /> : <ArrowRight size={16} aria-hidden="true" />}
            </Button>
          </div>
        </div>
      </div>
      {isMobile ? <details className="mobile-module mobile-suggestions">
        <summary>Precisa de um ponto de partida?<span aria-hidden="true">+</span></summary>
        <div className="quick-tags-list">
          {QUICK_QUERIES.map((query) => (
            <Button variant="ghost" key={query} type="button" className="quick-tag-pill" disabled={loading}
              onClick={() => { setPrompt(query); textareaRef.current?.focus(); }}>
              {query}<ArrowRight size={14} aria-hidden="true" />
            </Button>
          ))}
        </div>
      </details> : <div className="quick-tags-container" aria-label="Consultas sugeridas">
        <span className="quick-tags-label">Pontos de partida</span>
        <div className="quick-tags-list">
          {QUICK_QUERIES.map((query, index) => (
            <Button variant="ghost" size="default" key={query} type="button" className="quick-tag-pill" onClick={() => onSelectQuickTag(query)}>
              <span>{String(index + 1).padStart(2, '0')}</span>{query}
            </Button>
          ))}
        </div>
      </div>}
    </section>
  );
}
