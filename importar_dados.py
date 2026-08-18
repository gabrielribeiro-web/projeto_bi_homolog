import csv
import io
import pandas as pd
import re
import requests
import unicodedata
from sqlalchemy import create_engine

# 1. Conexão com Supabase (SSL ativo)
DATABASE_URL = "postgresql://postgres.dychhsqpvqtwaslujbir:Acess%40bi2026@aws-0-sa-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
engine = create_engine(DATABASE_URL)


# 2. Higienização de Nomes de Colunas
def limpar_nome_coluna(coluna):
    nfkd = unicodedata.normalize("NFKD", str(coluna))
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    texto = sem_acento.lower().strip()
    texto = re.sub(r"[\s\/\-\.]+", "_", texto)
    texto = re.sub(r"[^a-z0-9_]", "", texto)
    col_limpa = re.sub(r"_+", "_", texto).strip("_")
    return col_limpa if col_limpa else "coluna_sem_nome"


# 3. Higienização de Conteúdo
def limpar_documento(val):
    if pd.isna(val) or val is None:
        return None
    numeros = re.sub(r"\D", "", str(val))
    return numeros if numeros else None


def limpar_moeda(val):
    if pd.isna(val) or val is None:
        return 0.0
    texto = (
        str(val)
        .replace("R$", "")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
    )
    try:
        return float(texto)
    except ValueError:
        return 0.0


# 4. Leitor Robusto via módulo csv do Python
def baixar_dataframe_limpo(url_csv):
    url_limpa = url_csv.strip("[]() ")
    response = requests.get(url_limpa)
    response.encoding = "utf-8"

    # Processa o texto com o leitor oficial de CSV
    leitor = list(csv.reader(io.StringIO(response.text)))

    linha_cabecalho = None
    palavras_chave = [
        "STATUS COMERCIAL",
        "STATUS FOLLOW-UP",
        "PROCESSO",
        "INSTRUTOR",
        "CÓD. CLIENTE",
        "COD. CLIENTE",
        "CLIENTE",
        "NOME",
        "CPF",
    ]

    for idx, linha in enumerate(leitor):
        texto_linha = " ".join(linha).upper()

        # Descarta linhas técnicas do AutoCrat/scripts
        if any(
            x in texto_linha
            for x in ["AUTOCRAT", "DATASHEET", "NVSCRIPTS", "SCRIPT"]
        ):
            continue

        # Localiza o cabeçalho real pelas palavras-chave
        if any(p in texto_linha for p in palavras_chave):
            linha_cabecalho = idx
            break

    if linha_cabecalho is None:
        linha_cabecalho = 0

    dados_uteis = leitor[linha_cabecalho:]

    # Monta o DataFrame garantindo alinhar todas as colunas
    cabecalho = dados_uteis[0]
    linhas_dados = dados_uteis[1:]

    df = pd.DataFrame(linhas_dados, columns=cabecalho)
    return df


# 5. Carga e Sanitização
def processar_e_carregar(url_csv, nome_tabela):
    print(f"Baixando e sanitizando: {nome_tabela}...")

    df = baixar_dataframe_limpo(url_csv)

    # Aplica limpeza nos cabeçalhos
    df.columns = [limpar_nome_coluna(col) for col in df.columns]

    # Elimina colunas totalmente vazias ou sem nome válido
    df = df.loc[:, df.columns != "coluna_sem_nome"]
    df = df.loc[:, ~df.columns.duplicated()]

    # Sanitização de CPFs / CNPJs
    cols_doc = [c for c in df.columns if "cnpj" in c or "cpf" in c]
    for c in cols_doc:
        df[c] = df[c].apply(limpar_documento)

    # Sanitização de Moedas
    cols_valor = [
        c
        for c in df.columns
        if "valor" in c or "custo" in c or "despesas" in c
    ]
    for c in cols_valor:
        df[c] = df[c].apply(limpar_moeda)

    # Gravação no Supabase
    df.to_sql(nome_tabela, con=engine, if_exists="replace", index=False)
    print(
        f"Sucesso! {len(df)} linhas e {len(df.columns)} colunas salvas em '{nome_tabela}'.\n"
    )


if __name__ == "__main__":
    planilhas = {
        "dim_instrutores": "https://docs.google.com/spreadsheets/d/1tCMAPU7pDdttOceiiBAA2CptbPe6QoAfyrmuhcrQRRY/export?format=csv&gid=2064220220",
        "fato_comercial": "https://docs.google.com/spreadsheets/d/1tCMAPU7pDdttOceiiBAA2CptbPe6QoAfyrmuhcrQRRY/export?format=csv&gid=1723286423",
        "fato_treinamentos": "https://docs.google.com/spreadsheets/d/1KDMNd0D19BJo5diZneNClCTKlC_EcfIez2KazDWG9kY/export?format=csv&gid=392845010",
    }

    for tabela, url in planilhas.items():
        try:
            processar_e_carregar(url, tabela)
        except Exception as e:
            print(f"Erro ao processar {tabela}: {e}\n")