"""
Ingestão e tratamento da Produção Agrícola Municipal (PAM/IBGE, tabela 1612).

Lê os JSON baixados da API do SIDRA, aplica limpeza e gera as tabelas fato e
dimensão do modelo dimensional.

Uso:
    python scripts/ingestao.py                    # lê tudo em dados/bruto/*.json
    python scripts/ingestao.py --amostra          # dados sintéticos, para testar o pipeline

Como obter os dados: ver README, seção "Como rodar".
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

# Nome da variável no SIDRA -> nome da coluna no modelo.
# O mapeamento é por NOME e não por código: se o IBGE mudar o código, não quebra.
VARIAVEIS = {
    "Área plantada": "area_plantada_ha",
    "Área colhida": "area_colhida_ha",
    "Quantidade produzida": "quantidade_t",
    "Valor da produção": "valor_producao_mil_reais",
}

# Marcadores textuais do IBGE. Não são números.
#   "-"  = zero          "..." = não se aplica
#   ".." = não disponível  "X"  = omitido para não identificar o informante
MARCADORES = {"-", "..", "...", "X", "", " ", "nan"}

# Código IBGE da UF (2 primeiros dígitos do código do município) -> sigla.
UF_POR_CODIGO = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
    41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF",
}


# --------------------------------------------------------------------------
# 1. Leitura
# --------------------------------------------------------------------------
def ler_sidra(pasta: Path) -> pd.DataFrame:
    """
    Lê os JSON da API do SIDRA (formato apisidra.ibge.gov.br).

    O primeiro elemento de cada arquivo é um dicionário de rótulos, não um dado.
    As chaves D1..Dn variam conforme a consulta, então descobrimos os papéis
    pelos rótulos em vez de assumir posição fixa.
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

        # Descobre qual chave D* corresponde a cada dimensão, pelo rótulo.
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
    """Base sintética no formato longo já normalizado, para testar o pipeline."""
    rng = np.random.default_rng(42)
    # prefixos reais do IBGE, para o código sintético gerar UFs diferentes
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
    # sujeira proposital
    idx = df.sample(frac=0.03, random_state=1).index
    df.loc[idx, "V"] = rng.choice(["-", "...", ".."], size=len(idx))
    df = pd.concat([df, df.sample(frac=0.01, random_state=3)], ignore_index=True)
    print(f"[amostra] {len(df):,} registros sintéticos")
    return df


# --------------------------------------------------------------------------
# 2. Limpeza e pivot
# --------------------------------------------------------------------------
def limpar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Decisões (documentadas no README):
      - Marcadores do IBGE viram NaN, nunca zero. Zero é "plantou e não colheu";
        NaN é "não sei". Tratar os dois igual distorce o rendimento.
      - Duplicatas por local+produto+ano+variável são removidas.
      - Só as 4 variáveis do modelo são mantidas; rendimento é medida, não coluna.
      - O nome do município vem como "Sorriso (MT)": a UF é extraída daí.
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
    # dtype "object" (str puro) nas chaves de junção: o dtype "string" do pandas
    # conflita no merge quando o outro lado nasce de uma lista vazia.
    df["local"] = df["local"].astype(object).where(df["local"].notna()).str.strip()
    df["produto"] = df["produto"].astype(object).where(df["produto"].notna()).str.strip()

    # UF vem do código do município, não do nome. Os 2 primeiros dígitos do
    # código IBGE identificam a UF ("1100015" -> 11 -> RO). É estável; o nome
    # muda de formato entre consultas ("Sorriso - MT" ou "Sorriso (MT)").
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
    """Formato longo (uma linha por variável) -> largo (uma linha por evento)."""
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
    rel = (df.isna().mean().mul(100).round(2)
           .rename("pct_nulos").reset_index().rename(columns={"index": "coluna"}))
    print("\n[qualidade] nulos por coluna (%)")
    print(rel.to_string(index=False))
    print(f"[qualidade] área colhida > plantada: {int(df['flag_area_inconsistente'].sum())} registros")
    return rel


# --------------------------------------------------------------------------
# 3. Modelagem dimensional
# --------------------------------------------------------------------------
REGIOES = {
    "N": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
    "NE": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "CO": ["DF", "GO", "MT", "MS"],
    "SE": ["ES", "MG", "RJ", "SP"],
    "S": ["PR", "RS", "SC"],
}
UF_REGIAO = {uf: reg for reg, ufs in REGIOES.items() for uf in ufs}


def construir_dimensoes(df: pd.DataFrame):
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
    """Granularidade: uma linha por município, produto e ano-safra."""
    fato = (df.rename(columns={"cod_local": "cod_municipio"})
            .merge(dim_mun[["sk_municipio", "cod_municipio"]], on="cod_municipio", how="left")
            .merge(dim_prod[["sk_produto", "produto"]], on="produto", how="left")
            .merge(dim_tempo[["sk_tempo", "ano"]], on="ano", how="left"))

    fato["perda_area_ha"] = (fato["area_plantada_ha"] - fato["area_colhida_ha"]).round(1)

    colunas = ["sk_municipio", "sk_produto", "sk_tempo",
               "area_plantada_ha", "area_colhida_ha", "quantidade_t",
               "valor_producao_mil_reais", "perda_area_ha", "flag_area_inconsistente"]
    fato = fato[colunas]

    orfas = int(fato[["sk_municipio", "sk_produto", "sk_tempo"]].isna().any(axis=1).sum())
    if orfas:
        raise ValueError(f"{orfas} linhas da fato sem correspondência nas dimensões")

    print(f"[fato] {len(fato):,} linhas, integridade referencial OK")
    return fato


# --------------------------------------------------------------------------
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
