import csv
import io
import re
import unicodedata
import numpy as np
import pandas as pd
import requests
from sqlalchemy import create_engine, text
from database import get_engine

engine = get_engine()



def limpar_nome_coluna(coluna):
    nfkd = unicodedata.normalize("NFKD", str(coluna))
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    texto = sem_acento.lower().strip()
    texto = re.sub(r"[\s\/\-\.]+", "_", texto)
    texto = re.sub(r"[^a-z0-9_]", "", texto)
    col_limpa = re.sub(r"_+", "_", texto).strip("_")
    return col_limpa if col_limpa else "coluna_sem_nome"


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
        "PEDIDO",
        "STATUS PEDIDO",
        "EAD",
        "PRESENCIAL",
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

    return pd.DataFrame(linhas_dados, columns=cabecalho)


def processar_e_carregar(url_csv, nome_tabela):
    print(f"Baixando e sanitizando: {nome_tabela}...")

    df = baixar_dataframe_limpo(url_csv)
    df.columns = [limpar_nome_coluna(col) for col in df.columns]

    df = df.loc[:, df.columns != "coluna_sem_nome"]
    df = df.loc[:, ~df.columns.duplicated()]

    df = df.dropna(how="all")

    coluna_id = None
    if "processo" in df.columns:
        coluna_id = "processo"
    elif "cod_cliente" in df.columns:
        coluna_id = "cod_cliente"

    if coluna_id:
        df[coluna_id] = df[coluna_id].replace(r"^\s*$", np.nan, regex=True)
        df = df.dropna(subset=[coluna_id])

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


def recriar_views(engine):
    print("Recriando Views e Views Materializadas dependentes do banco...")

    # 1. VIEW COMERCIAL LIMPA (Calcula data_termino_efetiva priorizando Término 2)
    query_v_fato = """
    CREATE OR REPLACE VIEW public.v_fato_comercial_clean AS 
    SELECT 
        fc.*,
        to_date(NULLIF(TRIM(BOTH FROM inicio_1), ''), 'DD/MM/YYYY') AS data_inicio_1,
        to_date(NULLIF(TRIM(BOTH FROM termino_1), ''), 'DD/MM/YYYY') AS data_termino_1,
        to_date(NULLIF(TRIM(BOTH FROM inicio_2), ''), 'DD/MM/YYYY') AS data_inicio_2,
        to_date(NULLIF(TRIM(BOTH FROM termino_2), ''), 'DD/MM/YYYY') AS data_termino_2,
        
        -- DATA DE TÉRMINO EFETIVA: Pega o Término 2 se existir; senão, o Término 1
        COALESCE(
            to_date(NULLIF(TRIM(BOTH FROM termino_2), ''), 'DD/MM/YYYY'),
            to_date(NULLIF(TRIM(BOTH FROM termino_1), ''), 'DD/MM/YYYY')
        ) AS data_termino_efetiva,

        COALESCE(NULLIF(TRIM(BOTH FROM ch_formacao), '')::numeric, NULLIF(TRIM(BOTH FROM ch_reciclagem), '')::numeric, 0::numeric) AS ch_realizada_num,
        inicio_1 AS inicio_str,
        termino_ead AS termino_ead_str,
        instrutor_1 AS instrutor,
        COALESCE(fc.valor_total, 0) AS valor_presencial_calculado
    FROM fato_comercial fc;
    """

    # 2. VIEW MATERIALIZADA COMERCIAL
    query_mv_comercial = """
    DROP MATERIALIZED VIEW IF EXISTS public.mv_fato_comercial_tratada CASCADE;
    CREATE MATERIALIZED VIEW public.mv_fato_comercial_tratada AS
    SELECT 
        *,
        valor_presencial_calculado AS valor_turma,
        ch_realizada_num AS carga_horaria,
        data_inicio_1 AS dt_inicio_1,
        data_termino_efetiva AS dt_termino_1,
        data_inicio_1 AS dt_inicio_presencial,
        data_termino_efetiva AS dt_termino_presencial
    FROM public.v_fato_comercial_clean;
    """

    # 3. MOTOR DE FATURAMENTO, SLA E REGRAS DE AÇÃO DETALHADA
    query_vw_motor_faturamento = """
    CREATE OR REPLACE VIEW public.vw_motor_faturamento AS
    SELECT 
        c.processo AS id_processo,
        c.grupo,
        c.cliente,
        c.unidade,
        c.modalidade,
        c.valor_total,
        c.validacao,
        c.status_comercial,
        cli.faturamento AS tipo_faturamento,
        f.valor AS saldo_oc,
        
        -- DATA ESTIMADA DE ENVIO DA MEDIÇÃO (ATÉ DIA 10 DO MÊS SEGUINTE AO TÉRMINO EFETIVO)
        CASE 
            WHEN cli.faturamento = 'MEDIÇÃO' 
                THEN (DATE_TRUNC('month', c.data_termino_efetiva) + INTERVAL '1 month + 9 days')::date
            ELSE c.data_termino_efetiva
        END AS data_envio_estimada,

        -- MOTOR 1: SLA DE MEDIÇÃO E APROVAÇÃO (TÍTULOS CLAROS)
        CASE 
            WHEN UPPER(c.validacao) IN ('CANCELADO', 'REAGENDADO') OR UPPER(c.status_comercial) IN ('CANCELADO', 'REAGENDADO')
                THEN '⚪ Cancelado / Reagendado'
            
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H')
                 OR NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NOT NULL 
                 OR NULLIF(TRIM(BOTH FROM f.data_pagamento), '') IS NOT NULL 
                THEN '✅ Liberado (Fora do SLA)'

            WHEN cli.faturamento = 'MEDIÇÃO' THEN
                CASE 
                    WHEN DATE_TRUNC('month', CURRENT_DATE) = DATE_TRUNC('month', c.data_termino_efetiva) 
                        THEN '⚪ Turmas do Mês Vigente'
                    
                    WHEN DATE_TRUNC('month', CURRENT_DATE) = DATE_TRUNC('month', c.data_termino_efetiva + INTERVAL '1 month') THEN
                        CASE 
                            WHEN EXTRACT(DAY FROM CURRENT_DATE) <= 10 
                                THEN '🟢 Em Compilação Interna (Até dia 10)'
                            ELSE '🟡 Em Análise no Cliente (No Prazo)'
                        END
                    
                    WHEN DATE_TRUNC('month', CURRENT_DATE) >= DATE_TRUNC('month', c.data_termino_efetiva + INTERVAL '2 month') 
                        THEN '🔴 Medição Atrasada no Cliente'
                END
            
            WHEN CURRENT_DATE > c.data_termino_efetiva AND c.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H')
                THEN '🔴 Falta Validação Interna'
            ELSE '⚪ Turma em Andamento'
        END AS status_sla_medicao,

        -- MOTOR 2 E 3: STATUS FINANCEIRO E SALDO DE OC (TÍTULOS CLAROS)
        CASE
            WHEN UPPER(c.validacao) IN ('CANCELADO', 'REAGENDADO') OR UPPER(c.status_comercial) IN ('CANCELADO', 'REAGENDADO')
                THEN '⚪ Cancelado / Reagendado'
            WHEN NULLIF(TRIM(BOTH FROM f.data_pagamento), '') IS NOT NULL 
                 AND (NULLIF(TRIM(BOTH FROM f.nota_fiscal_2), '') IS NULL OR NULLIF(TRIM(BOTH FROM f.data_pagamento_2), '') IS NOT NULL)
                THEN '💰 Pago'
            WHEN NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NOT NULL THEN
                CASE 
                    WHEN CURRENT_DATE <= to_date(NULLIF(TRIM(BOTH FROM f.data_vencimento), ''), 'DD/MM/YYYY') 
                         AND (NULLIF(TRIM(BOTH FROM f.nota_fiscal_2), '') IS NULL OR CURRENT_DATE <= to_date(NULLIF(TRIM(BOTH FROM f.data_vencimento_2), ''), 'DD/MM/YYYY'))
                        THEN '💸 Faturas a Vencer'
                    ELSE '🚨 Faturas Vencidas'
                END
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') THEN
                CASE 
                    WHEN COALESCE(c.valor_total, 0) > COALESCE(f.valor, 0) 
                        THEN '🛑 Bloqueado por Saldo de OC'
                    ELSE '✅ Aguardando Emissão de NF'
                END
            ELSE '⏳ Aguardando Operação'
        END AS status_financeiro,

        -- MOTOR 4: QUEM ATUA (RESPONSÁVEL PELA PENDÊNCIA)
        CASE 
            WHEN UPPER(c.validacao) IN ('CANCELADO', 'REAGENDADO') OR UPPER(c.status_comercial) IN ('CANCELADO', 'REAGENDADO') 
                THEN '⚪ Cancelado'
            WHEN c.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NULL 
                THEN '🏢 Operação Interna'
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND COALESCE(c.valor_total, 0) > COALESCE(f.valor, 0) AND NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NULL 
                THEN '👤 Cliente'
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NULL 
                THEN '🏢 Financeiro Interno'
            WHEN NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NOT NULL AND NULLIF(TRIM(BOTH FROM f.data_pagamento), '') IS NULL 
                THEN '👤 Cliente'
            ELSE '✅ Concluído'
        END AS responsavel_acao,

        -- MOTOR 5: O QUE FAZER (AÇÃO REQUERIDA DETALHADA)
        CASE 
            WHEN UPPER(c.validacao) IN ('CANCELADO', 'REAGENDADO') OR UPPER(c.status_comercial) IN ('CANCELADO', 'REAGENDADO') 
                THEN '⚪ Nenhuma ação necessária'
            
            -- OPERAÇÃO INTERNA
            WHEN c.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND UPPER(c.status_comercial) LIKE '%PEDIDO%' 
                THEN '📌 Cobrar Comercial / Digitar número da Ordem de Compra (OC)'
            WHEN c.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND UPPER(c.status_comercial) LIKE '%FOLHA%' 
                THEN '📌 Cobrar Instrutor / Anexar número da Folha de Serviço (FS)'
            WHEN c.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND c.data_termino_efetiva <= CURRENT_DATE 
                THEN '📌 Conferir Lista de Presença e alterar validação para FATURAR'
            WHEN c.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND c.data_termino_efetiva > CURRENT_DATE 
                THEN '⏳ Aguardar a realização física do treinamento'

            -- FINANCEIRO INTERNO
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND COALESCE(c.valor_total, 0) <= COALESCE(f.valor, 0) AND NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NULL 
                THEN '📌 Processo liberado: Emitir Nota Fiscal'

            -- CLIENTE
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND COALESCE(c.valor_total, 0) > COALESCE(f.valor, 0) AND NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NULL 
                THEN '📩 Solicitar ao cliente suplementação de verba ou nova Ordem de Compra'
            WHEN NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NOT NULL AND CURRENT_DATE > to_date(NULLIF(TRIM(BOTH FROM f.data_vencimento), ''), 'DD/MM/YYYY') AND NULLIF(TRIM(BOTH FROM f.data_pagamento), '') IS NULL 
                THEN '📩 Cobrar do contas a pagar do cliente o comprovante da NF vencida'
            WHEN NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NOT NULL AND CURRENT_DATE <= to_date(NULLIF(TRIM(BOTH FROM f.data_vencimento), ''), 'DD/MM/YYYY') AND NULLIF(TRIM(BOTH FROM f.data_pagamento), '') IS NULL 
                THEN '📩 Acompanhar vencimento regular da Nota Fiscal'

            ELSE '✅ Processo sem pendências abertas'
        END AS acao_detalhada

    FROM v_fato_comercial_clean c
    LEFT JOIN fato_faturamento f ON c.processo = f.processo
    LEFT JOIN dim_clientes cli ON c.cod_cliente = cli.cod_cliente;
    """

    with engine.begin() as conn:
        conn.execute(text(query_v_fato))
        conn.execute(text(query_mv_comercial))
        conn.execute(text(query_vw_motor_faturamento))

        res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'fato_valores';"))
        cols = [row[0] for row in res.fetchall()]

        select_exprs = ["*"]
        if 'pedido_de_compra' not in cols:
            select_exprs.append("pedido AS pedido_de_compra" if 'pedido' in cols else "'' AS pedido_de_compra")
        if 'status_calculado' not in cols:
            select_exprs.append("status_pedido AS status_calculado" if 'status_pedido' in cols else "'SEM PEDIDO' AS status_calculado")
        if 'valor_j' not in cols:
            select_exprs.append("COALESCE(valor::numeric, 0) AS valor_j" if 'valor' in cols else "0 AS valor_j")
        if 'consumido_n' not in cols:
            select_exprs.append("COALESCE(consumido::numeric, 0) AS consumido_n" if 'consumido' in cols else "0 AS consumido_n")
        if 'saldo_m' not in cols:
            select_exprs.append("COALESCE(saldo::numeric, 0) AS saldo_m" if 'saldo' in cols else "0 AS saldo_m")

        query_mv_valores = f"""
        DROP MATERIALIZED VIEW IF EXISTS public.mv_fato_valores_tratada CASCADE;
        CREATE MATERIALIZED VIEW public.mv_fato_valores_tratada AS 
        SELECT {", ".join(select_exprs)}
        FROM public.fato_valores;
        """

        conn.execute(text(query_mv_valores))

    print("Views e Views Materializadas recriadas com sucesso!")


if __name__ == "__main__":
    planilhas = {
        "dim_instrutores": "https://docs.google.com/spreadsheets/d/1zkfSjlvdgid3D2EZoYKW6BNvMwxhwyGbmFrVQ3jxh0Y/export?format=csv&gid=2064220220",
        "fato_comercial": "https://docs.google.com/spreadsheets/d/14pmwdJL2YAPBRmdabrD2WnbmDsEs8cAK1te8JmE75h4/export?format=csv&gid=1723286423",
        "fato_treinamentos": "https://docs.google.com/spreadsheets/d/1IEJVUpt8Z-Bxov6KDfqJ9BRbxZ8-NJ-LHs-D06mhWE4/export?format=csv&gid=392845010",
        "fato_valores": "https://docs.google.com/spreadsheets/d/1fApHv-xutoZLr6hwDlZwTh2OBYyWIA23tcB4r6O57NQ/export?format=csv&gid=137403279",
        "fato_faturamento": "https://docs.google.com/spreadsheets/d/1fApHv-xutoZLr6hwDlZwTh2OBYyWIA23tcB4r6O57NQ/export?format=csv&gid=168836866",
        "dim_clientes": "https://docs.google.com/spreadsheets/d/1d_8PJE-oHVZ3x7pwAHqcfMPRP_zdT0NJzCSXfrMb8ZE/export?format=csv&gid=1660918080",
    }

    print("removendo estruturas antigas...")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS public.dim_clientes CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS public.fato_faturamento CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS public.fato_comercial CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS public.fato_valores CASCADE;"))
        conn.execute(text("DROP VIEW IF EXISTS public.v_fato_comercial_clean CASCADE;"))
        conn.execute(text("DROP VIEW IF EXISTS public.vw_motor_faturamento CASCADE;"))

    for tabela, url in planilhas.items():
        try:
            processar_e_carregar(url, tabela)
        except Exception as e:
            print(f"Erro ao processar {tabela}: {e}\n")

    try:
        recriar_views(engine)
    except Exception as e:
        print(f"Erro ao recriar views: {e}")