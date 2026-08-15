"use strict";

const estado = {
  modo: "assistida",
  consultaTJSP: null,
  selecionados: new Set(),
  maxImportacao: 5,
  perguntaContexto: null,
};
const formulario = document.querySelector("#formulario-pesquisa");
const pergunta = document.querySelector("#pergunta");
const botaoEnviar = document.querySelector("#botao-enviar");
const avisoModo = document.querySelector("#aviso-modo");
const limitesIA = document.querySelector("#limites-ia");
const painelFiltros = document.querySelector(".painel-filtros");
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
const filtrosLocais = document.querySelector("#filtros-locais");
const filtrosTJSP = document.querySelector("#filtros-tjsp");
const limitesLocais = document.querySelector("#limites-locais");
const barraImportacao = document.querySelector("#barra-importacao");
const botaoImportar = document.querySelector("#botao-importar");
const quantidadeSelecionada = document.querySelector("#quantidade-selecionada");
const resultadoImportacao = document.querySelector("#resultado-importacao");

document.querySelectorAll("[data-modo]").forEach((botao) => {
  botao.addEventListener("click", () => alterarModo(botao.dataset.modo));
});

document.querySelectorAll("[data-consulta]").forEach((botao) => {
  botao.addEventListener("click", () => {
    pergunta.value = botao.dataset.consulta;
    pergunta.focus();
  });
});

formulario.addEventListener("submit", executarPesquisa);
botaoAuditorias.addEventListener("click", carregarAuditorias);
botaoImportar.addEventListener("click", importarSelecionados);

alterarModo("assistida");
verificarSaude();
carregarAuditorias();

function alterarModo(modo) {
  estado.modo = ["busca", "ia", "tjsp", "assistida"].includes(modo) ? modo : "busca";
  document.querySelectorAll("[data-modo]").forEach((botao) => {
    const ativo = botao.dataset.modo === estado.modo;
    botao.classList.toggle("ativo", ativo);
    botao.setAttribute("aria-selected", String(ativo));
  });
  const coletaTJSP = estado.modo === "tjsp";
  const pesquisaAssistida = estado.modo === "assistida";
  filtrosLocais.hidden = coletaTJSP;
  filtrosTJSP.hidden = !coletaTJSP;
  limitesLocais.hidden = coletaTJSP;
  limitesIA.hidden = estado.modo !== "ia";
  painelFiltros.hidden = pesquisaAssistida;
  document.querySelector("#limite-fontes").max = estado.modo === "ia" ? "20" : "50";
  const textosBotao = {
    busca: "Buscar jurisprudência",
    ia: "Gerar resposta fundamentada",
    tjsp: "Pesquisar no site do TJSP",
    assistida: "Iniciar pesquisa com IA",
  };
  const avisos = {
    busca: "Busca local em SQLite + Chroma. Nenhuma chamada de IA.",
    ia: "Usa Maritaca após verificar fontes e teto de custo.",
    tjsp: "Consulta externa controlada no CJSG. Sem chamada de IA.",
    assistida:
      "Maritaca planeja a pesquisa; scraper consulta o TJSP em tempo real.",
  };
  botaoEnviar.querySelector("span").textContent = textosBotao[estado.modo];
  avisoModo.textContent = avisos[estado.modo];
}

async function verificarSaude() {
  const elemento = document.querySelector("#estado-api");
  try {
    const resposta = await fetch("/saude");
    if (!resposta.ok) throw new Error("API indisponível");
    const dados = await resposta.json();
    const campoCusto = formulario.elements.max_custo_brl;
    const campoTokens = formulario.elements.max_output_tokens;
    campoCusto.max = String(dados.max_custo_brl);
    campoTokens.max = String(dados.max_output_tokens);
    if (Number(campoCusto.value) > dados.max_custo_brl) {
      campoCusto.value = String(dados.max_custo_brl);
    }
    if (Number(campoTokens.value) > dados.max_output_tokens) {
      campoTokens.value = String(dados.max_output_tokens);
    }
    estado.maxImportacao = Number(dados.max_importacao_pdfs) || 5;
    formulario.elements.paginas_tjsp.max = String(dados.max_paginas_tjsp || 1);
    elemento.classList.add("online");
    elemento.classList.remove("sem-dados");
    elemento.classList.remove("offline");
    elemento.lastChild.textContent = " API ativa · pesquisa TJSP";
  } catch (_erro) {
    elemento.classList.add("offline");
    elemento.classList.remove("online", "sem-dados");
    elemento.lastChild.textContent = " API indisponível";
  }
}

async function executarPesquisa(evento) {
  evento.preventDefault();
  const texto = pergunta.value.trim();
  if (!texto) {
    pergunta.focus();
    return;
  }
  if (estado.perguntaContexto !== null && estado.perguntaContexto !== texto) {
    formulario.elements.contexto_caso.value = "";
  }
  estado.perguntaContexto = texto;

  prepararCarregamento();
  const limite = Number(formulario.elements.limite.value || 6);
  let endpoint;
  let payload;
  if (estado.modo === "assistida") {
    endpoint = "/tjsp/pesquisa-assistida";
    payload = {
      pergunta: texto,
      contexto_caso: formulario.elements.contexto_caso.value.trim(),
    };
  } else if (estado.modo === "tjsp") {
    endpoint = "/tjsp/pesquisar";
    payload = {
      pesquisa: texto,
      inicio: converterDataBR(formulario.elements.inicio_tjsp.value),
      fim: converterDataBR(formulario.elements.fim_tjsp.value),
      tipo: formulario.elements.tipo_tjsp.value,
      origem: formulario.elements.origem_tjsp.value,
      sinonimos: formulario.elements.sinonimos_tjsp.checked,
      paginas: Number(formulario.elements.paginas_tjsp.value || 1),
    };
  } else {
    const filtros = coletarFiltros();
    endpoint = estado.modo === "ia" ? "/perguntar" : "/buscar";
    payload =
      estado.modo === "ia"
        ? {
            pergunta: texto,
            limite_fontes: limite,
            max_output_tokens: Number(formulario.elements.max_output_tokens.value),
            max_custo_brl: Number(formulario.elements.max_custo_brl.value),
            filtros,
          }
        : { pergunta: texto, limite, filtros };
  }

  try {
    const resposta = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(mensagemDaAPI(dados));
    if (estado.modo === "assistida") {
      renderizarPesquisaAssistida(dados);
      await carregarAuditorias();
    } else if (estado.modo === "ia") {
      renderizarResposta(dados);
      await carregarAuditorias();
    } else if (estado.modo === "tjsp") {
      renderizarPesquisaTJSP(dados);
    } else {
      renderizarBusca(dados);
    }
  } catch (erro) {
    exibirErro(erro instanceof Error ? erro.message : "Erro inesperado.");
  } finally {
    estadoCarregando.hidden = true;
    botaoEnviar.disabled = false;
  }
}

function coletarFiltros() {
  const filtros = {};
  ["processo", "cd_acordao", "assunto", "orgao_julgador", "classe"].forEach(
    (nome) => {
      const valor = formulario.elements[nome].value.trim();
      if (valor) filtros[nome] = valor;
    },
  );
  const pagina = formulario.elements.pagina.value;
  if (pagina) filtros.pagina = Number(pagina);
  return filtros;
}

function prepararCarregamento() {
  estadoVazio.hidden = true;
  estadoErro.hidden = true;
  respostaIA.hidden = true;
  fontesResposta.hidden = true;
  barraImportacao.hidden = true;
  resultadoImportacao.hidden = true;
  contadorResultados.hidden = true;
  listaResultados.replaceChildren();
  gradeFontes.replaceChildren();
  estadoCarregando.hidden = false;
  estadoCarregando.querySelector("strong").textContent =
    estado.modo === "assistida"
      ? "Planejando pesquisa jurisprudencial"
      : estado.modo === "tjsp"
        ? "Consultando o portal do TJSP"
        : "Consultando a base local";
  estadoCarregando.querySelector("span").textContent =
    estado.modo === "assistida"
      ? "Maritaca formulará as consultas e analisará as ementas encontradas…"
      : estado.modo === "tjsp"
        ? "A pesquisa externa respeita o intervalo entre requisições…"
        : "Combinando busca lexical e semântica…";
  botaoEnviar.disabled = true;
  tituloResultados.textContent =
    estado.modo === "assistida"
      ? "Planejando e consultando o TJSP"
      : estado.modo === "ia"
      ? "Preparando resposta"
      : estado.modo === "tjsp"
        ? "Consultando o TJSP"
        : "Pesquisando decisões";
}

function renderizarBusca(dados) {
  const resultados = Array.isArray(dados.resultados) ? dados.resultados : [];
  tituloResultados.textContent =
    resultados.length === 0 ? "Nenhuma decisão encontrada" : "Decisões encontradas";
  contadorResultados.textContent = `${resultados.length} resultado${resultados.length === 1 ? "" : "s"}`;
  contadorResultados.hidden = false;

  if (resultados.length === 0) {
    estadoVazio.querySelector("p").textContent =
      "Tente retirar filtros ou usar conceitos jurídicos mais amplos.";
    estadoVazio.hidden = false;
    return;
  }
  resultados.forEach((resultado, indice) => {
    listaResultados.append(criarCartaoResultado(resultado, indice + 1));
  });
}

function criarCartaoResultado(resultado, numero) {
  const cartao = criarElemento("article", "cartao-resultado");
  cartao.append(criarElemento("span", "numero-resultado", String(numero).padStart(2, "0")));

  const conteudo = criarElemento("div");
  const metadata = resultado.metadata || {};
  conteudo.append(
    criarElemento("h3", "", metadata.citacao || `Acórdão ${metadata.cd_acordao || resultado.id}`),
    criarElemento("p", "", limitarTexto(resultado.texto || "", 560)),
  );
  const metadados = criarElemento("div", "metadados-resultado");
  const origem = Array.isArray(resultado.origens) ? resultado.origens.join(" + ") : "híbrida";
  metadados.append(criarElemento("span", "", origem));
  if (metadata.classe) metadados.append(criarElemento("span", "", metadata.classe));
  if (metadata.assunto) metadados.append(criarElemento("span", "", metadata.assunto));
  if (metadata.pagina) metadados.append(criarElemento("span", "", `p. ${metadata.pagina}`));
  conteudo.append(metadados);
  cartao.append(conteudo);

  const link = criarLinkSeguro(metadata.inteiro_teor_url, "Abrir fonte ↗");
  if (link) {
    link.className = "acao-resultado";
    cartao.append(link);
  }
  return cartao;
}

function renderizarPesquisaAssistida(dados) {
  const processos = Array.isArray(dados.processos) ? dados.processos : [];
  const consultas = Array.isArray(dados.consultas) ? dados.consultas : [];
  const questoes = Array.isArray(dados.questoes) ? dados.questoes : [];
  respostaIA.querySelector("header span").textContent = "Estratégia de pesquisa";
  textoResposta.replaceChildren();
  metricasResposta.replaceChildren();

  if (dados.status === "precisa_esclarecimento") {
    tituloResultados.textContent = "IA precisa de mais contexto";
    textoResposta.append(
      criarElemento(
        "p",
        "",
        "Responda uma pergunta por vez. Suas respostas formarão o contexto da pesquisa:",
      ),
    );
    textoResposta.append(criarEntrevistaEsclarecimentos(questoes));
    respostaIA.hidden = false;
    contadorResultados.textContent = "Nenhuma consulta feita no TJSP";
    contadorResultados.hidden = false;
    renderizarCustoAssistido(dados);
    return;
  }

  tituloResultados.textContent =
    processos.length === 0 ? "Nenhum candidato encontrado" : "Processos sugeridos pela IA";
  textoResposta.append(
    criarElemento("h3", "", dados.tema || "Estratégia gerada"),
    criarElemento(
      "p",
      "",
      "Consultas formuladas pela Maritaca e executadas no CJSG do TJSP:",
    ),
  );
  const listaConsultas = criarElemento("ol", "consultas-assistidas");
  consultas.forEach((consulta) => {
    const item = criarElemento("li");
    item.append(
      criarElemento("strong", "", consulta.pesquisa || "Consulta"),
      criarElemento("span", "", consulta.justificativa || ""),
    );
    listaConsultas.append(item);
  });
  textoResposta.append(listaConsultas);
  if (dados.analise_parcial) {
    textoResposta.append(
      criarElemento(
        "p",
        "aviso-analise-parcial",
        "A resposta da Maritaca atingiu o limite de tokens. Resultados completos foram preservados; itens interrompidos foram descartados.",
      ),
    );
  }
  respostaIA.hidden = false;
  renderizarCustoAssistido(dados);

  contadorResultados.textContent = `${processos.length} processo${processos.length === 1 ? "" : "s"} ranqueado${processos.length === 1 ? "" : "s"}`;
  contadorResultados.hidden = false;
  if (processos.length === 0) {
    estadoVazio.querySelector("p").textContent =
      "A estratégia foi executada, mas nenhuma ementa aderente foi localizada. Acrescente fatos ou ajuste a tese.";
    estadoVazio.hidden = false;
    return;
  }

  estado.consultaTJSP = dados.consulta_id;
  estado.selecionados = new Set(
    processos
      .slice(0, Math.min(3, estado.maxImportacao))
      .map((processo) => String(processo.cd_acordao)),
  );
  processos.forEach((processo, indice) => {
    listaResultados.append(criarCartaoAssistido(processo, indice + 1));
  });
  atualizarSelecao();
  barraImportacao.hidden = false;
}

function criarEntrevistaEsclarecimentos(questoes) {
  const entrevista = criarElemento("section", "entrevista-esclarecimentos");
  const progresso = criarElemento("small", "progresso-entrevista");
  const historico = criarElemento("div", "historico-entrevista");
  historico.setAttribute("aria-live", "polite");
  const compositor = criarElemento("form", "compositor-entrevista");
  const rotulo = criarElemento("label", "", "Sua resposta");
  rotulo.htmlFor = "resposta-entrevista";
  const resposta = criarElemento("textarea");
  resposta.id = "resposta-entrevista";
  resposta.rows = 3;
  resposta.maxLength = 2_000;
  resposta.required = true;
  resposta.placeholder = "Responda com os fatos relevantes";
  const botao = criarElemento("button", "botao-principal");
  botao.type = "submit";
  botao.append(
    criarElemento("span", "", "Próxima pergunta"),
    criarElemento("b", "", "→"),
  );
  compositor.append(rotulo, resposta, botao);
  entrevista.append(progresso, historico, compositor);

  let indice = 0;
  const respostas = [];
  adicionarMensagemEntrevista(historico, "ia", questoes[indice]);
  atualizarEntrevista();

  compositor.addEventListener("submit", (evento) => {
    evento.preventDefault();
    const texto = resposta.value.trim();
    if (!texto) return;
    respostas.push(texto);
    adicionarMensagemEntrevista(historico, "usuario", texto);
    resposta.value = "";

    if (indice < questoes.length - 1) {
      indice += 1;
      adicionarMensagemEntrevista(historico, "ia", questoes[indice]);
      atualizarEntrevista();
      resposta.focus();
      return;
    }

    const pares = questoes.map(
      (questao, posicao) => `Pergunta: ${questao}\nResposta: ${respostas[posicao]}`,
    );
    const contextoAnterior = formulario.elements.contexto_caso.value.trim();
    formulario.elements.contexto_caso.value = [
      contextoAnterior,
      "Entrevista de esclarecimento:",
      ...pares,
    ]
      .filter(Boolean)
      .join("\n\n")
      .slice(0, 8_000);
    formulario.requestSubmit();
  });

  function atualizarEntrevista() {
    progresso.textContent = `Pergunta ${indice + 1} de ${questoes.length}`;
    botao.querySelector("span").textContent =
      indice === questoes.length - 1 ? "Concluir e pesquisar" : "Próxima pergunta";
  }
  return entrevista;
}

function adicionarMensagemEntrevista(historico, autor, texto) {
  const mensagem = criarElemento("article", `mensagem-entrevista ${autor}`);
  mensagem.append(
    criarElemento("small", "", autor === "ia" ? "Assistente" : "Você"),
    criarElemento("p", "", texto),
  );
  historico.append(mensagem);
  mensagem.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderizarCustoAssistido(dados) {
  const custo = dados.custo || {};
  const auditorias = Array.isArray(dados.auditorias_ia) ? dados.auditorias_ia : [];
  const itens = [
    ["Chamadas de IA", auditorias.length],
    ["Custo estimado", formatarReal(custo.custo_padrao_estimado_brl)],
    ["Auditorias", auditorias.length ? auditorias.map((id) => `#${id}`).join(", ") : "—"],
  ];
  itens.forEach(([rotulo, valor]) => {
    const grupo = criarElemento("div");
    grupo.append(criarElemento("dt", "", rotulo), criarElemento("dd", "", valor));
    metricasResposta.append(grupo);
  });
}

function criarCartaoAssistido(decisao, numero) {
  const cartao = criarElemento("article", "cartao-resultado selecionavel");
  const seletor = criarElemento("input", "seletor-acordao");
  seletor.type = "checkbox";
  seletor.value = String(decisao.cd_acordao);
  seletor.checked = estado.selecionados.has(seletor.value);
  seletor.setAttribute("aria-label", `Selecionar acórdão ${decisao.cd_acordao}`);
  seletor.addEventListener("change", () => alternarSelecao(seletor));
  cartao.append(
    seletor,
    criarElemento("span", "numero-resultado", String(numero).padStart(2, "0")),
  );

  const conteudo = criarElemento("div");
  const relevancia = Math.round(Number(decisao.relevancia || 0) * 100);
  conteudo.append(
    criarElemento(
      "h3",
      "",
      decisao.processo
        ? `${decisao.processo} · Acórdão ${decisao.cd_acordao}`
        : `Acórdão ${decisao.cd_acordao}`,
    ),
    criarElemento("span", "selo-relevancia", `${relevancia}% de aderência`),
    criarElemento("p", "ementa-assistida", limitarTexto(decisao.ementa || "", 700)),
  );
  const analise = criarElemento("div", "analise-processo");
  [
    ["Uso possível", decisao.argumento],
    ["Aderência fática", decisao.aderencia_fatica],
    ["Ressalva", decisao.ressalva],
  ].forEach(([rotulo, texto]) => {
    if (!texto) return;
    const bloco = criarElemento("p");
    bloco.append(criarElemento("strong", "", `${rotulo}: `), document.createTextNode(texto));
    analise.append(bloco);
  });
  conteudo.append(analise);
  const metadados = criarElemento("div", "metadados-resultado");
  [decisao.classe, decisao.assunto, decisao.orgao_julgador, decisao.data_julgamento]
    .filter(Boolean)
    .forEach((item) => metadados.append(criarElemento("span", "", item)));
  conteudo.append(metadados);
  cartao.append(conteudo);

  const link = criarLinkSeguro(decisao.inteiro_teor_url, "Ver no TJSP ↗");
  if (link) {
    link.className = "acao-resultado";
    cartao.append(link);
  }
  return cartao;
}

function renderizarPesquisaTJSP(dados) {
  const decisoes = Array.isArray(dados.decisoes) ? dados.decisoes : [];
  estado.consultaTJSP = dados.consulta_id;
  estado.selecionados = new Set(
    decisoes
      .slice(0, Math.min(3, estado.maxImportacao))
      .map((decisao) => String(decisao.cd_acordao)),
  );
  tituloResultados.textContent =
    decisoes.length === 0 ? "Nenhuma decisão encontrada no TJSP" : "Resultados no TJSP";
  contadorResultados.textContent =
    `${decisoes.length} coletados · ${formatarNumero(dados.total_disponivel)} disponíveis`;
  contadorResultados.hidden = false;

  if (decisoes.length === 0) {
    estadoVazio.querySelector("p").textContent =
      "Tente outros termos ou informe um intervalo de julgamento.";
    estadoVazio.hidden = false;
    return;
  }
  decisoes.forEach((decisao, indice) => {
    listaResultados.append(criarCartaoTJSP(decisao, indice + 1));
  });
  atualizarSelecao();
  barraImportacao.hidden = false;
}

function criarCartaoTJSP(decisao, numero) {
  const cartao = criarElemento("article", "cartao-resultado selecionavel");
  const seletor = criarElemento("input", "seletor-acordao");
  seletor.type = "checkbox";
  seletor.value = String(decisao.cd_acordao);
  seletor.checked = estado.selecionados.has(seletor.value);
  seletor.setAttribute("aria-label", `Selecionar acórdão ${decisao.cd_acordao}`);
  seletor.addEventListener("change", () => alternarSelecao(seletor));
  cartao.append(
    seletor,
    criarElemento("span", "numero-resultado", String(numero).padStart(2, "0")),
  );

  const conteudo = criarElemento("div");
  conteudo.append(
    criarElemento(
      "h3",
      "",
      decisao.processo
        ? `${decisao.processo} · Acórdão ${decisao.cd_acordao}`
        : `Acórdão ${decisao.cd_acordao}`,
    ),
    criarElemento("p", "", limitarTexto(decisao.ementa || "Ementa não informada.", 620)),
  );
  const metadados = criarElemento("div", "metadados-resultado");
  [decisao.classe, decisao.assunto, decisao.orgao_julgador, decisao.data_julgamento]
    .filter(Boolean)
    .forEach((item) => metadados.append(criarElemento("span", "", item)));
  conteudo.append(metadados);
  cartao.append(conteudo);

  const link = criarLinkSeguro(decisao.inteiro_teor_url, "Ver no TJSP ↗");
  if (link) {
    link.className = "acao-resultado";
    cartao.append(link);
  }
  return cartao;
}

function alternarSelecao(seletor) {
  estadoErro.hidden = true;
  if (seletor.checked && estado.selecionados.size >= estado.maxImportacao) {
    seletor.checked = false;
    mensagemErro.textContent = `Selecione no máximo ${estado.maxImportacao} acórdãos por importação.`;
    estadoErro.hidden = false;
    return;
  }
  if (seletor.checked) estado.selecionados.add(seletor.value);
  else estado.selecionados.delete(seletor.value);
  atualizarSelecao();
}

function atualizarSelecao() {
  const total = estado.selecionados.size;
  quantidadeSelecionada.textContent =
    `${total} acórdão${total === 1 ? "" : "s"} selecionado${total === 1 ? "" : "s"}`;
  botaoImportar.disabled = total === 0;
}

async function importarSelecionados() {
  if (!estado.consultaTJSP || estado.selecionados.size === 0) return;
  const acordaosImportados = [...estado.selecionados];
  estadoErro.hidden = true;
  resultadoImportacao.hidden = true;
  botaoImportar.disabled = true;
  botaoImportar.querySelector("span").textContent = "Baixando e processando…";
  try {
    const resposta = await fetch("/tjsp/importar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        consulta_id: estado.consultaTJSP,
        cd_acordaos: acordaosImportados,
      }),
    });
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(mensagemDaAPI(dados));
    renderizarImportacao(dados, acordaosImportados);
    await verificarSaude();
  } catch (erro) {
    mensagemErro.textContent =
      erro instanceof Error ? erro.message : "Erro inesperado durante a importação.";
    estadoErro.hidden = false;
  } finally {
    botaoImportar.querySelector("span").textContent = "Importar e indexar";
    botaoImportar.disabled = estado.selecionados.size === 0;
  }
}

function renderizarImportacao(dados, cdAcordaos) {
  const erros = Array.isArray(dados.erros) ? dados.erros : [];
  resultadoImportacao.replaceChildren(
    criarElemento(
      "h3",
      "",
      erros.length === 0 ? "Base local atualizada" : "Importação concluída com ressalvas",
    ),
    criarElemento(
      "p",
      "",
      `${dados.processados} PDF(s) processado(s), ${dados.chunks_indexados} trecho(s) indexado(s), ${erros.length} erro(s).`,
    ),
  );
  if (Number(dados.processados) > 0) {
    resultadoImportacao.append(
      criarElemento(
        "p",
        "aviso-custo-analise",
        "A análise dos inteiros teores faz uma nova chamada Maritaca, limitada pelo servidor a R$ 0,20.",
      ),
    );
    const botaoAnalisar = criarElemento("button", "botao-principal botao-analisar");
    botaoAnalisar.type = "button";
    botaoAnalisar.append(
      criarElemento("span", "", "Analisar PDFs com IA"),
      criarElemento("b", "", "→"),
    );
    botaoAnalisar.addEventListener("click", () =>
      analisarDocumentosImportados(cdAcordaos, botaoAnalisar),
    );
    resultadoImportacao.append(botaoAnalisar);
  }
  resultadoImportacao.hidden = false;
  tituloResultados.textContent = "Importação concluída";
}

async function analisarDocumentosImportados(cdAcordaos, botao) {
  estadoErro.hidden = true;
  botao.disabled = true;
  botao.querySelector("span").textContent = "Analisando inteiros teores…";
  try {
    const resposta = await fetch("/tjsp/analisar-documentos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pergunta: pergunta.value.trim(),
        contexto_caso: formulario.elements.contexto_caso.value.trim(),
        cd_acordaos: cdAcordaos,
      }),
    });
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(mensagemDaAPI(dados));
    renderizarAnaliseDocumental(dados);
    await carregarAuditorias();
  } catch (erro) {
    mensagemErro.textContent =
      erro instanceof Error ? erro.message : "Erro durante análise dos documentos.";
    estadoErro.hidden = false;
  } finally {
    botao.querySelector("span").textContent = "Analisar PDFs com IA";
    botao.disabled = false;
  }
}

function renderizarAnaliseDocumental(dados) {
  const validacao = dados.validacao || {};
  tituloResultados.textContent = "Argumentos encontrados nos inteiros teores";
  respostaIA.querySelector("header span").textContent = "Análise documental validada";
  contadorResultados.textContent =
    `Auditoria #${dados.auditoria_id} · ${validacao.aprovada ? "referências verificadas" : "revisão necessária"}`;
  contadorResultados.hidden = false;
  textoResposta.replaceChildren();
  if (!validacao.aprovada) {
    textoResposta.append(
      criarElemento(
        "p",
        "alerta-validacao",
        "A resposta contém citação ou referência que não foi confirmada nos trechos recuperados. Revise antes de utilizar.",
      ),
    );
  }
  adicionarTextoComCitacoes(textoResposta, dados.texto || "", dados.fontes || []);
  renderizarMetricas(dados);
  respostaIA.hidden = false;
  renderizarFontes(dados.fontes || []);
  respostaIA.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderizarResposta(dados) {
  tituloResultados.textContent = "Resposta e fundamentos";
  respostaIA.querySelector("header span").textContent = "Resposta fundamentada";
  contadorResultados.textContent = `Auditoria #${dados.auditoria_id}`;
  contadorResultados.hidden = false;
  textoResposta.replaceChildren();
  adicionarTextoComCitacoes(textoResposta, dados.texto || "", dados.fontes || []);
  renderizarMetricas(dados);
  respostaIA.hidden = false;
  renderizarFontes(dados.fontes || []);
}

function adicionarTextoComCitacoes(conteiner, texto, fontes) {
  const expressao = /\[Fonte\s+(\d+)\]/gi;
  let inicio = 0;
  let ocorrencia;
  while ((ocorrencia = expressao.exec(texto)) !== null) {
    conteiner.append(document.createTextNode(texto.slice(inicio, ocorrencia.index)));
    const numero = Number(ocorrencia[1]);
    const fonteExiste = fontes.some((fonte) => Number(fonte.numero) === numero);
    if (fonteExiste) {
      const link = criarElemento("a", "", ocorrencia[0]);
      link.href = `#fonte-${numero}`;
      link.setAttribute("aria-label", `Ir para a fonte ${numero}`);
      conteiner.append(link);
    } else {
      conteiner.append(document.createTextNode(ocorrencia[0]));
    }
    inicio = expressao.lastIndex;
  }
  conteiner.append(document.createTextNode(texto.slice(inicio)));
}

function renderizarMetricas(dados) {
  metricasResposta.replaceChildren();
  const custo = dados.custo || {};
  const itens = [
    ["Modelo", dados.modelo || "—"],
    ["Tokens", formatarNumero(dados.tokens_total)],
    ["Duração", dados.duracao_ms == null ? "—" : `${formatarNumero(dados.duracao_ms)} ms`],
    ["Custo estimado", formatarReal(custo.custo_padrao_estimado_brl)],
  ];
  itens.forEach(([rotulo, valor]) => {
    const grupo = criarElemento("div");
    grupo.append(criarElemento("dt", "", rotulo), criarElemento("dd", "", valor));
    metricasResposta.append(grupo);
  });
}

function renderizarFontes(fontes) {
  gradeFontes.replaceChildren();
  quantidadeFontes.textContent = `${fontes.length} fonte${fontes.length === 1 ? "" : "s"}`;
  fontes.forEach((fonte) => {
    const cartao = criarElemento("article", "cartao-fonte");
    cartao.id = `fonte-${fonte.numero}`;
    cartao.append(
      criarElemento("span", "rotulo-fonte", `Fonte ${fonte.numero}`),
      criarElemento("h4", "", fonte.citacao || fonte.id),
      criarElemento("p", "", limitarTexto(fonte.texto || "", 360)),
    );
    if (fonte.arquivo) {
      cartao.append(criarElemento("small", "arquivo-fonte", fonte.arquivo));
    }
    const destinoLocal = fonte.pagina
      ? `${fonte.url}#page=${Number(fonte.pagina)}`
      : fonte.url;
    const link = criarLinkSeguro(destinoLocal, "Abrir PDF na fonte ↗");
    if (link) cartao.append(link);
    const oficial = criarLinkSeguro(fonte.url_oficial, "Ver original no TJSP ↗");
    if (oficial) cartao.append(oficial);
    gradeFontes.append(cartao);
  });
  fontesResposta.hidden = fontes.length === 0;
}

async function carregarAuditorias() {
  botaoAuditorias.disabled = true;
  try {
    const resposta = await fetch("/auditorias?limite=5");
    const dados = await resposta.json();
    if (!resposta.ok) throw new Error(mensagemDaAPI(dados));
    renderizarAuditorias(Array.isArray(dados) ? dados : []);
  } catch (_erro) {
    listaAuditorias.replaceChildren(
      criarElemento("p", "texto-suave", "Histórico indisponível no momento."),
    );
  } finally {
    botaoAuditorias.disabled = false;
  }
}

function renderizarAuditorias(auditorias) {
  listaAuditorias.replaceChildren();
  if (auditorias.length === 0) {
    listaAuditorias.append(
      criarElemento("p", "texto-suave", "Nenhuma chamada de IA registrada."),
    );
    return;
  }
  auditorias.forEach((auditoria) => {
    const item = criarElemento("article", "item-auditoria");
    const status = criarElemento("span", "selo-status", auditoria.status || "—");
    if (auditoria.status === "erro") status.classList.add("erro");
    const centro = criarElemento("div");
    centro.append(
      criarElemento("p", "", limitarTexto(auditoria.pergunta || "Sem pergunta", 120)),
      criarElemento(
        "span",
        "",
        `#${auditoria.id} · ${auditoria.modelo || "modelo não informado"}`,
      ),
    );
    const detalhes = criarElemento("div", "detalhes-auditoria");
    detalhes.append(
      criarElemento("strong", "", `${formatarNumero(auditoria.tokens_total)} tokens`),
      criarElemento("span", "", formatarData(auditoria.criado_em)),
    );
    item.append(status, centro, detalhes);
    listaAuditorias.append(item);
  });
}

function exibirErro(mensagem) {
  tituloResultados.textContent = "A consulta não foi concluída";
  mensagemErro.textContent = mensagem;
  estadoErro.hidden = false;
}

function mensagemDaAPI(dados) {
  const detalhe = dados && dados.detail;
  if (typeof detalhe === "string") return detalhe;
  if (detalhe && typeof detalhe.erro === "string") {
    const valores = [];
    if (detalhe.estimativa_maxima_brl != null) {
      valores.push(`estimativa ${formatarReal(detalhe.estimativa_maxima_brl)}`);
    }
    if (detalhe.limite_brl != null) valores.push(`limite ${formatarReal(detalhe.limite_brl)}`);
    return `${detalhe.erro}${valores.length ? ` (${valores.join("; ")})` : ""}`;
  }
  if (Array.isArray(detalhe) && detalhe[0] && detalhe[0].msg) return detalhe[0].msg;
  return "A API devolveu uma resposta inesperada.";
}

function criarElemento(tag, classe = "", texto = "") {
  const elemento = document.createElement(tag);
  if (classe) elemento.className = classe;
  if (texto !== "") elemento.textContent = String(texto);
  return elemento;
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
  } catch (_erro) {
    return null;
  }
}

function limitarTexto(texto, limite) {
  const limpo = String(texto).replace(/\s+/g, " ").trim();
  return limpo.length > limite ? `${limpo.slice(0, limite).trim()}…` : limpo;
}

function formatarNumero(valor) {
  return valor == null ? "—" : new Intl.NumberFormat("pt-BR").format(valor);
}

function formatarReal(valor) {
  return valor == null
    ? "—"
    : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(valor);
}

function formatarData(valor) {
  if (!valor) return "—";
  const data = new Date(String(valor).replace(" ", "T") + "Z");
  return Number.isNaN(data.getTime())
    ? String(valor)
    : new Intl.DateTimeFormat("pt-BR", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(data);
}

function converterDataBR(valor) {
  if (!valor) return "";
  const [ano, mes, dia] = valor.split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : valor;
}
