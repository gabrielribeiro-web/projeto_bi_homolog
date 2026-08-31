import os
from datetime import date
import pandas as pd
import streamlit as st
from sqlalchemy import text
from database import get_engine

def renderizar_filtros():
    user = st.session_state.get("usuario_logado")
    if not user:
        st.warning("Acesso negado. Por favor, faça login.")
        st.stop()

    st.sidebar.markdown(
        f"""
        <div style="background-color: var(--secondary-background-color); padding: 12px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #84cc16;">
            <p style="margin: 0; font-weight: bold; color: var(--text-color);">👤 {user['nome']}</p>
            <p style="margin: 0; font-size: 12px; color: var(--text-color); opacity: 0.8;">Perfil: {user['perfil'].upper()}</p>
        </div>
    """, unsafe_allow_html=True)

    if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
        st.session_state["usuario_logado"] = None
        st.rerun()

    engine = get_engine()

    col_tit, col_logo = st.columns([3, 1])
    with col_tit:
        st.title("📊 Portal de BI e Gestão Executiva")
        st.caption("Visão Unificada de Treinamentos, Vendas e Saúde Financeira - Grupo Querino")
    with col_logo:
        if os.path.exists("logo.png"): st.image("logo.png", width=180)

    st.subheader("🔍 Filtros Globais")
    f1, f2, f3, f4 = st.columns([1.5, 1.2, 1, 1])

    with f1:
        if user["perfil"] == "admin":
            df_grupos = pd.read_sql_query("SELECT DISTINCT grupo FROM dim_clientes WHERE grupo IS NOT NULL ORDER BY grupo", engine)
            grupo_sel = st.selectbox("Grupo / Cliente:", ["Todos"] + df_grupos["grupo"].tolist())
        else:
            grupo_sel = user.get("grupo")
            st.info(f"Grupo: **{grupo_sel}**")

    with f2:
        if grupo_sel and grupo_sel != "Todos":
            df_unidades = pd.read_sql_query(text("SELECT DISTINCT unidade FROM public.fato_comercial WHERE unidade IS NOT NULL AND unidade != '' AND grupo = :grupo ORDER BY unidade"), engine, params={"grupo": grupo_sel})
        else:
            df_unidades = pd.read_sql_query(text("SELECT DISTINCT unidade FROM public.fato_comercial WHERE unidade IS NOT NULL AND unidade != '' ORDER BY unidade"), engine)
        unidade_sel = st.selectbox("Unidade:", ["Todas"] + df_unidades["unidade"].tolist())

    with f3: dt_inicio = st.date_input("Data Inicial:", value=date(2026, 1, 1))
    with f4: dt_fim = st.date_input("Data Final:", value=date(2026, 12, 31))

    st.divider()
    modo_visao = st.radio("Modalidade:", ["Presencial", "Geral"], horizontal=True, index=0)
    st.divider()

    # CSS Global dos botões de Dashboard para todas as telas
    st.markdown("""
        <style>
        div.stButton > button {
            width: 100%; min-height: 95px; border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.12); background-color: #18181b;
            color: #ffffff; font-weight: 600; transition: all 0.25s ease; padding: 10px;
        }
        div.stButton > button:hover { border-color: #84cc16; color: #84cc16; transform: translateY(-3px); }
        </style>
    """, unsafe_allow_html=True)

    return engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao

def get_hover_style():
    return dict(bgcolor="#ffffff", font_size=13, font_color="#09090b", font_family="Arial")