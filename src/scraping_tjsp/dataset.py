from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .downloader import DownloadPDFError, PDFDownloader
from .models import Consulta, Decisao, ResultadoPesquisa
from .processor import ProcessadorPDF, ProcessamentoPDFError
from .storage import RepositorioSQLite
from .vector_store import RepositorioChunksChroma


@dataclass(slots=True, frozen=True)
class FonteDataset:
    caso_id: str
    cd_acordao: str
    cd_foro: str
    processo: str
    fonte_url: str
    ementa: str = ""

    @classmethod
    def de_dict(cls, dados: dict) -> FonteDataset:
        if not isinstance(dados, dict):
            raise ValueError("Cada linha do dataset deve ser um objeto JSON.")
        acordaos = dados.get("acordaos_relevantes", ())
        if not isinstance(acordaos, list) or len(acordaos) != 1:
            raise ValueError("Cada caso deve indicar exatamente um acórdão relevante.")
        cd_acordao = str(acordaos[0])
        caso_id = str(dados.get("caso_id", "")).strip()
        processo = str(dados.get("processo", "")).strip()
        fonte_url = str(dados.get("fonte_url", "")).strip()
        cd_foro = _validar_url(fonte_url, cd_acordao)
        if not caso_id or not processo:
            raise ValueError("Caso exige caso_id e processo.")
        return cls(
            caso_id=caso_id,
            cd_acordao=cd_acordao,
            cd_foro=cd_foro,
            processo=processo,
            fonte_url=fonte_url,
            ementa=str(dados.get("ementa", "")).strip(),
        )

    def como_decisao(self) -> Decisao:
        return Decisao(
            processo=self.processo,
            cd_acordao=self.cd_acordao,
            cd_foro=self.cd_foro,
            classe="",
            assunto="",
            relator="",
            comarca="",
            orgao_julgador="",
            data_julgamento="",
            data_publicacao="",
            ementa=self.ementa,
            inteiro_teor_url=self.fonte_url,
        )


@dataclass(slots=True, frozen=True)
class ResultadoPreparacaoDataset:
    total_fontes: int
    baixados: int
    reutilizados: int
    erros_download: int
    processados: int
    erros_processamento: int
    chunks_indexados: int

    @property
    def aprovado(self) -> bool:
        return self.erros_download == 0 and self.erros_processamento == 0


class PreparadorDataset:
    def __init__(
        self,
        repositorio: RepositorioSQLite,
        downloader: PDFDownloader,
        processador: ProcessadorPDF,
        repositorio_chunks: RepositorioChunksChroma,
    ) -> None:
        self.repositorio = repositorio
        self.downloader = downloader
        self.processador = processador
        self.repositorio_chunks = repositorio_chunks

    def preparar(
        self,
        fontes: tuple[FonteDataset, ...],
        *,
        nome_dataset: str,
        limite: int | None = None,
    ) -> ResultadoPreparacaoDataset:
        selecionadas = fontes[:limite] if limite is not None else fontes
        decisoes = tuple(fonte.como_decisao() for fonte in selecionadas)
        self.repositorio.inicializar()
        self.repositorio.salvar_pesquisa(
            Consulta(pesquisa=f"dataset de avaliação: {nome_dataset}"[:120]),
            ResultadoPesquisa(len(decisoes), 0, decisoes),
        )

        baixados = reutilizados = erros_download = 0
        processados = erros_processamento = chunks_indexados = 0
        for decisao in decisoes:
            try:
                documento = self.downloader.baixar(decisao)
                baixados += 1
                reutilizados += int(documento.reutilizado)
                self.repositorio.registrar_documento(documento)
            except DownloadPDFError as exc:
                erros_download += 1
                self.repositorio.registrar_erro_download(
                    decisao.cd_acordao,
                    decisao.inteiro_teor_url,
                    str(exc),
                )
                continue

            self.repositorio.iniciar_processamento(decisao.cd_acordao)
            try:
                processamento = self.processador.processar(documento)
                self.repositorio.registrar_processamento(processamento)
                chunks_indexados += self.repositorio_chunks.indexar(
                    processamento, decisao
                )
                processados += 1
            except ProcessamentoPDFError as exc:
                erros_processamento += 1
                self.repositorio.registrar_erro_processamento(
                    decisao.cd_acordao, str(exc)
                )

        return ResultadoPreparacaoDataset(
            total_fontes=len(selecionadas),
            baixados=baixados,
            reutilizados=reutilizados,
            erros_download=erros_download,
            processados=processados,
            erros_processamento=erros_processamento,
            chunks_indexados=chunks_indexados,
        )


def carregar_fontes_dataset(caminho: Path | str) -> tuple[FonteDataset, ...]:
    caminho = Path(caminho)
    fontes = []
    for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
        if not linha.strip():
            continue
        try:
            fontes.append(FonteDataset.de_dict(json.loads(linha)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Fonte inválida na linha {numero}: {exc}") from exc
    if not fontes:
        raise ValueError("Dataset não contém fontes.")
    casos = [fonte.caso_id for fonte in fontes]
    acordaos = [fonte.cd_acordao for fonte in fontes]
    if len(casos) != len(set(casos)):
        raise ValueError("Dataset contém caso_id duplicado.")
    if len(acordaos) != len(set(acordaos)):
        raise ValueError("Dataset contém acórdão duplicado.")
    return tuple(fontes)


def _validar_url(url: str, cd_acordao: str) -> str:
    destino = urlsplit(url)
    parametros = parse_qs(destino.query)
    if (
        destino.scheme != "https"
        or destino.hostname != "esaj.tjsp.jus.br"
        or destino.path != "/cjsg/getArquivo.do"
        or not cd_acordao.isdigit()
        or parametros.get("cdAcordao") != [cd_acordao]
        or parametros.get("casChecked") != ["true"]
    ):
        raise ValueError("URL oficial não corresponde ao acórdão informado.")
    cd_foro = parametros.get("cdForo", [""])[0]
    if not cd_foro.isdigit():
        raise ValueError("URL oficial exige cdForo numérico.")
    return cd_foro
