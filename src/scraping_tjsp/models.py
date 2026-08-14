from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal


TipoDecisao = Literal["acordao", "homologacao", "monocratica"]
Origem = Literal["segundo_grau", "colegio_recursal"]


@dataclass(slots=True, frozen=True)
class Consulta:
    pesquisa: str = ""
    ementa: str = ""
    classe: str = ""
    assunto: str = ""
    comarca: str = ""
    orgao_julgador: str = ""
    data_julgamento_inicio: str = ""
    data_julgamento_fim: str = ""
    origem: Origem = "segundo_grau"
    tipo_decisao: TipoDecisao = "acordao"
    pesquisar_sinonimos: bool = True

    def validar(self) -> None:
        if self.tipo_decisao not in ("acordao", "homologacao", "monocratica"):
            raise ValueError(f"Tipo de decisão inválido: {self.tipo_decisao!r}.")
        if self.origem not in ("segundo_grau", "colegio_recursal"):
            raise ValueError(f"Origem inválida: {self.origem!r}.")
        if len(self.pesquisa) > 120:
            raise ValueError("Pesquisa livre aceita no máximo 120 caracteres.")

        filtros = (
            self.pesquisa,
            self.ementa,
            self.classe,
            self.assunto,
            self.comarca,
            self.orgao_julgador,
            self.data_julgamento_inicio,
            self.data_julgamento_fim,
        )
        if not any(valor.strip() for valor in filtros):
            raise ValueError("Informe pesquisa livre ou pelo menos um filtro.")

        tem_inicio = bool(self.data_julgamento_inicio)
        tem_fim = bool(self.data_julgamento_fim)
        if tem_inicio != tem_fim:
            raise ValueError("Informe início e fim do julgamento juntos.")
        if tem_inicio:
            inicio = _data(self.data_julgamento_inicio)
            fim = _data(self.data_julgamento_fim)
            if fim < inicio:
                raise ValueError("Data final não pode anteceder a inicial.")
            if (fim - inicio).days > 366:
                raise ValueError("Intervalo de julgamento não pode exceder 366 dias.")


@dataclass(slots=True, frozen=True)
class Decisao:
    processo: str
    cd_acordao: str
    cd_foro: str
    classe: str
    assunto: str
    relator: str
    comarca: str
    orgao_julgador: str
    data_julgamento: str
    data_publicacao: str
    ementa: str
    inteiro_teor_url: str
    ocorrencias: int | None = None

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ResultadoPesquisa:
    total_disponivel: int
    paginas_coletadas: int
    decisoes: tuple[Decisao, ...]


def _data(valor: str) -> datetime:
    try:
        return datetime.strptime(valor, "%d/%m/%Y")
    except ValueError as exc:
        raise ValueError(f"Data inválida: {valor!r}; use DD/MM/AAAA.") from exc
