"""
Script de ingestao dos dados do IBGE (PAM, tabela 1612).

Le os JSON que eu baixei do SIDRA e monta os CSV da fato e das dimensoes.

Rodar:
    python scripts/ingestao.py                    # usa os json de dados/bruto
    python scripts/ingestao.py --amostra          # dados fake, so pra testar

Onde baixar os arquivos esta explicado no README.
Fonte: https://sidra.ibge.gov.br/tabela/1612
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
BRUTO = RAIZ / "dados" / "bruto"
SAIDA = RAIZ / "dados" / "processado"

# de/para do nome da variavel no SIDRA pro nome da coluna que eu uso aqui.
# fiz pelo nome porque o codigo da variavel ja mudou uma vez e quebrou tudo.
VARIAVEIS = {
    "Área plantada": "area_plantada_ha",
    "Área colhida": "area_colhida_ha",
    "Quantidade produzida": "quantidade_t",
    "Valor da produção": "valor_producao_mil_reais",
}

# as vezes o IBGE manda texto no lugar do numero:
#   "-" = zero, ".." = nao disponivel, "..." = nao se aplica, "X" = sigilo
MARCADORES = {"-", "..", "...", "X", "", " ", "nan"}

# os 2 primeiros digitos do codigo do municipio sao a UF
UF_POR_CODIGO = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}


# ----- leitura dos arquivos -----
def ler_sidra(pasta: Path) -> pd.DataFrame:
    """
    Le os json da API do SIDRA.

    A primeira posicao do arquivo nao e dado, e um dicionario com os nomes das
    colunas. E as chaves D1, D2... mudam conforme a consulta, entao procuro
    pelo rotulo em vez de fixar a posicao.
    """
    arquivos = sorted(pasta.glob("*.json"))
    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum .json em {pasta}. Veja o README, seção 'Como rodar'."
        )

    partes = []
    for arq in arquivos:
        with open(arq, encoding="utf-8") as f:
            bruto = json.load(f)

        rotulos, registros = bruto[0], bruto[1:]
        if not registros:
            print(f"[aviso] {arq.name} sem registros, ignorado")
            continue

        df = pd.DataFrame(registros)

        # acha a chave D* certa olhando o rotulo
        def chave(trecho: str, sufixo: str) -> str | None:
            for k, v in rotulos.items():
                if k.startswith("D") and k.endswith(sufixo) and trecho.lower() in v.lower():
                    return k
            return None

        mapa = {
            chave("município", "C") or chave("unidade da federação", "C"): "cod_local",
            chave("município", "N") or chave("unidade da federação", "N"): "local",
            chave("variável", "N"): "variavel",
            chave("ano", "C"): "ano",
            chave("produto", "N"): "produto",
        }
        mapa = {k: v for k, v in mapa.items() if k is not None}
        faltando = {"cod_local", "local", "variavel", "ano", "produto"} - set(mapa.values())
        if faltando:
            raise ValueError(f"{arq.name}: não identifiquei as dimensões {faltando}")

        df = df.rename(columns=mapa)[list(mapa.values()) + ["V"]]
        partes.append(df)
        print(f"[leitura] {arq.name}: {len(df):,} registros")

    df = pd.concat(partes, ignore_index=True)
    print(f"[leitura] total: {len(df):,} registros brutos")
    return df


def gerar_amostra(n_locais: int = 60, anos=range(2018, 2024)) -> pd.DataFrame:
    """Gera uma base fake pra eu testar o pipeline sem depender dos json."""
    rng = np.random.default_rng(42)
    # uso prefixo de UF real pro codigo fake ficar parecido com o do IBGE
    prefixos = {51: "MT", 41: "PR", 43: "RS", 52: "GO", 50: "MS", 29: "BA"}
    codigos_uf = list(prefixos)
    graos = ["Soja (em grão)", "Milho (em grão)", "Trigo (em grão)"]
    linhas = []
    for i in range(n_locais):
        cod_uf = codigos_uf[i % len(codigos_uf)]
        uf = prefixos[cod_uf]
        cod = cod_uf * 100_000 + (i + 1) * 13
        nome = f"Município {i + 1:02d} - {uf}"
        for ano in anos:
            for produto in graos:
                if rng.random() < 0.25:
                    continue
                plantada = float(rng.integers(500, 90_000))
                colhida = plantada * float(rng.uniform(0.88, 1.0))
                qtd = colhida * float(rng.uniform(2.2, 4.0))
                valor = qtd * float(rng.uniform(1.1, 2.4))
                for var, val in [
                    ("Área plantada", plantada), ("Área colhida", colhida),
                    ("Quantidade produzida", qtd), ("Valor da produção", valor),
                ]:
                    linhas.append({"cod_local": str(cod), "local": nome, "variavel": var,
                                   "ano": str(ano), "produto": produto, "V": str(round(val))})
    df = pd.DataFrame(linhas)
    # sujo uns registros de proposito pra ver se a limpeza pega
    idx = df.sample(frac=0.03, random_state=1).index
    df.loc[idx, "V"] = rng.choice(["-", "...", ".."], size=len(idx))
    df = pd.concat([df, df.sample(frac=0.01, random_state=3)], ignore_index=True)
    print(f"[amostra] {len(df):,} registros sintéticos")
    return df


# ----- limpeza e pivot -----
def limpar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpeza geral antes de montar o modelo.

    O que eu faco aqui:
      - marcador de texto do IBGE vira NaN. Nao converti pra zero porque zero
        quer dizer que plantou e nao colheu, e ai o rendimento sairia errado
        nos municipios que so nao tem informacao.
      - tiro duplicata de local + produto + ano + variavel.
      - guardo so as 4 variaveis do modelo. Rendimento eu calculo no Power BI.
    """
    antes = len(df)

    df["V"] = df["V"].astype("string").str.strip()
    df["valor"] = pd.to_numeric(df["V"].where(~df["V"].isin(MARCADORES)), errors="coerce")

    df["variavel_norm"] = df["variavel"].astype("string").str.strip()
    for rotulo, coluna in VARIAVEIS.items():
        df.loc[df["variavel_norm"].str.startswith(rotulo, na=False), "campo"] = coluna
    df = df.dropna(subset=["campo"])

    df["cod_local"] = pd.to_numeric(df["cod_local"], errors="coerce").astype("Int64")
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce").astype("Int64")
    # tive que forcar object aqui. Com o dtype "string" do pandas o merge la
    # embaixo dava erro quando um dos lados vinha de uma lista vazia.
    df["local"] = df["local"].astype(object).where(df["local"].notna()).str.strip()
    df["produto"] = df["produto"].astype(object).where(df["produto"].notna()).str.strip()

    # pego a UF pelo codigo do municipio ("1100015" -> 11 -> RO). Tentei pelo
    # nome antes, mas o formato muda ("Sorriso - MT", "Sorriso (MT)") e quebrava.
    df["uf"] = (df["cod_local"] // 100_000).map(UF_POR_CODIGO).astype(object)
    df["municipio"] = df["local"].str.replace(r"\s*[-(]\s*[A-Z]{2}\)?$", "", regex=True)

    df = df.dropna(subset=["cod_local", "ano", "produto"])
    df = df.drop_duplicates(subset=["cod_local", "ano", "produto", "campo"], keep="first")

    print(f"[limpeza] {antes:,} -> {len(df):,} registros ({antes - len(df):,} descartados)")
    print(f"[limpeza] variáveis encontradas: {sorted(df['campo'].unique())}")
    print(f"[limpeza] produtos encontrados: {sorted(df['produto'].unique())}")
    if df.empty:
        raise ValueError(
            "Nenhum registro sobrou após a limpeza. Verifique se o JSON tem as "
            "variáveis esperadas (área plantada, área colhida, quantidade, valor)."
        )
    return df


def pivotar(df: pd.DataFrame) -> pd.DataFrame:
    """Passa de formato longo (uma linha por variavel) pra largo."""
    largo = (
        df.pivot_table(
            index=["cod_local", "municipio", "uf", "ano", "produto"],
            columns="campo", values="valor", aggfunc="first",
        )
        .reset_index()
        .rename_axis(columns=None)
    )
    for coluna in VARIAVEIS.values():
        if coluna not in largo.columns:
            largo[coluna] = np.nan

    if largo.empty:
        raise ValueError(
            "O pivot resultou em zero linhas. Causa mais provável: alguma chave do "
            "índice (município, uf, ano ou produto) está nula — pivot_table descarta "
            "essas linhas. Confira a saída de [limpeza] acima."
        )

    largo["flag_area_inconsistente"] = largo["area_colhida_ha"] > largo["area_plantada_ha"]
    print(f"[pivot] {len(largo):,} linhas (município x produto x ano)")
    return largo


def relatorio_qualidade(df: pd.DataFrame) -> pd.DataFrame:
    """Conta os nulos por coluna, so pra eu ter ideia de como esta a base."""
    rel = (df.isna().mean().mul(100).round(2)
           .rename("pct_nulos").reset_index().rename(columns={"index": "coluna"}))
    print("\n[qualidade] nulos por coluna (%)")
    print(rel.to_string(index=False))
    print(f"[qualidade] área colhida > plantada: {int(df['flag_area_inconsistente'].sum())} registros")
    return rel


# ----- dimensoes e fato -----
REGIOES = {
    "N": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
    "NE": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "CO": ["DF", "GO", "MT", "MS"],
    "SE": ["ES", "MG", "RJ", "SP"],
    "S": ["PR", "RS", "SC"],
}
UF_REGIAO = {uf: reg for reg, ufs in REGIOES.items() for uf in ufs}


def construir_dimensoes(df: pd.DataFrame):
    """Monta as tres dimensoes. A sk e so o indice + 1 mesmo."""
    dim_mun = (df[["cod_local", "municipio", "uf"]].drop_duplicates()
               .sort_values("cod_local").reset_index(drop=True)
               .rename(columns={"cod_local": "cod_municipio"}))
    dim_mun.insert(0, "sk_municipio", dim_mun.index + 1)
    dim_mun["regiao"] = dim_mun["uf"].map(UF_REGIAO)

    produtos = sorted(df["produto"].dropna().unique())
    if not produtos:
        raise ValueError("Nenhum produto identificado no JSON. Confira o código c81 da consulta.")
    dim_prod = pd.DataFrame({"produto": pd.Series(produtos, dtype=object)})
    dim_prod.insert(0, "sk_produto", dim_prod.index + 1)
    dim_prod["grupo"] = "Grãos"

    dim_tempo = pd.DataFrame({"ano": sorted(df["ano"].dropna().unique())})
    dim_tempo.insert(0, "sk_tempo", dim_tempo.index + 1)
    dim_tempo["decada"] = (dim_tempo["ano"] // 10 * 10).astype(int)
    dim_tempo["data_referencia"] = pd.to_datetime(dim_tempo["ano"].astype(str) + "-12-31")

    return dim_mun, dim_prod, dim_tempo


def construir_fato(df, dim_mun, dim_prod, dim_tempo) -> pd.DataFrame:
    """Uma linha por municipio, produto e ano."""
    fato = (df.rename(columns={"cod_local": "cod_municipio"})
            .merge(dim_mun[["sk_municipio", "cod_municipio"]], on="cod_municipio", how="left")
            .merge(dim_prod[["sk_produto", "produto"]], on="produto", how="left")
            .merge(dim_tempo[["sk_tempo", "ano"]], on="ano", how="left"))

    fato["perda_area_ha"] = (fato["area_plantada_ha"] - fato["area_colhida_ha"]).round(1)

    colunas = ["sk_municipio", "sk_produto", "sk_tempo",
               "area_plantada_ha", "area_colhida_ha", "quantidade_t",
               "valor_producao_mil_reais", "perda_area_ha", "flag_area_inconsistente"]
    fato = fato[colunas]

    # confere se sobrou linha sem sk. Se sobrar e porque algum merge nao pegou.
    orfas = int(fato[["sk_municipio", "sk_produto", "sk_tempo"]].isna().any(axis=1).sum())
    if orfas:
        raise ValueError(f"{orfas} linhas da fato sem correspondência nas dimensões")

    print(f"[fato] {len(fato):,} linhas, integridade referencial OK")
    return fato


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--amostra", action="store_true", help="usar dados sintéticos")
    ap.add_argument("--bruto", type=Path, default=BRUTO, help="pasta com os .json do SIDRA")
    args = ap.parse_args()

    df = gerar_amostra() if args.amostra else ler_sidra(args.bruto)
    df = limpar(df)
    largo = pivotar(df)
    rel = relatorio_qualidade(largo)

    dim_mun, dim_prod, dim_tempo = construir_dimensoes(largo)
    fato = construir_fato(largo, dim_mun, dim_prod, dim_tempo)

    SAIDA.mkdir(parents=True, exist_ok=True)
    dim_mun.to_csv(SAIDA / "dim_municipio.csv", index=False)
    dim_prod.to_csv(SAIDA / "dim_produto.csv", index=False)
    dim_tempo.to_csv(SAIDA / "dim_tempo.csv", index=False)
    fato.to_csv(SAIDA / "fato_producao.csv", index=False)
    rel.to_csv(SAIDA / "relatorio_qualidade.csv", index=False)

    print(f"\n[ok] gravado em {SAIDA}")
    print(f"     dim_municipio {len(dim_mun):,} | dim_produto {len(dim_prod):,} "
          f"| dim_tempo {len(dim_tempo):,} | fato_producao {len(fato):,}")


if __name__ == "__main__":
    main()
