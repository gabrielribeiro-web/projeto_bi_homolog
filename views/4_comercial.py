import streamlit as st
import plotly.express as px
import pandas as pd
from components import renderizar_filtros, get_hover_style
from queries import buscar_ranking_vendedores

engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros()
hover_style = get_hover_style()

df_vendedores = buscar_ranking_vendedores(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

st.markdown("### 📈 Desempenho da Equipe Comercial")
st.caption("Métricas consolidadas de faturamento, ticket médio e volume de turmas por executivo.")

if df_vendedores.empty:
    st.info("Nenhum dado comercial encontrado para os filtros selecionados.")
else:
    # 1. PREPARAÇÃO DOS DADOS E NOVOS CÁLCULOS
    # Remove eventuais linhas zeradas
    df_comercial = df_vendedores[df_vendedores['valor_total_vendido'] > 0].copy()
    
    # Cálculos Globais da Equipe
    total_faturado = df_comercial['valor_total_vendido'].sum()
    total_turmas = df_comercial['turmas_vendidas'].sum()
    ticket_medio_geral = total_faturado / total_turmas if total_turmas > 0 else 0
    
    # Cálculos Individuais (Ticket Médio e Share %)
    df_comercial['ticket_medio'] = df_comercial['valor_total_vendido'] / df_comercial['turmas_vendidas']
    df_comercial['share_vendas'] = (df_comercial['valor_total_vendido'] / total_faturado) * 100 if total_faturado > 0 else 0
    
    # Ordena pelo maior faturamento
    df_comercial = df_comercial.sort_values(by='valor_total_vendido', ascending=False)

    # 2. CARDS DE RESUMO (KPIs NO TOPO)
    k1, k2, k3, k4 = st.columns(4)
    
    exec_lider = df_comercial.iloc[0]['executivo'] if not df_comercial.empty else "N/A"
    fat_lider = df_comercial.iloc[0]['valor_total_vendido'] if not df_comercial.empty else 0

    k1.metric("Faturamento Total Equipe", f"R$ {total_faturado:,.2f}")
    k2.metric("Total de Turmas Vendidas", f"{total_turmas:,}")
    k3.metric("Ticket Médio por Turma", f"R$ {ticket_medio_geral:,.2f}")
    k4.metric("🏆 Líder de Vendas", str(exec_lider).upper(), f"R$ {fat_lider:,.2f}")

    st.write("")

    # 3. GRÁFICOS VISUAIS
    cg1, cg2 = st.columns([1.2, 1])

    with cg1:
        # Gráfico de Barras original melhorado
        fig_vend = px.bar(
            df_comercial.head(10).sort_values(by="valor_total_vendido", ascending=True), 
            x="valor_total_vendido", 
            y="executivo", 
            orientation="h", 
            title="Top Executivos por Faturamento (R$)", 
            text_auto=".2s", 
            color_discrete_sequence=["#aecb36"]
        )
        fig_vend.update_layout(
            yaxis_title=None, 
            xaxis_title="Faturamento (R$)", 
            hoverlabel=hover_style, 
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_vend, use_container_width=True)
        
    with cg2:
        # Novo Gráfico de Pizza (% de Share)
        fig_pie_share = px.pie(
            df_comercial,
            names="executivo",
            values="valor_total_vendido",
            hole=0.45,
            title="Participação nas Vendas (% Share)",
            color_discrete_sequence=['#1a1e38', '#aecb36', '#da2c38', '#4b5563', '#00b4d8']
        )
        fig_pie_share.update_layout(
            margin=dict(l=10, r=10, t=30, b=10), 
            hoverlabel=hover_style, 
            paper_bgcolor="rgba(0,0,0,0)", 
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_pie_share, use_container_width=True)

    # 4. TABELA ANALÍTICA DETALHADA
    st.write("")
    st.markdown("##### 📋 Tabela Analítica de Performance")
    
    # Configuração customizada das colunas na tabela
    col_config = {
        "executivo": st.column_config.TextColumn("Executivo", width="medium"),
        "turmas_vendidas": st.column_config.NumberColumn("Qtd Turmas", format="%d"),
        "valor_total_vendido": st.column_config.NumberColumn("Faturamento (R$)", format="R$ %.2f"),
        "ticket_medio": st.column_config.NumberColumn("Ticket Médio (R$)", format="R$ %.2f"),
        "share_vendas": st.column_config.NumberColumn("Share (%)", format="%.1f%%")
    }
    
    # Se a query também trouxer clientes únicos, exibe na tabela
    if 'clientes_atendidos' in df_comercial.columns:
        col_config["clientes_atendidos"] = st.column_config.NumberColumn("Clientes Únicos", format="%d")

    st.dataframe(
        df_comercial,
        use_container_width=True,
        hide_index=True,
        column_config=col_config,
        height=300
    )