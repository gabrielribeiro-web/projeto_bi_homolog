import csv
import io
import re
import unicodedata
import numpy as np
import pandas as pd
import requests
import streamlit as st
from sqlalchemy import text
from database import get_engine
from components import renderizar_filtros

# =====================================================================
# 1. FUNÇÕES DE LIMPEZA E FORMATAÇÃO
# =====================================================================
def limpar_nome_coluna(coluna):
    nfkd = unicodedata.normalize("NFKD", str(coluna))
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    texto = sem_acento.lower().strip()
    texto = re.sub(r"[\s\/\-\.]+", "_", texto)
    texto = re.sub(r"[^a-z0-9_]", "", texto)
    col_limpa = re.sub(r"_+", "_", texto).strip("_")
    return col_limpa if col_limpa else "coluna_sem_nome"

def limpar_documento(val):
    if pd.isna(val) or val is None: return None
    numeros = re.sub(r"\D", "", str(val))
    return numeros if numeros else None

def limpar_moeda(val):
    if pd.isna(val) or val is None: return 0.0
    texto = str(val).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try: return float(texto)
    except ValueError: return 0.0

def baixar_dataframe_limpo(url_csv):
    url_limpa = url_csv.strip("[]() ")
    response = requests.get(url_limpa)
    response.encoding = "utf-8"

    leitor = list(csv.reader(io.StringIO(response.text)))
    linha_cabecalho = None
    palavras_chave = [
        "STATUS COMERCIAL", "STATUS FOLLOW-UP", "PROCESSO", "INSTRUTOR",
        "CÓD. CLIENTE", "COD. CLIENTE", "CLIENTE", "NOME", "CPF",
        "PEDIDO", "STATUS PEDIDO", "EAD", "PRESENCIAL",
    ]

    for idx, linha in enumerate(leitor):
        texto_linha = " ".join(linha).upper()
        if any(x in texto_linha for x in ["AUTOCRAT", "DATASHEET", "NVSCRIPTS", "SCRIPT"]):
            continue
        if any(p in texto_linha for p in palavras_chave):
            linha_cabecalho = idx
            break

    if linha_cabecalho is None: linha_cabecalho = 0

    dados_uteis = leitor[linha_cabecalho:]
    cabecalho = dados_uteis[0]
    linhas_dados = dados_uteis[1:]

    return pd.DataFrame(linhas_dados, columns=cabecalho)

def processar_e_carregar(engine, url_csv, nome_tabela):
    df = baixar_dataframe_limpo(url_csv)
    df.columns = [limpar_nome_coluna(col) for col in df.columns]

    df = df.loc[:, df.columns != "coluna_sem_nome"]
    df = df.loc[:, ~df.columns.duplicated()]
    df = df.dropna(how="all")

    coluna_id = None
    if "processo" in df.columns: coluna_id = "processo"
    elif "cod_cliente" in df.columns: coluna_id = "cod_cliente"

    if coluna_id:
        df[coluna_id] = df[coluna_id].replace(r"^\s*$", np.nan, regex=True)
        df = df.dropna(subset=[coluna_id])

    cols_doc = [c for c in df.columns if "cnpj" in c or "cpf" in c]
    for c in cols_doc: df[c] = df[c].apply(limpar_documento)

    cols_valor = [c for c in df.columns if "valor" in c or "custo" in c or "despesas" in c]
    for c in cols_valor: df[c] = df[c].apply(limpar_moeda)

    df.to_sql(nome_tabela, con=engine, if_exists="replace", index=False)
    return len(df)

# =====================================================================
# 2. MOTOR DE RECRIAÇÃO DE VIEWS
# =====================================================================
def recriar_views(engine):
    query_v_fato = """
    CREATE OR REPLACE VIEW public.v_fato_comercial_clean AS 
    SELECT 
        fc.*,
        to_date(NULLIF(TRIM(BOTH FROM inicio_1), ''), 'DD/MM/YYYY') AS data_inicio_1,
        to_date(NULLIF(TRIM(BOTH FROM termino_1), ''), 'DD/MM/YYYY') AS data_termino_1,
        to_date(NULLIF(TRIM(BOTH FROM inicio_2), ''), 'DD/MM/YYYY') AS data_inicio_2,
        to_date(NULLIF(TRIM(BOTH FROM termino_2), ''), 'DD/MM/YYYY') AS data_termino_2,
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

    query_vw_motor_faturamento = """
    CREATE OR REPLACE VIEW public.vw_motor_faturamento AS
    SELECT 
        c.processo AS id_processo, c.grupo, c.cliente, c.unidade, c.modalidade, c.valor_total, c.validacao, c.status_comercial, cli.faturamento AS tipo_faturamento, f.valor AS saldo_oc,
        CASE WHEN cli.faturamento = 'MEDIÇÃO' THEN (DATE_TRUNC('month', c.data_termino_efetiva) + INTERVAL '1 month + 9 days')::date ELSE c.data_termino_efetiva END AS data_envio_estimada,
        CASE 
            WHEN UPPER(c.validacao) IN ('CANCELADO', 'REAGENDADO') OR UPPER(c.status_comercial) IN ('CANCELADO', 'REAGENDADO') THEN '⚪ Cancelado / Reagendado'
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') OR NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NOT NULL OR NULLIF(TRIM(BOTH FROM f.data_pagamento), '') IS NOT NULL THEN '✅ Liberado (Fora do SLA)'
            WHEN cli.faturamento = 'MEDIÇÃO' THEN
                CASE 
                    WHEN DATE_TRUNC('month', CURRENT_DATE) = DATE_TRUNC('month', c.data_termino_efetiva) THEN '⚪ Turmas do Mês Vigente'
                    WHEN DATE_TRUNC('month', CURRENT_DATE) = DATE_TRUNC('month', c.data_termino_efetiva + INTERVAL '1 month') THEN
                        CASE WHEN EXTRACT(DAY FROM CURRENT_DATE) <= 10 THEN '🟢 Em Compilação Interna (Até dia 10)' ELSE '🟡 Em Análise no Cliente (No Prazo)' END
                    WHEN DATE_TRUNC('month', CURRENT_DATE) >= DATE_TRUNC('month', c.data_termino_efetiva + INTERVAL '2 month') THEN '🔴 Medição Atrasada no Cliente'
                END
            WHEN CURRENT_DATE > c.data_termino_efetiva AND c.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') THEN '🔴 Falta Validação Interna'
            ELSE '⚪ Turma em Andamento'
        END AS status_sla_medicao,
        CASE
            WHEN UPPER(c.validacao) IN ('CANCELADO', 'REAGENDADO') OR UPPER(c.status_comercial) IN ('CANCELADO', 'REAGENDADO') THEN '⚪ Cancelado / Reagendado'
            WHEN NULLIF(TRIM(BOTH FROM f.data_pagamento), '') IS NOT NULL AND (NULLIF(TRIM(BOTH FROM f.nota_fiscal_2), '') IS NULL OR NULLIF(TRIM(BOTH FROM f.data_pagamento_2), '') IS NOT NULL) THEN '💰 Pago'
            WHEN NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NOT NULL THEN
                CASE WHEN CURRENT_DATE <= to_date(NULLIF(TRIM(BOTH FROM f.data_vencimento), ''), 'DD/MM/YYYY') THEN '💸 Faturas a Vencer' ELSE '🚨 Faturas Vencidas' END
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') THEN
                CASE WHEN COALESCE(c.valor_total, 0) > COALESCE(f.valor, 0) THEN '🛑 Bloqueado por Saldo de OC' ELSE '✅ Aguardando Emissão de NF' END
            ELSE '⏳ Aguardando Operação'
        END AS status_financeiro,
        CASE 
            WHEN UPPER(c.validacao) IN ('CANCELADO', 'REAGENDADO') OR UPPER(c.status_comercial) IN ('CANCELADO', 'REAGENDADO') THEN '⚪ Cancelado'
            WHEN c.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NULL THEN '🏢 Operação Interna'
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND COALESCE(c.valor_total, 0) > COALESCE(f.valor, 0) AND NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NULL THEN '👤 Cliente'
            WHEN c.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NULL THEN '🏢 Financeiro Interno'
            WHEN NULLIF(TRIM(BOTH FROM f.nota_fiscal), '') IS NOT NULL AND NULLIF(TRIM(BOTH FROM f.data_pagamento), '') IS NULL THEN '👤 Cliente'
            ELSE '✅ Concluído'
        END AS responsavel_acao
    FROM v_fato_comercial_clean c LEFT JOIN fato_faturamento f ON c.processo = f.processo LEFT JOIN dim_clientes cli ON c.cod_cliente = cli.cod_cliente;
    """

    with engine.begin() as conn:
        conn.execute(text(query_v_fato))
        conn.execute(text(query_mv_comercial))
        conn.execute(text(query_vw_motor_faturamento))

        res = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'fato_valores';"))
        cols = [row[0] for row in res.fetchall()]

        select_exprs = ["*"]
        if 'pedido_de_compra' not in cols: select_exprs.append("pedido AS pedido_de_compra" if 'pedido' in cols else "'' AS pedido_de_compra")
        if 'status_calculado' not in cols: select_exprs.append("status_pedido AS status_calculado" if 'status_pedido' in cols else "'SEM PEDIDO' AS status_calculado")
        if 'valor_j' not in cols: select_exprs.append("COALESCE(valor::numeric, 0) AS valor_j" if 'valor' in cols else "0 AS valor_j")
        if 'consumido_n' not in cols: select_exprs.append("COALESCE(consumido::numeric, 0) AS consumido_n" if 'consumido' in cols else "0 AS consumido_n")
        if 'saldo_m' not in cols: select_exprs.append("COALESCE(saldo::numeric, 0) AS saldo_m" if 'saldo' in cols else "0 AS saldo_m")

        query_mv_valores = f"""
        DROP MATERIALIZED VIEW IF EXISTS public.mv_fato_valores_tratada CASCADE;
        CREATE MATERIALIZED VIEW public.mv_fato_valores_tratada AS SELECT {", ".join(select_exprs)} FROM public.fato_valores;
        """
        conn.execute(text(query_mv_valores))

# =====================================================================
# 3. INTERFACE DE USUÁRIO DO STREAMLIT E APLICAÇÃO VISUAL
# =====================================================================
engine_filtros, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros(mostrar_filtros=False)

st.markdown("### 🔄 Sincronização de Dados (Google Sheets)")
st.caption("Esta ferramenta conecta ao Google Sheets e atualiza todas as tabelas do painel automaticamente.")

if not user or user.get("perfil") != "admin":
    st.error("Acesso restrito a Administradores.")
    st.stop()

# Links de Produção Oficiais (Padrão)
planilhas_oficiais = {
    "dim_instrutores": "https://docs.google.com/spreadsheets/d/1zkfSjlvdgid3D2EZoYKW6BNvMwxhwyGbmFrVQ3jxh0Y/export?format=csv&gid=2064220220",
    "fato_comercial": "https://docs.google.com/spreadsheets/d/1zkfSjlvdgid3D2EZoYKW6BNvMwxhwyGbmFrVQ3jxh0Y/export?format=csv&gid=1723286423",
    "fato_treinamentos": "https://docs.google.com/spreadsheets/d/1IEJVUpt8Z-Bxov6KDfqJ9BRbxZ8-NJ-LHs-D06mhWE4/export?format=csv&gid=392845010",
    "fato_valores": "https://docs.google.com/spreadsheets/d/1UvXfXwjXOO0dd0dzvHJB49YrInGGlh0LugFhVvOFkJI/export?format=csv&gid=137403279",
    "fato_faturamento": "https://docs.google.com/spreadsheets/d/1UvXfXwjXOO0dd0dzvHJB49YrInGGlh0LugFhVvOFkJI/export?format=csv&gid=168836866",
    "dim_clientes": "https://docs.google.com/spreadsheets/d/1uVrYVCQ1xVeoeNmlVHp6KB0CRyA8mu7JdML9hFzgYdk/export?format=csv&gid=1660918080",
}

planilhas_ativas = {}

# Menu expansível para inserir as planilhas de teste (cópias)
with st.expander("🔧 Configurar Links das Planilhas (Para Homologação/Cópias)", expanded=False):
    st.info("Caso esteja realizando testes, apague o link padrão e cole o link de exportação CSV da sua cópia. Ao fechar esta aba, o botão de sincronização usará os links que estão aqui preenchidos.")
    
    for tabela, url_padrao in planilhas_oficiais.items():
        link_usuario = st.text_input(f"🔗 Link: {tabela}", value=url_padrao, key=f"url_{tabela}")
        planilhas_ativas[tabela] = link_usuario

st.divider()

if st.button("🚀 Iniciar Sincronização Completa Agora", type="primary", use_container_width=True):
    with st.status("Conectando aos servidores do Google e Banco de Dados...", expanded=True) as status:
        try:
            engine = get_engine()
            
            st.write("🗑️ Limpando estruturas antigas no banco de dados...")
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS public.dim_clientes CASCADE;"))
                conn.execute(text("DROP TABLE IF EXISTS public.fato_faturamento CASCADE;"))
                conn.execute(text("DROP TABLE IF EXISTS public.fato_comercial CASCADE;"))
                conn.execute(text("DROP TABLE IF EXISTS public.fato_valores CASCADE;"))
                conn.execute(text("DROP VIEW IF EXISTS public.v_fato_comercial_clean CASCADE;"))
                conn.execute(text("DROP VIEW IF EXISTS public.vw_motor_faturamento CASCADE;"))

            # Roda as URLs que estão preenchidas nos campos de texto
            for tabela, url in planilhas_ativas.items():
                st.write(f"⬇️ Baixando e limpando dados: `{tabela}` ...")
                linhas = processar_e_carregar(engine, url, tabela)
                st.write(f"✅ `{tabela}` atualizada com {linhas} registros.")

            st.write("⚙️ Recriando Motor de Regras e Views de Performance...")
            recriar_views(engine)
            
            # ==========================================================
            # MOTOR DE HISTÓRICO (REGRA RF32 - RASTREABILIDADE)
            # ==========================================================
            st.write("📖 Registrando histórico de mudanças na Linha do Tempo...")
            query_historico = """
            WITH processos_atuais AS (
                SELECT 
                    id_processo, 
                    status_sla_medicao AS status_operacional,
                    status_financeiro
                FROM vw_motor_faturamento
            ),
            ultimo_historico AS (
                SELECT DISTINCT ON (id_processo, tipo_status) 
                    id_processo, 
                    status_novo, 
                    tipo_status
                FROM tb_historico_processos
                ORDER BY id_processo, tipo_status, data_mudanca DESC
            )
            INSERT INTO tb_historico_processos (id_processo, status_anterior, status_novo, tipo_status)
            
            -- MUDANÇAS OPERACIONAIS
            SELECT 
                p.id_processo, 
                COALESCE(u_op.status_novo, 'NOVO PROCESSO'), 
                p.status_operacional, 
                'OPERACIONAL'
            FROM processos_atuais p
            LEFT JOIN ultimo_historico u_op ON p.id_processo = u_op.id_processo AND u_op.tipo_status = 'OPERACIONAL'
            WHERE p.status_operacional IS NOT NULL 
              AND p.status_operacional <> COALESCE(u_op.status_novo, '')
            
            UNION ALL
            
            -- MUDANÇAS FINANCEIRAS
            SELECT 
                p.id_processo, 
                COALESCE(u_fin.status_novo, 'NOVO PROCESSO'), 
                p.status_financeiro, 
                'FINANCEIRO'
            FROM processos_atuais p
            LEFT JOIN ultimo_historico u_fin ON p.id_processo = u_fin.id_processo AND u_fin.tipo_status = 'FINANCEIRO'
            WHERE p.status_financeiro IS NOT NULL 
              AND p.status_financeiro <> COALESCE(u_fin.status_novo, '');
            """
            with engine.begin() as conn:
                conn.execute(text(query_historico))
            # ==========================================================

            st.cache_data.clear()

            status.update(label="Sincronização 100% concluída com sucesso!", state="complete", expanded=False)
            st.balloons()
            st.success("O sistema foi atualizado! Acesse as outras abas para visualizar os novos dados.")
            
        except Exception as e:
            status.update(label="Falha na Sincronização!", state="error", expanded=True)
            st.error(f"Erro técnico detalhado: {e}")