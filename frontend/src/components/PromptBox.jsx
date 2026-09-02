import React, { useRef, useEffect } from 'react';
import { Search, CornerDownLeft, X, Sparkles, SlidersHorizontal, Globe } from 'lucide-react';

const QUICK_TAGS = [
  'Dano Moral in re ipsa',
  'Prescrição Intercorrente',
  'Atraso de Voo e Extravio',
  'Vício Construtivo Imobiliário',
  'Golpe do PIX e Fortuito Interno',
  'Negativa de Plano de Saúde',
  'Desapropriação e Juros Moratórios',
];

export default function PromptBox({
  prompt,
  setPrompt,
  onSubmit,
  loading,
  onSelectQuickTag,
  onOpenSemanticAssistant,
}) {
  const textareaRef = useRef(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 150) + 'px';
    }
  }, [prompt]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  const handleClear = () => {
    setPrompt('');
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  };

  return (
    <div className="search-console">
      <div className="search-console-box">
        <div className="search-console-top">
          <div className="search-mode-tag">
            <Globe size={13} />
            <span>Pesquisa Unificada Multi-Tribunais • TJSP, TJSC, TJMS, TJCE, TJAM, TJAL, TJAC</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              type="button"
              className="semantic-assistant-btn"
              onClick={onOpenSemanticAssistant}
              title="Abrir opções e ramificações semânticas guiadas"
            >
              <SlidersHorizontal size={12} />
              <span>Opções Guiadas</span>
            </button>

            {prompt && (
              <button 
                type="button" 
                className="clear-query-btn" 
                onClick={handleClear}
                title="Limpar pesquisa"
              >
                <X size={14} /> Limpar
              </button>
            )}
          </div>
        </div>

        <div className="search-input-wrapper">
          <textarea
            ref={textareaRef}
            className="search-textarea"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Descreva o caso, fatos ou tese jurídica (a IA buscará precedentes em todos os Tribunais de Justiça simultaneamente)..."
            rows={2}
            disabled={loading}
          />
        </div>

        <div className="search-console-footer">
          <div className="search-shortcuts">
            <span className="shortcut-chip">
              <CornerDownLeft size={11} /> <strong>Enter</strong> para pesquisar
            </span>
            <span className="shortcut-chip">
              <strong>Shift + Enter</strong> para quebra de linha
            </span>
          </div>

          <button
            type="button"
            className="search-submit-btn"
            onClick={onSubmit}
            disabled={loading || !prompt.trim()}
            aria-label="Buscar Jurisprudência em todos os Tribunais"
          >
            {loading ? (
              <span className="btn-spinner" />
            ) : (
              <>
                <Search size={16} />
                <span>Pesquisar nos Tribunais</span>
              </>
            )}
          </button>
        </div>
      </div>

      <div className="quick-tags-container">
        <span className="quick-tags-label">
          <Sparkles size={12} /> Temas Rápidos:
        </span>
        <div className="quick-tags-list">
          {QUICK_TAGS.map((tag, idx) => (
            <button
              key={idx}
              type="button"
              className="quick-tag-pill"
              onClick={() => onSelectQuickTag(tag)}
            >
              {tag}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
