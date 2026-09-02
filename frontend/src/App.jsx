import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import PromptBox from './components/PromptBox';
import DecisionCard from './components/DecisionCard';
import PdfDrawer from './components/PdfDrawer';
import DraftingCanvas from './components/DraftingCanvas';
import SemanticClarificationModal from './components/SemanticClarificationModal';
import { 
  AlertCircle, 
  CheckSquare, 
  Scale, 
  Sparkles,
  FileText
} from 'lucide-react';

const CHAVE_HISTORICO = 'juris_tjsp_historico_react';
const CHAVE_TEMA = 'juris_tjsp_tema_react';

export default function App() {
  const [theme, setTheme] = useState('light');
  const [online, setOnline] = useState(true);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [thinkingStep, setThinkingStep] = useState('');
  const [history, setHistory] = useState([]);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [filterChamber, setFilterChamber] = useState('all');
  const [pdfData, setPdfData] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [selectedTribunal, setSelectedTribunal] = useState('tjsp');

  // Vocabulário Semântico e Desambiguação
  const [isSemanticModalOpen, setIsSemanticModalOpen] = useState(false);
  const [clarificationQuestions, setClarificationQuestions] = useState([]);
  const [clarificationTheme, setClarificationTheme] = useState('');

  // Seleção e Minuta
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [isDraftingOpen, setIsDraftingOpen] = useState(false);
  const [draftText, setDraftText] = useState('');
  const [generatingDraft, setGeneratingDraft] = useState(false);

  useEffect(() => {
    const savedTheme = localStorage.getItem(CHAVE_TEMA);
    if (savedTheme) {
      setTheme(savedTheme);
      document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setTheme('dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    }

    try {
      const savedHistory = JSON.parse(localStorage.getItem(CHAVE_HISTORICO) || '[]');
      setHistory(savedHistory);
    } catch {}

    fetch('/saude')
      .then((res) => setOnline(res.ok))
      .catch(() => setOnline(false));

    if (window.innerWidth < 1024) {
      setIsSidebarOpen(false);
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(nextTheme);
    document.documentElement.setAttribute('data-theme', nextTheme);
    localStorage.setItem(CHAVE_TEMA, nextTheme);
  };

  const saveToHistory = (query) => {
    if (!query || query.length < 3) return;
    const filtered = [query, ...history.filter((h) => h.toLowerCase() !== query.toLowerCase())].slice(0, 10);
    setHistory(filtered);
    try {
      localStorage.setItem(CHAVE_HISTORICO, JSON.stringify(filtered));
    } catch {}
  };

  const handleClearHistory = () => {
    setHistory([]);
    try {
      localStorage.removeItem(CHAVE_HISTORICO);
    } catch {}
  };

  const handleDeleteHistoryItem = (itemToDelete) => {
    const next = history.filter((h) => h !== itemToDelete);
    setHistory(next);
    try {
      localStorage.setItem(CHAVE_HISTORICO, JSON.stringify(next));
    } catch {}
  };

  const handleSearch = async (customQuery = null) => {
    const queryToSearch = customQuery || prompt;
    if (!queryToSearch || !queryToSearch.trim() || loading) return;

    setError(null);
    setLoading(true);
    setIsSemanticModalOpen(false);
    setThinkingStep('Consultando repositório jurisprudencial do TJSP...');
    saveToHistory(queryToSearch.trim());
    setSelectedIds(new Set());

    try {
      const response = await fetch('/tjsp/pesquisa-assistida/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pergunta: queryToSearch.trim(),
          contexto_caso: '',
          tribunal: selectedTribunal,
        }),
      });

      if (!response.ok) {
        let errMessage = `Erro do servidor (${response.status})`;
        try {
          const errData = await response.json();
          if (errData?.detail) {
            errMessage = typeof errData.detail === 'string' 
              ? errData.detail 
              : JSON.stringify(errData.detail);
          }
        } catch {}
        throw new Error(errMessage);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let finalData = null;

      const processBlock = (block) => {
        const clean = block.trim();
        if (!clean) return;

        let rawJson = clean;
        const dataPrefix = 'data: ';
        const dataIndex = clean.indexOf(dataPrefix);
        if (dataIndex !== -1) {
          rawJson = clean.slice(dataIndex + dataPrefix.length).trim();
        }

        let event;
        try {
          event = JSON.parse(rawJson);
        } catch {
          // Fragmento incompleto de chunk SSE
          return;
        }

        if (event.tipo === 'progresso') {
          setThinkingStep(event.mensagem);
        } else if (event.tipo === 'resultado') {
          finalData = event.dados;
        } else if (event.tipo === 'erro') {
          throw new Error(event.erro || 'Erro no processamento da pesquisa.');
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() || '';

        for (const block of blocks) {
          processBlock(block);
        }
      }

      // Flush remaining buffer if any
      if (buffer.trim()) {
        processBlock(buffer.trim());
      }

      if (finalData) {
        if (
          (finalData.status === 'precisa_esclarecimento' ||
            (finalData.questoes && finalData.questoes.length > 0)) &&
          (!finalData.processos || finalData.processos.length === 0)
        ) {
          setClarificationQuestions(finalData.questoes || []);
          setClarificationTheme(finalData.tema || queryToSearch);
          setIsSemanticModalOpen(true);
          setResults(null);
        } else {
          setResults(finalData);
          setFilterChamber('all');
          setIsSemanticModalOpen(false);
          const procs = finalData.processos || [];
          const top3 = procs.slice(0, 3).map((p) => String(p.cd_acordao));
          setSelectedIds(new Set(top3));
        }
      } else {
        throw new Error('Servidor concluiu sem dados de resultado. Verifique os termos e tente novamente.');
      }
    } catch (err) {
      setError(err.message || 'Erro inesperado na pesquisa.');
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (cd_acordao) => {
    const idStr = String(cd_acordao);
    const next = new Set(selectedIds);
    if (next.has(idStr)) {
      next.delete(idStr);
    } else {
      next.add(idStr);
    }
    setSelectedIds(next);
  };

  const selectAll = () => {
    const all = (results?.processos || []).map((p) => String(p.cd_acordao));
    setSelectedIds(new Set(all));
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  const handleGenerateDraft = async () => {
    const procs = (results?.processos || []).filter((p) => selectedIds.has(String(p.cd_acordao)));
    if (procs.length === 0) return;

    setGeneratingDraft(true);
    try {
      const res = await fetch('/tjsp/gerar-minuta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tema: results?.tema || prompt,
          pergunta: prompt,
          acordaos_selecionados: procs,
          instrucao: '',
        }),
      });
      const data = await res.json();
      if (res.ok && data.minuta) {
        setDraftText(data.minuta);
        setIsDraftingOpen(true);
      } else {
        alert(data.detail || 'Falha ao gerar minuta da petição.');
      }
    } catch {
      alert('Erro de conexão ao gerar minuta da petição.');
    } finally {
      setGeneratingDraft(false);
    }
  };

  const selectedDecisionsList = (results?.processos || []).filter((p) =>
    selectedIds.has(String(p.cd_acordao))
  );

  const filteredDecisions = (results?.processos || []).filter((d) => {
    if (filterChamber === 'all') return true;
    const matchOrgao = d.orgao_julgador && d.orgao_julgador.toLowerCase().includes(filterChamber.toLowerCase());
    const matchTribunal = d.tribunal && d.tribunal.toLowerCase() === filterChamber.toLowerCase();
    return matchOrgao || matchTribunal;
  });

  return (
    <div className="studio-app">
      <Header 
        theme={theme} 
        toggleTheme={toggleTheme} 
        online={online} 
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        isSidebarOpen={isSidebarOpen}
      />

      <div className="studio-body">
        <Sidebar
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          history={history}
          onSelectHistory={(query) => {
            setPrompt(query);
            handleSearch(query);
          }}
          onClearHistory={handleClearHistory}
          onDeleteHistoryItem={handleDeleteHistoryItem}
          results={results}
          selectedChamberFilter={filterChamber}
          onSelectChamberFilter={(chamber) => setFilterChamber(chamber)}
          selectedCount={selectedIds.size}
          onSelectPreset={(query) => {
            setPrompt(query);
            handleSearch(query);
          }}
        />

        <main className="studio-main">
          <div className="studio-main-inner">
            {!results && (
              <section className="workbench-hero">
                <div className="court-badge-pill">
                  <Scale size={13} /> Tribunal de Justiça de São Paulo
                </div>
                <h2 className="workbench-title">Inteligência Jurisprudencial</h2>
                <p className="workbench-desc">
                  Pesquisa assistida em acórdãos oficiais do TJSP. Análise fática automatizada, teses dominantes e geração de minutas para petições.
                </p>
              </section>
            )}

            <PromptBox
              prompt={prompt}
              setPrompt={setPrompt}
              onSubmit={() => handleSearch()}
              loading={loading}
              selectedTribunal={selectedTribunal}
              onSelectTribunal={(trib) => setSelectedTribunal(trib)}
              onSelectQuickTag={(tag) => {
                setPrompt(tag);
                handleSearch(tag);
              }}
              onOpenSemanticAssistant={() => {
                setClarificationQuestions([]);
                setClarificationTheme('');
                setIsSemanticModalOpen(true);
              }}
            />

            {loading && (
              <div className="thinking-radar-card">
                <div className="radar-spinner-wrap">
                  <div className="radar-glow-ring" />
                  <div className="radar-center-dot" />
                </div>
                <div className="thinking-radar-info">
                  <strong className="thinking-stage-title">{thinkingStep || 'Consultando acórdãos no TJSP...'}</strong>
                  <span className="thinking-stage-detail">
                    Análise semântica, cálculo de aderência fática e curadoria dos julgados em andamento...
                  </span>
                </div>
              </div>
            )}

            {error && (
              <div className="studio-error-banner">
                <AlertCircle size={18} />
                <span>{error}</span>
              </div>
            )}

            {results && (
              <section className="results-feed">
                <div className="feed-header-bar">
                  <div className="feed-header-info">
                    <span className="feed-tag">Relatório Jurisprudencial</span>
                    <h3 className="feed-theme-title">{results.tema || 'Tese Jurídica'}</h3>
                    <div className="feed-stats-sub">
                      <span><strong>{filteredDecisions.length}</strong> acórdão(s) filtrado(s)</span>
                      <span>•</span>
                      <span><strong>{(results.processos || []).length}</strong> precedentes localizados no TJSP</span>
                    </div>
                  </div>

                  <div className="feed-header-actions">
                    <button
                      type="button"
                      className="btn-select-batch"
                      onClick={selectedIds.size === (results.processos || []).length ? clearSelection : selectAll}
                    >
                      <CheckSquare size={13} />
                      <span>{selectedIds.size === (results.processos || []).length ? 'Desmarcar Todos' : 'Selecionar Todos'}</span>
                    </button>
                  </div>
                </div>

                <div className="precedents-list">
                  {filteredDecisions.map((decisao, idx) => (
                    <DecisionCard
                      key={idx}
                      decisao={decisao}
                      isSelected={selectedIds.has(String(decisao.cd_acordao))}
                      onToggleSelect={() => toggleSelect(decisao.cd_acordao)}
                      onOpenPdf={(url, title, subtitle) => setPdfData({ url, title, subtitle })}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        </main>
      </div>

      {/* Floating Action Dock for Drafting */}
      {selectedIds.size > 0 && (
        <aside className="drafting-floating-dock" aria-label="Ações de minuta jurídica">
          <div className="dock-info">
            <span className="dock-count-badge">{selectedIds.size}</span>
            <span className="dock-count-label">acórdão(s) selecionado(s)</span>
          </div>

          <button
            type="button"
            className="dock-generate-btn"
            onClick={handleGenerateDraft}
            disabled={generatingDraft}
          >
            <Sparkles size={14} />
            <span>{generatingDraft ? 'Gerando minuta...' : 'Gerar Argumentação da Petição'}</span>
          </button>
        </aside>
      )}

      {/* Official Court PDF Drawer */}
      <PdfDrawer
        isOpen={!!pdfData}
        onClose={() => setPdfData(null)}
        pdfData={pdfData}
      />

      {/* Legal Drafting Studio Modal */}
      <DraftingCanvas
        isOpen={isDraftingOpen}
        onClose={() => setIsDraftingOpen(false)}
        draft={draftText}
        setDraft={setDraftText}
        selectedDecisions={selectedDecisionsList}
        originalQuery={prompt}
        topic={results?.tema}
      />

      {/* Semantic Disambiguation Questionnaire Modal */}
      <SemanticClarificationModal
        isOpen={isSemanticModalOpen}
        onClose={() => setIsSemanticModalOpen(false)}
        initialQuery={prompt}
        aiQuestions={clarificationQuestions}
        aiTheme={clarificationTheme}
        onApplyAndSearch={(refinedQuery) => {
          setPrompt(refinedQuery);
          handleSearch(refinedQuery);
        }}
      />
    </div>
  );
}
