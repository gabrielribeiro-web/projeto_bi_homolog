import os
import bcrypt  # IMPORTANTE: importar a biblioteca
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# ... (Mantenha as configurações iniciais de página e engine) ...


# Função para gerar hash (use para cadastrar novas senhas no futuro)
def gerar_hash_senha(senha_plana: str) -> str:
    salt = bcrypt.gensalt(12)
    return bcrypt.hashpw(senha_plana.encode("utf-8"), salt).decode("utf-8")


# Função de Validação de Login Atualizada
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

            # Verifica a senha digitada contra o Hash armazenado no banco
            try:
                senha_valida = bcrypt.checkpw(
                    senha_informada.encode("utf-8"), hash_salvo.encode("utf-8")
                )
            except ValueError:
                # Caso haja algum resíduo de senha em texto puro antiga
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