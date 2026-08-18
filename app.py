import os
import bcrypt
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# 1. Configuração da Página
st.set_page_config(
    page_title="Portal B.I. - Grupo Querino", page_icon="📊", layout="wide"
)

# 2. Conexão com o Banco de Dados (Supabase)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.dychhsqpvqtwaslujbir:Acess%40bi2026@aws-0-sa-east-1.pooler.supabase.com:6543/postgres?sslmode=require",
)


@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL)


engine = get_engine()


# 3. Funções de Criptografia e Autenticação
def gerar_hash_senha(senha_plana: str) -> str:
    salt = bcrypt.gensalt(12)
    return bcrypt.hashpw(senha_plana.encode("utf-8"), salt).decode("utf-8")


def autenticar_usuario(email, senha_informada):
    query = text(
        """
        SELECT id, nome, email, senha_hash, perfil, ativo 
        FROM public.tb_usuarios 
        WHERE email = :email
    """
    )
    with engine.connect() as conn:
        res = conn.execute(query, {"email": email}).fetchone()
        if res:
            hash_salvo = res.senha_hash

            try:
                senha_valida = bcrypt.checkpw(
                    senha_informada.encode("utf-8"), hash_salvo.encode("utf-8")
                )
            except ValueError:
                senha_valida = hash_salvo == senha_informada

            if senha_valida:
                return {
                    "id": res.id,
                    "nome": res.nome,
                    "email": res.email,
                    "perfil": res.perfil,
                    "ativo": res.ativo,
                }
    return None


# 4. Controle de Sessão
if "usuario_logado" not in st.session_state:
    st.session_state["usuario_logado"] = None


# 5. Interface de Login
def exibir_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("🔑 Acesso ao Portal de B.I.")
        st.write("Insira suas credenciais para continuar.")

        with st.form("form_login"):
            email_input = st.text_input("E-mail")
            senha_input = st.text_input("Senha", type="password")
            botao_submit = st.form_submit_button("Entrar")

            if botao_submit:
                if not email_input or not senha_input:
                    st.warning("Por favor, preencha todos os campos.")
                else:
                    user = autenticar_usuario(email_input, senha_input)
                    if user:
                        if int(user["ativo"]) == 0:
                            st.error(
                                "Usuário inativo. Entre em contato com o suporte."
                            )
                        else:
                            st.session_state["usuario_logado"] = user
                            st.rerun()
                    else:
                        st.error("E-mail ou senha incorretos.")


# 6. Painel Principal
def exibir_painel():
    user = st.session_state["usuario_logado"]

    st.sidebar.title(f"👤 {user['nome']}")
    st.sidebar.caption(f"Perfil: {user['perfil'].upper()}")
    st.sidebar.write("---")

    if st.sidebar.button("Sair (Logout)"):
        st.session_state["usuario_logado"] = None
        st.rerun()

    st.title("📊 Portal de Business Intelligence - Grupo Querino")
    st.write(f"Bem-vindo(a), **{user['nome']}**!")

    st.write("---")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="Total de Instrutores",
            value=f"{pd.read_sql_query('SELECT COUNT(*) FROM dim_instrutores', engine).iloc[0, 0]:,}",
        )
    with col2:
        st.metric(
            label="Registros Comerciais",
            value=f"{pd.read_sql_query('SELECT COUNT(*) FROM fato_comercial', engine).iloc[0, 0]:,}",
        )
    with col3:
        st.metric(
            label="Treinamentos Realizados",
            value=f"{pd.read_sql_query('SELECT COUNT(*) FROM fato_treinamentos', engine).iloc[0, 0]:,}",
        )

    st.write("---")
    st.info("Módulos de relatórios e Power BI serão integrados nesta área.")


# 7. Execução do App
if st.session_state["usuario_logado"] is None:
    exibir_login()
else:
    exibir_painel()