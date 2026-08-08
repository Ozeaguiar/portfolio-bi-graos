/* =====================================================================
   Consultas analíticas sobre o modelo.
   Servem de validação cruzada: o número que sai daqui tem que bater
   com o número do dashboard. É assim que se testa um relatório.
   ===================================================================== */

-- 1. Top 10 municípios por volume de soja no último ano disponível
WITH ultimo_ano AS (SELECT MAX(ano) AS ano FROM dbo.dim_tempo)
SELECT TOP 10
    m.municipio,
    m.uf,
    SUM(f.quantidade_t)     AS producao_t,
    SUM(f.area_colhida_ha)  AS area_colhida_ha,
    SUM(f.quantidade_t) / NULLIF(SUM(f.area_colhida_ha), 0) AS rendimento_t_ha
FROM dbo.fato_producao f
JOIN dbo.dim_municipio m ON m.sk_municipio = f.sk_municipio
JOIN dbo.dim_produto   p ON p.sk_produto   = f.sk_produto
JOIN dbo.dim_tempo     t ON t.sk_tempo     = f.sk_tempo
WHERE p.produto = 'Soja (em grão)'
  AND t.ano = (SELECT ano FROM ultimo_ano)
GROUP BY m.municipio, m.uf
ORDER BY producao_t DESC;


-- 2. Evolução anual por UF, com variação percentual ano a ano
SELECT
    m.uf,
    t.ano,
    SUM(f.quantidade_t) AS producao_t,
    LAG(SUM(f.quantidade_t)) OVER (PARTITION BY m.uf ORDER BY t.ano) AS producao_ano_anterior,
    ROUND(
        100.0 * (SUM(f.quantidade_t) - LAG(SUM(f.quantidade_t)) OVER (PARTITION BY m.uf ORDER BY t.ano))
        / NULLIF(LAG(SUM(f.quantidade_t)) OVER (PARTITION BY m.uf ORDER BY t.ano), 0)
    , 2) AS variacao_pct
FROM dbo.fato_producao f
JOIN dbo.dim_municipio m ON m.sk_municipio = f.sk_municipio
JOIN dbo.dim_tempo     t ON t.sk_tempo     = f.sk_tempo
GROUP BY m.uf, t.ano
ORDER BY m.uf, t.ano;


-- 3. Perda de área entre plantio e colheita: onde o problema se concentra
SELECT
    m.uf,
    p.produto,
    SUM(f.area_plantada_ha) AS plantada_ha,
    SUM(f.area_colhida_ha)  AS colhida_ha,
    ROUND(100.0 * (SUM(f.area_plantada_ha) - SUM(f.area_colhida_ha))
          / NULLIF(SUM(f.area_plantada_ha), 0), 2) AS perda_pct
FROM dbo.fato_producao f
JOIN dbo.dim_municipio m ON m.sk_municipio = f.sk_municipio
JOIN dbo.dim_produto   p ON p.sk_produto   = f.sk_produto
GROUP BY m.uf, p.produto
HAVING SUM(f.area_plantada_ha) > 0
ORDER BY perda_pct DESC;


-- 4. Checagem de integridade: nenhuma linha da fato pode ficar órfã
SELECT 'municipio' AS dimensao, COUNT(*) AS orfas
FROM dbo.fato_producao f
LEFT JOIN dbo.dim_municipio d ON d.sk_municipio = f.sk_municipio
WHERE d.sk_municipio IS NULL
UNION ALL
SELECT 'produto', COUNT(*)
FROM dbo.fato_producao f
LEFT JOIN dbo.dim_produto d ON d.sk_produto = f.sk_produto
WHERE d.sk_produto IS NULL
UNION ALL
SELECT 'tempo', COUNT(*)
FROM dbo.fato_producao f
LEFT JOIN dbo.dim_tempo d ON d.sk_tempo = f.sk_tempo
WHERE d.sk_tempo IS NULL;
