import bcrypt
import pandas as pd
import streamlit as st
from database import get_engine
from sqlalchemy import text


def obter_ip_cliente():
    """Captura o IP real do cliente através dos cabeçalhos da requisição."""
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
    """
    GRAVAÇÃO DE LOG DESATIVADA TEMPORARIAMENTE.
    Para reativar no futuro, basta remover a linha 'return' abaixo.
    """
    return 

    # O código abaixo não será executado por causa do 'return' acima
    ip_origem = obter_ip_cliente()

    query = text(
        """
        INSERT INTO public.tb_logs_auditoria (usuario_id, usuario_email, acao, detalhes, ip_origem)
        VALUES (:usuario_id, :email, :acao, :detalhes, :ip)
    """
    )
    try:
        with engine.begin() as conn:
            conn.execute(
                query,
                {
                    "usuario_id": usuario_id,
                    "email": usuario_email,
                    "acao": acao,
                    "detalhes": detalhes,
                    "ip": ip_origem,
                },
            )
    except Exception as e:
        print(f"Erro ao gravar log: {e}")


def autenticar_usuario(email, senha_informada):
    engine = get_engine()
    email_limpo = email.strip().lower()

    query = text(
        """
        SELECT id, nome, email, senha_hash, perfil, ativo, grupo, COALESCE(primeiro_acesso, 1) AS primeiro_acesso
        FROM public.tb_usuarios 
        WHERE LOWER(email) = :email
    """
    )

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
                    registrar_log(
                        engine,
                        "LOGIN_BLOQUEADO",
                        email_limpo,
                        user_id,
                        "Usuário inativo tentou acessar",
                    )
                    return None

                registrar_log(
                    engine,
                    "LOGIN_SUCESSO",
                    email_limpo,
                    user_id,
                    f"Acesso liberado (Perfil: {res.perfil})",
                )

                return {
                    "id": user_id,
                    "nome": res.nome,
                    "email": res.email,
                    "perfil": res.perfil,
                    "ativo": int(res.ativo),
                    "grupo": res.grupo,
                    "primeiro_acesso": int(res.primeiro_acesso),
                }

        registrar_log(
            engine,
            "LOGIN_FALHA",
            email_limpo,
            None,
            "Tentativa com e-mail ou senha incorretos",
        )
        return None


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

        registrar_log(
            engine,
            "TROCA_SENHA_OBRIGATORIA",
            email_usuario,
            str(usuario_id),
            "Senha alterada no primeiro acesso com sucesso",
        )
        return True, "Senha alterada com sucesso!"
    except Exception as e:
        return False, f"Erro ao atualizar senha no banco: {e}"

def solicitar_redefinicao_senha(engine, email):
    """Grava o pedido de reset de senha no banco de dados por segurança."""
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