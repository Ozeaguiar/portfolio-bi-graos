# Produção de grãos no Brasil (2020-2023)

Projeto de BI usando dados públicos do IBGE. Fiz o pipeline em Python, o modelo
em SQL Server e o dashboard em Power BI.

![Dashboard](docs/dashboard.png)

## Objetivo

Analisar a produção de soja, milho e trigo por município e responder uma
pergunta: quando a produção cresce, o ganho vem de mais área plantada ou de
maior rendimento por hectare?

Escolhi essa pergunta porque volume sozinho engana. Um estado pode produzir mais
só porque plantou mais, sem ter ficado mais eficiente.

## Dados

- Fonte: IBGE, Produção Agrícola Municipal, [tabela 1612](https://sidra.ibge.gov.br/tabela/1612)
- Período: 2020 a 2023
- Produtos: soja, milho e trigo
- Volume: 34.396 linhas na tabela fato, 4.959 municípios

## Como está montado

```
JSON da API do SIDRA
      |
  ingestao.py        limpeza, tipagem, deduplicação
      |
  CSV (fato + dimensões)
      |
  SQL Server         star schema, consultas analíticas
      |
  Power BI           medidas DAX, dashboard, RLS
```

## Modelo de dados

Star schema com uma fato e três dimensões.

```
        dim_tempo
            |
dim_municipio - fato_producao - dim_produto
```

Granularidade da fato: uma linha por município, produto e ano.

Decisões que tomei:

**Chave surrogate nas dimensões.** Guardei o código do IBGE como atributo. Se
eles reorganizarem os códigos, o modelo não quebra.

**Rendimento não é coluna da fato.** Ele é `quantidade / área`, e essa divisão
não pode ser somada. Somar t/ha de dois municípios não significa nada. Deixei
como medida DAX usando `DIVIDE(SUM(qtd), SUM(area))`.

**Sem relacionamento bidirecional.** Cria ambiguidade e abre brecha no RLS.

**UF vem do código do município, não do nome.** Os dois primeiros dígitos do
código IBGE identificam o estado. Tentei extrair do nome primeiro e quebrou,
porque o formato muda entre consultas ("Sorriso - MT" e "Sorriso (MT)").

## Tratamento dos dados

O IBGE não usa números para tudo. Ele usa marcadores de texto:

| Marcador | Significado |
|---|---|
| `-` | zero |
| `...` | não se aplica |
| `..` | não disponível |
| `X` | omitido por sigilo |

Converti todos para nulo, nunca para zero. Zero quer dizer "plantou e não
colheu". Nulo quer dizer "não sei". Se eu tratasse igual, o rendimento sairia
errado nos municípios sem informação.

Na base final, 0,2% dos registros de quantidade estão nulos. A maior parte é
milho, provavelmente milho de segunda safra em municípios pequenos, onde o IBGE
omite por sigilo.

Também checquei se algum município colheu mais área do que plantou, o que seria
impossível. Não encontrei nenhum caso nas 34.396 linhas.

## Resultados

**A produção é bem concentrada.** Em 2023, metade do volume nacional saiu de 109
municípios, de 4.929 que produzem algum grão.

**Crescer área e crescer produtividade são coisas diferentes.** Entre 2020 e
2023, o rendimento médio subiu 9,6% no Pará e caiu 6,2% no Rio Grande do Sul.

**A média nacional esconde problema local.** A perda entre área plantada e
colhida é de 0,6% no país inteiro. Abrindo por estado e produto, o pior caso é
milho em Pernambuco em 2023, com 54,3% da área perdida.

**O preço subiu mais que a produção.** O valor por tonelada foi de R$ 1.070 em
2020 para R$ 1.570 em 2023, sem descontar inflação.

### Sobre o corte de relevância

Nas análises de variação percentual usei corte mínimo: 1% da produção nacional
para rendimento, 100 mil hectares para perda de área.

Fiz isso porque na primeira rodada, sem filtro, o ranking apontava Alagoas e
Ceará como extremos de produtividade de soja e trigo. Fui checar e o Ceará tinha
plantado 23 hectares de trigo e colhido 5. Dá 78% de perda, mas não significa
nada. Variação percentual em cima de base pequena vira ruído.

## Validação

Comparei o resultado com números públicos para ter certeza de que o pipeline
está certo:

- A produção de 2023 no meu modelo deu 291,8 milhões de toneladas. O número real
  divulgado para soja, milho e trigo foi de aproximadamente 297 milhões.
- O Rio Grande do Sul aparece com queda de 37,7% em 2022. Foi o ano da seca do La
  Niña, que derrubou a safra gaúcha de soja.
- Os mesmos números saem do Python, do SQL e do Power BI. Perda de área em
  Pernambuco: 54,3% no Python e 54,31% no SQL.

## Como rodar

### 1. Baixar os dados

Abra as URLs abaixo no navegador e salve o retorno em `dados/bruto/` com
extensão `.json`. A API do SIDRA tem limite de 50 mil valores por requisição,
então dividi em blocos de dois anos.

```
Soja  2020-21  https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/109,216,214,215/p/2020,2021/c81/2713?formato=json
Soja  2022-23  https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/109,216,214,215/p/2022,2023/c81/2713?formato=json
Milho 2020-21  https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/109,216,214,215/p/2020,2021/c81/2711?formato=json
Milho 2022-23  https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/109,216,214,215/p/2022,2023/c81/2711?formato=json
Trigo 2020-21  https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/109,216,214,215/p/2020,2021/c81/2716?formato=json
Trigo 2022-23  https://apisidra.ibge.gov.br/values/t/1612/n6/all/v/109,216,214,215/p/2022,2023/c81/2716?formato=json
```

O `?formato=json` no final é obrigatório. Sem ele a API devolve XML.

### 2. Rodar o pipeline

```bash
pip install -r requirements.txt

python scripts/ingestao.py --amostra   # teste com dados sintéticos
python scripts/ingestao.py             # lê dados/bruto/*.json
python scripts/analise.py              # gera os achados
```

### 3. Banco

Crie o banco e rode os scripts na ordem:

```sql
CREATE DATABASE portfolio_graos;
```

1. `sql/01_modelo_dimensional.sql` cria as tabelas
2. `sql/00_carga.sql` carrega os CSV (ajuste o caminho no script)
3. `sql/02_analises.sql` roda as consultas

A carga usa tabelas de staging em texto antes de converter. Fiz assim porque
carregar CSV direto em coluna decimal transforma campo vazio em zero, e zero não
é a mesma coisa que nulo.

### 4. Power BI

Abra `powerbi/producao_graos.pbix`. As medidas e a configuração de RLS estão
documentadas em `powerbi/medidas-e-rls.md`.

## Estrutura

```
scripts/ingestao.py             ingestão e tratamento
scripts/analise.py              análise exploratória
sql/00_carga.sql                carga dos CSV para o SQL Server
sql/01_modelo_dimensional.sql   criação das tabelas
sql/02_analises.sql             consultas analíticas
powerbi/producao_graos.pbix     dashboard
powerbi/medidas-e-rls.md        medidas DAX e RLS
dados/bruto                     JSON do SIDRA
dados/processado                CSV gerados pelo pipeline
```

## Limitações

Coisas que sei que ficaram de fora ou poderiam melhorar:

- Comparei rendimento entre regiões sem separar por produto em todas as
  análises. Como o Sul planta mais trigo (rende menos) e o Centro-Oeste planta
  soja e milho, parte da diferença é composição de cultura, não eficiência.
  Coloquei um filtro de produto no dashboard, mas o certo seria sempre analisar
  dentro do mesmo grão.
- Usei só 4 anos. Com uma série mais longa daria para separar tendência de
  variação climática.
- O download dos JSON é manual. O ideal seria o script buscar da API sozinho.
- Não trabalhei com dados de custo, então não dá para falar de rentabilidade,
  só de produtividade física.

## Stack

Python (pandas), SQL Server (T-SQL), Power BI (DAX, Power Query, RLS)
