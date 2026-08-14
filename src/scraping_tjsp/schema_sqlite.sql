PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS migracoes_schema (
    id TEXT PRIMARY KEY,
    aplicada_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS consultas_jurisprudencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parametros TEXT NOT NULL CHECK (json_valid(parametros)),
    total_disponivel INTEGER NOT NULL CHECK (total_disponivel >= 0),
    paginas_coletadas INTEGER NOT NULL CHECK (paginas_coletadas >= 0),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS decisoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cd_acordao TEXT NOT NULL UNIQUE,
    cd_foro TEXT NOT NULL,
    processo TEXT NOT NULL,
    classe TEXT NOT NULL DEFAULT '',
    assunto TEXT NOT NULL DEFAULT '',
    relator TEXT NOT NULL DEFAULT '',
    comarca TEXT NOT NULL DEFAULT '',
    orgao_julgador TEXT NOT NULL DEFAULT '',
    data_julgamento TEXT,
    data_publicacao TEXT,
    ementa TEXT NOT NULL DEFAULT '',
    inteiro_teor_url TEXT NOT NULL,
    ocorrencias INTEGER,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS consulta_decisoes (
    consulta_id INTEGER NOT NULL REFERENCES consultas_jurisprudencia(id) ON DELETE CASCADE,
    decisao_id INTEGER NOT NULL REFERENCES decisoes(id) ON DELETE CASCADE,
    posicao INTEGER NOT NULL CHECK (posicao > 0),
    PRIMARY KEY (consulta_id, decisao_id)
);

CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id INTEGER NOT NULL UNIQUE REFERENCES decisoes(id) ON DELETE CASCADE,
    url_origem TEXT NOT NULL,
    caminho_local TEXT,
    mime_type TEXT,
    tamanho_bytes INTEGER CHECK (tamanho_bytes IS NULL OR tamanho_bytes >= 0),
    sha256 TEXT CHECK (sha256 IS NULL OR length(sha256) = 64),
    status TEXT NOT NULL CHECK (status IN ('baixado', 'erro')),
    erro TEXT,
    tentativas INTEGER NOT NULL DEFAULT 1 CHECK (tentativas > 0),
    baixado_em TEXT,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processamentos_documento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_id INTEGER NOT NULL UNIQUE REFERENCES documentos(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('processando', 'processado', 'parcial', 'erro')),
    total_paginas INTEGER NOT NULL DEFAULT 0 CHECK (total_paginas >= 0),
    paginas_com_texto INTEGER NOT NULL DEFAULT 0 CHECK (paginas_com_texto >= 0),
    paginas_ocr INTEGER NOT NULL DEFAULT 0 CHECK (paginas_ocr >= 0),
    total_chunks INTEGER NOT NULL DEFAULT 0 CHECK (total_chunks >= 0),
    extrator TEXT NOT NULL DEFAULT 'pymupdf',
    erro TEXT,
    tentativas INTEGER NOT NULL DEFAULT 1 CHECK (tentativas > 0),
    iniciado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    concluido_em TEXT,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paginas_documento (
    processamento_id INTEGER NOT NULL REFERENCES processamentos_documento(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL CHECK (numero > 0),
    texto TEXT NOT NULL DEFAULT '',
    metodo TEXT NOT NULL CHECK (metodo IN ('nativo', 'ocr', 'vazio')),
    caracteres INTEGER NOT NULL CHECK (caracteres >= 0),
    erro TEXT,
    PRIMARY KEY (processamento_id, numero)
);

CREATE TABLE IF NOT EXISTS chunks_documento (
    id TEXT PRIMARY KEY,
    processamento_id INTEGER NOT NULL REFERENCES processamentos_documento(id) ON DELETE CASCADE,
    pagina INTEGER NOT NULL CHECK (pagina > 0),
    indice INTEGER NOT NULL CHECK (indice > 0),
    texto TEXT NOT NULL,
    caracteres INTEGER NOT NULL CHECK (caracteres > 0),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (processamento_id, pagina, indice)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    id UNINDEXED,
    texto,
    content = 'chunks_documento',
    content_rowid = 'rowid',
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_documento_ai AFTER INSERT ON chunks_documento BEGIN
    INSERT INTO chunks_fts(rowid, id, texto) VALUES (new.rowid, new.id, new.texto);
END;

CREATE TRIGGER IF NOT EXISTS chunks_documento_ad AFTER DELETE ON chunks_documento BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, id, texto)
    VALUES ('delete', old.rowid, old.id, old.texto);
END;

CREATE TRIGGER IF NOT EXISTS chunks_documento_au AFTER UPDATE ON chunks_documento BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, id, texto)
    VALUES ('delete', old.rowid, old.id, old.texto);
    INSERT INTO chunks_fts(rowid, id, texto) VALUES (new.rowid, new.id, new.texto);
END;

INSERT INTO chunks_fts(chunks_fts)
SELECT 'rebuild'
WHERE NOT EXISTS (
    SELECT 1 FROM migracoes_schema WHERE id = '001_chunks_fts'
);

INSERT OR IGNORE INTO migracoes_schema (id) VALUES ('001_chunks_fts');

CREATE TABLE IF NOT EXISTS execucoes_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pergunta TEXT NOT NULL,
    provedor TEXT NOT NULL,
    modelo TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processando', 'concluida', 'erro')),
    configuracao TEXT NOT NULL CHECK (json_valid(configuracao)),
    instrucoes_sistema TEXT NOT NULL,
    mensagem_usuario TEXT NOT NULL,
    resposta TEXT,
    resposta_externa_id TEXT,
    tokens_entrada INTEGER CHECK (tokens_entrada IS NULL OR tokens_entrada >= 0),
    tokens_saida INTEGER CHECK (tokens_saida IS NULL OR tokens_saida >= 0),
    tokens_total INTEGER CHECK (tokens_total IS NULL OR tokens_total >= 0),
    duracao_ms INTEGER CHECK (duracao_ms IS NULL OR duracao_ms >= 0),
    erro TEXT,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    concluido_em TEXT
);

CREATE TABLE IF NOT EXISTS fontes_execucao_ia (
    execucao_id INTEGER NOT NULL REFERENCES execucoes_ia(id) ON DELETE CASCADE,
    posicao INTEGER NOT NULL CHECK (posicao > 0),
    chunk_id TEXT NOT NULL,
    citacao TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    texto TEXT NOT NULL,
    score_hibrido REAL NOT NULL,
    PRIMARY KEY (execucao_id, posicao)
);

CREATE TABLE IF NOT EXISTS execucoes_avaliacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset TEXT NOT NULL,
    configuracao TEXT NOT NULL CHECK (json_valid(configuracao)),
    resumo TEXT NOT NULL CHECK (json_valid(resumo)),
    aprovado INTEGER NOT NULL CHECK (aprovado IN (0, 1)),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS casos_avaliacao (
    avaliacao_id INTEGER NOT NULL REFERENCES execucoes_avaliacao(id) ON DELETE CASCADE,
    caso_id TEXT NOT NULL,
    pergunta TEXT NOT NULL,
    resultado TEXT NOT NULL CHECK (json_valid(resultado)),
    aprovado INTEGER NOT NULL CHECK (aprovado IN (0, 1)),
    PRIMARY KEY (avaliacao_id, caso_id)
);

CREATE INDEX IF NOT EXISTS idx_decisoes_processo ON decisoes (processo);
CREATE INDEX IF NOT EXISTS idx_decisoes_data_julgamento ON decisoes (data_julgamento);
CREATE INDEX IF NOT EXISTS idx_decisoes_orgao_julgador ON decisoes (orgao_julgador);
CREATE INDEX IF NOT EXISTS idx_documentos_status ON documentos (status);
CREATE INDEX IF NOT EXISTS idx_processamentos_status ON processamentos_documento (status);
CREATE INDEX IF NOT EXISTS idx_chunks_pagina ON chunks_documento (processamento_id, pagina);
CREATE INDEX IF NOT EXISTS idx_execucoes_ia_status ON execucoes_ia (status);
CREATE INDEX IF NOT EXISTS idx_execucoes_ia_criado_em ON execucoes_ia (criado_em);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_criado_em ON execucoes_avaliacao (criado_em);
