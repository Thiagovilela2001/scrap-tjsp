# Scraping TJSP - jurisprudência CJSG

Coletor para a [Consulta Completa de Jurisprudência do Segundo Grau do TJSP](https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do?f=1). A pesquisa usa texto livre e filtros; número CNJ não é entrada obrigatória.

## Escopo atual

- consulta de acórdãos, decisões monocráticas ou homologações;
- filtros por ementa, data de julgamento e IDs internos do TJSP;
- paginação preservando a sessão HTTP;
- extração de processo, classe, assunto, relator, comarca, órgão julgador, datas, ementa e URL do inteiro teor;
- download opcional e sequencial dos PDFs, com limite de quantidade e tamanho;
- validação de assinatura `%PDF-`, SHA-256, arquivo temporário e substituição atômica;
- persistência SQLite idempotente de consultas, decisões e documentos;
- indexação local das ementas no Chroma para busca semântica;
- extração opcional do inteiro teor por página com PyMuPDF e fallback OCR;
- chunks com IDs estáveis e citação por processo, acórdão e página;
- busca híbrida combinando SQLite FTS5/BM25 e similaridade vetorial Chroma;
- pacote RAG rastreável, pronto para conectar a um provedor de IA;
- auditoria SQLite de respostas, fontes, tokens, latência e erros;
- API FastAPI local para busca, resposta Maritaca e consulta de auditorias;
- avaliação reproduzível de recuperação, citações e respostas jurídicas;
- saída JSONL ou CSV;
- intervalo entre requisições, retentativas com backoff e limite explícito de páginas.

O coletor não contorna CAPTCHA, autenticação, segredo de justiça ou bloqueios. Se o TJSP exigir validação humana, a execução para com erro. Use somente dados públicos, respeite a LGPD e revise as condições do portal. O próprio TJSP atribui ao usuário a responsabilidade pelo uso e divulgação das informações obtidas.

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### OCR em português no Windows

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact
New-Item -ItemType Directory -Force data\tessdata
Invoke-WebRequest `
  -Uri "https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata" `
  -OutFile "data\tessdata\por.traineddata"
```

O diretório `data/` não entra no Git. O processador descobre automaticamente `data/tessdata`, `TESSDATA_PREFIX` ou a instalação padrão em `C:\Program Files\Tesseract-OCR\tessdata`.

## Exemplo

```powershell
python -m scraping_tjsp "dano moral" `
  --inicio 01/08/2026 `
  --fim 14/08/2026 `
  --paginas 2 `
  --saida output/dano_moral.jsonl
```

Busca apenas na ementa:

```powershell
python -m scraping_tjsp --ementa "prescrição intercorrente" --paginas 1
```

Filtros estruturados como classe, assunto, comarca e órgão julgador recebem os IDs internos usados pelo formulário do TJSP.

## Persistência local: SQLite + Chroma

Nenhum servidor ou Docker é necessário:

- `data/tjsp.sqlite3`: fonte de verdade relacional;
- `data/chroma/`: índice vetorial persistente;
- `data/pdfs/`: inteiros teores baixados.

Na primeira execução, o coletor cria automaticamente estas tabelas SQLite:

- `consultas_jurisprudencia`: parâmetros e métricas de cada busca;
- `decisoes`: metadados e ementas, atualizados por `cd_acordao`;
- `consulta_decisoes`: vínculo e posição dos resultados;
- `documentos`: caminho, tamanho, SHA-256, status e tentativas;
- `processamentos_documento`: estado, tentativas e métricas da extração;
- `paginas_documento`: texto, método nativo/OCR e erro por página;
- `chunks_documento`: trechos usados pelo índice vetorial.
- `execucoes_ia` e `fontes_execucao_ia`: trilha completa de cada chamada;
- `execucoes_avaliacao` e `casos_avaliacao`: histórico dos relatórios de qualidade.

Ementas são gravadas na coleção Chroma `ementas_tjsp`, usando `cd_acordao` como identificador estável. Modelo padrão local: `all-MiniLM-L6-v2`; arquivos do modelo podem ser baixados automaticamente na primeira indexação. Ele serve ao MVP sem configuração, mas deverá ser comparado com BGE-M3 antes da avaliação jurídica de relevância.

Trechos dos inteiros teores ficam na coleção `chunks_tjsp`. Cada ID segue `acordao:{cd_acordao}:pagina:{pagina}:chunk:{indice}`. SQLite continua sendo fonte de verdade; Chroma pode ser reconstruído.

## Pesquisa, persistência e PDFs

```powershell
python -m scraping_tjsp "dano moral" `
  --inicio 01/08/2026 `
  --fim 14/08/2026 `
  --paginas 2 `
  --baixar-pdfs `
  --processar-pdfs `
  --max-pdfs 10 `
  --max-mb-pdf 50 `
  --sqlite-path data/tjsp.sqlite3 `
  --chroma-path data/chroma `
  --diretorio-pdfs data/pdfs `
  --saida output/dano_moral.jsonl
```

Sem `--baixar-pdfs`, somente metadados e ementas são persistidos. Use `--sem-persistencia` para produzir apenas JSONL/CSV, sem SQLite ou Chroma.

`--processar-pdfs` exige `--baixar-pdfs` e persistência ativa. PyMuPDF tenta OCR somente quando uma página tem menos de 80 caracteres úteis. OCR requer Tesseract e dados do idioma português instalados no sistema; sem eles, a página fica marcada como parcial, sem perder texto nativo. Use `--sem-ocr` para desligar a tentativa. Ajuste trechos com `--tamanho-chunk` e `--sobreposicao-chunk`.

## Busca híbrida

```powershell
tjsp-busca "responsabilidade civil por dano moral" --limite 5
```

Filtros opcionais: `--cd-acordao`, `--processo`, `--classe`, `--assunto`, `--orgao-julgador` e `--pagina`. Use `--json` para saída estruturada.

A busca lexical usa FTS5 com tokenização Unicode e ranking BM25. A busca semântica usa `chunks_tjsp` no Chroma. Os rankings são fundidos com Reciprocal Rank Fusion (RRF), sem comparar diretamente escalas incompatíveis de BM25 e distância vetorial.

## Contexto para inteligência artificial

```powershell
tjsp-busca "Quando o TJSP reconhece dano moral?" `
  --limite 6 `
  --contexto-ia `
  --json
```

O resultado contém instruções de sistema, pergunta, fontes, URLs, citações e trechos limitados por tamanho. `ProvedorIA` mantém a recuperação desacoplada do modelo. Sem `--responder`, nenhuma chamada externa de IA ocorre.

### Resposta com Maritaca AI

O adaptador usa a Responses API compatível com OpenAI, recomendada pela [documentação da Maritaca](https://docs.maritaca.ai/pt/responses-api), com `sabia-4` como modelo padrão.

```powershell
Copy-Item .env.example .env
# Edite .env e informe MARITACA_API_KEY sem aspas.

tjsp-busca "Quando o TJSP reconhece dano moral?" `
  --limite 6 `
  --responder `
  --modelo sabia-4 `
  --json
```

Também é possível definir a chave somente na sessão:

```powershell
$env:MARITACA_API_KEY = "sua-chave"
```

`.env` está ignorado pelo Git. `--responder` faz chamada externa potencialmente tarifada; `--contexto-ia` apenas prepara o pacote local, sem chamar o modelo.

Cada uso de `--responder` cria uma auditoria antes da chamada e a conclui com resposta, ID externo, modelo, tokens, duração e fontes. Falhas também são registradas. A saída informa `auditoria_id`; chaves da API nunca são persistidas.

```powershell
tjsp-auditoria --limite 20
tjsp-auditoria 1 --json
```

## API local

Inicie o serviço somente na máquina local:

```powershell
tjsp-api
```

A documentação interativa fica em `http://127.0.0.1:8000/docs`. O endereço padrão não expõe o serviço para a rede.

Busca híbrida sem chamada de IA:

```powershell
$corpo = @{
  pergunta = "Quando o TJSP reconhece dano moral?"
  limite = 5
  filtros = @{ assunto = "Dano Moral" }
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/buscar `
  -ContentType "application/json" `
  -Body $corpo
```

Resposta Maritaca com fontes e auditoria:

```powershell
$corpo = @{
  pergunta = "Quando o TJSP reconhece dano moral?"
  limite_fontes = 6
  max_output_tokens = 800
  max_custo_brl = 0.10
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/perguntar `
  -ContentType "application/json" `
  -Body $corpo
```

Endpoints disponíveis:

- `GET /saude`: configuração pública e estado do serviço;
- `POST /buscar`: recuperação híbrida local, sem cobrança;
- `POST /perguntar`: RAG com Maritaca, fontes, tokens e custo estimado;
- `GET /auditorias`: últimas chamadas registradas;
- `GET /auditorias/{id}`: detalhes, fontes e resultado de uma chamada.

O servidor limita cada requisição a `TJSP_API_MAX_CUSTO_BRL=0.10` e `TJSP_API_MAX_OUTPUT_TOKENS=2000`. O cliente pode pedir limites menores, nunca maiores. A estimativa conservadora é calculada antes da chamada; ausência de fontes, chave Maritaca ou orçamento suficiente impede a chamada paga. Caminhos podem ser alterados por `TJSP_SQLITE_PATH` e `TJSP_CHROMA_PATH` no `.env`.

O serviço não possui autenticação de usuário. Mantenha o `host` padrão `127.0.0.1`; não use `--host 0.0.0.0` em ambiente acessível por terceiros sem adicionar autenticação e proteção de tráfego.

## Avaliação jurídica

O arquivo [evals/casos.jsonl](evals/casos.jsonl) contém 20 casos reais e rastreáveis; [evals/casos.example.jsonl](evals/casos.example.jsonl) mostra o formato mínimo. Cada linha define pergunta, filtros, chunks ou acórdãos relevantes, termos esperados, resposta de referência, limiares e a URL oficial da fonte. Consulte [evals/README.md](evals/README.md) para conhecer o recorte.

Preparação reproduzível das fontes e avaliação local completa:

```powershell
tjsp-preparar-dataset evals/casos.jsonl
```

O comando baixa os PDFs oficiais ausentes, reutiliza arquivos válidos, processa OCR quando necessário e popula SQLite + Chroma antes de avaliar. Nenhuma chamada à Maritaca é feita.

Avaliação local de recuperação, sem chamada tarifada:

```powershell
tjsp-avaliar evals/casos.jsonl `
  --sqlite-path data/tjsp.sqlite3 `
  --chroma-path data/chroma `
  --saida output/avaliacao.json
```

Avaliação completa, gerando resposta e usando segunda chamada Maritaca como juiz:

```powershell
tjsp-avaliar evals/casos.jsonl `
  --gerar-respostas `
  --juiz-ia `
  --modelo sabia-4
```

`--gerar-respostas` e `--juiz-ia` podem gerar cobrança. O relatório mede `recall`, `hit`, MRR, cobertura dos termos, precisão/cobertura das citações e similaridade com resposta de referência. O juiz opcional pontua aderência às fontes, correção jurídica, completude e citações. Resultados e chamadas ficam auditados no SQLite.

Para um smoke controlado, limite a quantidade de chamadas pagas e deixe o juiz desligado:

```powershell
tjsp-avaliar evals/casos.jsonl `
  --max-casos 5 `
  --gerar-respostas `
  --modelo sabia-4 `
  --max-output-tokens 800 `
  --max-custo-brl 0.40
```

O teto usa uma estimativa conservadora antes de qualquer chamada. Os preços padrão do Sabiá 4, verificados em 14/08/2026, são R$ 5,00 por milhão de tokens de entrada e R$ 20,00 por milhão de tokens de saída. Atualize-os com `--preco-entrada-milhao` e `--preco-saida-milhao` quando a tabela mudar. O limite ainda não pode ser combinado com `--juiz-ia`.

Pontuação do juiz de IA é sinal heurístico para regressão, não substitui revisão jurídica humana.

## Controles de carga

- padrão: somente 1 página;
- padrão: 2 segundos entre requisições;
- datas inicial e final devem ser informadas juntas;
- intervalo máximo: 366 dias, conforme validação do portal;
- download de PDFs desligado por padrão;
- máximo padrão: 20 PDFs de até 50 MB cada;
- PDF existente e válido é reutilizado por `cd_acordao`;
- sem paralelismo.

## Testes

```powershell
python -m pytest
```
