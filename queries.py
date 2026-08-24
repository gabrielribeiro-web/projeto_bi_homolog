from datetime import date
import pandas as pd
from sqlalchemy import text
import streamlit as st

def _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao="Consolidado (Geral)"):
    condicoes = []
    params = {}

    if grupo_cliente and grupo_cliente != "Todos":
        condicoes.append("fc.grupo = :grupo")
        params["grupo"] = grupo_cliente

    if unidade and unidade != "Todas":
        condicoes.append("fc.unidade = :unidade")
        params["unidade"] = unidade

    if data_inicio:
        campo_data = "fc.dt_termino_ead" if modo_visao == "EAD" else "fc.dt_inicio_1"
        condicoes.append(f"{campo_data} IS NOT NULL AND {campo_data} >= TO_DATE(:data_inicio, 'YYYY-MM-DD')")
        params["data_inicio"] = data_inicio.strftime("%Y-%m-%d")

    if data_fim:
        campo_data = "fc.dt_termino_ead" if modo_visao == "EAD" else "fc.dt_inicio_1"
        condicoes.append(f"{campo_data} IS NOT NULL AND {campo_data} <= TO_DATE(:data_fim, 'YYYY-MM-DD')")
        params["data_fim"] = data_fim.strftime("%Y-%m-%d")

    if modo_visao == "Presencial":
        condicoes.append("fc.modalidade LIKE '%PRESENCIAL%'")
    elif modo_visao == "EAD":
        condicoes.append("(fc.modalidade LIKE '%EAD%' OR fc.modalidade LIKE '%ON-LINE%')")

    where_clause = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return where_clause, params


@st.cache_data(ttl=600, show_spinner=False)
def buscar_kpis(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Consolidado (Geral)"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    col_data = "fc.dt_termino_ead" if modo_visao == "EAD" else "fc.dt_termino_presencial"

    query = text(f"""
        WITH BaseTreinamentos AS (
            SELECT 
                fc.processo,
                fc.unidade,
                fc.carga_horaria,
                fc.validacao,
                fc.status_comercial,
                fc.valor_turma,
                COALESCE(fv.status_calculado, 'SEM PEDIDO') AS status_calculado,
                {col_data} AS dt_termino
            FROM public.mv_fato_comercial_tratada fc
            LEFT JOIN public.mv_fato_valores_tratada fv ON fc.pedido_de_compra = fv.pedido_de_compra
            {where_clause}
            AND COALESCE(fc.valor_turma, 0) > 0
        ),
        DadosTreinamento AS (
            SELECT 
                processo, 
                COUNT(DISTINCT NULLIF(TRIM(CAST(nome_do_participante AS TEXT)), '')) AS qtd_pessoas,
                AVG(CAST(NULLIF(REGEXP_REPLACE(REPLACE(CAST(aval_final AS TEXT), ',', '.'), '[^0-9.]', '', 'g'), '') AS NUMERIC)) AS media_turma
            FROM public.fato_treinamentos
            GROUP BY processo
        )
        SELECT 
            COALESCE(SUM(CASE WHEN bt.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') 
                              AND bt.status_comercial = 'OK'
                              AND bt.status_calculado IN ('SALDO DISPONÍVEL', 'SALDO LIQUIDADO')
                              AND bt.dt_termino <= CURRENT_DATE
                        THEN bt.valor_turma ELSE 0 END), 0) AS total_faturado,
            
            COALESCE(SUM(CASE WHEN bt.validacao = 'CONFIRMADO' AND bt.dt_termino > CURRENT_DATE
                        THEN bt.valor_turma ELSE 0 END), 0) AS futuro_agendado,
            
            COALESCE(SUM(CASE WHEN (bt.validacao IS NULL OR bt.validacao = '') AND bt.dt_termino > CURRENT_DATE
                        THEN bt.valor_turma ELSE 0 END), 0) AS futuro_lancado,
            
            COALESCE(SUM(CASE 
                        WHEN bt.dt_termino <= CURRENT_DATE AND (
                             bt.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') OR 
                             UPPER(bt.status_comercial) LIKE '%PEDIDO%' OR 
                             (bt.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND bt.status_comercial = 'OK' 
                              AND bt.status_calculado NOT IN ('SALDO DISPONÍVEL', 'SALDO LIQUIDADO'))
                        )
                        THEN bt.valor_turma ELSE 0 END), 0) AS total_pendencia,
            
            COALESCE(COUNT(DISTINCT CASE WHEN bt.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') AND bt.dt_termino <= CURRENT_DATE THEN bt.processo END), 0) AS turmas_realizadas,
            COALESCE(SUM(CASE WHEN bt.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') AND bt.dt_termino <= CURRENT_DATE THEN bt.carga_horaria ELSE 0 END), 0) AS horas_realizadas,
            COALESCE(SUM(CASE WHEN bt.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') AND bt.dt_termino <= CURRENT_DATE THEN COALESCE(dt.qtd_pessoas, 0) ELSE 0 END), 0) AS pessoas_treinadas,
            COALESCE(AVG(CASE WHEN bt.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') AND bt.dt_termino <= CURRENT_DATE THEN dt.media_turma END), 0) AS aproveitamento_medio,
            COALESCE(COUNT(DISTINCT CASE WHEN bt.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') AND bt.dt_termino <= CURRENT_DATE THEN bt.unidade END), 0) AS unidades_atendidas
        FROM BaseTreinamentos bt
        LEFT JOIN DadosTreinamento dt ON bt.processo = dt.processo
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_grafico_nrs(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Consolidado (Geral)"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    col_data = "fc.dt_termino_ead" if modo_visao == "EAD" else "fc.dt_termino_presencial"

    query = text(f"""
        SELECT 
            fc.cod_treinamento AS nr,
            COUNT(DISTINCT fc.processo) AS quantidade
        FROM public.mv_fato_comercial_tratada fc
        {where_clause} {complemento_where} {col_data} <= CURRENT_DATE
        AND fc.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
        GROUP BY nr ORDER BY quantidade DESC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_distribuicao_tipo(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Consolidado (Geral)"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    col_data = "fc.dt_termino_ead" if modo_visao == "EAD" else "fc.dt_termino_presencial"

    query = text(f"""
        SELECT 
            COALESCE(NULLIF(fc.modalidade, ''), 'NÃO INFORMADO') AS tipo,
            COUNT(DISTINCT fc.processo) AS quantidade
        FROM public.mv_fato_comercial_tratada fc
        {where_clause} {complemento_where} {col_data} <= CURRENT_DATE
        AND fc.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
        GROUP BY tipo ORDER BY quantidade DESC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_investimento_mensal(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Consolidado (Geral)"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    col_data = "fc.dt_termino_ead" if modo_visao == "EAD" else "fc.dt_termino_presencial"

    query = text(f"""
        SELECT 
            TO_CHAR({col_data}, 'MM/YYYY') AS mes_ano,
            TO_CHAR({col_data}, 'YYYY-MM') AS sort_date,
            SUM(CASE WHEN fc.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') 
                          AND fc.status_comercial = 'OK'
                          AND fv.status_calculado IN ('SALDO DISPONÍVEL', 'SALDO LIQUIDADO')
                          AND {col_data} <= CURRENT_DATE
                          AND COALESCE(fc.valor_turma, 0) > 0
                THEN fc.valor_turma ELSE 0 END) AS "Faturamento Realizado",
            SUM(CASE WHEN fc.validacao = 'CONFIRMADO' AND {col_data} > CURRENT_DATE AND COALESCE(fc.valor_turma, 0) > 0
                THEN fc.valor_turma ELSE 0 END) AS "Faturamento Projetado"
        FROM public.mv_fato_comercial_tratada fc
        LEFT JOIN public.mv_fato_valores_tratada fv ON fc.pedido_de_compra = fv.pedido_de_compra
        {where_clause}
        GROUP BY 1, 2 ORDER BY 2
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_proximas_turmas(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Consolidado (Geral)"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    col_data = "fc.dt_termino_ead" if modo_visao == "EAD" else "fc.dt_termino_presencial"

    query = text(f"""
        SELECT 
            CASE WHEN '{modo_visao}' = 'EAD' THEN fc.termino_ead_str ELSE fc.inicio_str END AS inicio,
            fc.modalidade, fc.grupo, fc.cod_treinamento AS treinamento, fc.unidade,
            CASE WHEN '{modo_visao}' = 'EAD' THEN 'Plataforma EAD' ELSE fc.instrutor END AS instrutor,
            fc.valor_turma AS valor
        FROM public.mv_fato_comercial_tratada fc
        {where_clause} {complemento_where} fc.validacao = 'CONFIRMADO' AND {col_data} > CURRENT_DATE
        ORDER BY {col_data} ASC LIMIT 20
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_ranking_instrutores(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Consolidado (Geral)"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    col_data = "fc.dt_termino_ead" if modo_visao == "EAD" else "fc.dt_termino_presencial"

    query = text(f"""
        WITH DadosTreinamento AS (
            SELECT processo, COUNT(DISTINCT NULLIF(TRIM(CAST(nome_do_participante AS TEXT)), '')) AS qtd_pessoas, AVG(CAST(NULLIF(REGEXP_REPLACE(REPLACE(CAST(aval_final AS TEXT), ',', '.'), '[^0-9.]', '', 'g'), '') AS NUMERIC)) AS media_turma
            FROM public.fato_treinamentos GROUP BY processo
        )
        SELECT 
            fc.instrutor, COUNT(DISTINCT fc.processo) AS turmas_realizadas, SUM(COALESCE(dt.qtd_pessoas, 0)) AS pessoas_treinadas, AVG(dt.media_turma) AS nota_media
        FROM public.mv_fato_comercial_tratada fc
        LEFT JOIN DadosTreinamento dt ON fc.processo = dt.processo
        {where_clause} {complemento_where} {col_data} <= CURRENT_DATE
          AND fc.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
          AND fc.instrutor IS NOT NULL AND fc.instrutor != ''
        GROUP BY fc.instrutor ORDER BY turmas_realizadas DESC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_detalhamento_financeiro(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Consolidado (Geral)"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    col_data = "fc.dt_termino_ead" if modo_visao == "EAD" else "fc.dt_termino_presencial"

    query = text(f"""
        SELECT 
            fc.processo AS "Processo",
            COALESCE(NULLIF(fc.pedido_de_compra, ''), 'NÃO INFORMADO') AS "Pedido",
            fc.modalidade AS "Modalidade",
            fc.grupo AS "Grupo",
            TO_CHAR({col_data}, 'DD/MM/YYYY') AS "Data Término",
            fc.validacao AS "Validação",
            fc.status_comercial AS "Status Comercial",
            
            CASE
                WHEN {col_data} > CURRENT_DATE AND fc.validacao = 'CONFIRMADO' THEN '🟦 FUTURO AGENDADO'
                WHEN {col_data} > CURRENT_DATE THEN '🟦 FUTURO LANÇADO'
                WHEN {col_data} <= CURRENT_DATE AND fc.validacao NOT IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') THEN '🔴 COBRAR EQUIPE (Faltou Validar)'
                WHEN {col_data} <= CURRENT_DATE AND UPPER(fc.status_comercial) LIKE '%PEDIDO%' THEN '🟡 COBRAR CLIENTE (Aguardando Doc)'
                WHEN {col_data} <= CURRENT_DATE AND fc.validacao IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND fc.status_comercial = 'OK' THEN
                     CASE 
                         WHEN fc.pedido_de_compra IS NOT NULL AND fc.pedido_de_compra != '' AND fv.status_calculado IN ('SALDO DISPONÍVEL', 'SALDO LIQUIDADO') THEN '✅ FATURAMENTO REALIZADO'
                         WHEN fc.pedido_de_compra IS NOT NULL AND fc.pedido_de_compra != '' THEN '🟡 GARGALO FINANCEIRO (Sem Saldo / Retido)'
                         ELSE '🔴 COBRAR COMERCIAL (Faltou Digitar OC)'
                     END
                ELSE '⚪ ANÁLISE MANUAL'
            END AS "Status Painel",
            
            COALESCE(fv.status_calculado, 'SEM PEDIDO') AS "Classificação Financeira",
            COALESCE(fc.valor_turma, 0) AS "Valor Processo (R$)",
            COALESCE(fv.valor_j, 0) AS "Valor Pedido (R$)",
            COALESCE(fv.consumido_n, 0) AS "Consumido (R$)",
            COALESCE(fv.saldo_m, 0) AS "Saldo Final (R$)"
        FROM public.mv_fato_comercial_tratada fc
        LEFT JOIN public.mv_fato_valores_tratada fv ON fc.pedido_de_compra = fv.pedido_de_compra
        {where_clause} AND fc.validacao NOT IN ('REAGENDADO', 'CANCELADO') AND COALESCE(fc.valor_turma, 0) > 0
        ORDER BY {col_data} DESC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_lista_participantes(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Consolidado (Geral)"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "

    query = text(f"""
        SELECT 
            ft.nome_do_participante AS "Nome do Participante", ft.cpf AS "CPF", fc.grupo AS "Grupo",
            ft.nr AS "Treinamento (NR)", ft.tipo AS "Tipo",
            CASE WHEN '{modo_visao}' = 'EAD' THEN fc.termino_ead_str ELSE fc.termino_1_str END AS "Data Conclusão",
            fc.unidade AS "Unidade"
        FROM public.fato_treinamentos ft
        INNER JOIN public.mv_fato_comercial_tratada fc ON ft.processo = fc.processo
        {where_clause} {complemento_where} fc.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
        ORDER BY fc.dt_termino_presencial DESC, ft.nome_do_participante ASC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)