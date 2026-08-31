import os
import base64
from datetime import date
import pandas as pd
import streamlit as st
from sqlalchemy import text
from database import get_engine

def aplicar_identidade_visual():
    css_bg = ""
    # Tenta achar a imagem (suporta tanto .jpg quanto .png)
    img_path = "1.jpg" if os.path.exists("1.jpg") else ("1.png" if os.path.exists("1.png") else None)
    
    if img_path:
        with open(img_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
            
        ext = "png" if img_path.endswith(".png") else "jpeg"
        
        css_bg = f"""
        .stApp {{
            background-image: linear-gradient(rgba(253, 253, 253, 0.88), rgba(253, 253, 253, 0.88)), url(data:image/{ext};base64,{encoded_string}) !important;
            background-size: cover !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            background-attachment: fixed !important;
        }}
        """

    css = f"""
    <style>
    {css_bg}
    
    /* 🔒 TRAVA DO TEMA: Oculta menu e Header */
    [data-testid="stHeader"] {{ display: none !important; }}
    [data-testid="stToolbar"] {{ display: none !important; }}
    #MainMenu {{ display: none !important; }}
    
    /* =========================================================
       1. MENU LATERAL (SIDEBAR) E CORES
       ========================================================= */
    [data-testid="stSidebar"] {{
        background-color: #1a1e38 !important;
        border-right: 3px solid #aecb36 !important;
    }}
    
    [data-testid="stSidebarNav"] span {{ color: #fdfdfd !important; font-weight: 500 !important; font-size: 15px !important; }}
    [data-testid="stSidebarNav"] svg {{ fill: #aecb36 !important; color: #aecb36 !important; }}
    [data-testid="stSidebarNav"] a:hover,
    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        background-color: rgba(174, 203, 54, 0.15) !important;
        border-radius: 8px !important;
    }}
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] div {{ color: #fdfdfd; }}

    /* =========================================================
       2. ORGANIZAÇÃO: PERFIL NO TOPO E SAIR NO RODAPÉ (FLEX MÁGICO)
       ========================================================= */
    /* Transforma a sidebar em uma coluna flexível real */
    [data-testid="stSidebarContent"] {{
        display: flex !important;
        flex-direction: column !important;
    }}

    /* "Desempacota" a div que o Streamlit cria para podermos reordenar os itens soltos */
    [data-testid="stSidebarUserContent"] {{
        display: contents !important;
    }}

    /* 1º ELEMENTO: PERFIL VAI PARA O TOPO ABSOLUTO */
    [data-testid="stSidebarUserContent"] > div:has(#profile-card) {{
        order: 1 !important;
        padding: 20px 15px 0px 15px !important;
    }}

    /* 2º ELEMENTO: MENU FICA LOGO ABAIXO DO PERFIL */
    [data-testid="stSidebarNav"] {{
        order: 2 !important;
        padding-top: 15px !important;
    }}

    /* 3º ELEMENTO: BOTÃO DE SAIR EMPURRADO PARA O FUNDO */
    [data-testid="stSidebarUserContent"] > div:has(.stButton) {{
        order: 3 !important;
        margin-top: auto !important; /* <-- A MÁGICA: O 'auto' empurra o botão pro limite do rodapé! */
        padding: 15px !important;
        padding-bottom: 30px !important;
    }}

    /* Estilo do Botão de Sair */
    [data-testid="stSidebar"] div.stButton > button {{
        background-color: transparent !important;
        border: 1px solid #da2c38 !important;
        color: #da2c38 !important;
        min-height: 40px !important;
        border-radius: 6px !important;
        width: 100% !important;
    }}
    [data-testid="stSidebar"] div.stButton > button * {{
        color: #da2c38 !important;
        font-weight: bold !important;
    }}
    [data-testid="stSidebar"] div.stButton > button:hover {{ background-color: #da2c38 !important; }}
    [data-testid="stSidebar"] div.stButton > button:hover * {{ color: #ffffff !important; }}

    /* =========================================================
       3. CARDS DE KPI (MÉTRICAS) COM ANIMAÇÃO E BORDA
       ========================================================= */
    [data-testid="metric-container"] {{
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-top: 4px solid #aecb36;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 4px 10px rgba(0,0,0,0.04);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    [data-testid="metric-container"]:hover {{
        transform: translateY(-4px);
        box-shadow: 2px 8px 20px rgba(0,0,0,0.1);
    }}
    
    /* =========================================================
       4. BOTÕES PRINCIPAIS (TELA BRANCA)
       ========================================================= */
    [data-testid="stMainBlockContainer"] div.stButton > button {{
        width: 100%; min-height: 95px; border-radius: 10px;
        border: none; background-color: #aecb36;
        color: #1a1e38; font-weight: bold; transition: all 0.25s ease; padding: 10px;
    }}
    [data-testid="stMainBlockContainer"] div.stButton > button:hover {{ 
        background-color: #1a1e38; color: #ffffff; transform: translateY(-3px); 
        box-shadow: 2px 5px 15px rgba(26, 30, 56, 0.3);
    }}
    
    /* =========================================================
       5. CAMPOS DE FILTRO ARREDONDADOS E ELEGANTES
       ========================================================= */
    [data-baseweb="select"] > div, [data-baseweb="input"] > div {{ border-radius: 8px !important; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def renderizar_filtros():
    aplicar_identidade_visual()

    # Perfil e Botão estão no app.py! Não os chame aqui.
    
    user = st.session_state.get("usuario_logado")
    if not user:
        st.warning("Acesso negado. Por favor, faça login.")
        st.stop()

    engine = get_engine()

    col_tit, col_logo = st.columns([3, 1])
    with col_tit:
        st.title("📊 Portal Dashboard")
        st.caption("Visão Unificada de Treinamentos, Vendas e Financeiro")
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

    return engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao

def get_hover_style():
    return dict(bgcolor="#ffffff", font_size=13, font_color="#1a1e38", font_family="Arial")