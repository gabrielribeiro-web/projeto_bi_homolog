import os
import urllib.parse
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine

@st.cache_resource
def get_engine():
    DATABASE_URL = None
    try:
        # 1. Identifica qual ambiente carregar (padrão: db_homolog)
        env_key = st.secrets.get("ACTIVE_ENV", "db_prod")
        db_config = st.secrets[env_key]
        
        # 2. Extrai as credenciais do ambiente selecionado
        db_user = db_config["DB_USER"]
        db_pass = db_config["DB_PASS"]
        db_host = db_config["DB_HOST"]
        db_port = db_config["DB_PORT"]
        db_name = db_config["DB_NAME"]
        
        # 3. Converte caracteres especiais da senha (@ vira %40)
        db_pass_encoded = urllib.parse.quote_plus(db_pass)
        
        # 4. Monta a URL dinamicamente
        DATABASE_URL = f"postgresql://{db_user}:{db_pass_encoded}@{db_host}:{db_port}/{db_name}?sslmode=require"
        
    except Exception:
        # Fallback caso ocorra falha ao ler o secrets.toml
        DATABASE_URL = os.getenv("DATABASE_URL")
        
    # Trava de segurança se nenhuma URL for montada
    if not DATABASE_URL:
        st.error("⚠️ Erro crítico: Credenciais do banco de dados não encontradas. Verifique o arquivo .streamlit/secrets.toml.")
        st.stop()
            
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return engine

def executar_query(query, params=None):
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)