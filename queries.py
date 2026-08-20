from datetime import date
import pandas as pd
from sqlalchemy import text


def _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim):
    condicoes = []
    params = {}

    if grupo_cliente and grupo_cliente != "Todos":
        condicoes.append("fc.grupo = :grupo")
        params["grupo"] = grupo_cliente

    if unidade and unidade != "Todas":
        condicoes.append("fc.unidade = :unidade")
        params["unidade"] = unidade

    if data_inicio:
        condicoes.append(
            "fc.inicio_1 IS NOT NULL AND fc.inicio_1 != '' AND TO_DATE(fc.inicio_1, 'DD/MM/YYYY') >= TO_DATE(:data_inicio, 'YYYY-MM-DD')"
        )
        params["data_inicio"] = data_inicio.strftime("%Y-%m-%d")

    if data_fim:
        condicoes.append(
            "fc.inicio_1 IS NOT NULL AND fc.inicio_1 != '' AND TO_DATE(fc.inicio_1, 'DD/MM/YYYY') <= TO_DATE(:data_fim, 'YYYY-MM-DD')"
        )
        params["data_fim"] = data_fim.strftime("%Y-%m-%d")

    where_clause = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return where_clause, params


def buscar_kpis(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)

    query = text(
        f"""
        WITH DadosTreinamento AS (
            SELECT 
                processo, 
                -- 1. Conta apenas os nomes distintos (reais) por turma
                COUNT(DISTINCT NULLIF(TRIM(CAST(nome_do_participante AS TEXT)), '')) AS qtd_pessoas,
                -- 2. Tira a média da nota final
                AVG(CAST(NULLIF(REGEXP_REPLACE(REPLACE(CAST(aval_final AS TEXT), ',', '.'), '[^0-9.]', '', 'g'), '') AS NUMERIC)) AS media_turma
            FROM public.fato_treinamentos
            GROUP BY processo
        )
        SELECT 
            -- 1. PAGO 
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND UPPER(TRIM(fc.status_comercial)) = 'OK' 
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS total_faturado,
            
            -- 2. FUTURO AGENDADO 
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) = 'CONFIRMADO' AND NULLIF(fc.inicio_1, '') IS NOT NULL AND TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY') > CURRENT_DATE
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS futuro_agendado,
            
            -- 3. FUTURO LANÇADO 
            SUM(CASE WHEN (fc.validacao IS NULL OR TRIM(fc.validacao) = '') AND NULLIF(fc.inicio_1, '') IS NOT NULL AND TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY') > CURRENT_DATE
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS futuro_lancado,
            
            -- 4. PENDÊNCIA 
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') AND (fc.status_comercial IS NULL OR UPPER(TRIM(fc.status_comercial)) != 'OK')
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS total_pendencia,
            
            -- 5. TURMAS REALIZADAS 
            COUNT(DISTINCT CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') < CURRENT_DATE 
                THEN fc.processo END) AS turmas_realizadas,
            
            -- 6. HORAS DE TREINAMENTO 
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') < CURRENT_DATE 
                THEN COALESCE(
                     CAST(NULLIF(REGEXP_REPLACE(CAST(fc.ch_formacao AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC),
                     CAST(NULLIF(REGEXP_REPLACE(CAST(fc.ch_reciclagem AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC), 
                     0) ELSE 0 END) AS horas_realizadas,
            
            -- 7. PESSOAS TREINADAS (Agora soma a contagem REAL vinda da tabela de treinamentos)
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') < CURRENT_DATE 
                THEN COALESCE(dt.qtd_pessoas, 0) ELSE 0 END) AS pessoas_treinadas,
            
            -- 8. APROVEITAMENTO MÉDIO
            AVG(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') < CURRENT_DATE 
                THEN dt.media_turma END) AS aproveitamento_medio,
            
            -- 9. UNIDADES ATENDIDAS
            COUNT(DISTINCT CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') < CURRENT_DATE 
                THEN fc.unidade END) AS unidades_atendidas
        FROM public.fato_comercial fc
        LEFT JOIN DadosTreinamento dt ON fc.processo = dt.processo
        {where_clause}
    """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


# Para garantir que todos os gráficos operacionais sigam a mesma regra exata da liderança:
regra_operacional = " UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') AND NULLIF(fc.processo, '') IS NOT NULL AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') < CURRENT_DATE "


def buscar_grafico_nrs(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    where_clause += f"{complemento_where} {regra_operacional}"

    query = text(
        f"""
        SELECT fc.cod_treinamento, COUNT(fc.cod_treinamento) AS contagem
        FROM public.fato_comercial fc 
        {where_clause}
        GROUP BY fc.cod_treinamento ORDER BY contagem DESC LIMIT 5
    """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def buscar_distribuicao_tipo(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    where_clause += f"{complemento_where} {regra_operacional}"

    query = text(
        f"""
        SELECT 
            CASE 
                WHEN TRIM(CAST(fc.ch_formacao AS TEXT)) != '' AND (fc.ch_reciclagem IS NULL OR TRIM(CAST(fc.ch_reciclagem AS TEXT)) = '') THEN 'FORMAÇÃO'
                WHEN TRIM(CAST(fc.ch_reciclagem AS TEXT)) != '' AND (fc.ch_formacao IS NULL OR TRIM(CAST(fc.ch_formacao AS TEXT)) = '') THEN 'RECICLAGEM'
                WHEN TRIM(CAST(fc.ch_formacao AS TEXT)) != '' AND TRIM(CAST(fc.ch_reciclagem AS TEXT)) != '' THEN 'FORMAÇÃO + RECICLAGEM'
                ELSE 'OUTROS'
            END AS tipo,
            COUNT(*) AS qtd
        FROM public.fato_comercial fc
        {where_clause}
        GROUP BY 1
        ORDER BY qtd DESC
    """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def buscar_investimento_mensal(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    # O gráfico financeiro mensal deve englobar o funil real, tirando cancelamentos absolutos (que não cobram)
    where_clause += f"{complemento_where} UPPER(TRIM(fc.validacao)) NOT IN ('REAGENDADO', 'CANCELADO')"

    query = text(
        f"""
        SELECT 
            TO_CHAR(TO_DATE(fc.inicio_1, 'DD/MM/YYYY'), 'MM/YYYY') AS mes_ano,
            DATE_TRUNC('month', TO_DATE(fc.inicio_1, 'DD/MM/YYYY')) AS mes_dt,
            COUNT(DISTINCT fc.processo) AS turmas,
            SUM(CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC)) AS investimento
        FROM public.fato_comercial fc
        {where_clause}
        GROUP BY mes_ano, mes_dt
        ORDER BY mes_dt ASC
        LIMIT 12
    """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def buscar_proximas_turmas(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    # A tabela exibe turmas Agendadas (Confirmado) ou Lançadas (Branco) cujo início seja > Hoje
    where_clause += f"{complemento_where} (UPPER(TRIM(fc.validacao)) = 'CONFIRMADO' OR fc.validacao IS NULL OR TRIM(fc.validacao) = '') AND TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY') > CURRENT_DATE"

    query = text(
        f"""
        SELECT 
            fc.inicio_1 AS inicio,
            fc.grupo AS grupo,
            fc.cod_treinamento AS treinamento,
            fc.unidade AS unidade,
            fc.instrutor_1 AS instrutor,
            CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) AS valor
        FROM public.fato_comercial fc
        {where_clause}
        ORDER BY TO_DATE(fc.inicio_1, 'DD/MM/YYYY') ASC
        LIMIT 20
    """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def buscar_ranking_instrutores(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    
    where_clause += f"{complemento_where} {regra_operacional} AND fc.instrutor_1 IS NOT NULL AND fc.instrutor_1 != ''"

    query = text(
        f"""
        WITH DadosTreinamento AS (
            SELECT 
                processo, 
                COUNT(DISTINCT NULLIF(TRIM(CAST(nome_do_participante AS TEXT)), '')) AS qtd_pessoas,
                AVG(CAST(NULLIF(REGEXP_REPLACE(REPLACE(CAST(aval_final AS TEXT), ',', '.'), '[^0-9.]', '', 'g'), '') AS NUMERIC)) AS media_turma
            FROM public.fato_treinamentos
            GROUP BY processo
        )
        SELECT 
            fc.instrutor_1 AS instrutor,
            COUNT(DISTINCT fc.processo) AS turmas_realizadas,
            
            -- Pessoas treinadas (Base REAL)
            SUM(COALESCE(dt.qtd_pessoas, 0)) AS pessoas_treinadas,
            
            -- Média da turma
            AVG(dt.media_turma) AS nota_media
            
        FROM public.fato_comercial fc
        LEFT JOIN DadosTreinamento dt ON fc.processo = dt.processo
        {where_clause}
        GROUP BY fc.instrutor_1
        ORDER BY turmas_realizadas DESC
    """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)