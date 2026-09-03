import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from components import renderizar_filtros, get_hover_style, render_query_admin
from queries import (
    buscar_kpis,
    buscar_investimento_mensal,
    buscar_distribuicao_tipo,
    buscar_grafico_nrs,
    buscar_motor_faturamento,
    buscar_proximas_turmas,
    sql_motor_faturamento_debug,
    sql_kpis_debug,
    sql_card_wrap,
)

engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros()
hover_style = get_hover_style()

# Verifica se é admin (A mesma verificação feita nas outras telas)
is_admin = user.get("perfil") == "admin"

st.markdown("### 🏢 Portal do Cliente — Gestão de Capacitação")
st.caption("Acompanhamento gerencial de treinamentos, medições, investimentos e status de atendimento.")

# ==============================================================
# GUIA EXPLICATIVO DE REGRAS E NOMENCLATURAS (NOMENCLATURA CLIENTE)
# ==============================================================
with st.expander("📖 Guia de Entendimento dos Indicadores e Status", expanded=False):
    st.markdown('''
    **📍 Linha do Tempo Operacional & Validações:**
    - **Previsão Futura:** Turmas confirmadas com término previsto em datas futuras.
    - **Medição em Compilação:** Turmas do mês anterior em fase de fechamento de documentação (Dias 01 a 10).
    - **Validação Pendente no Cliente:** Medições enviadas para conferência e aprovação da sua equipe (Dias 11 ao fim do mês).
    - **Medição em Atraso de Envio:** Medições de meses passados pendentes de aprovação ou emissão de Pedido de Compra (PO/FS).

    **💳 Linha do Tempo de Cobrança & Recebimento:**
    - **Validação Pendente (Pontual):** Treinamento do tipo Pontual concluído aguardando liberação para NF.
    - **Aguardando Emissão de NF:** Processos validados pela operação aguardando emissão da Nota Fiscal.
    - **Faturas a Vencer:** Notas Fiscais emitidas dentro do prazo regular de vencimento.
    - **Faturas Vencidas:** Notas Fiscais emitidas que ultrapassaram a data de vencimento.
    - **Pagamentos Confirmados:** Processos com pagamento quitado e baixado no sistema.
    ''')

st.divider()

# BUSCA DE DADOS CACHEADOS (MOTOR REFINADO)
df_kpi = buscar_kpis(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
df_motor = buscar_motor_faturamento(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

if df_kpi.empty or df_motor.empty:
    st.info("Nenhum dado encontrado para os filtros selecionados.")
else:
    kpi = df_kpi.iloc[0]
    
    # Função auxiliar para somar valor_total baseado na etapa_principal do Motor
    def get_valor_etapa(etapa):
        return df_motor[df_motor['etapa_principal'] == etapa]['valor_total'].sum()

    def get_qtd_etapa(etapa):
        return len(df_motor[df_motor['etapa_principal'] == etapa])

    # ==============================================================
    # 1. RENDERIZAÇÃO DOS CARDS (NOMENCLATURA REFINADA)
    # ==============================================================
    st.markdown("##### 📍 Linha do Tempo Operacional e Validações")
    m1, m2, m3, m4 = st.columns(4)

    # Restaura o fallback de KPIs globais para quando o filtro de data secar o motor
    df_futuros = df_motor[df_motor['etapa_principal'] == 'PREVISAO']
    v_futuro = df_futuros['valor_total'].sum() if not df_futuros.empty else float(kpi['futuro_agendado'] + kpi['futuro_lancado'])
    q_futuro = len(df_futuros) if not df_futuros.empty else int(kpi['turmas_realizadas']) # Mantido do código legado

    m1.metric(
        "Previsão Futura", 
        f"R$ {v_futuro:,.2f}", 
        f"{q_futuro} processos",
        help="Turmas agendadas ou confirmadas com término previsto em datas futuras."
    )
    
    m2.metric(
        "Medição em Compilação", 
        f"R$ {get_valor_etapa('MEDICAO_EM_PROCESSAMENTO'):,.2f}", 
        f"{get_qtd_etapa('MEDICAO_EM_PROCESSAMENTO')} processos",
        help="Turmas do mês anterior em fase de organização e compilação documental (Dias 01 a 10)."
    )
    m3.metric(
        "Validação de Medição Pendente", 
        f"R$ {get_valor_etapa('AGUARDANDO_CLIENTE'):,.2f}", 
        f"{get_qtd_etapa('AGUARDANDO_CLIENTE')} processos",
        help="Medições enviadas para conferência e validação da sua equipe (Dias 11 ao fim do mês)."
    )
    
    med_atraso_dias = df_motor[df_motor['etapa_principal'] == 'MEDICAO_EM_ATRASO']['dias_atraso_medicao'].max()
    m4.metric(
        "Medição em Atraso de Envio", 
        f"R$ {get_valor_etapa('MEDICAO_EM_ATRASO'):,.2f}", 
        f"{get_qtd_etapa('MEDICAO_EM_ATRASO')} parc. (Até {int(med_atraso_dias) if pd.notna(med_atraso_dias) else 0} dias)", 
        delta_color="inverse",
        help="Medições de meses passados pendentes de aprovação ou emissão de Pedido de Compra (PO/FS)."
    )

    st.write("")

    st.markdown("##### 💳 Linha do Tempo de Cobrança e Recebimento")
    c1, c2, c3, c4, c5 = st.columns(5)

    pontual_atraso_dias = df_motor[df_motor['etapa_principal'] == 'FATURAMENTO_PENDENTE']['dias_atraso_medicao'].max()
    c1.metric(
        "Validação Pendente (Pontual)", 
        f"R$ {get_valor_etapa('FATURAMENTO_PENDENTE'):,.2f}", 
        f"{get_qtd_etapa('FATURAMENTO_PENDENTE')} proc. (Até {int(pontual_atraso_dias) if pd.notna(pontual_atraso_dias) else 0} dias)", 
        delta_color="inverse",
        help="Treinamento pontual concluído (D+1) aguardando liberação para faturamento."
    )
    
    c2.metric(
        "Aguardando Emissão de NF", 
        f"R$ {get_valor_etapa('AGUARDANDO_NF'):,.2f}", 
        f"{get_qtd_etapa('AGUARDANDO_NF')} processos",
        help="Processos validados pela operação aguardando emissão da Nota Fiscal pelo Financeiro."
    )
    c3.metric(
        "Faturas a Vencer", 
        f"R$ {get_valor_etapa('A_VENCER'):,.2f}", 
        f"{get_qtd_etapa('A_VENCER')} processos",
        help="Notas Fiscais emitidas dentro do prazo regular de vencimento."
    )
    
    vencidas_dias = df_motor[df_motor['etapa_principal'] == 'PAGAMENTO_EM_ATRASO']['dias_atraso_pagamento'].max()
    c4.metric(
        "Faturas Vencidas", 
        f"R$ {get_valor_etapa('PAGAMENTO_EM_ATRASO'):,.2f}", 
        f"{get_qtd_etapa('PAGAMENTO_EM_ATRASO')} proc. (Até {int(vencidas_dias) if pd.notna(vencidas_dias) else 0} dias)", 
        delta_color="inverse",
        help="Notas Fiscais emitidas que ultrapassaram a data de vencimento."
    )
    
    v_pagos = get_valor_etapa('PAGO') + get_valor_etapa('PAGO_CANCELAMENTO')
    q_pagos = get_qtd_etapa('PAGO') + get_qtd_etapa('PAGO_CANCELAMENTO')
    c5.metric(
        "Pagamentos Confirmados", 
        f"R$ {v_pagos:,.2f}", 
        f"{q_pagos} processos",
        help="Valores com pagamento confirmado e quitado no sistema."
    )

    # ==============================================================
    # BLOCO ADMIN: QUERIES DE VALIDAÇÃO POR CARD (TEMPORÁRIO)
    # ==============================================================
    sql_base_motor = sql_motor_faturamento_debug(grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
    sql_base_kpis = sql_kpis_debug(grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

    render_query_admin({
        "Previsão Futura": sql_card_wrap(
            sql_base_motor, "Previsão Futura",
            "motor.etapa_principal = 'PREVISAO'"
        ),
        "Medição em Compilação": sql_card_wrap(
            sql_base_motor, "Medição em Compilação",
            "motor.etapa_principal = 'MEDICAO_EM_PROCESSAMENTO'"
        ),
        "Validação de Medição Pendente": sql_card_wrap(
            sql_base_motor, "Validação de Medição Pendente",
            "motor.etapa_principal = 'AGUARDANDO_CLIENTE'"
        ),
        "Medição em Atraso de Envio": sql_card_wrap(
            sql_base_motor, "Medição em Atraso de Envio",
            "motor.etapa_principal = 'MEDICAO_EM_ATRASO'"
        ),
        "Validação Pendente (Pontual)": sql_card_wrap(
            sql_base_motor, "Validação Pendente (Pontual)",
            "motor.etapa_principal = 'FATURAMENTO_PENDENTE'"
        ),
        "Aguardando Emissão de NF": sql_card_wrap(
            sql_base_motor, "Aguardando Emissão de NF",
            "motor.etapa_principal = 'AGUARDANDO_NF'"
        ),
        "Faturas a Vencer": sql_card_wrap(
            sql_base_motor, "Faturas a Vencer",
            "motor.etapa_principal = 'A_VENCER'"
        ),
        "Faturas Vencidas": sql_card_wrap(
            sql_base_motor, "Faturas Vencidas",
            "motor.etapa_principal = 'PAGAMENTO_EM_ATRASO'"
        ),
        "Pagamentos Confirmados": sql_card_wrap(
            sql_base_motor, "Pagamentos Confirmados",
            "motor.etapa_principal IN ('PAGO', 'PAGO_CANCELAMENTO')"
        ),
        "🔧 Base completa — Motor de Faturamento": sql_base_motor + "\n\n-- (sem filtro adicional: retorna TODAS as linhas usadas pelos cards acima)",
        "🔧 Base completa — KPIs de topo": sql_base_kpis,
    })

    st.divider()

    # ==============================================================
    # 2. GRÁFICOS EXECUTIVOS DE PERFORMANCE (INVESTIMENTO)
    # ==============================================================
    g1, g2 = st.columns([1.6, 1])

    with g1:
        st.markdown("##### 📈 Evolução do Investimento em Capacitação (Realizado vs. Projetado)")
        df_inv = buscar_investimento_mensal(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
        
        if not df_inv.empty:
            fig_inv = go.Figure()
            
            fig_inv.add_trace(go.Bar(
                x=df_inv['mes_ano'],
                y=df_inv['Faturamento Realizado'],
                name='Investimento Realizado',
                marker_color='#aecb36'
            ))
            
            fig_inv.add_trace(go.Scatter(
                x=df_inv['mes_ano'],
                y=df_inv['Faturamento Projetado'],
                name='Investimento Projetado',
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
        st.markdown("##### 🎓 Top Treinamentos Solicitados (NRs)")
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
    # 3. GRÁFICOS: INVESTIMENTO POR UNIDADE & MODALIDADE
    # ==============================================================
    g3, g4 = st.columns([1.3, 1])

    with g3:
        # Troca de 'grupo' para 'unidade' para fazer sentido na visão do cliente
        st.markdown("##### 🏢 Investimento por Unidade / Usina")
        if not df_motor.empty and 'unidade' in df_motor.columns:
            df_top_unidades = (
                df_motor.groupby('unidade')['valor_total']
                .sum()
                .reset_index()
                .sort_values(by='valor_total', ascending=False)
                .head(5)
            )
            fig_top_u = px.bar(
                df_top_unidades,
                x='valor_total',
                y='unidade',
                orientation='h',
                text_auto='.2s',
                color_discrete_sequence=['#1a1e38']
            )
            fig_top_u.update_layout(
                margin=dict(l=20, r=20, t=30, b=20),
                height=280,
                yaxis=dict(autorange="reversed"),
                xaxis_title="Investimento Total (R$)",
                yaxis_title=None,
                hoverlabel=hover_style,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_top_u, use_container_width=True)
        else:
            st.info("Sem dados de unidades para exibir.")

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
            "unidade": st.column_config.TextColumn("Unidade / Planta", width="medium"),
            "treinamento": st.column_config.TextColumn("Treinamento / NR", width="medium"),
            "instrutor": st.column_config.TextColumn("Instrutor", width="medium"),
            "valor": st.column_config.NumberColumn("Investimento (R$)", format="R$ %.2f")
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