import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.dychhsqpvqtwaslujbir:Acess%40bi2026@aws-0-sa-east-1.pooler.supabase.com:6543/postgres?sslmode=require",
)

@st.cache_resource
def get_engine():
    # Usa diretamente a DATABASE_URL definida lá em cima!
    # O SEGREDO ESTÁ AQUI: pool_pre_ping=True testa se o banco caiu antes de tentar usar
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return engine

def executar_query(query, params=None):
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn, params=params)