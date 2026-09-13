from __future__ import annotations

TRIBUNAIS_CONFIG: dict[str, dict[str, str | bool]] = {
    # Adaptadores nativos e-SAJ/CJSG ativos
    "tjsp": {
        "sigla": "TJSP",
        "nome": "Tribunal de Justiça de São Paulo",
        "base_url": "https://esaj.tjsp.jus.br/cjsg/",
        "uf": "SP",
        "adaptador": "esaj_cjsg",
        "ativo": True,
    },
    "tjms": {
        "sigla": "TJMS",
        "nome": "Tribunal de Justiça de Mato Grosso do Sul",
        "base_url": "https://esaj.tjms.jus.br/cjsg/",
        "uf": "MS",
        "adaptador": "esaj_cjsg",
        "ativo": True,
    },
    "tjam": {
        "sigla": "TJAM",
        "nome": "Tribunal de Justiça do Amazonas",
        "base_url": "https://consultasaj.tjam.jus.br/cjsg/",
        "uf": "AM",
        "adaptador": "esaj_cjsg",
        "ativo": True,
    },
    "tjac": {
        "sigla": "TJAC",
        "nome": "Tribunal de Justiça do Acre",
        "base_url": "https://esaj.tjac.jus.br/cjsg/",
        "uf": "AC",
        "adaptador": "esaj_cjsg",
        "ativo": True,
    },
    # Adaptador nativo TJPR
    "tjpr": {
        "sigla": "TJPR",
        "nome": "Tribunal de Justiça do Paraná",
        "base_url": "https://portal.tjpr.jus.br/jurisprudencia/",
        "uf": "PR",
        "adaptador": "tjpr",
        "ativo": True,
    },
    # Adaptador nativo STF
    "stf": {
        "sigla": "STF",
        "nome": "Supremo Tribunal Federal",
        "base_url": "https://jurisprudencia.stf.jus.br",
        "uf": "DF",
        "adaptador": "stf",
        "ativo": True,
    },
}

_DATAJUD_ESTADUAIS = [
    ("tjrj", "TJRJ", "Tribunal de Justiça do Rio de Janeiro", "RJ"),
    ("tjmg", "TJMG", "Tribunal de Justiça de Minas Gerais", "MG"),
    ("tjes", "TJES", "Tribunal de Justiça do Espírito Santo", "ES"),
    ("tjrs", "TJRS", "Tribunal de Justiça do Rio Grande do Sul", "RS"),
    ("tjsc", "TJSC", "Tribunal de Justiça de Santa Catarina", "SC"),
    (
        "tjdft",
        "TJDFT",
        "Tribunal de Justiça do Distrito Federal e dos Territórios",
        "DF",
    ),
    ("tjgo", "TJGO", "Tribunal de Justiça de Goiás", "GO"),
    ("tjmt", "TJMT", "Tribunal de Justiça de Mato Grosso", "MT"),
    ("tjba", "TJBA", "Tribunal de Justiça da Bahia", "BA"),
    ("tjpe", "TJPE", "Tribunal de Justiça de Pernambuco", "PE"),
    ("tjce", "TJCE", "Tribunal de Justiça do Ceará", "CE"),
    ("tjma", "TJMA", "Tribunal de Justiça do Maranhão", "MA"),
    ("tjpb", "TJPB", "Tribunal de Justiça da Paraíba", "PB"),
    ("tjrn", "TJRN", "Tribunal de Justiça do Rio Grande do Norte", "RN"),
    ("tjal", "TJAL", "Tribunal de Justiça de Alagoas", "AL"),
    ("tjpi", "TJPI", "Tribunal de Justiça do Piauí", "PI"),
    ("tjse", "TJSE", "Tribunal de Justiça de Sergipe", "SE"),
    ("tjpa", "TJPA", "Tribunal de Justiça do Pará", "PA"),
    ("tjro", "TJRO", "Tribunal de Justiça de Rondônia", "RO"),
    ("tjto", "TJTO", "Tribunal de Justiça do Tocantins", "TO"),
    ("tjap", "TJAP", "Tribunal de Justiça do Amapá", "AP"),
    ("tjrr", "TJRR", "Tribunal de Justiça de Roraima", "RR"),
]

for _cod, _sigla, _nome, _uf in _DATAJUD_ESTADUAIS:
    TRIBUNAIS_CONFIG[_cod] = {
        "sigla": _sigla,
        "nome": _nome,
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": _uf,
        "adaptador": "datajud",
        "ativo": True,
    }

_DATAJUD_FEDERAIS = [
    ("trf1", "TRF1", "Tribunal Regional Federal da 1ª Região", "DF"),
    ("trf2", "TRF2", "Tribunal Regional Federal da 2ª Região", "RJ"),
    ("trf3", "TRF3", "Tribunal Regional Federal da 3ª Região", "SP"),
    ("trf4", "TRF4", "Tribunal Regional Federal da 4ª Região", "RS"),
    ("trf5", "TRF5", "Tribunal Regional Federal da 5ª Região", "PE"),
    ("trf6", "TRF6", "Tribunal Regional Federal da 6ª Região", "MG"),
    ("stj", "STJ", "Superior Tribunal de Justiça", "DF"),
    ("tst", "TST", "Tribunal Superior do Trabalho", "DF"),
    ("tse", "TSE", "Tribunal Superior Eleitoral", "DF"),
    ("stm", "STM", "Superior Tribunal Militar", "DF"),
]

for _cod, _sigla, _nome, _uf in _DATAJUD_FEDERAIS:
    TRIBUNAIS_CONFIG[_cod] = {
        "sigla": _sigla,
        "nome": _nome,
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": _uf,
        "adaptador": "datajud",
        "ativo": True,
    }

# Alias
TRIBUNAIS_CONFIG["tjdf"] = TRIBUNAIS_CONFIG["tjdft"]

TRIBUNAIS_DATAJUD: dict[str, tuple[str, str]] = {
    # Sudeste
    "datajud_tjsp": ("TJSP", "SP"),
    "datajud_tjrj": ("TJRJ", "RJ"),
    "datajud_tjmg": ("TJMG", "MG"),
    "datajud_tjes": ("TJES", "ES"),
    # Sul
    "datajud_tjrs": ("TJRS", "RS"),
    "datajud_tjpr": ("TJPR", "PR"),
    "datajud_tjsc": ("TJSC", "SC"),
    # Centro-Oeste
    "datajud_tjdft": ("TJDFT", "DF"),
    "datajud_tjdf": ("TJDFT", "DF"),
    "datajud_tjgo": ("TJGO", "GO"),
    "datajud_tjmt": ("TJMT", "MT"),
    "datajud_tjms": ("TJMS", "MS"),
    # Nordeste
    "datajud_tjba": ("TJBA", "BA"),
    "datajud_tjpe": ("TJPE", "PE"),
    "datajud_tjce": ("TJCE", "CE"),
    "datajud_tjma": ("TJMA", "MA"),
    "datajud_tjpb": ("TJPB", "PB"),
    "datajud_tjrn": ("TJRN", "RN"),
    "datajud_tjal": ("TJAL", "AL"),
    "datajud_tjpi": ("TJPI", "PI"),
    "datajud_tjse": ("TJSE", "SE"),
    # Norte
    "datajud_tjpa": ("TJPA", "PA"),
    "datajud_tjam": ("TJAM", "AM"),
    "datajud_tjro": ("TJRO", "RO"),
    "datajud_tjto": ("TJTO", "TO"),
    "datajud_tjac": ("TJAC", "AC"),
    "datajud_tjap": ("TJAP", "AP"),
    "datajud_tjrr": ("TJRR", "RR"),
    # Tribunais Regionais Federais
    "datajud_trf1": ("TRF1", "DF"),
    "datajud_trf2": ("TRF2", "RJ"),
    "datajud_trf3": ("TRF3", "SP"),
    "datajud_trf4": ("TRF4", "RS"),
    "datajud_trf5": ("TRF5", "PE"),
    "datajud_trf6": ("TRF6", "MG"),
    # Tribunais Superiores
    "datajud_stj": ("STJ", "DF"),
    "datajud_tst": ("TST", "DF"),
    "datajud_tse": ("TSE", "DF"),
    "datajud_stm": ("STM", "DF"),
}

for _cod, (_sigla, _uf) in TRIBUNAIS_DATAJUD.items():
    TRIBUNAIS_CONFIG[_cod] = {
        "sigla": _sigla,
        "nome": f"Tribunal {_sigla} (DataJud / CNJ)",
        "base_url": "https://api-publica.datajud.cnj.jus.br",
        "uf": _uf,
        "adaptador": "datajud",
        "ativo": True,
    }


def tribunais_ativos(*, adaptador: str | None = None) -> tuple[str, ...]:
    return tuple(
        codigo
        for codigo, config in TRIBUNAIS_CONFIG.items()
        if config.get("ativo") is True
        and (adaptador is None or config.get("adaptador") == adaptador)
    )


TODOS_TJS: tuple[str, ...] = (
    "tjac",
    "tjal",
    "tjam",
    "tjap",
    "tjba",
    "tjce",
    "tjdft",
    "tjes",
    "tjgo",
    "tjma",
    "tjmg",
    "tjms",
    "tjmt",
    "tjpa",
    "tjpb",
    "tjpe",
    "tjpi",
    "tjpr",
    "tjrj",
    "tjrn",
    "tjro",
    "tjrr",
    "tjrs",
    "tjsc",
    "tjse",
    "tjsp",
    "tjto",
)
