# Scraping TJSP - jurisprudência CJSG

Coletor para a [Consulta Completa de Jurisprudência do Segundo Grau do TJSP](https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do?f=1). A pesquisa usa texto livre e filtros; número CNJ não é entrada obrigatória.

## Escopo atual

- consulta de acórdãos, decisões monocráticas ou homologações;
- filtros por ementa, data de julgamento e IDs internos do TJSP;
- paginação preservando a sessão HTTP;
- extração de processo, classe, assunto, relator, comarca, órgão julgador, datas, ementa e URL do inteiro teor;
- saída JSONL ou CSV;
- intervalo entre requisições, retentativas com backoff e limite explícito de páginas.

O coletor não contorna CAPTCHA, autenticação, segredo de justiça ou bloqueios. Se o TJSP exigir validação humana, a execução para com erro. Use somente dados públicos, respeite a LGPD e revise as condições do portal. O próprio TJSP atribui ao usuário a responsabilidade pelo uso e divulgação das informações obtidas.

## Instalação

```powershell
python -m pip install -e ".[dev]"
```

## Exemplo

```powershell
tjsp-jurisprudencia "dano moral" `
  --inicio 01/08/2026 `
  --fim 14/08/2026 `
  --paginas 2 `
  --saida output/dano_moral.jsonl
```

Busca apenas na ementa:

```powershell
tjsp-jurisprudencia --ementa "prescrição intercorrente" --paginas 1
```

Filtros estruturados como classe, assunto, comarca e órgão julgador recebem os IDs internos usados pelo formulário do TJSP.

## Controles de carga

- padrão: somente 1 página;
- padrão: 2 segundos entre requisições;
- datas inicial e final devem ser informadas juntas;
- intervalo máximo: 366 dias, conforme validação do portal;
- sem paralelismo.

## Testes

```powershell
pytest
```
