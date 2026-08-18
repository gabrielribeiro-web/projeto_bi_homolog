import os
import streamlit as st
from sqlalchemy import create_engine

# Configuração da página
st.set_page_config(
    page_title="Portal B.I. - Grupo Querino", page_icon="📊", layout="wide"
)

# Conexão com o banco (pega das variáveis de ambiente ou usa a URL padrão)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.dychhsqpvqtwaslujbir:Acess%40bi2026@aws-0-sa-east-1.pooler.supabase.com:6543/postgres?sslmode=require",
)


@st.cache_resource
def get_db_connection():
    return create_engine(DATABASE_URL)


st.title("📊 Portal de Business Intelligence - Grupo Querino")
st.write(
    "Bem-vindo ao sistema centralizado de relatórios e controle de dados."
)

st.success("Conexão com o banco de dados Supabase configurada com sucesso!")