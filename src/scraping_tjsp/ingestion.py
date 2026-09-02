from __future__ import annotations

from threading import Lock

from .client import TJSPClient
from .downloader import DownloadPDFError, PDFDownloader
from .models import Consulta
from .processor import ProcessadorPDF, ProcessamentoPDFError
from .storage import RepositorioSQLite
from .vector_store import RepositorioChroma, RepositorioChunksChroma


class ServicoColetaTJSP:
    def __init__(
        self,
        repositorio: RepositorioSQLite,
        cliente: TJSPClient,
        downloader: PDFDownloader,
        processador: ProcessadorPDF,
        repositorio_ementas: RepositorioChroma,
        repositorio_chunks: RepositorioChunksChroma,
        *,
        max_paginas: int = 1,
        max_pdfs: int = 5,
    ) -> None:
        if max_paginas < 1:
            raise ValueError("Máximo de páginas TJSP deve ser pelo menos 1.")
        if max_pdfs < 1:
            raise ValueError("Máximo de PDFs deve ser pelo menos 1.")
        self.repositorio = repositorio
        self.cliente = cliente
        self.downloader = downloader
        self.processador = processador
        self.repositorio_ementas = repositorio_ementas
        self.repositorio_chunks = repositorio_chunks
        self.max_paginas = max_paginas
        self.max_pdfs = max_pdfs
        self._bloqueio = Lock()

    def pesquisar(
        self,
        consulta: Consulta,
        *,
        paginas: int = 1,
        tribunal: str | None = None,
    ) -> dict:
        consulta.validar()
        if not 1 <= paginas <= self.max_paginas:
            raise ValueError(f"Páginas deve ficar entre 1 e {self.max_paginas}.")
        with self._bloqueio:
            trib_alvo = tribunal.lower().strip() if tribunal else getattr(self.cliente, "tribunal", "tjsp")
            if trib_alvo != getattr(self.cliente, "tribunal", "tjsp"):
                cliente_trib = TJSPClient(
                    tribunal=trib_alvo,
                    intervalo=self.cliente._limitador.intervalo,
                )
                resultado = cliente_trib.pesquisar(consulta, max_paginas=paginas)
            else:
                resultado = self.cliente.pesquisar(consulta, max_paginas=paginas)
        consulta_id = self.repositorio.salvar_pesquisa(consulta, resultado)
        ementas_indexadas = self.repositorio_ementas.indexar_decisoes(
            resultado.decisoes
        )
        return {
            "consulta_id": consulta_id,
            "total_disponivel": resultado.total_disponivel,
            "paginas_coletadas": resultado.paginas_coletadas,
            "ementas_indexadas": ementas_indexadas,
            "decisoes": [decisao.como_dict() for decisao in resultado.decisoes],
        }

    def importar(self, consulta_id: int, cd_acordaos: list[str]) -> dict:
        selecionados = list(dict.fromkeys(item.strip() for item in cd_acordaos))
        if not selecionados or any(not item.isdigit() for item in selecionados):
            raise ValueError("Informe códigos de acórdão numéricos.")
        if len(selecionados) > self.max_pdfs:
            raise ValueError(
                f"Importação aceita no máximo {self.max_pdfs} PDFs por vez."
            )

        disponiveis = {
            decisao.cd_acordao: decisao
            for decisao in self.repositorio.listar_decisoes_consulta(consulta_id)
        }
        ausentes = [item for item in selecionados if item not in disponiveis]
        if ausentes:
            raise ValueError(
                "Acórdãos não pertencem à consulta informada: " + ", ".join(ausentes)
            )

        baixados = reutilizados = processados = chunks_indexados = 0
        erros: list[dict[str, str]] = []
        with self._bloqueio:
            for cd_acordao in selecionados:
                decisao = disponiveis[cd_acordao]
                try:
                    documento = self.downloader.baixar(decisao)
                    baixados += 1
                    reutilizados += int(documento.reutilizado)
                    self.repositorio.registrar_documento(documento)
                except DownloadPDFError as exc:
                    self.repositorio.registrar_erro_download(
                        decisao.cd_acordao,
                        decisao.inteiro_teor_url,
                        str(exc),
                    )
                    erros.append(
                        {
                            "cd_acordao": cd_acordao,
                            "etapa": "download",
                            "erro": str(exc),
                        }
                    )
                    continue

                self.repositorio.iniciar_processamento(decisao.cd_acordao)
                try:
                    processamento = self.processador.processar(documento)
                    self.repositorio.registrar_processamento(processamento)
                    chunks_indexados += self.repositorio_chunks.indexar(
                        processamento,
                        decisao,
                    )
                    processados += 1
                except ProcessamentoPDFError as exc:
                    self.repositorio.registrar_erro_processamento(
                        decisao.cd_acordao,
                        str(exc),
                    )
                    erros.append(
                        {
                            "cd_acordao": cd_acordao,
                            "etapa": "processamento",
                            "erro": str(exc),
                        }
                    )

        return {
            "consulta_id": consulta_id,
            "solicitados": len(selecionados),
            "baixados": baixados,
            "reutilizados": reutilizados,
            "processados": processados,
            "chunks_indexados": chunks_indexados,
            "erros": erros,
        }
