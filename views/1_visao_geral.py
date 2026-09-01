import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from components import renderizar_filtros, get_hover_style
from queries import (
    buscar_kpis,
    buscar_investimento_mensal,
    buscar_distribuicao_tipo,
    buscar_grafico_nrs,
    buscar_motor_faturamento,
    buscar_proximas_turmas
)

engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros()
hover_style = get_hover_style()

st.markdown("### 💼 Visão Executiva - Presencial")
st.caption("Acompanhamento gerencial de previsão, medições, faturamento e recebimentos.")

# ==============================================================
# GUIA EXPLICATIVO DE REGRAS E NOMENCLATURAS (LEGENDA OPERACIONAL)
# ==============================================================
with st.expander("📖 Guia de Entendimento dos Indicadores e Status", expanded=False):
    st.markdown("""
    **📍 Linha do Tempo Operacional & Validações:**
    - **Previsão Futura:** Turmas confirmadas com término previsto em datas futuras (ainda não cobráveis)[cite: 1].
    - **Medição em Compilação:** Turmas do mês anterior sob responsabilidade da equipe interna para fechamento (Dias 01 a 10)[cite: 1].
    - **Em Análise no Cliente:** Medições enviadas para validação formal do cliente dentro do prazo amigável (Dias 11 ao fim do mês)[cite: 1].
    - **Medição Atrasada no Cliente:** Medições de meses passados pendentes de aprovação após a virada do mês (Atraso crítico)[cite: 1].

    **💳 Linha do Tempo de Cobrança & Recebimento:**
    - **Cobrança Pontual Atrasada:** Treinamento do tipo Pontual concluído (D+1) sem avanço para faturamento[cite: 1].
    - **Aguardando Emissão de NF:** Processos validados pela operação (FATURAR) aguardando emissão da NF pelo Financeiro[cite: 1].
    - **Faturas a Vencer:** Notas Fiscais emitidas dentro do prazo regular de vencimento[cite: 1].
    - **Faturas Vencidas:** Notas Fiscais emitidas que ultrapassaram a data de vencimento sem confirmação de pagamento[cite: 1].
    - **Valores Recebidos:** Processos com pagamento quitado e baixado no sistema[cite: 1].
    """)

st.divider()

# BUSCA DE DADOS CACHEADOS
df_kpi = buscar_kpis(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
df_motor = buscar_motor_faturamento(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

if df_kpi.empty or df_motor.empty:
    st.info("Nenhum dado encontrado para os filtros selecionados.")
else:
    kpi = df_kpi.iloc[0]
    
    # Previsão Futura (Somente Processos Futuros)
    df_futuros = df_motor[
        (df_motor['validacao'].str.upper().isin(['CONFIRMADO', 'EM PROGRAMAÇÃO'])) & 
        (df_motor['data_termino'] > pd.Timestamp.now().date())
    ]
    v_futuro = df_futuros['valor_total'].sum() if not df_futuros.empty else (kpi['futuro_agendado'] + kpi['futuro_lancado'])
    q_futuro = len(df_futuros) if not df_futuros.empty else int(kpi['turmas_realizadas'])

    # Medição em Compilação (Interno) - Dias 01 a 10
    df_compilacao = df_motor[df_motor['status_medicao'] == 'Medição em processamento']
    v_compilacao = df_compilacao['valor_total'].sum()
    q_compilacao = len(df_compilacao)

    # Em Análise no Cliente - Dias 11 ao fim do mês
    df_analise_cli = df_motor[df_motor['status_medicao'] == 'Aguardando validação do cliente']
    v_analise_cli = df_analise_cli['valor_total'].sum()
    q_analise_cli = len(df_analise_cli)

    # Medição Atrasada no Cliente - Virada do mês
    df_med_atraso = df_motor[df_motor['status_medicao'] == 'Medição em atraso cliente']
    v_med_atraso = df_med_atraso['valor_total'].sum()
    q_med_atraso = len(df_med_atraso)
    dias_max_med = int(df_med_atraso['dias_atraso_medicao'].max()) if not df_med_atraso.empty else 0

    # Cobrança Pontual Atrasada (D+1)
    df_pontual_atraso = df_motor[df_motor['status_medicao'] == 'Faturamento pendente - prazo vencido']
    v_pontual_atraso = df_pontual_atraso['valor_total'].sum()
    q_pontual_atraso = len(df_pontual_atraso)
    dias_max_pontual = int(df_pontual_atraso['dias_atraso_medicao'].max()) if not df_pontual_atraso.empty else 0

    # Aguardando Emissão de NF
    df_ag_nf = df_motor[df_motor['status_pagamento'] == 'Aguardando emissão de NF']
    v_ag_nf = df_ag_nf['valor_total'].sum()
    q_ag_nf = len(df_ag_nf)

    # Faturas a Vencer
    df_a_vencer = df_motor[df_motor['status_pagamento'] == 'A vencer / Em aberto']
    v_a_vencer = df_a_vencer['valor_total'].sum()
    q_a_vencer = len(df_a_vencer)

    # Faturas Vencidas (Pagamento em Atraso)
    df_vencidos = df_motor[df_motor['status_pagamento'] == 'Pagamento em Atraso']
    v_vencidos = df_vencidos['valor_total'].sum()
    q_vencidos = len(df_vencidos)
    dias_max_venc = int(df_vencidos['dias_atraso_pagamento'].max()) if not df_vencidos.empty else 0

    # Valores Recebidos (Pago)
    df_pagos = df_motor[df_motor['status_pagamento'].str.contains('Pago', na=False)]
    v_pagos = df_pagos['valor_total'].sum()
    q_pagos = len(df_pagos)

    # ==============================================================
    # 1. RENDERIZAÇÃO DOS CARDS
    # ==============================================================
    st.markdown("##### 📍 Linha do Tempo Operacional e Validações")
    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "Previsão Futura",
        f"R$ {v_futuro:,.2f}",
        f"{q_futuro} processos",
        help="Turmas agendadas ou confirmadas com término previsto em datas futuras[cite: 1]."
    )
    m2.metric(
        "Medição em Compilação",
        f"R$ {v_compilacao:,.2f}",
        f"{q_compilacao} processos",
        help="Turmas do mês anterior sob responsabilidade interna da Operação (Dias 01 a 10)[cite: 1]."
    )
    m3.metric(
        "Em Análise no Cliente",
        f"R$ {v_analise_cli:,.2f}",
        f"{q_analise_cli} processos",
        help="Medições enviadas para conferência do cliente dentro do prazo amigável (Dias 11 ao fim do mês)[cite: 1]."
    )
    m4.metric(
        "Medição Atrasada no Cliente",
        f"R$ {v_med_atraso:,.2f}",
        f"{q_med_atraso} parc. (Até {dias_max_med} dias)",
        delta_color="inverse",
        help="Medições de meses passados pendentes de aprovação após a virada do mês[cite: 1]."
    )

    st.write("")

    st.markdown("##### 💳 Linha do Tempo de Cobrança e Recebimento")
    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric(
        "Cobrança Pontual Atrasada",
        f"R$ {v_pontual_atraso:,.2f}",
        f"{q_pontual_atraso} proc. (Até {dias_max_pontual} dias)",
        delta_color="inverse",
        help="Treinamento pontual concluído (D+1) sem avanço para liberação de NF[cite: 1]."
    )
    c2.metric(
        "Aguardando Emissão de NF",
        f"R$ {v_ag_nf:,.2f}",
        f"{q_ag_nf} processos",
        help="Processos liberados pela operação aguardando emissão da Nota Fiscal pelo Financeiro[cite: 1]."
    )
    c3.metric(
        "Faturas a Vencer",
        f"R$ {v_a_vencer:,.2f}",
        f"{q_a_vencer} processos",
        help="Notas Fiscais emitidas que estão dentro do prazo regular de vencimento[cite: 1]."
    )
    c4.metric(
        "Faturas Vencidas",
        f"R$ {v_vencidos:,.2f}",
        f"{q_vencidos} proc. (Até {dias_max_venc} dias)",
        delta_color="inverse",
        help="Notas Fiscais emitidas que ultrapassaram a data de vencimento sem confirmação de pagamento[cite: 1]."
    )
    c5.metric(
        "Valores Recebidos",
        f"R$ {v_pagos:,.2f}",
        f"{q_pagos} processos",
        help="Valores com pagamento confirmado e baixado no sistema[cite: 1]."
    )

    st.divider()

    # ==============================================================
    # 2. GRÁFICOS EXECUTIVOS DE PERFORMANCE (LINHA PONTILHADA NO PROJETADO)
    # ==============================================================
    g1, g2 = st.columns([1.6, 1])

    with g1:
        st.markdown("##### 📈 Evolução Mensal do Faturamento (Realizado vs. Projetado)")
        df_inv = buscar_investimento_mensal(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
        
        if not df_inv.empty:
            fig_inv = go.Figure()
            
            # Faturamento Realizado em Barras Verdes Querino
            fig_inv.add_trace(go.Bar(
                x=df_inv['mes_ano'],
                y=df_inv['Faturamento Realizado'],
                name='Faturamento Realizado',
                marker_color='#aecb36'
            ))
            
            # Faturamento Projetado em Linha Pontilhada Escura
            fig_inv.add_trace(go.Scatter(
                x=df_inv['mes_ano'],
                y=df_inv['Faturamento Projetado'],
                name='Faturamento Projetado',
                mode='lines+markers',
                line=dict(color='#1a1e38', width=3, dash='dash'),
                marker=dict(size=8, color='#1a1e38')
            ))
            
            fig_inv.update_layout(
                margin=dict(l=20, r=20, t=30, b=20),
                height=320,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hoverlabel=hover_style,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_inv, use_container_width=True)
        else:
            st.info("Sem dados de evolução mensal para os filtros selecionados.")

    with g2:
        st.markdown("##### 🎓 Top Treinamentos por Categoria (NRs)")
        df_nrs = buscar_grafico_nrs(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
        
        if not df_nrs.empty:
            fig_nrs = px.bar(
                df_nrs.head(7),
                x='quantidade',
                y='nr',
                orientation='h',
                color_discrete_sequence=['#aecb36']
            )
            fig_nrs.update_layout(
                margin=dict(l=20, r=20, t=30, b=20),
                height=320,
                yaxis=dict(autorange="reversed"),
                xaxis_title="Qtd. Turmas",
                yaxis_title=None,
                hoverlabel=hover_style,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_nrs, use_container_width=True)
        else:
            st.info("Sem dados de treinamentos para os filtros selecionados.")

    st.divider()

    # ==============================================================
    # 3. NOVOS GRÁFICOS: TOP GRUPOS & DISTRIBUIÇÃO DE MODALIDADE
    # ==============================================================
    g3, g4 = st.columns([1.3, 1])

    with g3:
        st.markdown("##### 🏢 Top 5 Grupos / Clientes por Faturamento")
        if not df_motor.empty:
            df_top_grupos = (
                df_motor.groupby('grupo')['valor_total']
                .sum()
                .reset_index()
                .sort_values(by='valor_total', ascending=False)
                .head(5)
            )
            fig_top_g = px.bar(
                df_top_grupos,
                x='valor_total',
                y='grupo',
                orientation='h',
                text_auto='.2s',
                color_discrete_sequence=['#1a1e38']
            )
            fig_top_g.update_layout(
                margin=dict(l=20, r=20, t=30, b=20),
                height=280,
                yaxis=dict(autorange="reversed"),
                xaxis_title="Valor Total (R$)",
                yaxis_title=None,
                hoverlabel=hover_style,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_top_g, use_container_width=True)
        else:
            st.info("Sem dados de grupos para exibir.")

    with g4:
        st.markdown("##### 📊 Distribuição por Modalidade")
        df_mod = buscar_distribuicao_tipo(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
        if not df_mod.empty:
            fig_mod = px.pie(
                df_mod,
                names='tipo',
                values='quantidade',
                hole=0.5,
                color_discrete_sequence=['#aecb36', '#1a1e38', '#4b5563', '#da2c38']
            )
            fig_mod.update_layout(
                margin=dict(l=20, r=20, t=30, b=20),
                height=280,
                hoverlabel=hover_style,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_mod, use_container_width=True)
        else:
            st.info("Sem dados de modalidade para exibir.")

    st.divider()

    # ==============================================================
    # 4. TABELA DE PRÓXIMAS TURMAS CONFIRMADAS
    # ==============================================================
    st.markdown("##### 📅 Próximas Turmas Programadas")
    df_proximas = buscar_proximas_turmas(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

    if not df_proximas.empty:
        col_config_prox = {
            "inicio": st.column_config.TextColumn("Data Início", width="small"),
            "grupo": st.column_config.TextColumn("Grupo", width="medium"),
            "unidade": st.column_config.TextColumn("Unidade", width="medium"),
            "treinamento": st.column_config.TextColumn("Treinamento / NR", width="medium"),
            "instrutor": st.column_config.TextColumn("Instrutor", width="medium"),
            "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f")
        }
        st.dataframe(
            df_proximas,
            use_container_width=True,
            hide_index=True,
            column_config=col_config_prox,
            height=280
        )
    else:
        st.info("Nenhuma próxima turma agendada no momento.")