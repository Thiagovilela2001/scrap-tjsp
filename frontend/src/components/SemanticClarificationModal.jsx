import React, { useState, useEffect } from 'react';
import { 
  X, 
  Check,
  Search, 
  SlidersHorizontal, 
  CheckCircle2,
  HelpCircle
} from 'lucide-react';
import { SEMANTIC_BRANCHES, matchSemanticBranch, buildRefinedQuery } from '../utils/semanticVocabulary';

export default function SemanticClarificationModal({
  isOpen,
  onClose,
  initialQuery = '',
  aiQuestions = [],
  aiTheme = '',
  onApplyAndSearch,
}) {
  const [selectedBranch, setSelectedBranch] = useState(null);
  const [selectedAnswers, setSelectedAnswers] = useState({});
  const [customDetail, setCustomDetail] = useState('');

  useEffect(() => {
    if (!isOpen) return;

    setSelectedAnswers({});
    setCustomDetail('');

    const matched = matchSemanticBranch(initialQuery);
    if (matched) {
      setSelectedBranch(matched);
    } else {
      setSelectedBranch(SEMANTIC_BRANCHES[0]);
    }
  }, [isOpen, initialQuery]);

  if (!isOpen) return null;

  const hasAiQuestions = aiQuestions && aiQuestions.length > 0;
  
  const normalizedAiQuestions = hasAiQuestions
    ? aiQuestions.map((q, idx) => {
        if (typeof q === 'string') {
          return {
            id: `ai_${idx}`,
            title: q,
            multi: true,
            options: [
              'Pretendo demonstrar a procedência do pedido (Pelo autor/consumidor)',
              'Pretendo afastar a responsabilidade ou reduzir valor (Pela ré/empresa)',
              'Foco em dano moral in re ipsa e súmulas do TJSP',
              'Foco em restituição material e tutela de urgência',
            ],
          };
        }
        return {
          id: `ai_${idx}`,
          title: q.pergunta || `Questão ${idx + 1}`,
          multi: true,
          options: q.opcoes && q.opcoes.length > 0 ? q.opcoes : [
            'Opção favorável ao autor',
            'Opção favorável ao réu',
            'Tema pacificado no TJSP',
          ],
        };
      })
    : [];

  const currentQuestions = hasAiQuestions ? normalizedAiQuestions : selectedBranch?.questions || [];

  const handleToggleOption = (questionId, optionValue, isMulti) => {
    setSelectedAnswers((prev) => {
      const currentList = prev[questionId] || [];
      if (!isMulti) {
        return { ...prev, [questionId]: [optionValue] };
      }
      if (currentList.includes(optionValue)) {
        return { ...prev, [questionId]: currentList.filter((item) => item !== optionValue) };
      } else {
        return { ...prev, [questionId]: [...currentList, optionValue] };
      }
    });
  };

  const handleConfirm = () => {
    const refined = buildRefinedQuery(initialQuery, selectedAnswers, customDetail);
    onApplyAndSearch(refined);
    onClose();
  };

  const totalSelectedCount = Object.values(selectedAnswers).reduce(
    (acc, list) => acc + (Array.isArray(list) ? list.length : 0),
    0
  );

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="semantic-modal-wrapper" role="dialog" aria-modal="true">
        {/* Header */}
        <div className="semantic-modal-header">
          <div className="semantic-title-group">
            <div className="semantic-icon-badge">
              <SlidersHorizontal size={17} />
            </div>
            <div>
              <div className="semantic-modal-title">Desambiguação e Refinamento Semântico</div>
              <span className="semantic-modal-desc">
                {hasAiQuestions
                  ? 'Especifique os contornos fáticos e teses para focar os precedentes mais aderentes:'
                  : 'Selecione os elementos fáticos e teses aplicáveis ao seu caso:'}
              </span>
            </div>
          </div>

          <button
            type="button"
            className="drafting-close-btn"
            onClick={onClose}
            aria-label="Fechar formulário semântico"
          >
            <X size={16} />
          </button>
        </div>

        {/* Branch Selector Tabs (Segmented Bar) */}
        {!hasAiQuestions && (
          <nav className="semantic-branch-tabs" aria-label="Ramos do Direito">
            {SEMANTIC_BRANCHES.map((b) => (
              <button
                key={b.id}
                type="button"
                className={`semantic-branch-tab ${selectedBranch?.id === b.id ? 'active' : ''}`}
                onClick={() => {
                  setSelectedBranch(b);
                  setSelectedAnswers({});
                }}
              >
                {b.label}
              </button>
            ))}
          </nav>
        )}

        {/* Questions Body */}
        <div className="semantic-modal-body">
          {aiTheme && (
            <div className="semantic-branch-theme">
              <span className="theme-label">Tema Principal Detectado</span>
              <strong className="theme-title">{aiTheme}</strong>
            </div>
          )}

          {currentQuestions.map((q, qIdx) => {
            const currentSelected = selectedAnswers[q.id] || [];
            return (
              <section key={q.id} className="semantic-question-card">
                <div className="question-header-row">
                  <span className="question-step-number">{qIdx + 1}</span>
                  <h4 className="question-title">{q.title}</h4>
                </div>

                <div className="options-list">
                  {q.options.map((opt, idx) => {
                    const isChecked = currentSelected.includes(opt);
                    return (
                      <button
                        key={idx}
                        type="button"
                        className={`option-item-btn ${isChecked ? 'selected' : ''}`}
                        onClick={() => handleToggleOption(q.id, opt, q.multi)}
                      >
                        <div className={`option-checkbox-indicator ${isChecked ? 'checked' : ''}`}>
                          {isChecked && <Check size={12} strokeWidth={3} />}
                        </div>
                        <span className="option-text-label">{opt}</span>
                      </button>
                    );
                  })}
                </div>
              </section>
            );
          })}

          {/* Additional details */}
          <div className="semantic-custom-box">
            <label className="custom-box-label">
              Particularidade fática ou valor do dano (Opcional):
            </label>
            <input
              type="text"
              className="draft-refine-input"
              value={customDetail}
              onChange={(e) => setCustomDetail(e.target.value)}
              placeholder="Ex: Atraso de 14h em conexão internacional sem assistência material..."
            />
          </div>
        </div>

        {/* Footer Actions */}
        <div className="semantic-modal-footer">
          <div className="semantic-footer-count">
            <CheckCircle2 size={15} className="text-green" />
            <span className="footer-count-text">
              <strong>{totalSelectedCount}</strong> filtro(s) ativo(s)
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancelar
            </button>

            <button
              type="button"
              className="btn-primary"
              onClick={handleConfirm}
            >
              <Search size={14} />
              <span>Aplicar e Buscar no TJSP</span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
