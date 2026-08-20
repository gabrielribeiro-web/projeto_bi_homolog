import os
from datetime import date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from database import get_engine
from sqlalchemy import text
from queries import (
    buscar_distribuicao_tipo,
    buscar_grafico_nrs,
    buscar_investimento_mensal,
    buscar_kpis,
    buscar_proximas_turmas,
    buscar_ranking_instrutores,
)

st.set_page_config(
    page_title="Dashboard - Grupo Querino", page_icon="📊", layout="wide"
)

user = st.session_state.get("usuario_logado")
if not user:
    st.warning("Acesso negado. Por favor, faça login.")
    st.stop()

# Sidebar de perfil
st.sidebar.markdown(
    f"""
    <div style="background-color: #1e293b; padding: 12px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #84cc16;">
        <p style="margin: 0; font-weight: bold; color: #f8fafc;">👤 {user['nome']}</p>
        <p style="margin: 0; font-size: 12px; color: #94a3b8;">Perfil: {user['perfil'].upper()}</p>
    </div>
""",
    unsafe_allow_html=True,
)

if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
    st.session_state["usuario_logado"] = None
    st.rerun()

engine = get_engine()

# Cabeçalho
col_tit, col_logo = st.columns([3, 1])
with col_tit:
    st.title("📊 Portal de Business Intelligence")
    st.caption("Visão Consolidada de Treinamentos e Indicadores Financeiros")
with col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=180)

# --- PAINEL DE FILTROS SUPERIOR ---
st.subheader("🔍 Filtros de Visualização")
f1, f2, f3, f4 = st.columns([1.5, 1.2, 1, 1])

with f1:
    if user["perfil"] == "admin":
        df_grupos = pd.read_sql_query(
            "SELECT DISTINCT grupo FROM dim_clientes WHERE grupo IS NOT NULL ORDER BY grupo",
            engine,
        )
        grupo_sel = st.selectbox(
            "Grupo / Cliente:", ["Todos"] + df_grupos["grupo"].tolist()
        )
    else:
        grupo_sel = user.get("grupo")
        st.info(f"Grupo: **{grupo_sel}**")

# FILTRO DE UNIDADE
with f2:
    if grupo_sel and grupo_sel != "Todos":
        query_unidades = text(
            "SELECT DISTINCT unidade FROM public.fato_comercial WHERE unidade IS NOT NULL AND unidade != '' AND grupo = :grupo ORDER BY unidade"
        )
        df_unidades = pd.read_sql_query(
            query_unidades, engine, params={"grupo": grupo_sel}
        )
    else:
        query_unidades = text(
            "SELECT DISTINCT unidade FROM public.fato_comercial WHERE unidade IS NOT NULL AND unidade != '' ORDER BY unidade"
        )
        df_unidades = pd.read_sql_query(query_unidades, engine)

    unidade_sel = st.selectbox(
        "Unidade / Planta:", ["Todas"] + df_unidades["unidade"].tolist()
    )

with f3:
    dt_inicio = st.date_input("Data Inicial:", value=date(2026, 1, 1))
with f4:
    dt_fim = st.date_input("Data Final:", value=date(2026, 12, 31))

# Carregamento de dados com TODOS os filtros
df_kpis = buscar_kpis(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_nrs = buscar_grafico_nrs(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_tipo = buscar_distribuicao_tipo(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_mes = buscar_investimento_mensal(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_proximas = buscar_proximas_turmas(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_instrutores = buscar_ranking_instrutores(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)

st.divider()

# --- ESTRUTURA DE EXIBIÇÃO (ABAS PARA ADMIN, PÁGINA ÚNICA PARA CLIENTE) ---
if user["perfil"] == "admin":
    tabs = st.tabs(["📊 Visão Executiva", "🎓 Qualidade & Operação", "💰 Posição Financeira"])
    container_executiva = tabs[0]
    container_operacional = tabs[1]
    container_financeira = tabs[2]
else:
    # Se for cliente, cria blocos em branco um embaixo do outro
    container_executiva = st.container()
    container_operacional = st.container()
    container_financeira = None  # Cliente não vê posição financeira interna

# Estilo de Tooltips
hover_style = dict(
    bgcolor="#ffffff",
    font_size=13,
    font_color="#09090b",
    font_family="Arial",
)

# ==========================================
# BLOCO 1: VISÃO EXECUTIVA
# ==========================================
with container_executiva:
    
    if user["perfil"] == "admin":
        st.markdown("#### 💼 Funil Financeiro (Visão Interna)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Faturamento Realizado", f"R$ {df_kpis['total_faturado'].iloc[0]:,.2f}")
        c2.metric("Futuro Agendado", f"R$ {df_kpis['futuro_agendado'].iloc[0]:,.2f}")
        c3.metric("Futuro Lançado", f"R$ {df_kpis['futuro_lancado'].iloc[0]:,.2f}")
        c4.metric("Pendências (Gargalo)", f"R$ {df_kpis['total_pendencia'].iloc[0]:,.2f}")
    else:
        st.markdown("#### 💼 Resumo de Investimento")
        c1, c2, c3 = st.columns(3)
        c1.metric("Investimento Realizado (Turmas Concluídas)", f"R$ {df_kpis['total_faturado'].iloc[0]:,.2f}")
        investimento_futuro = df_kpis['futuro_agendado'].iloc[0] + df_kpis['futuro_lancado'].iloc[0]
        c2.metric("Investimento Agendado (Próximas Turmas)", f"R$ {investimento_futuro:,.2f}")
        c3.metric("Unidades Atendidas", f"{df_kpis['unidades_atendidas'].iloc[0]:,}")

    st.divider()

    st.markdown("#### ⚙️ Entregas e Qualidade (Realizado)")
    
    if user["perfil"] == "admin":
        c5, c6, c7, c8, c9 = st.columns(5)
        c5.metric("Turmas Realizadas", f"{df_kpis['turmas_realizadas'].iloc[0]:,}")
        c6.metric("Horas Treinamento", f"{df_kpis['horas_realizadas'].iloc[0]:,.0f}h")
        c7.metric("Pessoas Treinadas", f"{df_kpis['pessoas_treinadas'].iloc[0]:,}")
        c8.metric("Aproveitamento Médio", f"{df_kpis['aproveitamento_medio'].iloc[0] or 0:.2f} ⭐")
        c9.metric("Unidades Atendidas", f"{df_kpis['unidades_atendidas'].iloc[0]:,}")
    else:
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Turmas Realizadas", f"{df_kpis['turmas_realizadas'].iloc[0]:,}")
        c6.metric("Pessoas Treinadas (Certificados)", f"{df_kpis['pessoas_treinadas'].iloc[0]:,}")
        c7.metric("Carga Horária Consumida", f"{df_kpis['horas_realizadas'].iloc[0]:,.0f}h")
        c8.metric("Nota Média (Qualidade)", f"{df_kpis['aproveitamento_medio'].iloc[0] or 0:.2f} ⭐")

    st.divider()

    g1, g2, g3 = st.columns([1.2, 1, 1.5])
    with g1:
        fig_nrs = px.bar(
            df_nrs, x="contagem", y="cod_treinamento", orientation="h",
            title="Volume de Turmas por Norma (Top 5)", text="contagem",
            color_discrete_sequence=["#84cc16"]
        )
        fig_nrs.update_layout(yaxis={"categoryorder": "total ascending"}, hoverlabel=hover_style)
        st.plotly_chart(fig_nrs, use_container_width=True)

    with g2:
        fig_pie = px.pie(
            df_tipo, values="qtd", names="tipo", hole=0.5,
            title="Distribuição por Tipo",
            color_discrete_sequence=["#84cc16", "#38bdf8", "#a855f7"]
        )
        fig_pie.update_layout(hoverlabel=hover_style)
        st.plotly_chart(fig_pie, use_container_width=True)

    with g3:
        fig_mes = go.Figure()
        fig_mes.add_trace(go.Bar(x=df_mes["mes_ano"], y=df_mes["turmas"], name="Turmas", marker_color="#84cc16"))
        fig_mes.add_trace(go.Scatter(x=df_mes["mes_ano"], y=df_mes["investimento"], name="Investimento (R$)", yaxis="y2", line=dict(color="#38bdf8", width=3)))
        fig_mes.update_layout(
            title="Turmas e Investimento por Mês",
            yaxis=dict(title="Qtd Turmas"),
            yaxis2=dict(title="Investimento (R$)", overlaying="y", side="right"),
            legend=dict(x=0, y=1.1, orientation="h"),
            hoverlabel=hover_style,
        )
        st.plotly_chart(fig_mes, use_container_width=True)

    st.divider()

    st.subheader("📅 Próximas Turmas Agendadas")
    st.dataframe(
        df_proximas,
        use_container_width=True,
        hide_index=True,
        column_config={
            "inicio": "Data Início",
            "grupo": "Grupo / Cliente",
            "treinamento": "Treinamento / Norma",
            "unidade": "Unidade",
            "instrutor": "Instrutor",
            "valor": st.column_config.NumberColumn("Valor Contratado", format="R$ %.2f"),
        },
    )

# ==========================================
# BLOCO 2: QUALIDADE & OPERAÇÃO
# ==========================================
with container_operacional:
    
    # Se for cliente, colocamos um divisor e título para separar o conteúdo na mesma página
    if user["perfil"] != "admin":
        st.divider()
        st.markdown("### 🎓 Qualidade Operacional")
        
    st.subheader("👨‍🏫 Desempenho e Volume por Instrutor")
    st.caption("Acompanhe o volume de turmas realizadas e as notas médias de avaliação técnica.")
    
    if df_instrutores.empty:
        st.info("Nenhum dado de operação encontrado para os filtros selecionados.")
    else:
        df_top_instrutores = df_instrutores.head(10).sort_values(by="turmas_realizadas", ascending=True)
        
        o1, o2 = st.columns([1.5, 1])
        
        with o1:
            fig_inst = px.bar(
                df_top_instrutores, x="turmas_realizadas", y="instrutor", orientation="h",
                title="Top 10 Instrutores (Por Volume de Turmas)", text="turmas_realizadas",
                color_discrete_sequence=["#38bdf8"]
            )
            fig_inst.update_layout(hoverlabel=hover_style)
            st.plotly_chart(fig_inst, use_container_width=True)
            
        with o2:
            st.write("**Tabela Geral de Qualidade**")
            st.dataframe(
                df_instrutores,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "instrutor": "Nome do Instrutor",
                    "turmas_realizadas": st.column_config.NumberColumn("Turmas", format="%d"),
                    "pessoas_treinadas": st.column_config.NumberColumn("Alunos", format="%d"),
                    "nota_media": st.column_config.NumberColumn("Nota Média", format="%.2f ⭐", help="Média técnica calculada por aluno."),
                },
                height=350
            )

# ==========================================
# BLOCO 3: POSIÇÃO FINANCEIRA
# ==========================================
if container_financeira:
    with container_financeira:
        st.info("💡 Esta aba conterá a gestão detalhada de Pedidos de Compra (PO), NFs e Funil de Faturamento do Grupo Querino.")