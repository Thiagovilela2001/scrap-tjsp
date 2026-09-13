import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import React, { useEffect, useRef } from 'react';
import {
  ArrowRight,
  CornerDownLeft,
  SlidersHorizontal,
  X,
  Landmark,
} from 'lucide-react';

const QUICK_TOPICS = [
  {
    title: 'Golpe do PIX',
    desc: 'Engenharia social e responsabilidade bancária',
    query: 'Golpe do PIX responsabilidade objetiva da instituicao financeira',
  },
  {
    title: 'Dano moral in re ipsa',
    desc: 'Inscrição indevida e cadastro restritivo',
    query: 'Dano moral in re ipsa',
  },
  {
    title: 'Prescrição intercorrente',
    desc: 'Execução de título e ausência de bens',
    query: 'Prescrição intercorrente',
  },
  {
    title: 'Vício construtivo',
    desc: 'Prazo decadencial vs prescricional em obra',
    query: 'Vício construtivo',
  },
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

  const selectedCount = selectedCourtCodes ? selectedCourtCodes.size : 0;
  const courtNamesPreview = selectedCourtCodes
    ? [...selectedCourtCodes].map((c) => c.toUpperCase()).slice(0, 3).join(', ') +
      (selectedCourtCodes.size > 3 ? ` +${selectedCourtCodes.size - 3}` : '')
    : 'Nenhum';

  return (
    <section className="search-console modern-omnibar" aria-labelledby="search-title">
      <div className="search-console-box">
        <div className="search-console-top">
          <div className="search-header-group">
            <span className="search-kicker">Pesquisa de precedentes</span>
            <h2 id="search-title" className="search-title">Questão jurídica</h2>
          </div>

          <div className="omnibar-court-badge" title="Tribunais selecionados para a pesquisa">
            <Landmark size={14} className="court-badge-icon" aria-hidden="true" />
            <span className="court-badge-text">
              Tribunais: {courtNamesPreview}
            </span>
          </div>
        </div>

        <div className="search-input-wrapper">
          <label className="sr-only" htmlFor="legal-query">
            Descreva fatos, controvérsia e tese jurídica
          </label>
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
            <Button
              variant="ghost"
              size="icon"
              type="button"
              className="clear-query-btn"
              onClick={handleClear}
              aria-label="Limpar questão jurídica"
            >
              <X size={15} aria-hidden="true" />
            </Button>
          )}
        </div>

        <div className="search-console-footer">
          <Button
            variant="outline"
            size="default"
            type="button"
            className="semantic-assistant-btn"
            onClick={onOpenSemanticAssistant}
          >
            <SlidersHorizontal size={14} aria-hidden="true" />
            <span>Delimitar caso</span>
          </Button>

          <div className="search-submit-wrap">
            <span className="search-shortcut">
              <CornerDownLeft size={12} aria-hidden="true" /> Enter
            </span>
            <Button
              variant="default"
              size="default"
              type="button"
              className="search-submit-btn"
              onClick={onSubmit}
              disabled={loading || !prompt.trim() || selectedCount === 0}
            >
              <span>{loading ? 'Pesquisando' : 'Pesquisar'}</span>
              {loading ? (
                <span className="btn-spinner" aria-hidden="true" />
              ) : (
                <ArrowRight size={16} aria-hidden="true" />
              )}
            </Button>
          </div>
        </div>
      </div>

      {isMobile ? (
        <details className="mobile-module mobile-suggestions">
          <summary>
            Precisa de um ponto de partida? <span aria-hidden="true">+</span>
          </summary>
          <div className="quick-tags-list">
            {QUICK_TOPICS.map((topic) => (
              <Button
                variant="ghost"
                key={topic.title}
                type="button"
                className="quick-tag-pill"
                disabled={loading}
                onClick={() => {
                  setPrompt(topic.query);
                  textareaRef.current?.focus();
                }}
              >
                {topic.title}
                <ArrowRight size={14} aria-hidden="true" />
              </Button>
            ))}
          </div>
        </details>
      ) : (
        <div className="quick-tags-container" aria-label="Consultas sugeridas">
          <div className="quick-tags-heading">
            <h2 className="quick-tags-label">Pontos de partida frequentes</h2>
            <span className="quick-tags-hint">Consultas recorrentes em pesquisa jurisprudencial</span>
          </div>
          <ul className="quick-topics-list">
            {QUICK_TOPICS.map((topic) => (
              <li key={topic.title}>
                <button
                  type="button"
                  className="quick-topic-card"
                  onClick={() => onSelectQuickTag(topic.query)}
                  disabled={loading}
                >
                  <div className="topic-card-content">
                    <strong className="topic-card-title">{topic.title}</strong>
                    <span className="topic-card-description">{topic.desc}</span>
                  </div>
                  <ArrowRight size={14} className="topic-card-arrow" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
