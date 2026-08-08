/* =====================================================================
   Modelo dimensional (star schema) - Produção de grãos
   T-SQL / SQL Server

   Granularidade da fato: 1 linha por município + produto + ano-safra.
   ===================================================================== */

IF OBJECT_ID('dbo.fato_producao', 'U')  IS NOT NULL DROP TABLE dbo.fato_producao;
IF OBJECT_ID('dbo.dim_municipio', 'U')  IS NOT NULL DROP TABLE dbo.dim_municipio;
IF OBJECT_ID('dbo.dim_produto', 'U')    IS NOT NULL DROP TABLE dbo.dim_produto;
IF OBJECT_ID('dbo.dim_tempo', 'U')      IS NOT NULL DROP TABLE dbo.dim_tempo;
GO

-- ---------------------------------------------------------------------
-- DIMENSÕES
-- sk_* = chave surrogate. A chave de negócio (cod_municipio) fica como
-- atributo, para o modelo não quebrar se o IBGE reorganizar os códigos.
-- ---------------------------------------------------------------------
CREATE TABLE dbo.dim_municipio (
    sk_municipio   INT           NOT NULL PRIMARY KEY,
    cod_municipio  INT           NOT NULL,
    municipio      VARCHAR(120)  NOT NULL,
    uf             CHAR(2)       NOT NULL,
    regiao         VARCHAR(20)   NULL
);
GO

CREATE TABLE dbo.dim_produto (
    sk_produto     INT           NOT NULL PRIMARY KEY,
    produto        VARCHAR(80)   NOT NULL,
    grupo          VARCHAR(40)   NOT NULL
);
GO

CREATE TABLE dbo.dim_tempo (
    sk_tempo       INT           NOT NULL PRIMARY KEY,
    ano            SMALLINT      NOT NULL,
    decada         SMALLINT      NOT NULL,
    data_referencia DATE         NULL   -- 31/12 do ano, p/ marcar como tabela de data no Power BI
);
GO

-- ---------------------------------------------------------------------
-- FATO
-- Só chaves e métricas aditivas. Nenhum atributo descritivo aqui:
-- é isso que mantém a compressão do VertiPaq eficiente.
-- ---------------------------------------------------------------------
CREATE TABLE dbo.fato_producao (
    sk_municipio             INT            NOT NULL,
    sk_produto               INT            NOT NULL,
    sk_tempo                 INT            NOT NULL,
    area_plantada_ha         DECIMAL(18,2)  NULL,
    area_colhida_ha          DECIMAL(18,2)  NULL,
    quantidade_t             DECIMAL(18,2)  NULL,
    valor_producao_mil_reais DECIMAL(18,2)  NULL,
    perda_area_ha            DECIMAL(18,2)  NULL,
    flag_area_inconsistente  BIT            NULL,
    CONSTRAINT pk_fato_producao PRIMARY KEY (sk_municipio, sk_produto, sk_tempo),
    CONSTRAINT fk_fato_municipio FOREIGN KEY (sk_municipio) REFERENCES dbo.dim_municipio(sk_municipio),
    CONSTRAINT fk_fato_produto   FOREIGN KEY (sk_produto)   REFERENCES dbo.dim_produto(sk_produto),
    CONSTRAINT fk_fato_tempo     FOREIGN KEY (sk_tempo)     REFERENCES dbo.dim_tempo(sk_tempo)
);
GO

/* Índice columnstore: padrão para tabela fato analítica.
   Ganho de compressão e de varredura em agregação. */
CREATE NONCLUSTERED COLUMNSTORE INDEX ix_cs_fato_producao
    ON dbo.fato_producao (sk_municipio, sk_produto, sk_tempo,
                          area_colhida_ha, quantidade_t, valor_producao_mil_reais);
GO

/* Rendimento NÃO é coluna da fato: é média ponderada, não é aditiva.
   Somar rendimento de dois municípios não faz sentido; a conta correta é
   SUM(quantidade) / SUM(area_colhida). Fica como medida DAX. */
