"use strict";

const estado = {
  modo: "assistida",
  consultaTJSP: null,
  selecionados: new Set(),
  recomendados: [],
  maxImportacao: 5,
  maxCustoAnaliseDocumentalBrl: null,
  ultimoResultado: null,
};

// Elementos da Interface
const formulario = document.querySelector("#formulario-pesquisa");
const pergunta = document.querySelector("#pergunta");
const botaoEnviar = document.querySelector("#botao-enviar");
const estadoVazio = document.querySelector("#estado-vazio");
const estadoCarregando = document.querySelector("#estado-carregando");
const estadoErro = document.querySelector("#estado-erro");
const mensagemErro = document.querySelector("#mensagem-erro");
const respostaIA = document.querySelector("#resposta-ia");
const textoResposta = document.querySelector("#texto-resposta");
const metricasResposta = document.querySelector("#metricas-resposta");
const listaResultados = document.querySelector("#lista-resultados");
const fontesResposta = document.querySelector("#fontes-resposta");
const gradeFontes = document.querySelector("#grade-fontes");
const quantidadeFontes = document.querySelector("#quantidade-fontes");
const tituloResultados = document.querySelector("#titulo-resultados");
const contadorResultados = document.querySelector("#contador-resultados");
const listaAuditorias = document.querySelector("#lista-auditorias");
const botaoAuditorias = document.querySelector("#atualizar-auditorias");
const barraImportacao = document.querySelector("#barra-importacao");
const botaoImportar = document.querySelector("#botao-importar");
const quantidadeSelecionada = document.querySelector("#quantidade-selecionada");
const resultadoImportacao = document.querySelector("#resultado-importacao");
const secaoResultados = document.querySelector("#secao-resultados");
const etapasPesquisa = [...document.querySelectorAll("[data-etapa]")];
const estadoEtapa = document.querySelector("#estado-etapa");
const botaoSelecionarRecomendados = document.querySelector("#selecionar-recomendados");
const botaoLimparSelecao = document.querySelector("#limpar-selecao");
const botaoCopiarRelatorio = document.querySelector("#botao-copiar-relatorio");
const barraFiltros = document.querySelector("#barra-chips-filtros");
const conteinerChips = document.querySelector("#chips-container");
const conteinerHistorico = document.querySelector("#historico-pesquisas");
const gradeHistorico = document.querySelector("#grade-chips-historico");
const botaoTema = document.querySelector("#alternar-tema");
const gavetaPDF = document.querySelector("#gaveta-pdf");
const backdropGaveta = document.querySelector("#backdrop-gaveta");
const iframePDF = document.querySelector("#iframe-pdf");
const tituloGaveta = document.querySelector("#titulo-gaveta-pdf");
const subtituloGaveta = document.querySelector("#subtitulo-gaveta-pdf");
const linkExternoPDF = document.querySelector("#link-externo-pdf");
const botaoFecharGaveta = document.querySelector("#fechar-gaveta-pdf");

const CHAVE_HISTORICO = "juris_tjsp_historico_buscas";
const CHAVE_TEMA = "juris_tjsp_tema";

// ============================================================================
// INICIALIZAÇÃO
// ============================================================================

inicializarTema();
renderizarHistorico();

document.querySelectorAll("[data-consulta]").forEach((botao) => {
  botao.addEventListener("click", () => {
    pergunta.value = botao.dataset.consulta;
    pergunta.focus();
    ajustarAlturaTextarea(pergunta);
  });
});

// Suporte ao envio por tecla Enter (Shift+Enter para quebra de linha)
if (pergunta) {
  pergunta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      formulario.dispatchEvent(new Event("submit", { cancelable: true }));
    }
  });
  pergunta.addEventListener("input", () => ajustarAlturaTextarea(pergunta));
}

function ajustarAlturaTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 220) + "px";
}

formulario.addEventListener("submit", executarPesquisa);
if (botaoAuditorias) botaoAuditorias.addEventListener("click", carregarAuditorias);
if (botaoImportar) botaoImportar.addEventListener("click", importarSelecionados);
if (botaoSelecionarRecomendados) botaoSelecionarRecomendados.addEventListener("click", selecionarRecomendados);
if (botaoLimparSelecao) botaoLimparSelecao.addEventListener("click", limparSelecao);
if (botaoCopiarRelatorio) botaoCopiarRelatorio.addEventListener("click", copiarRelatorioFormatado);
if (botaoFecharGaveta) botaoFecharGaveta.addEventListener("click", fecharVisualizadorPDF);
if (backdropGaveta) backdropGaveta.addEventListener("click", fecharVisualizadorPDF);

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && gavetaPDF && !gavetaPDF.hidden) {
    fecharVisualizadorPDF();
  }
});

atualizarEtapa("caso");
verificarSaude();
carregarAuditorias();

// ============================================================================
// GERENCIADOR DE TEMA
// ============================================================================

function inicializarTema() {
  const temaSalvo = localStorage.getItem(CHAVE_TEMA);
  if (temaSalvo) {
    document.documentElement.setAttribute("data-tema", temaSalvo);
  } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.setAttribute("data-tema", "escuro");
  }

  if (botaoTema) {
    botaoTema.addEventListener("click", () => {
      const atual = document.documentElement.getAttribute("data-tema");
      const novo = atual === "escuro" ? "claro" : "escuro";
      document.documentElement.setAttribute("data-tema", novo);
      localStorage.setItem(CHAVE_TEMA, novo);
    });
  }
}

// ============================================================================
// HISTÓRICO DE CONSULTAS
// ============================================================================

function salvarHistorico(busca) {
  if (!busca || busca.length < 3) return;
  let itens = carregarHistorico();
  itens = [busca, ...itens.filter((item) => item.toLowerCase() !== busca.toLowerCase())].slice(0, 5);
  try {
    localStorage.setItem(CHAVE_HISTORICO, JSON.stringify(itens));
  } catch {}
  renderizarHistorico();
}

function carregarHistorico() {
  try {
    const dados = JSON.parse(localStorage.getItem(CHAVE_HISTORICO) || "[]");
    return Array.isArray(dados) ? dados : [];
  } catch {
    return [];
  }
}

function renderizarHistorico() {
  const itens = carregarHistorico();
  if (!conteinerHistorico || !gradeHistorico) return;
  gradeHistorico.replaceChildren();
  if (itens.length === 0) {
    conteinerHistorico.hidden = true;
    return;
  }
  itens.forEach((busca) => {
    const chip = criarElemento("button", "chip-historico", busca);
    chip.type = "button";
    chip.title = `Repetir busca: ${busca}`;
    chip.addEventListener("click", () => {
      pergunta.value = busca;
      pergunta.focus();
      ajustarAlturaTextarea(pergunta);
    });
    gradeHistorico.append(chip);
  });
  conteinerHistorico.hidden = false;
}

// ============================================================================
// VISUALIZADOR DE PDF LATERAL
// ============================================================================

function abrirVisualizadorPDF(url, titulo = "Acórdão do TJSP", subtitulo = "") {
  if (!gavetaPDF || !iframePDF) return;
  tituloGaveta.textContent = titulo;
  subtituloGaveta.textContent = subtitulo || "Documento Oficial";
  linkExternoPDF.href = url;
  iframePDF.src = url;
  gavetaPDF.hidden = false;
  if (backdropGaveta) backdropGaveta.hidden = false;
}

function fecharVisualizadorPDF() {
  if (!gavetaPDF) return;
  gavetaPDF.hidden = true;
  if (backdropGaveta) backdropGaveta.hidden = true;
  iframePDF.src = "about:blank";
}

// ============================================================================
// ETAPAS & SAÚDE DO SERVIÇO
// ============================================================================

function atualizarEtapa(etapa, concluida = false) {
  const indiceAtual = etapasPesquisa.findIndex((item) => item.dataset.etapa === etapa);
  etapasPesquisa.forEach((item, indice) => {
    const ativa = indice === indiceAtual;
    item.classList.toggle("ativa", ativa);
    item.classList.toggle("concluida", indice < indiceAtual || (ativa && concluida));
    if (ativa) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  });
  if (indiceAtual >= 0 && estadoEtapa) {
    const rotulo = etapasPesquisa[indiceAtual].querySelector("strong")?.textContent || etapa;
    estadoEtapa.textContent = `Etapa ${indiceAtual + 1} de ${etapasPesquisa.length}: ${rotulo}`;
  }
}

async function verificarSaude() {
  const elemento = document.querySelector("#estado-api");
  try {
    const resposta = await fetch("/saude");
    if (!resposta.ok) throw new Error("API indisponível");
    const dados = await resposta.json();
    estado.maxImportacao = Number(dados.max_importacao_pdfs) || 5;
    const maxCustoAnalise = Number(dados.max_custo_analise_documental_brl);
    estado.maxCustoAnaliseDocumentalBrl =
      Number.isFinite(maxCustoAnalise) && maxCustoAnalise > 0 ? maxCustoAnalise : null;

    if (elemento) {
      elemento.classList.add("online");
      elemento.classList.remove("offline");
      elemento.lastChild.textContent = " IA pronta";
    }
  } catch (_erro) {
    if (elemento) {
      elemento.classList.add("offline");
      elemento.classList.remove("online");
      elemento.lastChild.textContent = " Conexão instável";
    }
  }
}

// ============================================================================
// EXECUÇÃO DA PESQUISA AUTOMATIZADA
// ============================================================================

async function consumirSSEAssistida(payload) {
  const resposta = await fetch("/tjsp/pesquisa-assistida/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resposta.ok) {
    const erroJson = await resposta.json().catch(() => null);
    throw new Error(mensagemDaAPI(erroJson));
  }
  const reader = resposta.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let resultadoFinal = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocos = buffer.split("\n\n");
    buffer = blocos.pop() || "";

    for (const bloco of blocos) {
      const linhaData = bloco.split("\n").find((l) => l.startsWith("data: "));
      if (!linhaData) continue;
      try {
        const evento = JSON.parse(linhaData.slice(6));
        if (evento.tipo === "progresso") {
          estadoCarregando.querySelector("strong").textContent = evento.mensagem;
          if (evento.etapa === "coleta") {
            atualizarEtapa("precedentes");
          } else if (evento.etapa === "analise") {
            atualizarEtapa("analise");
          }
        } else if (evento.tipo === "resultado") {
          resultadoFinal = evento.dados;
        } else if (evento.tipo === "erro") {
          throw new Error(evento.erro);
        }
      } catch (e) {
        if (e.message && !e.message.includes("JSON")) throw e;
      }
    }
  }

  if (!resultadoFinal) {
    throw new Error("A resposta não pôde ser completada pelo servidor.");
  }
  return resultadoFinal;
}

async function executarPesquisa(evento) {
  if (evento) evento.preventDefault();
  const texto = pergunta.value.trim();
  if (!texto) {
    pergunta.focus();
    return;
  }
  salvarHistorico(texto);
  document.body.classList.add("fluxo-iniciado");

  atualizarEtapa(
    formulario.elements.contexto_caso && formulario.elements.contexto_caso.value.trim()
      ? "precedentes"
      : "esclarecimentos",
  );
  prepararCarregamento();

  const payload = {
    pergunta: texto,
    contexto_caso: formulario.elements.contexto_caso ? formulario.elements.contexto_caso.value.trim() : "",
  };

  try {
    let dados;
    try {
      dados = await consumirSSEAssistida(payload);
    } catch (_erroStream) {
      const resposta = await fetch("/tjsp/pesquisa-assistida", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      dados = await resposta.json();
      if (!resposta.ok) throw new Error(mensagemDaAPI(dados));
    }
    estado.ultimoResultado = dados;
    renderizarPesquisaAssistida(dados);
    await carregarAuditorias();
    focarResultados();
  } catch (erro) {
    exibirErro(erro instanceof Error ? erro.message : "Erro inesperado ao consultar o TJSP.");
  } finally {
    estadoCarregando.hidden = true;
    botaoEnviar.disabled = false;
  }
}

function prepararCarregamento() {
  estadoVazio.hidden = true;
  estadoErro.hidden = true;
  respostaIA.hidden = true;
  fontesResposta.hidden = true;
  barraImportacao.hidden = true;
  resultadoImportacao.hidden = true;
  contadorResultados.hidden = true;
  if (botaoCopiarRelatorio) botaoCopiarRelatorio.hidden = true;
  if (barraFiltros) barraFiltros.hidden = true;
  listaResultados.replaceChildren();
  gradeFontes.replaceChildren();
  estadoCarregando.hidden = false;
  estadoCarregando.querySelector("strong").textContent = "Pensando e consultando o TJSP...";
  estadoCarregando.querySelector("span").textContent =
    "Interpretando termos jurídicos e localizando decisões aderentes no tribunal...";
  botaoEnviar.disabled = true;
  tituloResultados.textContent = "Pesquisando decisões...";
}

// ============================================================================
// COPIAR PARECER / RELATÓRIO FORMATADO
// ============================================================================

async function copiarRelatorioFormatado() {
  if (!estado.ultimoResultado) return;
  const dados = estado.ultimoResultado;
  let markdown = `# Relatório de Jurisprudência — TJSP\n\n`;
  markdown += `**Tema:** ${dados.tema || pergunta.value.trim()}\n`;
  markdown += `**Data da consulta:** ${new Date().toLocaleDateString("pt-BR")}\n\n`;

  const processos = dados.processos || dados.decisoes || [];
  if (processos.length) {
    markdown += `### Precedentes e Fundamentos Aplicáveis:\n\n`;
    processos.forEach((p, idx) => {
      markdown += `#### ${idx + 1}. Processo ${p.processo || "—"} (Acórdão nº ${p.cd_acordao})\n`;
      if (p.relator) markdown += `- **Relator(a):** ${p.relator}\n`;
      if (p.orgao_julgador) markdown += `- **Órgão Julgador:** ${p.orgao_julgador}\n`;
      if (p.data_julgamento) markdown += `- **Data do Julgamento:** ${p.data_julgamento}\n`;
      if (p.argumento) markdown += `- **Aplicação ao Caso:** ${p.argumento}\n`;
      if (p.aderencia_fatica) markdown += `- **Similaridade Fática:** ${p.aderencia_fatica}\n`;
      if (p.ressalva) markdown += `- **Ponto de Atenção:** ${p.ressalva}\n`;
      if (p.ementa) markdown += `\n> *\"${p.ementa.trim()}\"*\n\n`;
    });
  }

  try {
    await navigator.clipboard.writeText(markdown);
    if (botaoCopiarRelatorio) {
      const textoOriginal = botaoCopiarRelatorio.textContent;
      botaoCopiarRelatorio.textContent = "✓ Parecer copiado!";
      setTimeout(() => {
        botaoCopiarRelatorio.textContent = textoOriginal;
      }, 2500);
    }
  } catch {
    alert("Não foi possível acessar a área de transferência.");
  }
}

// ============================================================================
// FILTROS DINÂMICOS
// ============================================================================

function renderizarFiltrosDinamicos(decisoes) {
  if (!barraFiltros || !conteinerChips) return;
  conteinerChips.replaceChildren();
  if (!decisoes || decisoes.length < 2) {
    barraFiltros.hidden = true;
    return;
  }

  const orgaos = [...new Set(decisoes.map((d) => d.orgao_julgador).filter(Boolean))].slice(0, 3);
  const relatores = [...new Set(decisoes.map((d) => d.relator).filter(Boolean))].slice(0, 3);

  const todos = [
    { tipo: "todos", rotulo: "Todas as decisões", valor: "" },
    ...orgaos.map((v) => ({ tipo: "orgao", rotulo: v, valor: v })),
    ...relatores.map((v) => ({ tipo: "relator", rotulo: `Rel. ${v}`, valor: v })),
  ];

  todos.forEach((item, idx) => {
    const chip = criarElemento("button", "chip-filtro", item.rotulo);
    chip.type = "button";
    if (idx === 0) chip.classList.add("ativo");
    chip.addEventListener("click", () => {
      conteinerChips.querySelectorAll(".chip-filtro").forEach((c) => c.classList.remove("ativo"));
      chip.classList.add("ativo");
      aplicarFiltroDinamico(item.tipo, item.valor);
    });
    conteinerChips.append(chip);
  });
  barraFiltros.hidden = false;
}

function aplicarFiltroDinamico(tipo, valor) {
  const cartoes = listaResultados.querySelectorAll(".cartao-resultado");
  cartoes.forEach((cartao) => {
    if (tipo === "todos" || !valor) {
      cartao.hidden = false;
      return;
    }
    const textoCartao = cartao.textContent.toLowerCase();
    cartao.hidden = !textoCartao.includes(valor.toLowerCase());
  });
}

// ============================================================================
// RENDERIZAÇÃO DE RESULTADOS
// ============================================================================

function renderizarPesquisaAssistida(dados) {
  const processos = Array.isArray(dados.processos) ? dados.processos : [];
  const consultas = Array.isArray(dados.consultas) ? dados.consultas : [];
  textoResposta.replaceChildren();

  if (dados.status === "precisa_esclarecimento") {
    atualizarEtapa("esclarecimentos");
    tituloResultados.textContent = "Dúvidas para refinar a busca";
    contadorResultados.textContent = `${(dados.questoes || []).length} pontos`;
    contadorResultados.hidden = false;
    textoResposta.append(
      criarElemento("h3", "", dados.tema || "Tema em definição"),
      criarElemento(
        "p",
        "",
        "Para encontrar os precedentes mais precisos, responda a estes pontos rápidos:",
      ),
      criarEntrevistaEsclarecimentos(dados.questoes || []),
    );
    respostaIA.hidden = false;
    return;
  }

  atualizarEtapa("precedentes");

  tituloResultados.textContent =
    processos.length === 0 ? "Nenhum precedente localizado" : "Decisões Selecionadas do TJSP";

  if (consultas.length) {
    const detalhes = criarElemento("details", "detalhes-resultado");
    const resumo = criarElemento("summary", "", "🔍 Ver estratégia de busca no tribunal");
    const listaConsultas = criarElemento("ol", "consultas-assistidas");
    consultas.forEach((consulta) => {
      const item = criarElemento("li");
      item.append(
        criarElemento("strong", "", consulta.pesquisa || "Consulta"),
        criarElemento("span", "", consulta.justificativa ? `— ${consulta.justificativa}` : ""),
      );
      listaConsultas.append(item);
    });
    detalhes.append(resumo, listaConsultas);
    textoResposta.append(detalhes);
    respostaIA.hidden = false;
  }

  contadorResultados.textContent = `${processos.length} acórdão(s) relevante(s)`;
  contadorResultados.hidden = false;
  if (botaoCopiarRelatorio && processos.length > 0) botaoCopiarRelatorio.hidden = false;

  if (processos.length === 0) {
    estadoVazio.querySelector("p").textContent =
      "Nenhuma decisão diretamente aderente foi localizada. Tente descrever o caso com termos mais amplos.";
    estadoVazio.hidden = false;
    return;
  }

  estado.consultaTJSP = dados.consulta_id;
  estado.recomendados = processos
    .slice(0, Math.min(3, estado.maxImportacao))
    .map((processo) => String(processo.cd_acordao));
  estado.selecionados = new Set(estado.recomendados);

  processos.forEach((processo) => {
    listaResultados.append(criarCartaoAssistido(processo));
  });

  renderizarFiltrosDinamicos(processos);
  atualizarSelecao();
  barraImportacao.hidden = false;
}

function criarCartaoAssistido(decisao) {
  const cartao = criarElemento("article", "cartao-resultado");

  // Cabeçalho
  const cabecalho = criarElemento("div", "cabecalho-cartao-resultado");
  const numProcesso = decisao.processo || `Acórdão nº ${decisao.cd_acordao}`;
  cabecalho.append(criarElemento("span", "numero-processo", numProcesso));

  const relevancia = decisao.relevancia != null ? Math.round(decisao.relevancia * 100) : null;
  if (relevancia != null) {
    cabecalho.append(criarElemento("span", "badge-aderencia", `★ ${relevancia}% aderente ao caso`));
  }
  cartao.append(cabecalho);

  // Metadados
  const metadados = criarElemento("div", "metadados-resultado");
  [decisao.orgao_julgador, decisao.classe, decisao.data_julgamento ? `Julgado em ${decisao.data_julgamento}` : ""]
    .filter(Boolean)
    .forEach((item) => metadados.append(criarElemento("span", "", item)));
  cartao.append(metadados);

  // Aplicação ao Caso
  if (decisao.argumento || decisao.aderencia_fatica) {
    const caixaArgumento = criarElemento("div", "caixa-argumento");
    caixaArgumento.append(
      criarElemento("strong", "", "Como este julgado apoia seu caso:"),
      criarElemento("p", "", decisao.argumento || decisao.aderencia_fatica),
    );
    if (decisao.ressalva) {
      caixaArgumento.append(
        criarElemento("small", "", `⚠️ Atenção: ${decisao.ressalva}`),
      );
    }
    cartao.append(caixaArgumento);
  }

  // Ementa
  const ementa = decisao.ementa || "Ementa não informada.";
  cartao.append(
    criarDetalhesResultado(
      "Ver ementa da decisão",
      criarElemento("p", "ementa-completa", ementa),
    ),
  );

  // Rodapé com Botão de Leitura de PDF
  const rodape = criarElemento("div", "rodape-cartao");
  const acoes = criarElemento("div", "acoes-cartao");

  const botaoPDF = criarElemento("button", "botao-ler-pdf", "📄 Ler Decisão Completa");
  botaoPDF.type = "button";
  botaoPDF.addEventListener("click", () => {
    const url = `/documentos/${decisao.cd_acordao}`;
    abrirVisualizadorPDF(url, `Processo ${decisao.processo || decisao.cd_acordao}`, decisao.orgao_julgador || "");
  });
  acoes.append(botaoPDF);

  const linkTJSP = criarLinkSeguro(decisao.inteiro_teor_url, "Ver no TJSP ↗");
  if (linkTJSP) {
    linkTJSP.className = "link-tjsp";
    acoes.append(linkTJSP);
  }

  rodape.append(acoes);
  cartao.append(rodape);

  return cartao;
}

function criarEntrevistaEsclarecimentos(questoes) {
  const entrevista = criarElemento("section", "entrevista-esclarecimentos");
  const compositor = criarElemento("form", "compositor-entrevista");
  const rotulo = criarElemento("label", "", "Sua resposta");
  rotulo.htmlFor = "resposta-entrevista";
  const resposta = criarElemento("textarea");
  resposta.id = "resposta-entrevista";
  resposta.rows = 2;
  resposta.maxLength = 2000;
  resposta.required = true;
  resposta.placeholder = "Digite aqui para refinar a busca...";
  const botao = criarElemento("button", "botao-principal");
  botao.type = "submit";
  botao.append(criarElemento("span", "", "Continuar pesquisa"), criarElemento("b", "", "→"));
  compositor.append(rotulo, resposta, botao);
  entrevista.append(compositor);

  let indice = 0;
  const respostas = [];

  function mostrarQuestao() {
    const questaoAtual = questoes[indice];
    if (questaoAtual) {
      rotulo.textContent = questaoAtual;
      resposta.value = "";
      resposta.focus();
    }
  }

  compositor.addEventListener("submit", (e) => {
    e.preventDefault();
    const texto = resposta.value.trim();
    if (!texto) return;
    respostas.push({ questao: questoes[indice], resposta: texto });
    indice += 1;
    if (indice < questoes.length) {
      mostrarQuestao();
    } else {
      const contextoAtual = formulario.elements.contexto_caso ? formulario.elements.contexto_caso.value.trim() : "";
      const novoContexto = respostas.map(({ questao: q, resposta: r }) => `${q}: ${r}`).join("\n");
      if (formulario.elements.contexto_caso) {
        formulario.elements.contexto_caso.value = contextoAtual ? `${contextoAtual}\n\n${novoContexto}` : novoContexto;
      }
      entrevista.replaceChildren(
        criarElemento("p", "sucesso-entrevista", "✓ Refinamentos aplicados. Reexecutando pesquisa..."),
      );
      setTimeout(() => {
        formulario.dispatchEvent(new Event("submit", { cancelable: true }));
      }, 500);
    }
  });

  mostrarQuestao();
  return entrevista;
}

function alternarSelecao(seletor) {
  const valor = String(seletor.value);
  if (seletor.checked) {
    if (estado.selecionados.size >= estado.maxImportacao) {
      seletor.checked = false;
      alert(`Você pode selecionar no máximo ${estado.maxImportacao} acórdãos por vez.`);
      return;
    }
    estado.selecionados.add(valor);
  } else {
    estado.selecionados.delete(valor);
  }
  atualizarSelecao();
}

function selecionarRecomendados() {
  estado.selecionados = new Set(estado.recomendados.slice(0, estado.maxImportacao));
  atualizarSelecao();
}

function limparSelecao() {
  estado.selecionados.clear();
  atualizarSelecao();
}

function atualizarSelecao() {
  const total = estado.selecionados.size;
  if (quantidadeSelecionada) {
    quantidadeSelecionada.textContent = `${total} acórdão(s) selecionado(s) de ${estado.maxImportacao}`;
  }
  if (botaoImportar) botaoImportar.disabled = total === 0;
}

async function importarSelecionados() {
  if (!estado.consultaTJSP || estado.selecionados.size === 0) return;
  atualizarEtapa("analise");
  botaoImportar.disabled = true;
  resultadoImportacao.hidden = false;
  resultadoImportacao.replaceChildren(
    criarElemento("p", "texto-carregando", `Baixando e indexando ${estado.selecionados.size} acórdão(s)...`),
  );

  try {
    const resposta = await fetch("/tjsp/importar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        consulta_id: estado.consultaTJSP,
        cd_acordaos: [...estado.selecionados],
      }),
    });
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(mensagemDaAPI(dados));
    resultadoImportacao.replaceChildren(
      criarElemento("p", "sucesso-entrevista", `✓ ${dados.processados} acórdão(s) prontos para leitura e análise.`),
    );
  } catch (erro) {
    resultadoImportacao.replaceChildren(
      criarElemento("p", "alerta-validacao", erro instanceof Error ? erro.message : "Falha ao baixar acórdãos."),
    );
  } finally {
    botaoImportar.disabled = false;
  }
}

async function carregarAuditorias() {
  if (!listaAuditorias) return;
  try {
    const resposta = await fetch("/auditorias?limite=5");
    const dados = await resposta.json();
    if (!resposta.ok) return;
    const auditorias = Array.isArray(dados) ? dados : [];
    listaAuditorias.replaceChildren();
    if (auditorias.length === 0) {
      listaAuditorias.append(criarElemento("p", "texto-suave", "Nenhuma consulta realizada ainda."));
      return;
    }
    auditorias.forEach((a) => {
      const item = criarElemento("div", "chip-historico", limitarTexto(a.pergunta || "Pesquisa", 60));
      listaAuditorias.append(item);
    });
  } catch {}
}

function exibirErro(mensagem, titulo = "Não foi possível concluir a pesquisa") {
  tituloResultados.textContent = titulo;
  mensagemErro.textContent = mensagem;
  estadoErro.hidden = false;
  estadoErro.tabIndex = -1;
  estadoErro.focus();
}

function focarResultados() {
  secaoResultados.focus({ preventScroll: true });
  secaoResultados.scrollIntoView({ behavior: "smooth", block: "start" });
}

function mensagemDaAPI(dados) {
  const detalhe = dados && dados.detail;
  if (typeof detalhe === "string") return detalhe;
  if (detalhe && typeof detalhe.erro === "string") return detalhe.erro;
  if (Array.isArray(detalhe) && detalhe[0] && detalhe[0].msg) return detalhe[0].msg;
  return "O servidor retornou uma resposta inesperada.";
}

function criarElemento(tag, classe = "", texto = "") {
  const elemento = document.createElement(tag);
  if (classe) elemento.className = classe;
  if (texto !== "") elemento.textContent = String(texto);
  return elemento;
}

function criarDetalhesResultado(rotulo, ...conteudos) {
  const detalhes = criarElemento("details", "detalhes-resultado");
  const resumo = criarElemento("summary", "", rotulo);
  detalhes.append(resumo, ...conteudos);
  return detalhes;
}

function criarLinkSeguro(url, texto) {
  if (!url) return null;
  try {
    const destino = new URL(url, window.location.origin);
    if (!['http:', 'https:'].includes(destino.protocol)) return null;
    const link = criarElemento("a", "", texto);
    link.href = destino.href;
    link.target = "_blank";
    link.rel = "noreferrer";
    return link;
  } catch {
    return null;
  }
}

function limitarTexto(texto, limite) {
  const limpo = String(texto).replace(/\s+/g, " ").trim();
  return limpo.length > limite ? `${limpo.slice(0, limite).trim()}…` : limpo;
}
