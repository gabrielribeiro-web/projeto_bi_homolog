import os
import base64
from datetime import date
import pandas as pd
import streamlit as st
from sqlalchemy import text
from database import get_engine

# =====================================================================
# 1. HELPER CACHEADO PARA IMAGEM DE FUNDO
# =====================================================================
@st.cache_data(show_spinner=False)
def _obter_imagem_fundo_base64():
    img_path = "1.jpg" if os.path.exists("1.jpg") else ("1.png" if os.path.exists("1.png") else None)
    if img_path:
        with open(img_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        ext = "png" if img_path.endswith(".png") else "jpeg"
        return encoded_string, ext
    return None, None

# =====================================================================
# 2. HELPERS CACHEADOS PARA OS FILTROS GLOBAIS
# =====================================================================
@st.cache_data(ttl=300, show_spinner=False)
def _obter_lista_grupos(_engine):
    try:
        df = pd.read_sql_query("SELECT DISTINCT grupo FROM public.dim_clientes WHERE grupo IS NOT NULL ORDER BY grupo", _engine)
        return ["Todos"] + df["grupo"].tolist()
    except Exception:
        return ["Todos"]

@st.cache_data(ttl=300, show_spinner=False)
def _obter_lista_unidades(_engine, grupo_sel):
    try:
        if grupo_sel and grupo_sel != "Todos":
            df = pd.read_sql_query(
                text("SELECT DISTINCT unidade FROM public.fato_comercial WHERE unidade IS NOT NULL AND unidade != '' AND grupo = :grupo ORDER BY unidade"),
                _engine, params={"grupo": grupo_sel}
            )
        else:
            df = pd.read_sql_query(
                text("SELECT DISTINCT unidade FROM public.fato_comercial WHERE unidade IS NOT NULL AND unidade != '' ORDER BY unidade"),
                _engine
            )
        return ["Todas"] + df["unidade"].tolist()
    except Exception:
        return ["Todas"]


def aplicar_identidade_visual():
    encoded_string, ext = _obter_imagem_fundo_base64()
    css_bg = ""
    
    if encoded_string:
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
       1. BARRA LATERAL (SIDEBAR) - ESTRUTURA FLEX & ORDEM
       ========================================================= */
    [data-testid="stSidebar"] {{
        background-color: #1a1e38 !important;
        border-right: 3px solid #aecb36 !important;
    }}
    
    [data-testid="stSidebarContent"] {{
        display: flex !important;
        flex-direction: column !important;
        height: 100vh !important;
    }}

    [data-testid="stSidebarUserContent"] {{
        display: contents !important;
    }}

    [data-testid="stSidebarUserContent"] > div:has(#profile-card) {{
        order: 1 !important;
        margin-top: 0 !important;
        padding: 15px 15px 5px 15px !important;
    }}

    [data-testid="stSidebarNav"] {{
        order: 2 !important;
        margin-top: 0 !important;
        padding-top: 10px !important;
        flex-grow: 1 !important;
    }}

    [data-testid="stSidebarNav"] span {{ color: #fdfdfd !important; font-weight: 500 !important; font-size: 15px !important; }}
    [data-testid="stSidebarNav"] svg {{ fill: #aecb36 !important; color: #aecb36 !important; }}
    [data-testid="stSidebarNav"] a:hover,
    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        background-color: rgba(174, 203, 54, 0.15) !important;
        border-radius: 8px !important;
    }}
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] div {{ color: #fdfdfd; }}

    [data-testid="stSidebarUserContent"] > div:has(.stButton) {{
        order: 3 !important;
        margin-top: auto !important;
        padding: 15px !important;
        padding-bottom: 25px !important;
    }}

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
       2. CARDS DE KPI (MÉTRICAS) COM ANIMAÇÃO E BORDA
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
       3. OVERRIDE TOTAL DOS SELECTBOXES E INPUTS (FUNDO BRANCO)
       ========================================================= */
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] *,
    [data-testid="stWidgetLabel"] p,
    label,
    .stWidgetLabel {{
        background-color: transparent !important;
        background: transparent !important;
        color: #1a1e38 !important;
        font-weight: 600 !important;
    }}

    /* Força a caixa do Selectbox e DateInput a ficar 100% Branca */
    [data-testid="stSelectbox"] div[role="combobox"],
    [data-testid="stSelectbox"] div[data-baseweb="select"],
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    [data-testid="stDateInput"] div[data-baseweb="input"],
    div[data-baseweb="select"],
    div[data-baseweb="select"] > div {{
        background-color: #ffffff !important;
        background: #ffffff !important;
        border: 1px solid #cccccc !important;
        border-radius: 8px !important;
    }}

    /* Texto dentro dos campos em Azul Escuro */
    [data-testid="stSelectbox"] span,
    [data-testid="stSelectbox"] div,
    [data-testid="stDateInput"] input,
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] div {{
        color: #1a1e38 !important;
        -webkit-text-fill-color: #1a1e38 !important;
        font-weight: 500 !important;
    }}

    /* Setas e Ícones em Azul Escuro */
    [data-testid="stSelectbox"] svg,
    [data-testid="stDateInput"] svg,
    div[data-baseweb="select"] svg {{
        fill: #1a1e38 !important;
        color: #1a1e38 !important;
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
            lista_grupos = _obter_lista_grupos(engine)
            grupo_sel = st.selectbox("Grupo / Cliente:", lista_grupos)
        else:
            grupo_sel = user.get("grupo")
            st.info(f"Grupo: **{grupo_sel}**")

    with f2:
        lista_unidades = _obter_lista_unidades(engine, grupo_sel)
        unidade_sel = st.selectbox("Unidade:", lista_unidades)

    with f3: dt_inicio = st.date_input("Data Inicial:", value=date(2026, 1, 1))
    with f4: dt_fim = st.date_input("Data Final:", value=date(2026, 12, 31))

    st.divider()
    modo_visao = st.radio("Modalidade:", ["Presencial", "Geral"], horizontal=True, index=0)
    st.divider()

    return engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao

def get_hover_style():
    return dict(bgcolor="#ffffff", font_size=13, font_color="#1a1e38", font_family="Arial")