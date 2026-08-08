/* =====================================================================
   Carga dos CSV gerados pelo pipeline Python para o SQL Server.

   Estratégia: staging em VARCHAR -> conversão explícita -> tabelas finais.

   Por que staging? O CSV traz campo vazio onde o valor é nulo. Carregar
   direto em coluna DECIMAL falha ou converte vazio em zero — e zero não é
   a mesma coisa que "não informado". Carregando como texto primeiro, a
   conversão fica explícita e controlada por NULLIF.

   ANTES DE RODAR: ajuste @caminho para a sua pasta.
   ===================================================================== */

USE portfolio_graos;
GO

/* ---------------------------------------------------------------------
   1. Tabelas de staging (tudo texto)
   --------------------------------------------------------------------- */
IF OBJECT_ID('stg.dim_municipio','U') IS NOT NULL DROP TABLE stg.dim_municipio;
IF OBJECT_ID('stg.dim_produto','U')   IS NOT NULL DROP TABLE stg.dim_produto;
IF OBJECT_ID('stg.dim_tempo','U')     IS NOT NULL DROP TABLE stg.dim_tempo;
IF OBJECT_ID('stg.fato_producao','U') IS NOT NULL DROP TABLE stg.fato_producao;
GO

IF SCHEMA_ID('stg') IS NULL EXEC('CREATE SCHEMA stg');
GO

CREATE TABLE stg.dim_municipio (
    sk_municipio VARCHAR(50), cod_municipio VARCHAR(50),
    municipio VARCHAR(200), uf VARCHAR(50), regiao VARCHAR(50)
);

CREATE TABLE stg.dim_produto (
    sk_produto VARCHAR(50), produto VARCHAR(200), grupo VARCHAR(100)
);

CREATE TABLE stg.dim_tempo (
    sk_tempo VARCHAR(50), ano VARCHAR(50),
    decada VARCHAR(50), data_referencia VARCHAR(50)
);

CREATE TABLE stg.fato_producao (
    sk_municipio VARCHAR(50), sk_produto VARCHAR(50), sk_tempo VARCHAR(50),
    area_plantada_ha VARCHAR(50), area_colhida_ha VARCHAR(50),
    quantidade_t VARCHAR(50), valor_producao_mil_reais VARCHAR(50),
    perda_area_ha VARCHAR(50), flag_area_inconsistente VARCHAR(50)
);
GO

/* ---------------------------------------------------------------------
   2. Carga dos CSV
   Ajuste o caminho abaixo para a sua pasta dados\processado
   --------------------------------------------------------------------- */
BULK INSERT stg.dim_municipio
FROM 'C:\Projetos\portfolio-bi-graos-v2\portfolio-bi-graos\dados\processado\dim_municipio.csv'
WITH (FORMAT='CSV', FIRSTROW=2, CODEPAGE='65001', TABLOCK);

BULK INSERT stg.dim_produto
FROM 'C:\Projetos\portfolio-bi-graos-v2\portfolio-bi-graos\dados\processado\dim_produto.csv'
WITH (FORMAT='CSV', FIRSTROW=2, CODEPAGE='65001', TABLOCK);

BULK INSERT stg.dim_tempo
FROM 'C:\Projetos\portfolio-bi-graos-v2\portfolio-bi-graos\dados\processado\dim_tempo.csv'
WITH (FORMAT='CSV', FIRSTROW=2, CODEPAGE='65001', TABLOCK);

BULK INSERT stg.fato_producao
FROM 'C:\Projetos\portfolio-bi-graos-v2\portfolio-bi-graos\dados\processado\fato_producao.csv'
WITH (FORMAT='CSV', FIRSTROW=2, CODEPAGE='65001', TABLOCK);
GO

/* ---------------------------------------------------------------------
   3. Conversão para as tabelas finais
   NULLIF(campo,'') transforma vazio em NULL antes do CAST.
   TRY_CAST devolve NULL em vez de estourar erro se vier lixo.
   Ordem: dimensões primeiro, fato depois (chave estrangeira).
   --------------------------------------------------------------------- */
DELETE FROM dbo.fato_producao;
DELETE FROM dbo.dim_municipio;
DELETE FROM dbo.dim_produto;
DELETE FROM dbo.dim_tempo;
GO

INSERT INTO dbo.dim_municipio (sk_municipio, cod_municipio, municipio, uf, regiao)
SELECT TRY_CAST(NULLIF(sk_municipio,'')  AS INT),
       TRY_CAST(NULLIF(cod_municipio,'') AS INT),
       municipio,
       NULLIF(uf,''),
       NULLIF(regiao,'')
FROM stg.dim_municipio;

INSERT INTO dbo.dim_produto (sk_produto, produto, grupo)
SELECT TRY_CAST(NULLIF(sk_produto,'') AS INT), produto, grupo
FROM stg.dim_produto;

INSERT INTO dbo.dim_tempo (sk_tempo, ano, decada, data_referencia)
SELECT TRY_CAST(NULLIF(sk_tempo,'') AS INT),
       TRY_CAST(NULLIF(ano,'')      AS SMALLINT),
       TRY_CAST(NULLIF(decada,'')   AS SMALLINT),
       TRY_CAST(NULLIF(data_referencia,'') AS DATE)
FROM stg.dim_tempo;

INSERT INTO dbo.fato_producao (
    sk_municipio, sk_produto, sk_tempo,
    area_plantada_ha, area_colhida_ha, quantidade_t,
    valor_producao_mil_reais, perda_area_ha, flag_area_inconsistente)
SELECT TRY_CAST(NULLIF(sk_municipio,'') AS INT),
       TRY_CAST(NULLIF(sk_produto,'')   AS INT),
       TRY_CAST(NULLIF(sk_tempo,'')     AS INT),
       TRY_CAST(NULLIF(area_plantada_ha,'')         AS DECIMAL(18,2)),
       TRY_CAST(NULLIF(area_colhida_ha,'')          AS DECIMAL(18,2)),
       TRY_CAST(NULLIF(quantidade_t,'')             AS DECIMAL(18,2)),
       TRY_CAST(NULLIF(valor_producao_mil_reais,'') AS DECIMAL(18,2)),
       TRY_CAST(NULLIF(perda_area_ha,'')            AS DECIMAL(18,2)),
       CASE WHEN flag_area_inconsistente = 'True' THEN 1
            WHEN flag_area_inconsistente = 'False' THEN 0 END
FROM stg.fato_producao;
GO

/* ---------------------------------------------------------------------
   4. Conferência
   --------------------------------------------------------------------- */
SELECT 'dim_municipio' AS tabela, COUNT(*) AS linhas FROM dbo.dim_municipio
UNION ALL SELECT 'dim_produto',   COUNT(*) FROM dbo.dim_produto
UNION ALL SELECT 'dim_tempo',     COUNT(*) FROM dbo.dim_tempo
UNION ALL SELECT 'fato_producao', COUNT(*) FROM dbo.fato_producao;

/* Esperado: 4.959 / 3 / 4 / 34.396 */

/* Validação de negócio: produção de 2023 deve ficar perto de 292 milhões
   de toneladas, o número real divulgado para soja + milho + trigo. */
SELECT t.ano, SUM(f.quantidade_t) AS producao_t
FROM dbo.fato_producao f
JOIN dbo.dim_tempo t ON t.sk_tempo = f.sk_tempo
GROUP BY t.ano
ORDER BY t.ano;
GO
