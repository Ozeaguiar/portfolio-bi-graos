# Especificação do dashboard

Três páginas. A regra que vale para todas: **cada visual responde a uma pergunta.**
Se você não consegue escrever a pergunta acima do gráfico, o gráfico não entra.

---

## Página 1 — Visão geral

**Pergunta:** onde está a produção e como ela evoluiu?

| Elemento | Visual | Detalhe |
|---|---|---|
| Cartões (4) | KPI | Produção (t), Área Colhida (ha), Rendimento (t/ha), Valor da Produção |
| Evolução anual | Linhas | Eixo: `dim_tempo[ano]`. Série: Produção (t). Linha secundária: Rendimento (t/ha) |
| Produção por UF | Mapa ou barras | Barras ordenadas são mais legíveis que mapa. Use mapa só se acrescentar informação |
| Mix por produto | Barras empilhadas 100% | Participação de cada grão ao longo dos anos |
| Filtros | Segmentação | Ano, Produto, UF |

**Cuidado:** não coloque o rendimento no mesmo eixo do volume. Escalas diferentes
em eixo único é o erro mais comum de dashboard júnior.

---

## Página 2 — Produtividade

**Pergunta:** crescimento vem de mais área ou de mais rendimento por hectare?

Essa é a página que demonstra raciocínio analítico, não habilidade de ferramenta.

| Elemento | Visual | Detalhe |
|---|---|---|
| Área x Rendimento | Dispersão | Eixo X: área colhida. Eixo Y: rendimento. Bolha: município. Tamanho: produção |
| Decomposição do crescimento | Cascata | Quanto da variação vem de área e quanto vem de rendimento |
| Ranking de municípios | Tabela | Com a medida `Ranking Município` e barras de dados |
| Variação YoY | Matriz | Linhas: UF. Colunas: ano. Valor: `Variação YoY %` com formatação condicional |

---

## Página 3 — Qualidade dos dados

**Pergunta:** dá para confiar nesses números?

Quase ninguém faz essa página, e é justamente por isso que ela chama atenção.
Mostra que você pensa como analista responsável pelo dado, não como quem só recebe.

| Elemento | Visual | Detalhe |
|---|---|---|
| Cobertura | Cartão | % de registros com quantidade informada |
| Nulos por ano e produto | Matriz | Onde a base tem buraco |
| Inconsistências | Tabela | Registros com `flag_area_inconsistente = Verdadeiro` |
| Nota metodológica | Caixa de texto | Marcadores do IBGE, e por que `-` virou nulo e não zero |

---

## Row Level Security

Configure a função **`Regional`** conforme `medidas-e-rls.md` e deixe evidência
no README: um print do "Exibir como" filtrando por uma UF.

RLS é item de vaga que quase nenhum candidato júnior demonstra. Ter o print vale
mais do que escrever "conhecimento em RLS" na lista de skills.

---

## Antes de publicar

- [ ] Nenhum visual sem título em linguagem de negócio
- [ ] Nada de "Soma de quantidade_t" — renomeie tudo
- [ ] Formatação numérica com separador de milhar e casas decimais coerentes
- [ ] Tooltip configurado nos visuais principais
- [ ] Paleta consistente, no máximo 3 cores + neutros
- [ ] Tempo de carregamento aceitável com a base completa
- [ ] Os números batem com o resultado de `sql/02_analises.sql`

O último item é o mais importante. **Validação cruzada é o que transforma um
dashboard bonito em um dashboard confiável** — e é exatamente o que perguntam
em entrevista: "como você sabia que estava certo?"
