from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, Tag

from ..models import Consulta, Decisao, ResultadoPesquisa


@dataclass(frozen=True, slots=True)
class TJPRAdapter:
    """Adaptador do portal público de jurisprudência do TJPR."""

    base_url: str

    RESULTADOS_POR_PAGINA: ClassVar[int] = 50
    LIMITE_ARQUIVO_COMPACTADO: ClassVar[int] = 100 * 1024 * 1024
    TIPOS: ClassVar[dict[str, str]] = {
        "acordao": "1",
        "monocratica": "2",
        "homologacao": "-1",
    }

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/") + "/")

    def url(self, caminho: str) -> str:
        return urljoin(self.base_url, caminho)

    def pesquisar(
        self,
        requisitar: Callable[..., requests.Response],
        consulta: Consulta,
        *,
        max_paginas: int,
    ) -> ResultadoPesquisa:
        pagina_inicial = requisitar("GET", self.base_url)
        soup = BeautifulSoup(pagina_inicial.content, "html.parser")
        formulario = soup.find("form", id="pesquisaForm")
        if not isinstance(formulario, Tag) or not formulario.get("action"):
            raise RuntimeError("TJPR não apresentou formulário público de pesquisa.")

        destino = urljoin(pagina_inicial.url, str(formulario["action"]))
        dados = self._corpo_consulta(consulta)
        decisoes: list[Decisao] = []
        total = 0
        paginas_coletadas = 0

        for pagina in range(1, max_paginas + 1):
            if pagina > 1:
                dados.update(
                    {
                        "pageNumber": str(pagina),
                        "pageSize": str(self.RESULTADOS_POR_PAGINA),
                        "sortColumn": "processo_sDataJulgamento",
                        "sortOrder": "DESC",
                    }
                )
            resposta = requisitar(
                "POST",
                destino,
                data=dados,
                headers={"Referer": pagina_inicial.url},
            )
            total_pagina, itens = self._parsear_resultados(resposta.content)
            if pagina == 1:
                total = total_pagina
            if not itens:
                break
            decisoes.extend(itens)
            paginas_coletadas += 1
            if len(decisoes) >= total:
                break
            destino = resposta.url

        return ResultadoPesquisa(
            total_disponivel=total,
            paginas_coletadas=paginas_coletadas,
            decisoes=tuple(decisoes),
        )

    def obter_pdf(
        self,
        requisitar: Callable[..., requests.Response],
        url_detalhe: str,
    ) -> requests.Response:
        destino = urlsplit(url_detalhe)
        base = urlsplit(self.base_url)
        if destino.scheme != "https" or destino.hostname != base.hostname:
            raise ValueError("URL de inteiro teor fora do portal oficial do TJPR.")
        if not destino.path.startswith("/jurisprudencia/j/"):
            raise ValueError("URL de inteiro teor do TJPR possui caminho inválido.")

        detalhe = requisitar("GET", url_detalhe)
        soup = BeautifulSoup(detalhe.content, "html.parser")
        link = soup.select_one('a[href*="visualizacao.do"]')
        correspondencia = re.search(
            r"replace\('([^']+)'\)", str(link.get("href", "")) if link else ""
        )
        if correspondencia is None:
            raise RuntimeError("TJPR não apresentou link do inteiro teor.")

        url_arquivo = urljoin(detalhe.url, correspondencia.group(1))
        arquivo = requisitar("GET", url_arquivo)
        with zipfile.ZipFile(io.BytesIO(arquivo.content)) as pacote:
            candidatos = [
                item
                for item in pacote.infolist()
                if not item.is_dir() and item.filename.casefold().endswith(".pdf")
            ]
            if len(candidatos) != 1:
                raise RuntimeError("Pacote do TJPR não contém PDF único.")
            item = candidatos[0]
            if item.file_size > self.LIMITE_ARQUIVO_COMPACTADO:
                raise RuntimeError("PDF do TJPR excede limite de segurança.")
            conteudo = pacote.read(item)

        if not conteudo.startswith(b"%PDF-"):
            raise RuntimeError("Inteiro teor do TJPR não possui assinatura PDF.")
        resposta = requests.Response()
        resposta.status_code = 200
        resposta.url = url_arquivo
        resposta.headers["Content-Type"] = "application/pdf"
        resposta.headers["Content-Length"] = str(len(conteudo))
        resposta._content = conteudo
        resposta._content_consumed = True
        return resposta

    def _corpo_consulta(self, consulta: Consulta) -> dict[str, str]:
        criterio = consulta.ementa.strip() or consulta.pesquisa.strip()
        return {
            "criterioPesquisa": criterio,
            "idLocalPesquisa": "1" if consulta.ementa else "99",
            "ambito": "-1",
            "idsTipoDecisaoSelecionados": self.TIPOS[consulta.tipo_decisao],
            "segredoJustica": "",
            "dataJulgamentoInicio": consulta.data_julgamento_inicio,
            "dataJulgamentoFim": consulta.data_julgamento_fim,
            "iniciar": "Pesquisar",
        }

    def _parsear_resultados(
        self, html: str | bytes
    ) -> tuple[int, list[Decisao]]:
        soup = BeautifulSoup(html, "html.parser")
        texto = self._texto(soup)
        total_match = re.search(r"([\d.]+)\s+registro\(s\) encontrado", texto)
        if total_match is None:
            if "nenhum registro" in texto.casefold():
                return 0, []
            raise RuntimeError("TJPR não informou quantidade de resultados.")
        total = int(total_match.group(1).replace(".", ""))

        decisoes: list[Decisao] = []
        for linha in soup.select(
            "table.resultTable.jurisprudencia tr.even, "
            "table.resultTable.jurisprudencia tr.odd"
        ):
            decisao = self._parsear_decisao(linha)
            if decisao is not None:
                decisoes.append(decisao)
        return total, decisoes

    def _parsear_decisao(self, linha: Tag) -> Decisao | None:
        identificador = linha.select_one('input[name="idsSelecionados"]')
        link = linha.select_one("a.acordao[href]")
        ementa_tag = linha.select_one('[id^="ementa"]')
        propriedades = linha.select_one(".juris-tabela-propriedades")
        if identificador is None or link is None or propriedades is None:
            return None

        cd_acordao = str(identificador.get("value", "")).strip()
        processo = self._texto(link)
        metadados = self._texto(propriedades, separador=" ")
        tipo_match = re.search(r"\(([^)]+)\)", metadados)
        relator_match = re.search(r"Relator:\s*(.*?)\s*Processo:", metadados)
        orgao_match = re.search(
            r"Órgão Julgador:\s*(.*?)\s*Data Julgamento:", metadados
        )
        data_match = re.search(r"Data Julgamento:\s*(\d{2}/\d{2}/\d{4})", metadados)
        return Decisao(
            processo=processo,
            cd_acordao=cd_acordao,
            cd_foro="0",
            classe=tipo_match.group(1).strip() if tipo_match else "Acórdão",
            assunto="",
            relator=relator_match.group(1).strip() if relator_match else "",
            comarca="",
            orgao_julgador=orgao_match.group(1).strip() if orgao_match else "",
            data_julgamento=data_match.group(1) if data_match else "",
            data_publicacao="",
            ementa=self._texto(ementa_tag) if ementa_tag else "",
            inteiro_teor_url=urljoin(self.base_url, str(link["href"])),
        )

    @staticmethod
    def _texto(tag: Tag | BeautifulSoup, *, separador: str = " ") -> str:
        valor = " ".join(tag.get_text(separador, strip=True).split())
        if "Ã" not in valor and "Â" not in valor:
            return valor
        partes = re.split(r"([^\x00-\xff]+)", valor)
        for indice, parte in enumerate(partes):
            if "Ã" not in parte and "Â" not in parte:
                continue
            try:
                partes[indice] = parte.encode("latin-1").decode("utf-8")
            except UnicodeError:
                pass
        return "".join(partes)
