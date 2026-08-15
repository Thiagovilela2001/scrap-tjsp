# Dataset jurídico

`casos.jsonl` contém 20 casos reais, um por acórdão público do TJSP. Cada linha registra a pergunta, o acórdão relevante, termos verificáveis, resposta de referência, número do processo e URL oficial do PDF. Cinco casos não usam filtro de acórdão e medem recuperação no corpus inteiro; os outros quinze medem a seleção de passagens dentro da decisão indicada.

O recorte foi coletado em 14/08/2026, pela consulta pública CJSG, com quatro PDFs por pesquisa e intervalo de um segundo. Pesquisas usadas: `dano moral`, `prescrição intercorrente`, `tutela de urgência`, `responsabilidade objetiva`, `embargos de declaração` e `fraude bancária`. Resultados podem mudar; `cd_acordao` e `fonte_url` preservam a identidade da fonte avaliada.

O dataset não inclui os PDFs nem dados pessoais extraídos. Para reconstruir a base local e executar a avaliação em uma única etapa:

```powershell
tjsp-preparar-dataset evals/casos.jsonl
```

O comando valida a correspondência entre URL e `cd_acordao`, baixa somente do endpoint público permitido, reutiliza PDFs locais válidos, processa texto/OCR, indexa SQLite + Chroma e chama `tjsp-avaliar`. Ele não chama a Maritaca.

Para preparar apenas uma amostra, sem avaliar o dataset incompleto:

```powershell
tjsp-preparar-dataset evals/casos.jsonl --max-fontes 2 --sem-avaliacao
```

Avaliação somente local, sem chamada à Maritaca:

```powershell
tjsp-avaliar evals/casos.jsonl `
  --sqlite-path data/tjsp.sqlite3 `
  --chroma-path data/chroma `
  --saida output/avaliacao.json
```

Smoke de cinco respostas Maritaca, sem a segunda chamada do juiz:

```powershell
tjsp-avaliar evals/casos.jsonl `
  --max-casos 5 `
  --gerar-respostas `
  --modelo sabia-4 `
  --max-output-tokens 800 `
  --max-custo-brl 0.40
```

Esse comando pode gerar cobrança por cinco chamadas, mas aborta antes da primeira se a estimativa conservadora superar R$ 0,40. O relatório registra preços, teto, tokens e custo padrão estimado. O teto também pode ser usado com `--juiz-ia`; nesse caso, a estimativa cobre as duas chamadas por caso.

O arquivo `casos.example.jsonl` permanece como exemplo mínimo de formato.

Em `termos_esperados`, use `|` para alternativas lexicalmente equivalentes, por exemplo `prova técnica|prova pericial`. Uma alternativa encontrada satisfaz o termo.

Comparação reproduzível de `all-MiniLM-L6-v2` e `BAAI/bge-m3`, incluindo caminhos
separados e relatório de deltas, está documentada no README principal.
