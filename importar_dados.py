import csv
import io
import pandas as pd
import re
import requests
import unicodedata
from sqlalchemy import create_engine, text

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

        if any(
            x in texto_linha
            for x in ["AUTOCRAT", "DATASHEET", "NVSCRIPTS", "SCRIPT"]
        ):
            continue

        if any(p in texto_linha for p in palavras_chave):
            linha_cabecalho = idx
            break

    if linha_cabecalho is None:
        linha_cabecalho = 0

    dados_uteis = leitor[linha_cabecalho:]

    cabecalho = dados_uteis[0]
    linhas_dados = dados_uteis[1:]

    df = pd.DataFrame(linhas_dados, columns=cabecalho)
    return df


# 5. Carga e Sanitização
def processar_e_carregar(url_csv, nome_tabela):
    print(f"Baixando e sanitizando: {nome_tabela}...")

    df = baixar_dataframe_limpo(url_csv)

    df.columns = [limpar_nome_coluna(col) for col in df.columns]

    df = df.loc[:, df.columns != "coluna_sem_nome"]
    df = df.loc[:, ~df.columns.duplicated()]

    cols_doc = [c for c in df.columns if "cnpj" in c or "cpf" in c]
    for c in cols_doc:
        df[c] = df[c].apply(limpar_documento)

    cols_valor = [
        c
        for c in df.columns
        if "valor" in c or "custo" in c or "despesas" in c
    ]
    for c in cols_valor:
        df[c] = df[c].apply(limpar_moeda)

    df.to_sql(nome_tabela, con=engine, if_exists="replace", index=False)
    print(f"Sucesso! {len(df)} linhas salvas em '{nome_tabela}'.\n")


# 6. Recriação das Views Automática
def recriar_views(engine):
    print("Recriando Views dependentes do banco...")
    
    query_dim_clientes = """
    CREATE OR REPLACE VIEW public.dim_clientes AS 
    SELECT DISTINCT cod_cliente, cliente, grupo, cnpj
    FROM fato_comercial
    WHERE cod_cliente IS NOT NULL AND cod_cliente <> '';
    """
    
    query_v_fato = """
    CREATE OR REPLACE VIEW public.v_fato_comercial_clean AS 
    SELECT status_comercial, validacao, margem_de_lucro, status_envios, semana, processo, id_treinamento_cliente, cod_cliente, grupo, cliente, cidade, uf, unidade, polo_regional, cnpj, executivo_de_vendas, solicitante, solicitacao_canal, cod_treinamento, ch_formacao, ch_reciclagem, pessoas, procedencia, valor_contrato, valor, pedido_de_compra, folha_de_servico, condicao, valor_total, modalidade, lista_presenca, avaliacao, apresentacao_apostila_avaliacao, modulo, continuidade, processo_associado, inicio_1, termino_1, inicio_2, termino_2, termino_ead, horario, cliente_agendamento, cliente_liberacao_portaria, instrutor_1_agenda, instrutor_1_cpf, instrutor_1, custo_1_instrutor, despesas_1_km, despesas_1_hotel, despesas_1_extras, adiantamento_1_instrutor, instrutor_1_total, negociacao_1_ch, negociacao_1_inicio, negociacao_1_termino, instrutor_2_agenda, instrutor_2_cpf, instrutor_2, custo_2_instrutor, despesas_2_km, despesas_2_hotel, despesas_2_extras, adiantamento_2_instrutor, instrutor_2_total, negociacao_2_ch, negociacao_2_inicio, negociacao_2_termino, link_da_reuniao_online, cancelamento_data, cancelamento_solicitante, cancelamento_canal, cancelamento, observacoes_internas, observacoes_ao_financeiro, observacoes_gerais, id_cliente, listas_de_presenca, avaliacoes, materiais_didaticos, certificados, obs_pos1, obs_pos2, equipamentos, cnpj_2, valor_2, pedido_de_compra_2, folha_de_servico_2, condicao_dias_2, e_mail_nota_fiscal, data_da_1a_venda, procedencia_cadastrada, faturamento_cadastrado, exigencia_para_faturamento, cnpj_cpf, condicao_em_dias_ref, cnpj_cpf_2, condicao_em_dias_2_ref, condicao_dias_bd, instrutor_1_link_msg, instrutor_1_envio_msg, instrutor_2_link_msg, instrutor_2_envio_msg,
    to_date(NULLIF(TRIM(BOTH FROM inicio_1), ''), 'DD/MM/YYYY') AS data_inicio_1,
    to_date(NULLIF(TRIM(BOTH FROM termino_1), ''), 'DD/MM/YYYY') AS data_termino_1,
    COALESCE(NULLIF(TRIM(BOTH FROM ch_formacao), '')::numeric, NULLIF(TRIM(BOTH FROM ch_reciclagem), '')::numeric, 0::numeric) AS ch_realizada_num
    FROM fato_comercial fc;
    """
    
    with engine.begin() as conn:
        conn.execute(text(query_dim_clientes))
        conn.execute(text(query_v_fato))
    print("Views recriadas com sucesso! 🚀")


if __name__ == "__main__":
    planilhas = {
        "dim_instrutores": "https://docs.google.com/spreadsheets/d/1zkfSjlvdgid3D2EZoYKW6BNvMwxhwyGbmFrVQ3jxh0Y/export?format=csv&gid=2064220220",
        "fato_comercial": "https://docs.google.com/spreadsheets/d/1zkfSjlvdgid3D2EZoYKW6BNvMwxhwyGbmFrVQ3jxh0Y/export?format=csv&gid=1723286423",
        "fato_treinamentos": "https://docs.google.com/spreadsheets/d/1IEJVUpt8Z-Bxov6KDfqJ9BRbxZ8-NJ-LHs-D06mhWE4/export?format=csv&gid=392845010", # <-- GID CORRETO AGORA!
    }

    # PASSO A: Deletar as views temporariamente para o banco não dar erro de dependência
    print("Preparando o banco (removendo views antigas)...")
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS public.dim_clientes CASCADE;"))
        conn.execute(text("DROP VIEW IF EXISTS public.v_fato_comercial_clean CASCADE;"))

    # PASSO B: Carregar as 3 planilhas atualizadas
    for tabela, url in planilhas.items():
        try:
            processar_e_carregar(url, tabela)
        except Exception as e:
            print(f"Erro ao processar {tabela}: {e}\n")
            
    # PASSO C: Recriar as views automaticamente com os dados atualizados
    try:
        recriar_views(engine)
    except Exception as e:
        print(f"Erro ao recriar views: {e}")