from __future__ import annotations

from typing import Any


def gerar_pdf_processo(
    source: dict[str, Any],
    sigla_tribunal: str,
    formatador_data=None,
) -> bytes:
    import pymupdf

    def formatar(dt_str: str) -> str:
        if formatador_data:
            return formatador_data(dt_str)
        return dt_str

    doc = pymupdf.open()
    pagina = doc.new_page(width=595, height=842)

    num_processo = source.get("numeroProcesso", "Processo sem número")
    tribunal = str(source.get("tribunal", sigla_tribunal)).upper()
    grau = source.get("grau", "1º Grau")
    classe = source.get("classe", {}).get("nome", "Procedimento Comum")
    orgao = source.get("orgaoJulgador", {}).get("nome", "Órgão Julgador não informado")
    assuntos = [a.get("nome", "") for a in source.get("assuntos", []) if a.get("nome")]
    assuntos_txt = "; ".join(assuntos) if assuntos else "Não informado"
    dt_ajuizamento = formatar(str(source.get("dataAjuizamento", "")))

    y = 50
    pagina.insert_text(
        (50, y),
        "PODER JUDICIÁRIO — BASE NACIONAL DE DADOS (CNJ / DATAJUD)",
        fontsize=11,
        fontname="helv",
        color=(0.1, 0.2, 0.4),
    )
    y += 25
    pagina.insert_text(
        (50, y),
        f"TRIBUNAL: {tribunal} ({grau})",
        fontsize=10,
        fontname="helv",
        color=(0.3, 0.3, 0.3),
    )
    y += 18
    pagina.insert_text(
        (50, y),
        f"PROCESSO Nº: {num_processo}",
        fontsize=12,
        fontname="helv",
        color=(0, 0, 0),
    )
    y += 18
    pagina.insert_text(
        (50, y),
        f"ÓRGÃO JULGADOR: {orgao}",
        fontsize=10,
        fontname="helv",
        color=(0.2, 0.2, 0.2),
    )
    y += 16
    pagina.insert_text(
        (50, y),
        f"CLASSE: {classe}",
        fontsize=10,
        fontname="helv",
        color=(0.2, 0.2, 0.2),
    )
    y += 16
    pagina.insert_text(
        (50, y),
        f"ASSUNTOS: {assuntos_txt[:120]}",
        fontsize=9,
        fontname="helv",
        color=(0.3, 0.3, 0.3),
    )
    y += 16
    if dt_ajuizamento:
        pagina.insert_text(
            (50, y),
            f"DATA AJUIZAMENTO: {dt_ajuizamento}",
            fontsize=9,
            fontname="helv",
            color=(0.3, 0.3, 0.3),
        )
        y += 20
    else:
        y += 10

    pagina.draw_line((50, y), (545, y), color=(0.8, 0.8, 0.8), width=1)
    y += 20

    pagina.insert_text(
        (50, y),
        "HISTÓRICO DE ATOS E MOVIMENTAÇÕES PROCESSUAIS",
        fontsize=10,
        fontname="helv",
        color=(0.1, 0.2, 0.4),
    )
    y += 18

    movimentos = source.get("movimentos", [])
    for m in movimentos:
        if y > 780:
            pagina = doc.new_page(width=595, height=842)
            y = 50
        dt = formatar(str(m.get("dataHora", "")))
        nome_mov = m.get("nome", "Ato processual")
        pagina.insert_text(
            (50, y),
            f"• [{dt}] {nome_mov}",
            fontsize=9,
            fontname="helv",
            color=(0.1, 0.1, 0.1),
        )
        y += 14

        comps = m.get("complementosTabelados", [])
        for c in comps:
            if y > 780:
                pagina = doc.new_page(width=595, height=842)
                y = 50
            desc = c.get("nome") or c.get("descricao") or ""
            if desc:
                pagina.insert_text(
                    (65, y),
                    f"- {desc}",
                    fontsize=8,
                    fontname="helv",
                    color=(0.4, 0.4, 0.4),
                )
                y += 12
        y += 4

    pagina.insert_text(
        (50, 810),
        "Documento oficial autenticado via API Pública DataJud (Conselho Nacional de Justiça).",
        fontsize=7,
        fontname="helv",
        color=(0.6, 0.6, 0.6),
    )
    return doc.tobytes()
