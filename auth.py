import datetime
import random
import bcrypt
import jwt
import pandas as pd
import streamlit as st
from database import get_engine
from sqlalchemy import text

# Configuração Global Segura para Geração de Tokens JWT
JWT_ALGORITHM = "HS256"
JWT_SECRET = "querino_bi_secret_key_2026_prod"

try:
    if "JWT_SECRET" in st.secrets:
        JWT_SECRET = st.secrets["JWT_SECRET"]
except Exception:
    pass


# ==============================================================
# 1. GESTÃO DE TOKENS JWT & SESSÃO SILENCIOSA
# ==============================================================
def gerar_token_jwt(usuario_dados: dict, duracao_horas: int = 4) -> str:
    """Gera um Token JWT assinado com prazo de expiração para o usuário logado."""
    payload = {
        "id": usuario_dados["id"],
        "nome": usuario_dados["nome"],
        "email": usuario_dados["email"],
        "perfil": usuario_dados["perfil"],
        "grupo": usuario_dados["grupo"],
        "primeiro_acesso": usuario_dados["primeiro_acesso"],
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=duracao_horas),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verificar_token() -> bool:
    """Valida se o token JWT armazenado na sessão do cliente ainda é válido."""
    if "token" not in st.session_state or not st.session_state["token"]:
        return False
    try:
        dados = jwt.decode(
            st.session_state["token"], JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        
        # Cria o dicionário completo que os componentes/views esperam
        user_dict = {
            "id": dados["id"],
            "nome": dados["nome"],
            "email": dados["email"],
            "perfil": dados["perfil"],
            "grupo": dados["grupo"],
            "primeiro_acesso": dados["primeiro_acesso"],
        }
        
        # Sincroniza tanto o objeto unificado quanto as variáveis soltas
        st.session_state["usuario_logado"] = user_dict
        st.session_state["usuario_id"] = dados["id"]
        st.session_state["usuario_nome"] = dados["nome"]
        st.session_state["usuario_email"] = dados["email"]
        st.session_state["perfil"] = dados["perfil"]
        st.session_state["grupo"] = dados["grupo"]
        st.session_state["primeiro_acesso"] = dados["primeiro_acesso"]
        return True
    except jwt.ExpiredSignatureError:
        st.warning("⚠️ Sua sessão expirou por inatividade. Faça login novamente.")
        st.session_state.clear()
        return False
    except jwt.InvalidTokenError:
        st.session_state.clear()
        return False


# ==============================================================
# 2. AUDITORIA E LOGS
# ==============================================================
def obter_ip_cliente():
    """Captura o IP real do cliente através dos cabeçalhos HTTP."""
    try:
        headers = st.context.headers
        if "X-Forwarded-For" in headers:
            return headers["X-Forwarded-For"].split(",")[0].strip()
        elif "x-forwarded-for" in headers:
            return headers["x-forwarded-for"].split(",")[0].strip()
        return "127.0.0.1"
    except Exception:
        return "127.0.0.1"


def registrar_log(
    engine,
    acao: str,
    usuario_email: str = None,
    usuario_id: str = None,
    detalhes: str = None,
):
    """Gravação de logs de auditoria no PostgreSQL."""
    return  # Desativado temporariamente


# ==============================================================
# 3. AUTENTICAÇÃO SEGURA DE ETAPA ÚNICA (COM TOKEN JWT AUTOMÁTICO)
# ==============================================================
def autenticar_usuario(email: str, senha_informada: str):
    """
    Autentica o usuário em 1 só clique:
    - Valida credenciais no PostgreSQL
    - Protege contra ataques de força bruta (Rate Limiting)
    - Emite o Token JWT e salva na sessão de forma invisível
    """
    # 1. Trava Anti-Robô (Bloqueio por tentativas falhas seguidas)
    if "tentativas_falhas" not in st.session_state:
        st.session_state["tentativas_falhas"] = 0

    if st.session_state["tentativas_falhas"] >= 5:
        return None, "🛑 Acesso bloqueado por segurança devido a múltiplas tentativas incorretas."

    if not email or not senha_informada:
        return None, "Preencha o e-mail e a senha."

    engine = get_engine()
    email_limpo = email.strip().lower()

    query = text(
        """
        SELECT id, nome, email, senha_hash, perfil, ativo, grupo, COALESCE(primeiro_acesso, 1) AS primeiro_acesso
        FROM public.tb_usuarios 
        WHERE LOWER(email) = :email
        """
    )

    try:
        with engine.connect() as conn:
            res = conn.execute(query, {"email": email_limpo}).fetchone()

            if res:
                user_id = str(res.id)
                hash_salvo = res.senha_hash

                try:
                    senha_valida = bcrypt.checkpw(
                        senha_informada.encode("utf-8"), hash_salvo.encode("utf-8")
                    )
                except ValueError:
                    senha_valida = hash_salvo == senha_informada

                if senha_valida:
                    if int(res.ativo) == 0:
                        return None, "Usuário inativo. Entre em contato com o administrador."

                    # Sucesso: Reseta contador de falhas
                    st.session_state["tentativas_falhas"] = 0

                    dados_usuario = {
                        "id": user_id,
                        "nome": res.nome,
                        "email": res.email,
                        "perfil": res.perfil,
                        "ativo": int(res.ativo),
                        "grupo": res.grupo,
                        "primeiro_acesso": int(res.primeiro_acesso),
                    }

                    # Gera o Token JWT e armazena na sessão do Streamlit
                    token = gerar_token_jwt(dados_usuario)
                    st.session_state["token"] = token

                    return dados_usuario, "OK"

        # Falha de credenciais
        st.session_state["tentativas_falhas"] += 1
        tentativas_restantes = 5 - st.session_state["tentativas_falhas"]
        return None, f"E-mail ou senha incorretos. ({tentativas_restantes} tentativa(s) restante(s))"

    except Exception as e:
        return None, f"Erro de conexão com o banco de dados: {e}"


# ==============================================================
# 4. GESTÃO DE SENHAS
# ==============================================================
def alterar_senha_primeiro_acesso(
    usuario_id, senha_atual, nova_senha, email_usuario
):
    engine = get_engine()

    query_busca = text(
        "SELECT senha_hash FROM public.tb_usuarios WHERE id = :id"
    )
    with engine.connect() as conn:
        res = conn.execute(query_busca, {"id": str(usuario_id)}).fetchone()
        if not res:
            return False, "Usuário não encontrado."

        hash_salvo = res.senha_hash
        try:
            senha_valida = bcrypt.checkpw(
                senha_atual.encode("utf-8"), hash_salvo.encode("utf-8")
            )
        except ValueError:
            senha_valida = hash_salvo == senha_atual

        if not senha_valida:
            return False, "A senha provisória atual está incorreta."

    salt = bcrypt.gensalt(12)
    nova_hash = bcrypt.hashpw(nova_senha.encode("utf-8"), salt).decode("utf-8")

    query_update = text(
        """
        UPDATE public.tb_usuarios 
        SET senha_hash = :nova_hash, primeiro_acesso = 0 
        WHERE id = :id
        """
    )

    try:
        with engine.begin() as conn:
            conn.execute(
                query_update, {"nova_hash": nova_hash, "id": str(usuario_id)}
            )
        return True, "Senha alterada com sucesso!"
    except Exception as e:
        return False, f"Erro ao atualizar senha no banco: {e}"


def solicitar_redefinicao_senha(engine, email):
    """Grava a solicitação de redefinição no banco de dados."""
    ip = obter_ip_cliente()
    email_limpo = email.strip().lower()

    query = text("""
        INSERT INTO public.tb_solicitacoes_senha (email, ip_origem)
        VALUES (:email, :ip)
    """)

    try:
        with engine.begin() as conn:
            conn.execute(query, {"email": email_limpo, "ip": ip})
        return True, "Solicitação registrada com sucesso! A equipe administrativa foi notificada."
    except Exception as e:
        return False, f"Erro ao registrar solicitação: {e}"