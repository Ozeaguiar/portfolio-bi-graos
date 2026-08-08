"""
Análise exploratória sobre o modelo dimensional.

Gera os achados numéricos que vão para a seção "Resultados" do README —
a parte que separa análise de exercício técnico.

Uso:
    python scripts/analise.py
    python scripts/analise.py --markdown > docs/resultados.md
"""

import argparse
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PROC = RAIZ / "dados" / "processado"


def carregar() -> pd.DataFrame:
    fato = pd.read_csv(PROC / "fato_producao.csv")
    mun = pd.read_csv(PROC / "dim_municipio.csv")
    prod = pd.read_csv(PROC / "dim_produto.csv")
    tempo = pd.read_csv(PROC / "dim_tempo.csv")
    return (fato.merge(mun, on="sk_municipio")
                .merge(prod, on="sk_produto")
                .merge(tempo, on="sk_tempo"))


def fmt(n, casas=0):
    if pd.isna(n):
        return "n/d"
    return f"{n:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


# --------------------------------------------------------------------------
def concentracao(df: pd.DataFrame) -> str:
    """Quanto do total nacional está em poucos municípios."""
    ultimo = int(df["ano"].max())
    base = df[df["ano"] == ultimo].groupby("municipio", as_index=False)["quantidade_t"].sum()
    base = base.sort_values("quantidade_t", ascending=False)
    total = base["quantidade_t"].sum()
    top50 = base.head(50)["quantidade_t"].sum()
    n_para_metade = int((base["quantidade_t"].cumsum() <= total / 2).sum()) + 1
    return (
        f"Em {ultimo}, os 50 maiores municípios respondem por "
        f"**{top50 / total:.1%}** da produção nacional de grãos da amostra. "
        f"Metade de todo o volume sai de apenas **{n_para_metade} municípios**, "
        f"de um universo de {fmt(base['municipio'].nunique())}."
    )


def rendimento_por_uf(df: pd.DataFrame, participacao_minima: float = 0.01) -> str:
    """
    Rendimento é razão de somas, nunca média de médias.

    Filtro de relevância: só entram UFs com pelo menos 1% da produção nacional.
    Sem esse corte, o ranking é dominado por estados que quase não plantam grão,
    onde uma variação absoluta pequena vira percentual enorme. Extremo de
    percentual sobre base pequena é ruído, não sinal.
    """
    primeiro, ultimo = int(df["ano"].min()), int(df["ano"].max())

    total_nacional = df[df["ano"] == ultimo]["quantidade_t"].sum()
    volume_uf = df[df["ano"] == ultimo].groupby("uf")["quantidade_t"].sum()
    relevantes = volume_uf[volume_uf / total_nacional >= participacao_minima].index
    if len(relevantes) < 2:
        raise ValueError("poucas UFs acima do corte de relevância")

    g = (df[df["ano"].isin([primeiro, ultimo]) & df["uf"].isin(relevantes)]
         .groupby(["uf", "ano"], as_index=False)[["quantidade_t", "area_colhida_ha"]].sum())
    g["rend"] = g["quantidade_t"] / g["area_colhida_ha"]
    piv = g.pivot(index="uf", columns="ano", values="rend").dropna()
    piv = piv[piv[primeiro] > 0]
    piv["var_pct"] = (piv[ultimo] / piv[primeiro] - 1) * 100
    piv = piv.sort_values("var_pct", ascending=False)
    melhor, pior = piv.index[0], piv.index[-1]

    return (
        f"Entre {primeiro} e {ultimo}, considerando apenas as **{len(relevantes)} UFs "
        f"com pelo menos 1% da produção nacional**, o rendimento médio (t/ha) variou "
        f"**{piv.loc[melhor, 'var_pct']:+.1f}%** em **{melhor}** e "
        f"**{piv.loc[pior, 'var_pct']:+.1f}%** em **{pior}**. "
        f"O corte de relevância é necessário: sem ele, o ranking é ocupado por estados "
        f"que quase não plantam grão, onde uma variação absoluta mínima vira percentual enorme."
    )


def perda_de_area(df: pd.DataFrame, area_minima: float = 100_000) -> str:
    """
    Perda entre plantio e colheita, por UF e produto.

    No agregado nacional a perda é diluída e não diz nada. O sinal aparece ao
    abrir por UF e produto — e novamente com corte de relevância (área mínima),
    pela mesma razão do rendimento.
    """
    g = (df.groupby(["uf", "produto", "ano"], as_index=False)[["area_plantada_ha", "area_colhida_ha"]].sum())
    g = g[g["area_plantada_ha"] >= area_minima]
    g["perda_pct"] = (1 - g["area_colhida_ha"] / g["area_plantada_ha"]) * 100
    if g.empty:
        raise ValueError("nenhum recorte acima da área mínima")

    nacional = df.groupby("ano", as_index=False)[["area_plantada_ha", "area_colhida_ha"]].sum()
    media_nacional = (1 - nacional["area_colhida_ha"].sum() / nacional["area_plantada_ha"].sum()) * 100

    pior = g.sort_values("perda_pct", ascending=False).iloc[0]
    return (
        f"No agregado nacional a perda entre área plantada e colhida é de apenas "
        f"**{media_nacional:.1f}%**, número que esconde o problema. Abrindo por UF e produto "
        f"(com no mínimo {fmt(area_minima)} ha plantados), o pior caso é "
        f"**{pior['produto']} em {pior['uf']}** em {int(pior['ano'])}, com "
        f"**{pior['perda_pct']:.1f}%** de área perdida. Média nacional dilui evento localizado."
    )


def valor_por_tonelada(df: pd.DataFrame) -> str:
    """Preço implícito: valor da produção dividido pelo volume."""
    g = (df.groupby("ano", as_index=False)[["valor_producao_mil_reais", "quantidade_t"]].sum())
    g["r_por_t"] = g["valor_producao_mil_reais"] * 1000 / g["quantidade_t"]
    primeiro, ultimo = g.iloc[0], g.iloc[-1]
    var = (ultimo["r_por_t"] / primeiro["r_por_t"] - 1) * 100
    return (
        f"O valor implícito por tonelada saiu de **R$ {fmt(primeiro['r_por_t'])}** em "
        f"{int(primeiro['ano'])} para **R$ {fmt(ultimo['r_por_t'])}** em {int(ultimo['ano'])} "
        f"(**{var:+.1f}%**), sem correção pela inflação."
    )


def cobertura(df: pd.DataFrame) -> str:
    nulos = df["quantidade_t"].isna().mean() * 100
    return (
        f"Base final: **{fmt(len(df))} linhas** na fato, cobrindo "
        f"{fmt(df['municipio'].nunique())} municípios, {df['produto'].nunique()} produtos e "
        f"{df['ano'].nunique()} anos. **{nulos:.1f}%** dos registros de quantidade vêm sem valor "
        f"informado pelo IBGE e foram mantidos como nulos, não como zero."
    )


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true", help="saída pronta para colar no README")
    args = ap.parse_args()

    df = carregar()
    achados = []
    for fn in (cobertura, concentracao, rendimento_por_uf, perda_de_area, valor_por_tonelada):
        try:
            achados.append(fn(df))
        except Exception as e:  # base pequena demais para o recorte
            print(f"[aviso] {fn.__name__} não pôde ser calculado: {e}")

    if args.markdown:
        print("## Resultados\n")
        for a in achados:
            print(f"- {a}\n")
    else:
        print("\n=== ACHADOS ===\n")
        for i, a in enumerate(achados, 1):
            print(f"{i}. {a}\n")


if __name__ == "__main__":
    main()
