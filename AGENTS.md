# Scraping TJSP — Vibe Coding Toolkit Configuration

> Memória e governança de desenvolvimento com IA para o projeto.
> Segue o padrão do Vibe Coding Toolkit (Superpowers + Ponytail + Caveman + Subagentes em Ondas).

## Diretrizes Comportamentais (Behavioral Guidelines)

1. **Pense antes de codar (Think before coding)** — Declare premissas explicitamente. Se houver mais de uma interpretação razoável, apresente as opções em vez de escolher silenciosamente. Se algo for ambíguo, pare e pergunte antes de escrever código.
2. **Simplicidade primeiro (Ponytail / Simplicity first)** — Busque sempre a solução mais simples e com menos código. Evite abstrações especulativas, classes genéricas para uso único ou tratamento de erros para cenários impossíveis. Use a biblioteca padrão sempre que possível.
3. **Mudanças cirúrgicas (Surgical changes)** — Modifique apenas o que a tarefa exige. Respeite o estilo existente. Não refatore nem formate arquivos adjacentes sem solicitação explícita.
4. **Execução orientada a metas (Goal-driven execution / TDD)** — Transforme cada tarefa em um objetivo verificável com teste (`pytest`). Para tarefas com múltiplos passos, crie um plano com verificação e só avance quando o teste passar.
5. **Orquestrador, não implementador (Orchestrator, not implementer)** — A sessão principal planeja, decide e coordena; despacha especialistas para tarefas executáveis, em ondas paralelas quando não houver colisão de arquivos.

## Quality Gates

- **Teto de tamanho:** Máximo de **350 linhas** por arquivo. Arquivos que ultrapassam esse limite devem ser decompostos por responsabilidade (lógica de parsing, acesso a dados, rotas de API).
- **Linter & Formatador:** O código deve passar 100% limpo em `ruff check .` e `ruff format --check .`.
- **Testes:** Toda nova funcionalidade ou correção deve ser acompanhada de teste automatizado executável via `pytest`.

## Stack do Projeto

- **Linguagem:** Python 3.11+
- **Parsing & Scraping:** BeautifulSoup4, Requests, PyMuPDF (fitz)
- **Armazenamento & Vetores:** SQLite, ChromaDB, Sentence-Transformers
- **API & CLI:** FastAPI, Uvicorn, Python standard argparse/CLI
- **Qualidade & Testes:** Pytest, HTTPX, Ruff

## Comandos Canônicos

Sempre use os comandos canônicos abaixo:

- **Instalar:** `pip install -e ".[dev]"`
- **Lint:** `ruff check .`
- **Formatação:** `ruff format --check .` (ou `ruff format .` para aplicar)
- **Testes:** `pytest` (ou `pytest tests/test_especifico.py -v`)
- **Executar API:** `uvicorn scraping_tjsp.api:app --reload`
- **CLI TJSP:** `tjsp-jurisprudencia --help`

## Tabela de Roteamento de Agentes Especialistas

| Especialista | Quando acionar |
|---|---|
| `scraper-engineer` | Coleta de jurisprudência TJSP, requisições HTTP, paginação CJSG, parsing de HTML/PDF, headers e rate limiting. |
| `database-architect` | Schema SQLite, migrações, coleções no ChromaDB, geração e armazenamento de embeddings. |
| `backend-specialist` | Endpoints FastAPI, schemas Pydantic, rotas de busca e comandos CLI. |
| `test-engineer` | Criação de testes unitários e de integração com fixtures e mocks usando pytest. |
| `debugger` | Diagnóstico de causa raiz para falhas de scraping, erros de parsing ou quebras de testes. |
| `code-reviewer` | Revisão geral de conformidade, complexidade e qualidade antes de mesclar ou concluir tarefas. |
| `security-auditor` | Proteção de credenciais (`.env`), sanitização de entradas e conformidade de acesso. |

