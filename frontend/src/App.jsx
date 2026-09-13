import { Toaster } from "@/components/ui/sonner";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import MobileNavigation from './components/MobileNavigation';
import MobileSearchScope from './components/MobileSearchScope';
import useMobileLayout from './hooks/useMobileLayout';
import Sidebar from './components/Sidebar';
import PromptBox from './components/PromptBox';
import DecisionCard from './components/DecisionCard';
import PdfDrawer from './components/PdfDrawer';
import DraftingCanvas from './components/DraftingCanvas';
import SemanticClarificationModal from './components/SemanticClarificationModal';
import { cleanLegalText } from './utils/cleanLegalText';
import { AlertCircle, CheckSquare, PenLine } from 'lucide-react';
import { DEFAULT_ACTIVE_COURTS } from './data/courts';

const CHAVE_HISTORICO = 'juris_tjsp_historico_react';
const CHAVE_TEMA = 'juris_tjsp_tema_react';

export default function App() {
  const isMobile = useMobileLayout();
  const [mobileView, setMobileView] = useState('search');
  const navigateMobile = (view) => {
    setMobileView(view);
    window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, behavior: 'instant' });
      document.getElementById('mobile-view-title')?.focus({ preventScroll: true });
    });
  };
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
  const [activeCourtCodes, setActiveCourtCodes] = useState(new Set(DEFAULT_ACTIVE_COURTS));
  const [selectedCourtCodes, setSelectedCourtCodes] = useState(new Set(DEFAULT_ACTIVE_COURTS));
  const [courtBackendCodes, setCourtBackendCodes] = useState(
    new Map(DEFAULT_ACTIVE_COURTS.map((code) => [code, code])),
  );

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

    fetch('/tribunais')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error('Falha ao listar tribunais'))))
      .then((tribunais) => {
        const backendCodes = new Map();
        tribunais.filter((item) => item.ativo).forEach((item) => {
          const canonicalCode = item.codigo.replace(/^datajud_/, '');
          const currentCode = backendCodes.get(canonicalCode);
          const nativeAdapter = !item.codigo.startsWith('datajud_');
          if (!currentCode || (currentCode.startsWith('datajud_') && nativeAdapter)) {
            backendCodes.set(canonicalCode, item.codigo);
          }
        });
        setCourtBackendCodes(backendCodes);
        setActiveCourtCodes(new Set(backendCodes.keys()));
        setSelectedCourtCodes((current) => new Set(
          [...current].filter((code) => backendCodes.has(code)),
        ));
      })
      .catch(() => {});

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
    if (selectedCourtCodes.size === 0) {
      setError('Selecione pelo menos um tribunal ativo para pesquisar.');
      if (isMobile) navigateMobile('search');
      return;
    }

    setError(null);
    setLoading(true);
    if (isMobile) navigateMobile('results');
    else setMobileView('results');
    setIsSemanticModalOpen(false);
    setThinkingStep('Consultando jurisprudência nos tribunais brasileiros...');
    saveToHistory(queryToSearch.trim());
    setSelectedIds(new Set());

    try {
      const response = await fetch('/pesquisa-assistida/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pergunta: queryToSearch.trim(),
          contexto_caso: '',
          tribunal: [...selectedCourtCodes]
            .map((code) => courtBackendCodes.get(code) || code)
            .join(','),
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
          setMobileView('search');
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
        setDraftText(cleanLegalText(data.minuta));
        setIsDraftingOpen(true);
      } else {
        toast.error(data.detail || 'Falha ao gerar minuta da petição.');
      }
    } catch {
      toast.error('Erro de conexão ao gerar minuta da petição.');
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
    <div className={`studio-app ${isMobile ? 'mobile-workspace' : ''}`} data-mobile-view={mobileView}>
      <Toaster theme={theme} position="top-right" closeButton richColors />
      <a className="skip-link" href={isMobile && mobileView === 'archive' ? '#research-sidebar' : '#conteudo-principal'}>Ir para conteúdo</a>
      <Header
        theme={theme}
        toggleTheme={toggleTheme}
        online={online}
        toggleSidebar={() => isMobile ? navigateMobile(mobileView === 'archive' ? 'search' : 'archive') : setIsSidebarOpen(!isSidebarOpen)}
        isSidebarOpen={isMobile ? mobileView === 'archive' : isSidebarOpen}
      />

      <div className="studio-body">
        {(!isMobile || mobileView === 'archive') && <Sidebar
          isMobile={isMobile}
          isOpen={isMobile || isSidebarOpen}
          onClose={() => isMobile ? navigateMobile('search') : setIsSidebarOpen(false)}
          history={history}
          onSelectHistory={(query) => {
            setPrompt(query);
            handleSearch(query);
          }}
          onClearHistory={handleClearHistory}
          onDeleteHistoryItem={handleDeleteHistoryItem}
          results={results}
          selectedChamberFilter={filterChamber}
          onSelectChamberFilter={(chamber) => { setFilterChamber(chamber); if (isMobile) navigateMobile('results'); }}
          selectedCount={selectedIds.size}
          activeCourtCodes={activeCourtCodes}
          selectedCourtCodes={selectedCourtCodes}
          onCourtSelectionChange={setSelectedCourtCodes}
          loading={loading}
        />}

        {!isMobile && isSidebarOpen && (
          <button
            type="button"
            className="sidebar-backdrop"
            onClick={() => setIsSidebarOpen(false)}
            aria-label="Fechar arquivo de pesquisa"
          />
        )}

        <main id="conteudo-principal" className="studio-main" hidden={isMobile && mobileView === 'archive'}>
          <div className="studio-main-inner">
            <h1 className="sr-only">Juris — pesquisa de precedentes</h1>
            {isMobile && mobileView !== 'archive' && <header className="mobile-page-heading">
              <span className="search-kicker">{mobileView === 'search' ? 'Pesquisa de precedentes' : 'Caderno de pesquisa'}</span>
              <h2 id="mobile-view-title" tabIndex={-1}>{mobileView === 'search' ? 'Qual é o seu caso?' : 'Resultados'}</h2>
              <p>{mobileView === 'search' ? 'Descreva a controvérsia. Encontre fundamentos em fontes oficiais.' : 'Compare os precedentes e selecione os que apoiam sua minuta.'}</p>
            </header>}
            {!isMobile && !results && (
              <section className="workbench-hero">
                <div className="hero-index" aria-hidden="true">01 / PESQUISA</div>
                <h2 className="workbench-title">Encontre o precedente que sustenta o argumento.</h2>
                <p className="workbench-desc">
                  Descreva fatos e controvérsia. O sistema confronta acórdãos oficiais,
                  aponta aderência e organiza fundamentos prontos para revisão jurídica.
                </p>
                <div className="hero-rule"><span>Acervo oficial</span><span>Análise rastreável</span><span>Minuta editável</span></div>
              </section>
            )}

            <div hidden={isMobile && mobileView !== 'search'}>
            <PromptBox
              isMobile={isMobile}
              prompt={prompt}
              setPrompt={setPrompt}
              onSubmit={() => handleSearch()}
              loading={loading}
              onSelectQuickTag={(tag) => {
                setPrompt(tag);
                handleSearch(tag);
              }}
              onOpenSemanticAssistant={() => {
                setClarificationQuestions([]);
                setClarificationTheme('');
                setIsSemanticModalOpen(true);
              }}
              selectedCourtCodes={selectedCourtCodes}
            />
            {isMobile && <MobileSearchScope activeCodes={activeCourtCodes} selectedCodes={selectedCourtCodes}
              onChange={setSelectedCourtCodes} disabled={loading} />}
            </div>

            {loading && (!isMobile || mobileView === 'results') && (
              <div className="thinking-radar-card" role="status" aria-live="polite">
                <span className="thinking-index">02</span>
                <div className="thinking-radar-info">
                  <strong className="thinking-stage-title">{thinkingStep || 'Consultando acórdãos oficiais'}</strong>
                  <span className="thinking-stage-detail">Triagem semântica e leitura comparada em andamento.</span>
                </div>
                <div className="search-skeleton" aria-hidden="true">
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-5/6" />
                </div>
              </div>
            )}

            {error && (
              <Alert variant="destructive" className="studio-error-banner">
                <AlertCircle size={18} aria-hidden="true" />
                <div><AlertTitle>Não foi possível concluir a pesquisa</AlertTitle>
                <AlertDescription>{error}</AlertDescription></div>
              </Alert>
            )}

            {isMobile && mobileView === 'results' && !results && !loading && !error && <div className="mobile-empty-state">
              <h3>Seu caderno começa com uma pesquisa</h3>
              <p>Os precedentes encontrados ficam aqui, prontos para leitura e seleção.</p>
              <Button onClick={() => navigateMobile('search')}>Iniciar pesquisa</Button>
            </div>}
            {results && !loading && (!isMobile || mobileView === 'results') && (
              <section className="results-feed">
                <div className="feed-header-bar">
                  <div className="feed-header-info">
                    <span className="feed-tag">02 / Caderno de resultados</span>
                    <h2 className="feed-theme-title">{results.tema || 'Tese jurídica'}</h2>
                    <div className="feed-stats-sub">
                      <span><strong>{filteredDecisions.length}</strong> exibidos</span>
                      <span aria-hidden="true">/</span>
                      <span><strong>{(results.processos || []).length}</strong> precedentes localizados</span>
                    </div>
                  </div>

                  <div className="feed-header-actions">
                    {isMobile && <Button variant="outline" onClick={() => navigateMobile('archive')}>Filtrar resultados</Button>}
                    <Button variant="outline" size="default"
                      type="button"
                      className="btn-select-batch"
                      onClick={selectedIds.size === (results.processos || []).length ? clearSelection : selectAll}
                    >
                      <CheckSquare size={14} aria-hidden="true" />
                      <span>{selectedIds.size === (results.processos || []).length ? 'Limpar seleção' : 'Selecionar todos'}</span>
                    </Button>
                  </div>
                </div>

                <div className="precedents-list">
                  {filteredDecisions.length === 0 && <p className="mobile-empty-state">{(results.processos || []).length ? 'Nenhum precedente neste filtro. Escolha outro no Arquivo.' : 'Nenhum precedente encontrado. Ajuste os termos ou os tribunais da pesquisa.'}</p>}
                  {filteredDecisions.map((decisao, idx) => (
                    <DecisionCard
                      key={decisao.cd_acordao || decisao.processo || idx}
                      index={idx}
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

      {isMobile && <MobileNavigation view={mobileView} onChange={navigateMobile}
        resultCount={results?.processos?.length || 0} loading={loading} />}

      {selectedIds.size > 0 && (!isMobile || mobileView === 'results') && (
        <aside className="drafting-floating-dock" aria-label="Ações de minuta jurídica">
          <div className="dock-info">
            <span className="dock-count-badge">{selectedIds.size}</span>
            <span className="dock-count-label">precedente{selectedIds.size === 1 ? '' : 's'} no caderno</span>
          </div>
          <Button variant="default" size="default"
            type="button"
            className="dock-generate-btn"
            onClick={handleGenerateDraft}
            disabled={generatingDraft}
          >
            <PenLine size={15} aria-hidden="true" />
            <span>{generatingDraft ? 'Compondo minuta' : 'Abrir mesa de redação'}</span>
          </Button>
        </aside>
      )}

      <PdfDrawer
        isOpen={!!pdfData}
        onClose={() => setPdfData(null)}
        pdfData={pdfData}
      />

      <DraftingCanvas
        isOpen={isDraftingOpen}
        onClose={() => setIsDraftingOpen(false)}
        draft={draftText}
        setDraft={setDraftText}
        selectedDecisions={selectedDecisionsList}
        originalQuery={prompt}
        topic={results?.tema}
      />

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
