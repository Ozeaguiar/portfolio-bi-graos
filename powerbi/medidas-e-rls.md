# Medidas DAX e RLS

## Medidas

```dax
Produção (t) = SUM( fato_producao[quantidade_t] )

Área Colhida (ha) = SUM( fato_producao[area_colhida_ha] )

Área Plantada (ha) = SUM( fato_producao[area_plantada_ha] )

Valor da Produção = SUM( fato_producao[valor_producao_mil_reais] ) * 1000
```

### Rendimento: por que não é média simples

```dax
-- ERRADO: média das médias. Dá peso igual a um município de 500 ha e a um de 90.000 ha.
Rendimento Errado = AVERAGE( fato_producao[rendimento_t_ha] )

-- CERTO: razão de somas. Média ponderada pela área, que é o que o agrônomo quer ver.
Rendimento (t/ha) =
DIVIDE(
    [Produção (t)],
    [Área Colhida (ha)]
)
```

Essa distinção é o tipo de coisa que separa quem entende do negócio de quem só
arrasta campo. Vale citar em entrevista.

### Perda de área entre plantio e colheita

```dax
Perda de Área (ha) = [Área Plantada (ha)] - [Área Colhida (ha)]

Perda de Área % =
DIVIDE(
    [Perda de Área (ha)],
    [Área Plantada (ha)]
)
```

### Time intelligence

Requer `dim_tempo` marcada como tabela de data (coluna `data_referencia`).

```dax
Produção Ano Anterior =
CALCULATE(
    [Produção (t)],
    DATEADD( dim_tempo[data_referencia], -1, YEAR )
)

Variação YoY % =
VAR Atual = [Produção (t)]
VAR Anterior = [Produção Ano Anterior]
RETURN DIVIDE( Atual - Anterior, Anterior )
```

### Ranking dinâmico

```dax
Ranking Município =
IF(
    HASONEVALUE( dim_municipio[municipio] ),
    RANKX( ALLSELECTED( dim_municipio[municipio] ), [Produção (t)], , DESC )
)
```

O `HASONEVALUE` evita que a medida retorne número no total geral, onde ranking
não significa nada.

---

## Row Level Security

Simula o cenário real: cada regional enxerga apenas a sua UF.

### RLS estático

Rápido de fazer, não escala. Uma função por UF.

**Modelagem → Gerenciar funções → nova função `Regional_MT`:**

Tabela `dim_municipio`, expressão DAX:

```dax
[uf] = "MT"
```

O filtro entra na **dimensão** e se propaga para a fato pelo relacionamento.
Filtrar direto na fato funciona, mas é mais lento e quebra a lógica do modelo.

### RLS dinâmico

Uma função só, N usuários. É essa que cai em entrevista.

**1. Tabela de segurança** (`dim_acesso`), carregada junto com o modelo:

| email | uf |
|---|---|
| ana@empresa.com | MT |
| bruno@empresa.com | PR |
| bruno@empresa.com | RS |
| diretoria@empresa.com | * |

**2. Relacionamento:** `dim_acesso[uf]` → `dim_municipio[uf]` (um para muitos,
direção única, de `dim_acesso` para `dim_municipio`).

**3. Função `Regional`,** filtro em `dim_acesso`:

```dax
[email] = USERPRINCIPALNAME()
```

O filtro percorre: `dim_acesso` → `dim_municipio` → `fato_producao`.

**4. Diretoria vê tudo.** Duas saídas: uma função separada sem filtro, ou
tratar o coringa na própria expressão:

```dax
VAR Usuario = USERPRINCIPALNAME()
VAR TudoLiberado =
    NOT ISEMPTY(
        FILTER( ALL( dim_acesso ), dim_acesso[email] = Usuario && dim_acesso[uf] = "*" )
    )
RETURN TudoLiberado || dim_acesso[email] = Usuario
```

### Armadilhas que valem citar

- **RLS não vale para quem edita.** Membro, colaborador e admin do workspace
  ignoram RLS. Só viewer é filtrado.
- **`USERPRINCIPALNAME()` no Desktop** devolve o usuário local. Teste com
  "Exibir como" informando o e-mail manualmente.
- **Filtro bidirecional vaza dados.** Se houver relacionamento bidirecional no
  caminho, é preciso marcar "aplicar filtro de segurança nos dois sentidos",
  senão o usuário enxerga linhas que não deveria.
- **A atribuição de usuários à função é feita no Power BI Service**, não no
  Desktop. No Desktop você só cria a função.
- **RLS ≠ OLS.** RLS esconde linhas; Object Level Security esconde a coluna ou
  a tabela inteira.
