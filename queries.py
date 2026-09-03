from datetime import date
import pandas as pd
from sqlalchemy import text
import streamlit as st

# =====================================================================
# HELPERS DE DEPURAÇÃO / VALIDAÇÃO (uso exclusivo do painel admin)
# =====================================================================
def _params_to_literal_sql(sql_text: str, params: dict) -> str:
    out = sql_text
    for key in sorted(params.keys(), key=len, reverse=True):
        val = params[key]
        if val is None:
            literal = "NULL"
        elif isinstance(val, (int, float)):
            literal = str(val)
        else:
            literal = "'" + str(val).replace("'", "''") + "'"
        out = out.replace(f":{key}", literal)
    return out

def sql_card_wrap(sql_base_literal: str, titulo: str, where_fragment: str) -> str:
    return (
        f"-- ============================================================\n"
        f"-- CARD: {titulo}\n"
        f"-- ============================================================\n"
        f"SELECT * FROM (\n{sql_base_literal}\n) AS motor\n"
        f"WHERE {where_fragment}\n"
        f"ORDER BY motor.id_processo;"
    )

def _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao="Presencial"):
    condicoes = []
    params = {}

    if grupo_cliente and grupo_cliente != "Todos":
        condicoes.append("fc.grupo = :grupo")
        params["grupo"] = grupo_cliente

    if unidade and unidade != "Todas":
        condicoes.append("fc.unidade = :unidade")
        params["unidade"] = unidade

    campo_data = "fc.dt_termino_presencial"

    if data_inicio:
        condicoes.append(f"{campo_data} IS NOT NULL AND {campo_data} >= TO_DATE(:data_inicio, 'YYYY-MM-DD')")
        params["data_inicio"] = data_inicio.strftime("%Y-%m-%d")

    if data_fim:
        condicoes.append(f"{campo_data} IS NOT NULL AND {campo_data} <= TO_DATE(:data_fim, 'YYYY-MM-DD')")
        params["data_fim"] = data_fim.strftime("%Y-%m-%d")

    condicoes.append("UPPER(TRIM(fc.modalidade)) = 'PRESENCIAL'")

    where_clause = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return where_clause, params

# =====================================================================
# REFINAMENTO DO MOTOR CENTRAL (Baseado no DOC de Requisitos V1)
# =====================================================================
def _sql_motor_faturamento_template(where_clause: str) -> str:
    return f"""
    WITH params AS (
        SELECT COALESCE(MAX(data_referencia), CURRENT_DATE) as data_ref FROM public.tb_parametros WHERE id = 1
    ),
    base AS (
        SELECT 
            fc.processo AS id_processo, 
            fc.grupo, 
            fc.cliente, 
            fc.unidade, 
            fc.modalidade,
            fc.cod_treinamento,
            fc.exigencia_para_faturamento,
            fc.valor_turma AS valor_original,
            CASE WHEN fc.valor_turma IS NULL THEN TRUE ELSE FALSE END AS flag_valor_ausente,
            COALESCE(fc.valor_turma, 0) AS valor_total,
            
            NULLIF(TRIM(fc.validacao), '') AS validacao_original,
            COALESCE(NULLIF(TRIM(fc.validacao), ''), 'EM PROGRAMAÇÃO') AS validacao_calc,
            fc.status_comercial,
            
            fc.dt_inicio_presencial AS data_inicio,
            CASE WHEN fc.dt_inicio_presencial IS NULL THEN TRUE ELSE FALSE END AS flag_data_inicio_ausente,
            fc.dt_termino_presencial AS data_termino,
            
            NULLIF(TRIM(cli.faturamento), '') AS tipo_faturamento_original,
            CASE WHEN NULLIF(TRIM(cli.faturamento), '') IS NULL THEN TRUE ELSE FALSE END AS flag_tipo_faturamento_ausente,
            COALESCE(cli.faturamento, 'NÃO INFORMADO') AS tipo_faturamento,
            
            f.nota_fiscal, 
            f.data_faturamento AS data_emissao, 
            f.data_vencimento, 
            f.data_pagamento,
            
            fc.pedido_de_compra AS pedido_compra,
            fc.folha_de_servico AS folha_servico 
        FROM mv_fato_comercial_tratada fc 
        LEFT JOIN (
            SELECT processo, MAX(nota_fiscal) as nota_fiscal, MAX(data_faturamento) as data_faturamento, MAX(data_vencimento) as data_vencimento, MAX(data_pagamento) as data_pagamento
            FROM fato_faturamento GROUP BY processo
        ) f ON fc.processo = f.processo
        LEFT JOIN dim_clientes cli ON fc.cod_cliente = cli.cod_cliente
        {where_clause}
    ),
    logica_datas AS (
        SELECT 
            b.*,
            p.data_ref,
            b.data_inicio AS data_d,
            (b.data_inicio + INTERVAL '1 day')::date AS data_d_mais_1,
            
            (DATE_TRUNC('month', b.data_termino) + INTERVAL '1 month')::date AS mes_subsequente_inicio,
            (DATE_TRUNC('month', b.data_termino) + INTERVAL '1 month' + INTERVAL '9 days')::date AS limite_medicao_interna,
            (DATE_TRUNC('month', b.data_termino) + INTERVAL '1 month' + INTERVAL '2 months' - INTERVAL '1 day')::date AS limite_validacao_cliente,
            
            to_date(NULLIF(TRIM(b.data_emissao), ''), 'DD/MM/YYYY') AS dt_emissao_nf,
            to_date(NULLIF(TRIM(b.data_vencimento), ''), 'DD/MM/YYYY') AS dt_vencimento_nf,
            to_date(NULLIF(TRIM(b.data_pagamento), ''), 'DD/MM/YYYY') AS dt_pagamento_nf,
            
            CASE WHEN NULLIF(TRIM(b.nota_fiscal), '') IS NOT NULL AND to_date(NULLIF(TRIM(b.data_emissao), ''), 'DD/MM/YYYY') IS NOT NULL THEN TRUE ELSE FALSE END AS nf_completa
        FROM base b
        CROSS JOIN params p
    ),
    classificacao_motor AS (
        SELECT 
            *,
            CASE
                WHEN UPPER(validacao_calc) IN ('CANCELADO', 'REAGENDADO') OR UPPER(status_comercial) IN ('CANCELADO', 'REAGENDADO') THEN 'NAO_COBRAVEL'
                WHEN dt_pagamento_nf IS NOT NULL THEN 'PAGO'
                WHEN UPPER(validacao_calc) IN ('CANCELADO DIA', 'CANCELADO 24H') AND dt_pagamento_nf IS NULL THEN 'PAGO_CANCELAMENTO'
                WHEN nf_completa = TRUE AND dt_pagamento_nf IS NULL AND dt_vencimento_nf < data_ref THEN 'PAGAMENTO_EM_ATRASO'
                WHEN nf_completa = TRUE AND dt_pagamento_nf IS NULL AND dt_vencimento_nf >= data_ref THEN 'A_VENCER'
                WHEN UPPER(validacao_calc) = 'FATURAR' AND nf_completa = FALSE THEN 'AGUARDANDO_NF'
                WHEN UPPER(tipo_faturamento) = 'PONTUAL' AND data_d_mais_1 <= data_ref AND UPPER(validacao_calc) != 'FATURAR' THEN 'FATURAMENTO_PENDENTE'
                WHEN UPPER(tipo_faturamento) IN ('MEDIÇÃO', 'MEDICAO') AND data_ref > limite_validacao_cliente AND UPPER(validacao_calc) != 'FATURAR' THEN 'MEDICAO_EM_ATRASO'
                WHEN UPPER(tipo_faturamento) IN ('MEDIÇÃO', 'MEDICAO') AND data_ref > limite_medicao_interna AND data_ref <= limite_validacao_cliente AND UPPER(validacao_calc) != 'FATURAR' THEN 'AGUARDANDO_CLIENTE'
                WHEN UPPER(tipo_faturamento) IN ('MEDIÇÃO', 'MEDICAO') AND data_ref >= mes_subsequente_inicio AND data_ref <= limite_medicao_interna AND UPPER(validacao_calc) != 'FATURAR' THEN 'MEDICAO_EM_PROCESSAMENTO'
                WHEN (data_termino > data_ref OR data_termino IS NULL) AND (UPPER(validacao_calc) LIKE '%PROGRAMA%' OR UPPER(validacao_calc) = 'CONFIRMADO') THEN 'PREVISAO'
                WHEN UPPER(tipo_faturamento) = 'PONTUAL' AND data_d = data_ref THEN 'COBRAVEL_D'
                WHEN UPPER(tipo_faturamento) IN ('MEDIÇÃO', 'MEDICAO') AND data_termino <= data_ref AND data_ref < mes_subsequente_inicio THEN 'AGUARDANDO_VIRADA_MES'
                ELSE 'DESCONHECIDO'
            END AS etapa_principal
            
        FROM logica_datas
    )
    SELECT 
        *,
        CASE 
            WHEN etapa_principal = 'PREVISAO' THEN 'Em Programação'
            WHEN etapa_principal = 'MEDICAO_EM_PROCESSAMENTO' THEN 'Medição em processamento'
            WHEN etapa_principal = 'AGUARDANDO_CLIENTE' THEN 'Aguardando validação do cliente'
            WHEN etapa_principal = 'MEDICAO_EM_ATRASO' THEN 'Medição em atraso cliente'
            WHEN etapa_principal = 'FATURAMENTO_PENDENTE' THEN 'Faturamento pendente - prazo vencido'
            WHEN etapa_principal = 'AGUARDANDO_NF' THEN 'Aguardando emissão de NF'
            WHEN etapa_principal = 'A_VENCER' THEN 'A vencer / Em aberto'
            WHEN etapa_principal = 'PAGAMENTO_EM_ATRASO' THEN 'Pagamento em Atraso'
            WHEN etapa_principal = 'PAGO' THEN 'Pago no Prazo'
            WHEN etapa_principal = 'PAGO_CANCELAMENTO' THEN 'Finalizado (Pago)'
            WHEN etapa_principal = 'AGUARDANDO_VIRADA_MES' THEN 'Aguardando virada do mês para fechar a medição'
            WHEN etapa_principal = 'NAO_COBRAVEL' THEN 'Não Cobrável'
            WHEN etapa_principal = 'COBRAVEL_D' THEN 'Cobrável em D'
            ELSE 'Desconhecido'
        END AS status_medicao,
        
        CASE 
            WHEN etapa_principal IN ('PAGO', 'PAGO_CANCELAMENTO') THEN 'Pago Confirmado'
            WHEN etapa_principal = 'PAGAMENTO_EM_ATRASO' THEN 'Pagamento em Atraso'
            WHEN etapa_principal = 'A_VENCER' THEN 'A vencer / Em aberto'
            WHEN etapa_principal = 'AGUARDANDO_NF' THEN 'Aguardando emissão de NF'
            WHEN etapa_principal IN ('NAO_COBRAVEL') THEN 'N/A'
            ELSE 'NF Não Emitida'
        END AS status_pagamento,

        CASE 
            WHEN etapa_principal = 'FATURAMENTO_PENDENTE' THEN (data_ref - data_d_mais_1)
            WHEN etapa_principal = 'MEDICAO_EM_ATRASO' THEN (data_ref - limite_validacao_cliente)
            ELSE 0
        END AS dias_atraso_medicao,
        
        CASE
            WHEN etapa_principal = 'PAGAMENTO_EM_ATRASO' THEN (data_ref - dt_vencimento_nf)
            WHEN etapa_principal = 'PAGO' AND dt_pagamento_nf > dt_vencimento_nf THEN (dt_pagamento_nf - dt_vencimento_nf)
            ELSE 0
        END AS dias_atraso_pagamento,

        -- -----------------------------------------------------
        -- COLUNA DE RESPONSÁVEL REINSERIDA AQUI (CORREÇÃO)
        -- -----------------------------------------------------
        CASE 
            WHEN etapa_principal IN ('PAGO', 'PAGO_CANCELAMENTO', 'NAO_COBRAVEL') THEN '✅ Concluído'
            WHEN etapa_principal = 'AGUARDANDO_NF' THEN '🏢 Financeiro Interno'
            WHEN etapa_principal IN ('AGUARDANDO_CLIENTE', 'MEDICAO_EM_ATRASO', 'A_VENCER', 'PAGAMENTO_EM_ATRASO') THEN '👤 Cliente'
            ELSE '🏢 Operação Interna'
        END AS responsavel_acao
        
    FROM classificacao_motor
    """

@st.cache_data(ttl=300, show_spinner=False)
def buscar_motor_faturamento(_engine, grupo_cliente, unidade, data_inicio, data_fim, modo_visao):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    sql = text(_sql_motor_faturamento_template(where_clause))
    with _engine.connect() as conn:
        return pd.read_sql_query(sql, conn, params=params)

def sql_motor_faturamento_debug(grupo_cliente, unidade, data_inicio, data_fim, modo_visao) -> str:
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    sql_template = _sql_motor_faturamento_template(where_clause)
    return _params_to_literal_sql(sql_template, params)

def _sql_kpis_template(where_clause: str, col_data: str) -> str:
    return f"""
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
            
            COALESCE(SUM(CASE WHEN bt.validacao = 'CONFIRMADO' AND (bt.dt_termino > CURRENT_DATE OR bt.dt_termino IS NULL)
                        THEN bt.valor_turma ELSE 0 END), 0) AS futuro_agendado,
            
            COALESCE(SUM(CASE WHEN (bt.validacao IS NULL OR bt.validacao = '') AND (bt.dt_termino > CURRENT_DATE OR bt.dt_termino IS NULL)
                        THEN bt.valor_turma ELSE 0 END), 0) AS futuro_lancado,
            
            COALESCE(SUM(CASE 
                        WHEN bt.dt_termino <= CURRENT_DATE 
                          AND UPPER(COALESCE(bt.validacao, '')) NOT IN ('CANCELADO', 'REAGENDADO')
                          AND UPPER(COALESCE(bt.status_comercial, '')) NOT IN ('CANCELADO', 'REAGENDADO')
                          AND (
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
    """

@st.cache_data(ttl=600, show_spinner=False)
def buscar_kpis(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    col_data = "fc.dt_termino_presencial"
    query = text(_sql_kpis_template(where_clause, col_data))
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)

def sql_kpis_debug(grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial") -> str:
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    col_data = "fc.dt_termino_presencial"
    return _params_to_literal_sql(_sql_kpis_template(where_clause, col_data), params)

@st.cache_data(ttl=600, show_spinner=False)
def buscar_grafico_nrs(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    col_data = "fc.dt_termino_presencial"

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
def buscar_distribuicao_tipo(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    col_data = "fc.dt_termino_presencial"

    query = text(f"""
        SELECT 
            COALESCE(NULLIF(TRIM(fc.modalidade), ''), 'NÃO INFORMADO') AS tipo,
            COUNT(DISTINCT fc.processo) AS quantidade
        FROM public.mv_fato_comercial_tratada fc
        {where_clause} {complemento_where} {col_data} <= CURRENT_DATE
        AND fc.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
        GROUP BY tipo ORDER BY quantidade DESC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_investimento_mensal(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    col_data = "fc.dt_termino_presencial"

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
def buscar_proximas_turmas(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    col_data_inicio = "fc.dt_inicio_presencial"

    query = text(f"""
        SELECT 
            fc.inicio_1 AS inicio,
            fc.modalidade, fc.grupo, fc.cod_treinamento AS treinamento, fc.unidade,
            fc.instrutor_1 AS instrutor,
            fc.valor_turma AS valor
        FROM public.mv_fato_comercial_tratada fc
        {where_clause} {complemento_where} fc.validacao = 'CONFIRMADO' AND {col_data_inicio} > CURRENT_DATE
        ORDER BY {col_data_inicio} ASC LIMIT 20
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_ranking_instrutores(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    col_data = "fc.dt_termino_presencial"

    query = text(f"""
        WITH DadosTreinamento AS (
            SELECT processo, COUNT(DISTINCT NULLIF(TRIM(CAST(nome_do_participante AS TEXT)), '')) AS qtd_pessoas, AVG(CAST(NULLIF(REGEXP_REPLACE(REPLACE(CAST(aval_final AS TEXT), ',', '.'), '[^0-9.]', '', 'g'), '') AS NUMERIC)) AS media_turma
            FROM public.fato_treinamentos GROUP BY processo
        )
        SELECT 
            fc.instrutor_1 AS instrutor, COUNT(DISTINCT fc.processo) AS turmas_realizadas, SUM(COALESCE(dt.qtd_pessoas, 0)) AS pessoas_treinadas, AVG(dt.media_turma) AS nota_media
        FROM public.mv_fato_comercial_tratada fc
        LEFT JOIN DadosTreinamento dt ON fc.processo = dt.processo
        {where_clause} {complemento_where} {col_data} <= CURRENT_DATE
          AND fc.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
          AND fc.instrutor_1 IS NOT NULL AND fc.instrutor_1 != ''
        GROUP BY fc.instrutor_1 ORDER BY turmas_realizadas DESC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_detalhamento_financeiro(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    col_data = "fc.dt_termino_presencial"

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
        {where_clause} 
          AND UPPER(COALESCE(fc.validacao, '')) NOT IN ('REAGENDADO', 'CANCELADO') 
          AND UPPER(COALESCE(fc.status_comercial, '')) NOT IN ('REAGENDADO', 'CANCELADO')
          AND COALESCE(fc.valor_turma, 0) > 0
        ORDER BY {col_data} DESC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_lista_participantes(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "

    query = text(f"""
        SELECT 
            ft.nome_do_participante AS "Nome do Participante", ft.cpf AS "CPF", fc.grupo AS "Grupo",
            ft.nr AS "Treinamento (NR)", ft.tipo AS "Tipo",
            fc.termino_1 AS "Data Conclusão",
            fc.unidade AS "Unidade"
        FROM public.fato_treinamentos ft
        INNER JOIN public.mv_fato_comercial_tratada fc ON ft.processo = fc.processo
        {where_clause} {complemento_where} fc.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
        ORDER BY fc.dt_termino_presencial DESC, ft.nome_do_participante ASC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=600, show_spinner=False)
def buscar_ranking_vendedores(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    col_data = "fc.dt_termino_presencial"

    query = text(f"""
        SELECT 
            COALESCE(NULLIF(TRIM(fc.executivo_de_vendas), ''), 'NÃO INFORMADO') AS executivo,
            COUNT(DISTINCT fc.processo) AS turmas_vendidas,
            SUM(COALESCE(fc.valor_turma, 0)) AS valor_total_vendido
        FROM public.mv_fato_comercial_tratada fc
        {where_clause} {complemento_where} {col_data} <= CURRENT_DATE
          AND fc.validacao IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
        GROUP BY executivo ORDER BY valor_total_vendido DESC
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=300, show_spinner=False)
def buscar_analise_margem(_engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao):
    query = """
    SELECT 
        fc.processo,
        fc.cliente,
        fc.dt_inicio_presencial AS data_inicio_presencial,
        COALESCE(fc.instrutor_1, fc.instrutor_2, 'Não Informado') AS instrutor,
        COALESCE(fc.valor_total, 0) AS receita,
        
        -- Somatório dos Custos Discriminados
        (COALESCE(fc.custo_1_instrutor, 0) + COALESCE(fc.custo_2_instrutor, 0)) AS custo_honorario,
        (COALESCE(fc.despesas_1_km, 0) + COALESCE(fc.despesas_2_km, 0)) AS custo_km,
        (COALESCE(fc.despesas_1_hotel, 0) + COALESCE(fc.despesas_2_hotel, 0)) AS custo_hospedagem,
        (COALESCE(fc.despesas_1_extras, 0) + COALESCE(fc.despesas_2_extras, 0)) AS custo_extra,
        
        -- Custo Operacional Total da Turma
        (
            COALESCE(fc.custo_1_instrutor, 0) + COALESCE(fc.despesas_1_km, 0) + 
            COALESCE(fc.despesas_1_hotel, 0) + COALESCE(fc.despesas_1_extras, 0) +
            COALESCE(fc.custo_2_instrutor, 0) + COALESCE(fc.despesas_2_km, 0) + 
            COALESCE(fc.despesas_2_hotel, 0) + COALESCE(fc.despesas_2_extras, 0)
        ) AS custo_total
    FROM public.mv_fato_comercial_tratada fc
    WHERE fc.dt_inicio_presencial BETWEEN :dt_inicio AND :dt_fim
    """
    params = {"dt_inicio": dt_inicio, "dt_fim": dt_fim}

    if grupo_sel and grupo_sel != "Todos":
        query += " AND fc.grupo = :grupo"
        params["grupo"] = grupo_sel

    if unidade_sel and unidade_sel != "Todas":
        query += " AND fc.unidade = :unidade"
        params["unidade"] = unidade_sel

    try:
        return pd.read_sql_query(text(query), _engine, params=params)
    except Exception as e:
        st.error(f"⚠️ Erro ao consultar DRE Operacional: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def buscar_colaboradores_treinados(_engine, grupo_sel, unidade_sel, dt_inicio, dt_fim):
    query = """
    SELECT 
        nome_aluno AS nome,
        -- Mascara o CPF para LGPD (Ex: ***.123.456-**)
        CONCAT('***.', SUBSTRING(cpf_aluno FROM 4 FOR 3), '.', SUBSTRING(cpf_aluno FROM 7 FOR 3), '-**') AS cpf,
        treinamento,
        tipo_treinamento AS tipo,
        data_conclusao,
        unidade
    FROM public.mv_alunos_treinados 
    WHERE data_conclusao BETWEEN :dt_inicio AND :dt_fim
    """
    params = {"dt_inicio": dt_inicio, "dt_fim": dt_fim}

    if grupo_sel and grupo_sel != "Todos":
        query += " AND grupo = :grupo"
        params["grupo"] = grupo_sel

    if unidade_sel and unidade_sel != "Todas":
        query += " AND unidade = :unidade"
        params["unidade"] = unidade_sel

    try:
        return pd.read_sql_query(text(query), _engine, params=params)
    except Exception as e:
        return pd.DataFrame(columns=["nome", "cpf", "treinamento", "tipo", "data_conclusao", "unidade"])