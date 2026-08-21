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
    complemento_where = " AND " if where_clause else " WHERE "
    
    # Garante que só puxe linhas que tenham data de início preenchida
    where_clause += f"{complemento_where} fc.inicio_1 IS NOT NULL AND TRIM(fc.inicio_1) != ''"

    query = text(f"""
        WITH DadosTreinamento AS (
            SELECT 
                processo, 
                -- Conta apenas os nomes distintos (reais) por turma
                COUNT(DISTINCT NULLIF(TRIM(CAST(nome_do_participante AS TEXT)), '')) AS qtd_pessoas,
                -- Tira a média da nota final
                AVG(CAST(NULLIF(REGEXP_REPLACE(REPLACE(CAST(aval_final AS TEXT), ',', '.'), '[^0-9.]', '', 'g'), '') AS NUMERIC)) AS media_turma
            FROM public.fato_treinamentos
            GROUP BY processo
        )
        SELECT 
            -- 1. FATURAMENTO REALIZADO (Trava: status OK e data de início MENOR OU IGUAL a HOJE)
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') 
                          AND UPPER(TRIM(fc.status_comercial)) = 'OK'
                          AND TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS total_faturado,
            
            -- 2. FUTURO AGENDADO (Trava: data estritamente MAIOR que HOJE)
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) = 'CONFIRMADO' 
                          AND TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY') > CURRENT_DATE
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS futuro_agendado,
            
            -- 3. FUTURO LANÇADO (Trava: data estritamente MAIOR que HOJE)
            SUM(CASE WHEN (fc.validacao IS NULL OR TRIM(fc.validacao) = '') 
                          AND TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY') > CURRENT_DATE
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS futuro_lancado,
            
            -- 4. PENDÊNCIA / GARGALO
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') 
                          AND (fc.status_comercial IS NULL OR UPPER(TRIM(fc.status_comercial)) != 'OK')
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS total_pendencia,
            
            -- 5. TURMAS REALIZADAS (Trava: data de término MENOR OU IGUAL a HOJE)
            COUNT(DISTINCT CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE 
                THEN fc.processo END) AS turmas_realizadas,
            
            -- 6. HORAS DE TREINAMENTO (Trava: data de término MENOR OU IGUAL a HOJE)
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE 
                THEN COALESCE(
                     CAST(NULLIF(REGEXP_REPLACE(CAST(fc.ch_formacao AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC),
                     CAST(NULLIF(REGEXP_REPLACE(CAST(fc.ch_reciclagem AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC), 
                     0) ELSE 0 END) AS horas_realizadas,
            
            -- 7. PESSOAS TREINADAS (Trava: data de término MENOR OU IGUAL a HOJE)
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE 
                THEN COALESCE(dt.qtd_pessoas, 0) ELSE 0 END) AS pessoas_treinadas,
            
            -- 8. APROVEITAMENTO MÉDIO (Trava: data de término MENOR OU IGUAL a HOJE)
            AVG(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE 
                THEN dt.media_turma END) AS aproveitamento_medio,
            
            -- 9. UNIDADES ATENDIDAS (Trava: data de término MENOR OU IGUAL a HOJE)
            COUNT(DISTINCT CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') 
                                 AND NULLIF(fc.processo, '') IS NOT NULL 
                                 AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE 
                THEN fc.unidade END) AS unidades_atendidas

        FROM public.fato_comercial fc
        LEFT JOIN DadosTreinamento dt ON fc.processo = dt.processo
        {where_clause}
    """)
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


# Para garantir que todos os gráficos operacionais sigam a mesma regra exata da liderança:
regra_operacional = " UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR') AND NULLIF(fc.processo, '') IS NOT NULL AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') < CURRENT_DATE "


def buscar_grafico_nrs(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    where_clause += f"{complemento_where} fc.termino_1 IS NOT NULL AND TRIM(fc.termino_1) != '' AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE"

    query = text(f"""
        SELECT 
            COALESCE(NULLIF(TRIM(cod_treinamento), ''), 'OUTROS') AS nr,
            COUNT(DISTINCT processo) AS quantidade
        FROM public.fato_comercial fc
        {where_clause}
        AND UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
        GROUP BY nr
        ORDER BY quantidade DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def buscar_distribuicao_tipo(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    where_clause += f"{complemento_where} fc.termino_1 IS NOT NULL AND TRIM(fc.termino_1) != '' AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE"

    query = text(f"""
        SELECT 
            COALESCE(NULLIF(TRIM(modalidade), ''), 'NÃO INFORMADO') AS tipo,
            COUNT(DISTINCT processo) AS quantidade
        FROM public.fato_comercial fc
        {where_clause}
        AND UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
        GROUP BY tipo
        ORDER BY quantidade DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def buscar_investimento_mensal(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    where_clause += f"{complemento_where} fc.inicio_1 IS NOT NULL AND TRIM(fc.inicio_1) != ''"

    query = text(f"""
        SELECT 
            TO_CHAR(TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY'), 'MM/YYYY') AS mes_ano,
            TO_CHAR(TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY'), 'YYYY-MM') AS sort_date,
            
            -- Soma apenas o que já aconteceu (Data <= Hoje)
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('FATURAR', 'CANCELADO DIA', 'CANCELADO 24H') 
                          AND UPPER(TRIM(fc.status_comercial)) = 'OK'
                          AND TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS "Faturamento Realizado",
                
            -- Soma o que está para o futuro (Data > Hoje) para a linha de "Projetado"
            SUM(CASE WHEN UPPER(TRIM(fc.validacao)) IN ('CONFIRMADO', '') 
                          AND TO_DATE(NULLIF(fc.inicio_1, ''), 'DD/MM/YYYY') > CURRENT_DATE
                THEN CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) ELSE 0 END) AS "Faturamento Projetado"
                
        FROM public.fato_comercial fc
        {where_clause}
        GROUP BY 1, 2
        ORDER BY 2
    """)
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def buscar_proximas_turmas(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    
    # Regra estrita da liderança: APENAS Confirmado + Data Início > Hoje
    where_clause += f"{complemento_where} UPPER(TRIM(fc.validacao)) = 'CONFIRMADO' AND NULLIF(fc.inicio_1, '') IS NOT NULL AND TO_DATE(fc.inicio_1, 'DD/MM/YYYY') > CURRENT_DATE"

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
    
    # Aplica a trava de data direto no filtro base
    where_clause += f"{complemento_where} fc.termino_1 IS NOT NULL AND TRIM(fc.termino_1) != '' AND TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') <= CURRENT_DATE"

    query = text(f"""
        WITH DadosTreinamento AS (
            SELECT 
                processo, 
                COUNT(DISTINCT NULLIF(TRIM(CAST(nome_do_participante AS TEXT)), '')) AS qtd_pessoas, -- Ajuste para 'nome' se você mudou no banco
                AVG(CAST(NULLIF(REGEXP_REPLACE(REPLACE(CAST(aval_final AS TEXT), ',', '.'), '[^0-9.]', '', 'g'), '') AS NUMERIC)) AS media_turma
            FROM public.fato_treinamentos
            GROUP BY processo
        )
        SELECT 
            fc.instrutor_1 AS instrutor,
            COUNT(DISTINCT fc.processo) AS turmas_realizadas,
            SUM(COALESCE(dt.qtd_pessoas, 0)) AS pessoas_treinadas,
            AVG(dt.media_turma) AS nota_media
        FROM public.fato_comercial fc
        LEFT JOIN DadosTreinamento dt ON fc.processo = dt.processo
        {where_clause}
          AND UPPER(TRIM(fc.validacao)) IN ('CANCELADO 24H', 'CANCELADO DIA', 'CONFIRMADO', 'FATURAR')
          AND fc.instrutor_1 IS NOT NULL AND TRIM(fc.instrutor_1) != ''
        GROUP BY fc.instrutor_1
        ORDER BY turmas_realizadas DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)

def buscar_detalhamento_financeiro(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "
    
    # Trazemos tudo que não seja cancelamento absoluto, para o financeiro ver o funil real
    where_clause += f"{complemento_where} UPPER(TRIM(fc.validacao)) NOT IN ('REAGENDADO', 'CANCELADO')"

    query = text(
        f"""
        SELECT 
            fc.processo AS "Processo",
            fc.grupo AS "Grupo",
            fc.unidade AS "Unidade",
            fc.termino_1 AS "Data Término",
            UPPER(TRIM(fc.validacao)) AS "Validação (Operação)",
            COALESCE(UPPER(TRIM(fc.status_comercial)), 'PENDENTE') AS "Status Comercial",
            CAST(NULLIF(REGEXP_REPLACE(CAST(fc.valor AS TEXT), '[^0-9.]', '', 'g'), '') AS NUMERIC) AS "Valor (R$)"
        FROM public.fato_comercial fc
        {where_clause}
        ORDER BY TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') DESC
    """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)

def buscar_lista_participantes(engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim)
    complemento_where = " AND " if where_clause else " WHERE "

    where_clause += f"{complemento_where} {regra_operacional} AND ft.nome_do_participante IS NOT NULL AND TRIM(CAST(ft.nome_do_participante AS TEXT)) != ''"

    query = text(
        f"""
        SELECT 
            ft.nome_do_participante AS "Nome do Participante",
            ft.cpf AS "CPF",
            fc.grupo AS "Grupo", -- <--- ADICIONE ESTA LINHA AQUI
            ft.nr AS "Treinamento (NR)",
            ft.tipo AS "Tipo",
            fc.termino_1 AS "Data Conclusão",
            fc.unidade AS "Unidade"
        FROM public.fato_treinamentos ft
        INNER JOIN public.fato_comercial fc ON ft.processo = fc.processo
        {where_clause}
        ORDER BY TO_DATE(NULLIF(fc.termino_1, ''), 'DD/MM/YYYY') DESC, ft.nome_do_participante ASC
    """
    )
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)