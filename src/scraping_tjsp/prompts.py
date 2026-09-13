from __future__ import annotations

import json
import re


def instrucoes_planejamento(tribunal: str = "tjsp") -> str:
    trib_limpo = tribunal.lower().strip()
    alvo = (
        "nos tribunais brasileiros"
        if trib_limpo in ("todos", "all", "brasil", "todas_cortes")
        else f"no tribunal {tribunal.upper()}"
    )
    return f"""Você planeja pesquisa jurisprudencial {alvo}.
Converta o relato em consultas curtas para o campo de pesquisa jurisprudencial.
Não invente IDs, processos, julgados ou fatos.
Defina precisa_esclarecimento como true SOMENTE se a pergunta for excessivamente curta ou genérica (ex: apenas uma palavra como "icms", "banco", "dano moral") sem qualquer contexto fático.
Se a pergunta contiver fatos mínimos, especificações ou detalhes do caso, defina precisa_esclarecimento como false, defina questoes como [] (lista vazia) e SEMPRE gere entre 1 e 3 consultas objetivas.
Se precisa_esclarecimento for true, defina consultas como [] (lista vazia) e gere até 3 questões de esclarecimento com até 4 opções cada.
Responda somente em JSON válido, sem Markdown, neste formato:
{{
  "precisa_esclarecimento": true ou false,
  "questoes": [
    {{
      "pergunta": "Qual a situação fática ou ponto controvertido?",
      "opcoes": ["Opção 1", "Opção 2", "Opção 3", "Opção 4"]
    }}
  ],
  "tema": "síntese curta",
  "consultas": [
    {{"pesquisa": "termos com até 120 caracteres", "justificativa": "motivo"}}
  ]
}}
Gere no máximo três consultas ou três questões de esclarecimento."""


def instrucoes_analise(tribunal: str = "tjsp") -> str:
    trib_limpo = tribunal.lower().strip()
    alvo = (
        "dos tribunais brasileiros"
        if trib_limpo in ("todos", "all", "brasil", "todas_cortes")
        else f"do tribunal {tribunal.upper()}"
    )
    return f"""Você analisa candidatos de jurisprudência {alvo}.
Use somente as ementas fornecidas. Não afirme que uma decisão sustenta uma tese além
do que está expresso na ementa. Ranqueie aderência ao caso e explique como cada
processo pode contribuir como argumento, sempre indicando a necessidade de revisar
o inteiro teor. Responda somente em JSON válido, sem Markdown, neste formato:
{{
  "resultados": [
    {{
      "cd_acordao": "identificador fornecido",
      "relevancia": 0.0,
      "argumento": "possível uso argumentativo",
      "aderencia_fatica": "pontos de aproximação ou diferença",
      "ressalva": "limitação relevante"
    }}
  ]
}}
Retorne no máximo seis resultados, ordenados por relevância decrescente.
Seja conciso: cada campo textual deve ter no máximo 350 caracteres."""


INSTRUCOES_PLANEJAMENTO = instrucoes_planejamento("tjsp")
INSTRUCOES_ANALISE = instrucoes_analise("tjsp")


def reparar_json_string(s: str) -> str:
    s = re.sub(r"//.*?(\r\n|\n|$)", "\n", s)
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNone\b", "null", s)
    s = re.sub(r",\s*([\]}])", r"\1", s)
    return s


def fechar_json_truncado(s: str) -> str:
    in_string = False
    escape = False
    stack: list[str] = []
    for c in s:
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if not in_string:
            if c in "{[":
                stack.append("}" if c == "{" else "]")
            elif c in "}]":
                if stack and stack[-1] == c:
                    stack.pop()
    if in_string:
        s += '"'
    while stack:
        s += stack.pop()
    return s


def extrair_plano_fallback(texto: str) -> dict | None:
    consultas = []
    for m in re.finditer(r'"pesquisa"\s*:\s*"([^"]+)"', texto):
        pesq = m.group(1).strip()
        if pesq:
            consultas.append({"pesquisa": pesq, "justificativa": ""})
    tema_match = re.search(r'"tema"\s*:\s*"([^"]+)"', texto)
    tema = tema_match.group(1).strip() if tema_match else "Pesquisa jurisprudencial"
    escl_match = re.search(
        r'"precisa_esclarecimento"\s*:\s*(true|false)', texto, re.IGNORECASE
    )
    escl = escl_match.group(1).lower() == "true" if escl_match else False
    if consultas or escl:
        return {
            "precisa_esclarecimento": escl,
            "tema": tema,
            "questoes": [],
            "consultas": consultas[:3],
        }
    return None


def carregar_json(
    texto: str,
    *,
    permitir_resultados_parciais: bool = False,
) -> dict:
    limpo = texto.strip()
    limpo = re.sub(r"^```(?:json)?\s*", "", limpo, flags=re.IGNORECASE)
    limpo = re.sub(r"\s*```$", "", limpo)
    inicio = limpo.find("{")
    fim = limpo.rfind("}")

    # 1. Tentativa direta se encontrar delimitadores
    if inicio >= 0 and fim >= inicio:
        candidato = limpo[inicio : fim + 1]
        try:
            dados = json.loads(candidato)
            if isinstance(dados, dict):
                return dados
        except json.JSONDecodeError:
            pass

        # 2. Tentativa com limpeza de comentários/vírgulas/booleans
        reparado = reparar_json_string(candidato)
        try:
            dados = json.loads(reparado)
            if isinstance(dados, dict):
                return dados
        except json.JSONDecodeError:
            pass

    # 3. Resultados parciais se análise
    if permitir_resultados_parciais:
        parcial = carregar_resultados_parciais(limpo)
        if parcial is not None:
            return parcial

    # 4. Se JSON estiver truncado
    if inicio >= 0:
        candidato = fechar_json_truncado(reparar_json_string(limpo[inicio:]))
        try:
            dados = json.loads(candidato)
            if isinstance(dados, dict):
                return dados
        except json.JSONDecodeError:
            pass

    # 5. Fallback para plano de pesquisa
    plano_fallback = extrair_plano_fallback(limpo)
    if plano_fallback is not None:
        return plano_fallback

    from .assisted_research import ErroPesquisaAssistida

    raise ErroPesquisaAssistida("Maritaca não devolveu JSON válido estruturado.")


def carregar_resultados_parciais(texto: str) -> dict | None:
    chave = re.search(r'"resultados"\s*:\s*\[', texto)
    if chave is None:
        return None
    posicao = chave.end()
    decoder = json.JSONDecoder()
    resultados = []
    while posicao < len(texto):
        while posicao < len(texto) and texto[posicao] in " \t\r\n,":
            posicao += 1
        if posicao >= len(texto) or texto[posicao] == "]":
            break
        if texto[posicao] != "{":
            break
        try:
            item, fim = decoder.raw_decode(texto, posicao)
        except json.JSONDecodeError:
            break
        if isinstance(item, dict):
            resultados.append(item)
        posicao = fim
    if not resultados:
        return None
    return {"resultados": resultados, "_resposta_parcial": True}

