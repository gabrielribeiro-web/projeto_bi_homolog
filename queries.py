from datetime import date
import pandas as pd
from sqlalchemy import text
import streamlit as st

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

    # ==============================================================
    # TRAVA DE SEGURANÇA: EXCLUSIVIDADE PRESENCIAL
    # ==============================================================
    # Como as regras financeiras e SLAs foram mapeadas estritamente para 
    # a operação presencial, o sistema filtrará APENAS 'PRESENCIAL', 
    # barrando EAD, On-line e Híbrido, independentemente do botão clicado.
    condicoes.append("UPPER(TRIM(fc.modalidade)) = 'PRESENCIAL'")

    where_clause = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return where_clause, params


@st.cache_data(ttl=600, show_spinner=False)
def buscar_kpis(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    col_data = "fc.dt_termino_presencial"

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
            
            -- BLINDAGEM: Exclui cancelados/reagendados do cálculo do gargalo financeiro
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
    """)
    with _engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


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
def buscar_motor_faturamento(_engine, grupo_cliente, unidade, data_inicio, data_fim, modo_visao):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    
    sql = f"""
    WITH base AS (
        SELECT 
            fc.processo AS id_processo, 
            fc.grupo, 
            fc.cliente, 
            fc.unidade, 
            fc.modalidade,
            COALESCE(fc.valor_turma, 0) AS valor_total,
            -- RF03: Tratamento de status vazio para "Em Programação"
            COALESCE(NULLIF(TRIM(fc.validacao), ''), 'Em Programação') AS validacao,
            fc.status_comercial,
            fc.dt_inicio_presencial AS data_inicio,
            fc.dt_termino_presencial AS data_termino,
            COALESCE(cli.faturamento, 'MEDIÇÃO') AS tipo_faturamento,
            f.nota_fiscal, 
            f.data_faturamento AS data_emissao, 
            f.data_vencimento, 
            f.data_pagamento,
            fc.pedido_de_compra AS pedido_compra,
            fc.folha_de_servico AS folha_servico 
        FROM mv_fato_comercial_tratada fc 
        LEFT JOIN fato_faturamento f ON fc.processo = f.processo
        LEFT JOIN dim_clientes cli ON fc.cod_cliente = cli.cod_cliente
        {where_clause}
    ),
    logica_datas AS (
        SELECT 
            *,
            -- RF07 e RF13: D e D+1
            data_inicio AS data_d,
            (data_inicio + INTERVAL '1 day')::date AS data_d_mais_1,
            
            -- RF15 a RF18: Ciclo Mensal de Medição
            (DATE_TRUNC('month', data_inicio) + INTERVAL '1 month')::date AS mes_subsequente_inicio,
            (DATE_TRUNC('month', data_inicio) + INTERVAL '1 month' + INTERVAL '9 days')::date AS limite_medicao_interna,
            (DATE_TRUNC('month', data_inicio) + INTERVAL '2 months' - INTERVAL '1 day')::date AS limite_validacao_cliente,
            
            -- Tratamento de datas do Financeiro
            to_date(NULLIF(TRIM(data_emissao), ''), 'DD/MM/YYYY') AS dt_emissao_nf,
            to_date(NULLIF(TRIM(data_vencimento), ''), 'DD/MM/YYYY') AS dt_vencimento_nf,
            to_date(NULLIF(TRIM(data_pagamento), ''), 'DD/MM/YYYY') AS dt_pagamento_nf
        FROM base
    )
    SELECT 
        *,
        CASE 
            WHEN UPPER(validacao) IN ('CANCELADO DIA', 'CANCELADO 24H') THEN 'Cancelado com Cobrança'
            WHEN UPPER(validacao) = 'CANCELADO' THEN 'Cancelado'
            WHEN UPPER(validacao) = 'REAGENDADO' THEN 'Reagendado'
            WHEN UPPER(validacao) = 'FATURAR' THEN 'Liberado para Faturamento'
            WHEN CURRENT_DATE >= data_d_mais_1 THEN 'Realizado'
            WHEN UPPER(validacao) = 'CONFIRMADO' THEN 'Confirmado'
            ELSE 'Em Programação'
        END AS status_operacional,
        
        CASE
            WHEN UPPER(validacao) IN ('CANCELADO', 'REAGENDADO') THEN 'Não Cobrável'
            WHEN UPPER(validacao) = 'FATURAR' THEN 'Liberado para NF'
            WHEN UPPER(tipo_faturamento) = 'PONTUAL' THEN
                CASE 
                    WHEN CURRENT_DATE = data_d THEN 'Cobrável em D'
                    WHEN CURRENT_DATE >= data_d_mais_1 THEN 'Faturamento pendente - prazo vencido'
                    ELSE 'Aguardando data de realização'
                END
            ELSE 
                CASE
                    WHEN CURRENT_DATE < mes_subsequente_inicio THEN 'Aguardando virada do mês'
                    WHEN CURRENT_DATE <= limite_medicao_interna THEN 'Medição em processamento'
                    WHEN CURRENT_DATE <= limite_validacao_cliente THEN 'Aguardando validação do cliente'
                    ELSE 'Medição em atraso cliente'
                END
        END AS status_medicao,
        
        CASE 
            WHEN UPPER(validacao) = 'FATURAR' THEN 0
            WHEN UPPER(tipo_faturamento) = 'PONTUAL' AND CURRENT_DATE >= data_d_mais_1 THEN (CURRENT_DATE - data_d_mais_1)
            WHEN UPPER(tipo_faturamento) != 'PONTUAL' AND CURRENT_DATE > limite_validacao_cliente THEN (CURRENT_DATE - limite_validacao_cliente)
            ELSE 0
        END AS dias_atraso_medicao,

        CASE
            WHEN UPPER(validacao) IN ('CANCELADO', 'REAGENDADO') THEN 'N/A'
            WHEN dt_emissao_nf IS NULL AND UPPER(validacao) = 'FATURAR' THEN 'Aguardando emissão de NF'
            WHEN dt_emissao_nf IS NULL THEN 'NF Não Emitida'
            WHEN dt_pagamento_nf IS NOT NULL THEN
                CASE WHEN dt_pagamento_nf <= dt_vencimento_nf THEN 'Pago no Prazo' ELSE 'Pago com Atraso' END
            WHEN CURRENT_DATE <= dt_vencimento_nf THEN 'A vencer / Em aberto'
            ELSE 'Pagamento em Atraso'
        END AS status_pagamento,
        
        CASE
            WHEN dt_emissao_nf IS NOT NULL AND dt_pagamento_nf IS NULL AND CURRENT_DATE > dt_vencimento_nf THEN (CURRENT_DATE - dt_vencimento_nf)
            WHEN dt_emissao_nf IS NOT NULL AND dt_pagamento_nf IS NOT NULL AND dt_pagamento_nf > dt_vencimento_nf THEN (dt_pagamento_nf - dt_vencimento_nf)
            ELSE 0
        END AS dias_atraso_pagamento,
        
        CASE 
            WHEN dt_emissao_nf IS NULL AND UPPER(validacao) = 'FATURAR' THEN 'Financeiro'
            WHEN dt_emissao_nf IS NOT NULL AND dt_pagamento_nf IS NULL AND CURRENT_DATE > dt_vencimento_nf THEN 'Cliente'
            WHEN UPPER(validacao) != 'FATURAR' THEN
                CASE 
                    WHEN UPPER(tipo_faturamento) != 'PONTUAL' AND CURRENT_DATE BETWEEN mes_subsequente_inicio AND limite_medicao_interna THEN 'Gestão de Contratos / Interno'
                    WHEN UPPER(tipo_faturamento) != 'PONTUAL' AND CURRENT_DATE > limite_medicao_interna THEN 'Cliente'
                    WHEN UPPER(tipo_faturamento) = 'PONTUAL' AND CURRENT_DATE >= data_d_mais_1 THEN 'Gestão de Contratos / Interno'
                    ELSE 'Gestão de Contratos / Interno'
                END
            ELSE 'Nenhum'
        END AS responsavel_acao

    FROM logica_datas
    """
    
    return pd.read_sql_query(text(sql), _engine, params=params)

@st.cache_data(ttl=600, show_spinner=False)
def buscar_analise_margem(_engine, grupo_cliente=None, unidade=None, data_inicio=None, data_fim=None, modo_visao="Presencial"):
    where_clause, params = _construir_filtros(grupo_cliente, unidade, data_inicio, data_fim, modo_visao)
    complemento_where = " AND " if where_clause else " WHERE "
    
    query = text(f"""
        SELECT 
            fc.processo,
            fc.cliente,
            fc.instrutor_1 AS instrutor,
            COALESCE(fc.valor_turma, 0) AS receita,
            fc.instrutor_1_total,
            fc.instrutor_2_total,
            fc.validacao,
            fc.status_comercial
        FROM public.mv_fato_comercial_tratada fc
        {where_clause} {complemento_where} 
            UPPER(fc.validacao) NOT IN ('CANCELADO', 'REAGENDADO') 
            AND UPPER(fc.status_comercial) NOT IN ('CANCELADO', 'REAGENDADO')
    """)
    
    with _engine.connect() as conn:
        df = pd.read_sql_query(query, conn, params=params)
        
        def limpar_moeda(val):
            if pd.isna(val) or val == '': return 0.0
            if isinstance(val, (int, float)): return float(val)
            v_str = str(val).replace('R$', '').strip()
            if ',' in v_str and '.' in v_str:
                v_str = v_str.replace('.', '').replace(',', '.')
            elif ',' in v_str:
                v_str = v_str.replace(',', '.')
            try:
                return float(v_str)
            except:
                return 0.0
                
        if not df.empty:
            if 'instrutor_1_total' not in df.columns: df['instrutor_1_total'] = 0.0
            if 'instrutor_2_total' not in df.columns: df['instrutor_2_total'] = 0.0
            
            df['receita'] = df['receita'].apply(limpar_moeda)
            df = df[df['receita'] > 0].copy()
            
            if not df.empty:
                df['custo_instrutor_1'] = df['instrutor_1_total'].apply(limpar_moeda)
                df['custo_instrutor_2'] = df['instrutor_2_total'].apply(limpar_moeda)
                
                df['custo_impostos_comissao'] = df['receita'] * 0.25
                df['custo_fixo'] = 400.0
                
                df['custo_total'] = (
                    df['custo_impostos_comissao'] + 
                    df['custo_fixo'] + 
                    df['custo_instrutor_1'] + 
                    df['custo_instrutor_2']
                )
                
                df['margem_lucro'] = df['receita'] - df['custo_total']
                df['margem_percentual'] = (df['margem_lucro'] / df['receita']) * 100
                
        return df