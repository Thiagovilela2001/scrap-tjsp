from __future__ import annotations

import os
from collections.abc import Callable

from .api_schemas import RequisicaoMinuta
from .parser import limpar_quebras_juridicas
from .rag import PacoteContextoIA


def gerar_minuta_juridica(
    requisicao: RequisicaoMinuta,
    criar_provedor: Callable,
) -> dict:
    tema = requisicao.tema or requisicao.pergunta
    acordaos = requisicao.acordaos_selecionados
    instrucao = requisicao.instrucao.strip()

    resumo_acordaos = []
    for a in acordaos:
        proc = a.get("processo") or f"Acórdão {a.get('cd_acordao', '')}"
        rel = a.get("relator") or "Relator não informado"
        orgao = a.get("orgao_julgador") or "Tribunal competente"
        dt = a.get("data_julgamento") or ""
        ementa = limpar_quebras_juridicas(a.get("ementa") or "")
        arg = a.get("argumento") or a.get("aderencia_fatica") or ""
        resumo_acordaos.append(
            f"- Processo: {proc} | Órgão: {orgao} | Relator: {rel} | Julgamento: {dt}\n"
            f"  Aplicação: {arg}\n"
            f"  Ementa: {ementa[:450]}"
        )
    texto_precedentes = "\n\n".join(resumo_acordaos)

    chave = os.getenv("MARITACA_API_KEY")
    if chave:
        try:
            provedor = criar_provedor(None, 2000)
            prompt_sistema = (
                "Você é um especialista em redação de peças processuais e teses jurídicas assertivas para tribunais brasileiros.\n"
                "Redija uma fundamentação jurídica formal, assertiva e bem estruturada para inclusão direta em petição.\n"
                "IMPORTANTE: Escreva em parágrafos contínuos e fluidos, sem quebras de linha no meio de frases.\n\n"
                "Estrutura recomendada:\n"
                "# EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO...\n\n"
                "## I. DOS FATOS RELEVANTES E DO CONTEXTO\n"
                "## II. DA JURISPRUDÊNCIA FIRME (PRECEDENTES APLICÁVEIS)\n"
                "## III. DA FUNDAMENTAÇÃO E APLICAÇÃO AO CASO CONCRETO\n"
                "## IV. DOS PEDIDOS E REQUERIMENTOS\n\n"
                f"Tema: {tema}\n"
                f"Fatos / Consulta: {requisicao.pergunta}\n"
                f"Detalhes do caso: {requisicao.contexto_caso}\n\n"
                f"Precedentes Selecionados:\n{texto_precedentes}\n\n"
            )
            if instrucao:
                prompt_sistema += f"\nInstruções de Ajuste do Advogado: {instrucao}\n"

            pacote = PacoteContextoIA(
                instrucoes_sistema=prompt_sistema,
                mensagem_usuario=f"Redija a minuta de fundamentação jurídica com base nos precedentes: {tema}",
            )
            resposta_ia = provedor.responder(pacote)
            return {
                "minuta": limpar_quebras_juridicas(resposta_ia.texto),
                "tema": tema,
                "acordaos_utilizados": len(acordaos),
            }
        except Exception:
            pass

    # Fallback local estruturado
    linhas = [
        f"# MINUTA DE FUNDAMENTAÇÃO JURÍDICA — {tema.upper()}",
        "",
        "## I. DO CONTEXTO FÁTICO",
        requisicao.contexto_caso or requisicao.pergunta,
        "",
        "## II. DA JURISPRUDÊNCIA PACÍFICA DOS TRIBUNAIS",
        "A pretensão formulada encontra integral acolhimento na iterativa jurisprudência dos tribunais pátrios:",
        "",
    ]
    for idx, a in enumerate(acordaos, 1):
        proc = a.get("processo") or f"Acórdão nº {a.get('cd_acordao', '')}"
        rel = a.get("relator") or "Relator designado"
        orgao = a.get("orgao_julgador") or "Tribunal competente"
        dt = f", j. em {a.get('data_julgamento')}" if a.get("data_julgamento") else ""
        ementa = limpar_quebras_juridicas(a.get("ementa", "").strip())
        arg = a.get("argumento") or a.get("aderencia_fatica") or ""

        linhas.append(f"### {idx}. {proc} — {orgao}")
        if rel:
            linhas.append(f"**Relator(a):** {rel}{dt}")
        if arg:
            linhas.append(f"**Tese Aplicável:** {arg}")
        if ementa:
            linhas.append("")
            linhas.append(f"> *\"{ementa}\"*")
            linhas.append("")

    linhas.extend(
        [
            "## III. DA SUBSUNÇÃO FÁTICA E DO DIREITO",
            f"Como se extrai dos precedentes colacionados, a jurisprudência do TJSP é uníssona em acolher o pleito ora formulado quanto ao tema '{tema}', sendo manifesto o direito da parte requerente.",
            "",
            "## IV. DOS PEDIDOS",
            "Ante o exposto, requer-se o acolhimento integral da tese com base na iterativa jurisprudência desta Corte.",
        ]
    )

    if instrucao:
        linhas.extend(["", f"*(Ajuste solicitado pelo advogado: {instrucao})*"])

    return {
        "minuta": "\n".join(linhas),
        "tema": tema,
        "acordaos_utilizados": len(acordaos),
    }

