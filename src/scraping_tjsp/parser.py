from __future__ import annotations

import math
import re
import unicodedata
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from .models import Decisao

BASE_URL = "https://esaj.tjsp.jus.br/cjsg/getArquivo.do"
RESULTADOS_POR_PAGINA = 20


def parsear_pagina(
    html: str | bytes,
    *,
    inteiro_teor_base_url: str = BASE_URL,
) -> tuple[int, list[Decisao]]:
    soup = BeautifulSoup(html, "html.parser")
    _validar_pagina(soup)
    linhas = soup.select("tr.fundocinza1, tr.fundocinza2")
    total = _extrair_total(soup, len(linhas))
    decisoes = [
        _parsear_decisao(linha, inteiro_teor_base_url=inteiro_teor_base_url)
        for linha in linhas
    ]
    return total, decisoes


def numero_paginas(total: int) -> int:
    return math.ceil(total / RESULTADOS_POR_PAGINA) if total else 0


def _validar_pagina(soup: BeautifulSoup) -> None:
    mensagens = [
        _texto(tag)
        for tag in soup.select(".mensagemErro, .error, .spwMensagemErro")
        if _texto(tag)
    ]
    if mensagens:
        mensagem = " ".join(mensagens)
        if "captcha" in mensagem.casefold():
            raise RuntimeError(
                "TJSP exigiu CAPTCHA. Coleta interrompida; validação não será contornada."
            )
        raise RuntimeError(f"TJSP devolveu erro: {mensagem}")

    if soup.find("form", attrs={"name": "consultaCompletaForm"}):
        raise RuntimeError(
            "TJSP manteve a sessão na página de consulta; pesquisa não foi aceita."
        )


def _extrair_total(soup: BeautifulSoup, quantidade_linhas: int) -> int:
    seletores = (
        'input[id^="totalResultadoAbaRetornoFiltro-"]',
        'input[id^="totalResultadoAba-"]',
    )
    for seletor in seletores:
        campo = soup.select_one(seletor)
        if campo and str(campo.get("value", "")).isdigit():
            return int(str(campo["value"]))

    texto = _texto(soup)
    if any(
        frase in texto.casefold() for frase in ("nenhum resultado", "sem resultados")
    ):
        return 0
    if quantidade_linhas:
        return quantidade_linhas
    raise RuntimeError(
        "Não foi possível identificar a quantidade de resultados do TJSP."
    )


def _parsear_decisao(
    linha: Tag,
    *,
    inteiro_teor_base_url: str = BASE_URL,
) -> Decisao:
    link = linha.select_one("a.downloadEmenta[cdacordao]")
    if link is None:
        raise RuntimeError("Resultado sem identificador de acórdão.")

    cd_acordao = str(link.get("cdacordao", "")).strip()
    cd_foro = str(link.get("cdforo", "0")).strip() or "0"
    processo = _texto(link)
    campos = _campos_rotulados(linha)
    classe_assunto = campos.get("classe/assunto", "")
    classe, separador, assunto = classe_assunto.partition(" / ")

    ementa = _ementa_completa(linha)
    ocorrencias = _ocorrencias(linha)
    parametros = urlencode(
        {"casChecked": "true", "cdAcordao": cd_acordao, "cdForo": cd_foro}
    )
    inteiro_teor_url = f"{inteiro_teor_base_url}?{parametros}"

    return Decisao(
        processo=processo,
        cd_acordao=cd_acordao,
        cd_foro=cd_foro,
        classe=classe.strip(),
        assunto=assunto.strip() if separador else "",
        relator=campos.get("relator(a)", campos.get("relator", "")),
        comarca=campos.get("comarca", ""),
        orgao_julgador=campos.get("orgao julgador", ""),
        data_julgamento=campos.get("data do julgamento", ""),
        data_publicacao=campos.get("data de publicacao", ""),
        ementa=ementa,
        inteiro_teor_url=inteiro_teor_url,
        ocorrencias=ocorrencias,
    )


def _campos_rotulados(linha: Tag) -> dict[str, str]:
    campos: dict[str, str] = {}
    for item in linha.select("tr.ementaClass2"):
        rotulo_tag = item.find("strong")
        if rotulo_tag is None:
            continue
        rotulo_original = _texto(rotulo_tag).rstrip(":")
        rotulo = _sem_acentos(rotulo_original).casefold()
        if rotulo == "ementa":
            continue
        valor_com_rotulo = _texto(item)
        valor = re.sub(
            rf"^{re.escape(rotulo_original)}\s*:\s*",
            "",
            valor_com_rotulo,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
        campos[rotulo] = valor
    return campos


def limpar_quebras_juridicas(texto: str) -> str:
    """Corrige quebras de linha fragmentadas preservando parágrafos e tópicos."""
    if not texto:
        return ""
    t = re.sub(r"\s*\n\s*([.,;:!?])", r"\1", texto)
    linhas = [item.strip() for item in t.split("\n")]
    resultado: list[str] = []

    for linha in linhas:
        if not linha:
            if resultado and resultado[-1] != "":
                resultado.append("")
            continue

        if not resultado or resultado[-1] == "":
            resultado.append(linha)
            continue

        anterior = resultado[-1]
        is_novo_topico = bool(
            re.match(
                r"^(?:[0-9]+[\.\)\-]|[IVXLCDM]+[\.\)\-]|\([a-z0-9]\))\s*",
                linha,
                re.IGNORECASE,
            )
        )
        is_fim_paragrafo = anterior.endswith((".", ":", ";")) and not re.search(
            r"\b(?:art|fls|inc|n|v|rel|dr|dra|exmo|des)\.$",
            anterior,
            re.IGNORECASE,
        )

        if is_novo_topico or (is_fim_paragrafo and len(anterior) > 40):
            resultado.append(linha)
        else:
            resultado[-1] = f"{anterior} {linha}"

    return "\n\n".join(
        re.sub(r"[ \t]+", " ", bloco).strip()
        for bloco in "\n".join(resultado).split("\n\n")
        if bloco.strip()
    )


def _ementa_completa(linha: Tag) -> str:
    candidatos = linha.select('tr.ementaClass2 div[align="justify"]')
    textos: list[str] = []
    for candidato in candidatos:
        texto = _texto(candidato, separador="\n")
        texto = re.sub(r"^Ementa\s*:\s*", "", texto, flags=re.IGNORECASE).strip()
        if texto:
            textos.append(limpar_quebras_juridicas(texto))
    if textos:
        return max(textos, key=len)

    identificador = str(
        linha.select_one("a.downloadEmenta[cdacordao]").get("cdacordao", "")
    )
    sem_formatacao = linha.select_one(f"#textAreaDados_{identificador}")
    return (
        limpar_quebras_juridicas(_texto(sem_formatacao, separador="\n"))
        if sem_formatacao
        else ""
    )


def _ocorrencias(linha: Tag) -> int | None:
    tag = linha.select_one("span.segredoJustica")
    if tag is None:
        return None
    correspondencia = re.search(r"(\d+)\s+ocorr", _texto(tag), re.IGNORECASE)
    return int(correspondencia.group(1)) if correspondencia else None


def _texto(tag: Tag | BeautifulSoup | None, separador: str = " ") -> str:
    if tag is None:
        return ""
    texto = tag.get_text(separador, strip=True)
    texto = texto.replace("\xa0", " ")
    if separador == "\n":
        linhas = [re.sub(r"[ \t]+", " ", item).strip() for item in texto.splitlines()]
        return "\n".join(item for item in linhas if item)
    return re.sub(r"\s+", " ", texto).strip()


def _sem_acentos(valor: str) -> str:
    normalizado = unicodedata.normalize("NFKD", valor)
    return "".join(
        caractere for caractere in normalizado if not unicodedata.combining(caractere)
    )
