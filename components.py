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
        [data-testid="stHeader"] {{
            background-color: transparent !important;
        }}
        """

    css = f"""
    <style>
    {css_bg}
    
    /* =========================================================
       1. MENU LATERAL (SIDEBAR) PREMIUM - Azul Escuro 
       ========================================================= */
    [data-testid="stSidebar"] {{
        background-color: #1a1e38 !important;
        border-right: 3px solid #aecb36 !important; /* Linha divisória verde */
    }}
    
    /* Textos e Ícones do Menu em Branco e Verde */
    [data-testid="stSidebarNav"] span {{
        color: #fdfdfd !important;
        font-weight: 500 !important;
        font-size: 15px !important;
    }}
    [data-testid="stSidebarNav"] svg {{
        fill: #aecb36 !important; /* Ícones em Verde Querino */
        color: #aecb36 !important;
    }}
    
    /* Efeito ao passar o mouse ou item selecionado no Menu */
    [data-testid="stSidebarNav"] a:hover,
    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        background-color: rgba(174, 203, 54, 0.15) !important;
        border-radius: 8px !important;
    }}

    /* Textos gerais dentro da sidebar */
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] div {{
        color: #fdfdfd;
    }}

    /* =========================================================
       2. CARDS DE KPI (MÉTRICAS) COM ANIMAÇÃO E BORDA
       ========================================================= */
    [data-testid="metric-container"] {{
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-top: 4px solid #aecb36; /* Fio verde no topo do card */
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 4px 10px rgba(0,0,0,0.04);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    [data-testid="metric-container"]:hover {{
        transform: translateY(-4px); /* Levanta o card ao passar o mouse */
        box-shadow: 2px 8px 20px rgba(0,0,0,0.1);
    }}
    
    /* =========================================================
       3. BOTÕES PRINCIPAIS (TELA BRANCA)
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
       4. BOTÃO DE SAIR NA BARRA LATERAL (Fundo Escuro)
       ========================================================= */
    [data-testid="stSidebar"] div.stButton > button {{
        background-color: transparent !important;
        border: 1px solid #da2c38 !important;
        color: #da2c38 !important;
        min-height: 40px !important;
        border-radius: 6px !important;
        margin-top: 10px;
    }}
    [data-testid="stSidebar"] div.stButton > button * {{
        color: #da2c38 !important;
        font-weight: bold !important;
    }}
    [data-testid="stSidebar"] div.stButton > button:hover {{
        background-color: #da2c38 !important;
    }}
    [data-testid="stSidebar"] div.stButton > button:hover * {{
        color: #ffffff !important;
    }}
    
    /* =========================================================
       5. CAMPOS DE FILTRO ARREDONDADOS E ELEGANTES
       ========================================================= */
    [data-baseweb="select"] > div, [data-baseweb="input"] > div {{
        border-radius: 8px !important;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def renderizar_filtros():
    aplicar_identidade_visual()

    user = st.session_state.get("usuario_logado")
    if not user:
        st.warning("Acesso negado. Por favor, faça login.")
        st.stop()

    # O card do usuário agora tem fundo semi-transparente para combinar com a sidebar azul
    st.sidebar.markdown(
        f"""
        <div style="background-color: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; margin-bottom: 5px; border-left: 4px solid #aecb36;">
            <p style="margin: 0; font-weight: bold; color: #fdfdfd; font-size: 15px;">👤 {user['nome']}</p>
            <p style="margin: 0; font-size: 11px; color: #aecb36; font-weight: bold; letter-spacing: 1px; margin-top: 3px;">PERFIL: {user['perfil'].upper()}</p>
        </div>
    """, unsafe_allow_html=True)

    if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
        st.session_state["usuario_logado"] = None
        st.rerun()

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