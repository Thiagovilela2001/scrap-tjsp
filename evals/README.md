# Dataset jurídico

`casos.jsonl` contém 20 casos reais, um por acórdão público do TJSP. Cada linha registra a pergunta, o acórdão relevante, termos verificáveis, resposta de referência, número do processo e URL oficial do PDF. Cinco casos não usam filtro de acórdão e medem recuperação no corpus inteiro; os outros quinze medem a seleção de passagens dentro da decisão indicada.

O recorte foi coletado em 14/08/2026, pela consulta pública CJSG, com quatro PDFs por pesquisa e intervalo de um segundo. Pesquisas usadas: `dano moral`, `prescrição intercorrente`, `tutela de urgência`, `responsabilidade objetiva`, `embargos de declaração` e `fraude bancária`. Resultados podem mudar; `cd_acordao` e `fonte_url` preservam a identidade da fonte avaliada.

O dataset não inclui os PDFs nem dados pessoais extraídos. Antes de avaliar, as fontes indicadas precisam estar processadas no SQLite e no Chroma locais.

Avaliação somente local, sem chamada à Maritaca:

```powershell
tjsp-avaliar evals/casos.jsonl `
  --sqlite-path data/tjsp.sqlite3 `
  --chroma-path data/chroma `
  --saida output/avaliacao.json
```

O arquivo `casos.example.jsonl` permanece como exemplo mínimo de formato.
