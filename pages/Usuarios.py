import bcrypt
import pandas as pd
import streamlit as st
from auth import registrar_log
from database import get_engine
from sqlalchemy import text

st.set_page_config(
    page_title="Gestão de Clientes - Grupo Querino",
    page_icon="👤",
    layout="wide",
)

user = st.session_state.get("usuario_logado")
if not user or user["perfil"] != "admin":
    st.error("Acesso restrito a Administradores.")
    st.stop()

engine = get_engine()

# Componente de Perfil na Barra Lateral
st.sidebar.markdown(
    f"""
    <div style="background-color: #1e293b; padding: 12px; border-radius: 8px; margin-bottom: 15px; border-left: 4px solid #84cc16;">
        <p style="margin: 0; font-weight: bold; color: #f8fafc;">👤 {user['nome']}</p>
        <p style="margin: 0; font-size: 12px; color: #94a3b8;">Perfil: {user['perfil'].upper()}</p>
    </div>
""",
    unsafe_allow_html=True,
)

if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
    st.session_state["usuario_logado"] = None
    st.rerun()

st.title("👤 Gestão e Cadastro de Clientes")
st.caption(
    "Cadastre novos acessos para clientes ou equipe interna, edite informações ou gerencie permissões."
)

tab_cadastro, tab_edicao = st.tabs(
    ["➕ Novo Cliente / Acesso", "✏️ Gerenciar / Editar Clientes"]
)

# Busca os grupos de clientes no banco
try:
    df_grupos = pd.read_sql_query(
        "SELECT DISTINCT grupo FROM dim_clientes WHERE grupo IS NOT NULL ORDER BY grupo",
        engine,
    )
    lista_grupos = df_grupos["grupo"].tolist()
except Exception:
    lista_grupos = []

# ==========================================
# ABA 1: CADASTRO DE CLIENTE / ACESSO
# ==========================================
with tab_cadastro:
    col_form, col_card = st.columns([1.2, 1])

    with col_form:
        st.subheader("Cadastrar Acesso")
        with st.form("form_novo_cliente", clear_on_submit=False):
            nome = st.text_input("Nome do Cliente / Empresa")
            email = st.text_input("E-mail de Acesso")
            senha_prov = st.text_input(
                "Senha Inicial Provisória", type="password"
            )

            # Mapeamento do perfil para facilitar o entendimento do comercial
            perfil_rotulo = st.selectbox(
                "Tipo de Acesso",
                [
                    "Cliente (Visualiza apenas seu Grupo)",
                    "Administrador Interno (Acesso Total)",
                ],
            )
            perfil = (
                "usuario"
                if perfil_rotulo.startswith("Cliente")
                else "admin"
            )

            grupo_sel = (
                st.selectbox("Vincular ao Grupo/Cliente", lista_grupos)
                if perfil == "usuario"
                else None
            )

            btn_cadastrar = st.form_submit_button(
                "Cadastrar Cliente", use_container_width=True
            )

            if btn_cadastrar:
                email_clean = email.strip().lower()

                if not nome or not email_clean or not senha_prov:
                    st.warning("Preencha todos os campos obrigatórios.")
                else:
                    # Checa duplicação de e-mail
                    query_checa_email = text(
                        "SELECT COUNT(*) FROM public.tb_usuarios WHERE LOWER(email) = :email"
                    )
                    with engine.connect() as conn:
                        qtd_existente = conn.execute(
                            query_checa_email, {"email": email_clean}
                        ).scalar()

                    if qtd_existente > 0:
                        st.error(
                            f"⚠️ O e-mail **{email_clean}** já possui um cadastro ativo no sistema!"
                        )
                    else:
                        salt = bcrypt.gensalt(12)
                        senha_hash = bcrypt.hashpw(
                            senha_prov.encode("utf-8"), salt
                        ).decode("utf-8")

                        query_insert = text(
                            """
                            INSERT INTO public.tb_usuarios (nome, email, senha_hash, perfil, ativo, grupo, primeiro_acesso)
                            VALUES (:nome, :email, :senha_hash, :perfil, 1, :grupo, 1)
                        """
                        )
                        try:
                            with engine.begin() as conn:
                                conn.execute(
                                    query_insert,
                                    {
                                        "nome": nome,
                                        "email": email_clean,
                                        "senha_hash": senha_hash,
                                        "perfil": perfil,
                                        "grupo": grupo_sel,
                                    },
                                )

                            registrar_log(
                                engine,
                                acao="CRIACAO_CLIENTE",
                                usuario_email=user["email"],
                                usuario_id=str(user["id"]),
                                detalhes=f"Cadastrou o cliente '{nome}' ({email_clean}) no grupo '{grupo_sel}'",
                            )

                            st.session_state["ultimo_cadastro"] = {
                                "nome": nome,
                                "email": email_clean,
                                "senha": senha_prov,
                            }
                            st.success(
                                f"Cliente **{nome}** cadastrado com sucesso!"
                            )
                        except Exception as e:
                            st.error(f"Erro ao cadastrar cliente: {e}")

    with col_card:
        st.subheader("📋 Card Próprio para Envio")
        if "ultimo_cadastro" in st.session_state:
            cad = st.session_state["ultimo_cadastro"]
            mensagem_padrao = f"""Olá, {cad['nome']}!

Seu acesso ao Portal de Dashboard do Grupo Querino foi liberado.

🔗 Link de Acesso: http://localhost:8501
📧 E-mail: {cad['email']}
🔑 Senha Provisória: {cad['senha']}

⚠️ No primeiro acesso, o sistema solicitará obrigatoriamente a criação da sua nova senha."""

            # Campo editável
            texto_editado = st.text_area(
                "Texto da Mensagem (Editável):",
                value=mensagem_padrao,
                height=180,
                key="txt_mensagem_envio",
            )

            st.write("**Bloco de Cópia Rápida:**")
            st.code(texto_editado, language="text")

            st.caption(
                "💡 **Dica:** Passe o mouse no bloco cinza acima e clique no ícone de cópia 📋 no canto superior direito para enviar ao cliente."
            )
        else:
            st.info(
                "Preencha o formulário ao lado para gerar os dados de envio do cliente."
            )

# ==========================================
# ABA 2: EDITAR, BLOQUEAR E EXCLUIR CLIENTES
# ==========================================
with tab_edicao:
    query_users = "SELECT id, nome, email, perfil, grupo, ativo, COALESCE(primeiro_acesso, 1) as primeiro_acesso FROM public.tb_usuarios ORDER BY nome ASC"
    df_users = pd.read_sql_query(query_users, engine)

    st.subheader("📋 Gerenciar Clientes Cadastrados")

    opcoes_usuarios = {
        f"{row['nome']} ({row['email']}) - [{row['grupo'] or 'ADMIN'}]": row
        for _, row in df_users.iterrows()
    }
    usuario_selecionado_label = st.selectbox(
        "Selecione um cliente/acesso para gerenciar:",
        list(opcoes_usuarios.keys()),
    )

    if usuario_selecionado_label:
        usr_dados = opcoes_usuarios[usuario_selecionado_label]

        st.write("---")
        st.subheader(f"Editar Cliente: **{usr_dados['nome']}**")

        col1, col2 = st.columns(2)
        with col1:
            novo_nome = st.text_input("Nome do Cliente / Empresa", value=usr_dados["nome"])
            novo_email = st.text_input("E-mail de Acesso", value=usr_dados["email"])
            novo_perfil = st.selectbox(
                "Perfil de Acesso",
                ["usuario", "admin"],
                index=0 if usr_dados["perfil"] == "usuario" else 1,
                format_func=lambda x: "Cliente (Visualiza seu Grupo)" if x == "usuario" else "Administrador Interno",
            )
            novo_grupo = (
                st.selectbox(
                    "Grupo Vinculado",
                    lista_grupos,
                    index=(
                        lista_grupos.index(usr_dados["grupo"])
                        if usr_dados["grupo"] in lista_grupos
                        else 0
                    ),
                )
                if novo_perfil == "usuario"
                else None
            )

        with col2:
            status_ativo = st.toggle(
                "Acesso Ativo?",
                value=bool(usr_dados["ativo"]),
                help="Desative para bloquear o acesso deste cliente imediatamente.",
            )
            st.divider()
            resetar_senha = st.checkbox(
                "Resetar Senha (Forçar Primeiro Acesso)"
            )
            nova_senha_prov = (
                st.text_input("Nova Senha Provisória", type="password")
                if resetar_senha
                else None
            )

        # Salvar Edições
        if st.button("💾 Salvar Alterações", use_container_width=True):
            email_edit_clean = novo_email.strip().lower()

            query_checa_email_outros = text(
                "SELECT COUNT(*) FROM public.tb_usuarios WHERE LOWER(email) = :email AND id != CAST(:id AS UUID)"
            )
            with engine.connect() as conn:
                qtd_outros = conn.execute(
                    query_checa_email_outros,
                    {"email": email_edit_clean, "id": str(usr_dados["id"])},
                ).scalar()

            if qtd_outros > 0:
                st.error(
                    f"⚠️ O e-mail **{email_edit_clean}** já pertence a outro cadastro."
                )
            else:
                query_update = """
                    UPDATE public.tb_usuarios 
                    SET nome = :nome, 
                        email = :email, 
                        perfil = :perfil, 
                        grupo = :grupo, 
                        ativo = :ativo
                """
                params = {
                    "nome": novo_nome,
                    "email": email_edit_clean,
                    "perfil": novo_perfil,
                    "grupo": novo_grupo,
                    "ativo": 1 if status_ativo else 0,
                    "id": str(usr_dados["id"]),
                }

                if resetar_senha and nova_senha_prov:
                    salt = bcrypt.gensalt(12)
                    params["senha_hash"] = bcrypt.hashpw(
                        nova_senha_prov.encode("utf-8"), salt
                    ).decode("utf-8")
                    query_update += (
                        ", senha_hash = :senha_hash, primeiro_acesso = 1"
                    )

                query_update += " WHERE id = CAST(:id AS UUID)"

                try:
                    with engine.begin() as conn:
                        conn.execute(text(query_update), params)

                    registrar_log(
                        engine,
                        acao="EDICAO_CLIENTE",
                        usuario_email=user["email"],
                        usuario_id=str(user["id"]),
                        detalhes=f"Alterou o cliente '{usr_dados['nome']}' -> Nome: '{novo_nome}', E-mail: '{email_edit_clean}', Grupo: '{novo_grupo}', Ativo: {status_ativo}",
                    )

                    st.success("Dados do cliente alterados com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar alterações: {e}")

        st.write("---")

        # Exclusão Definitiva
        with st.expander("🚨 Zona de Perigo: Excluir Cliente"):
            st.warning(
                "A exclusão é permanente. O cliente perderá o acesso ao portal imediatamente."
            )
            confirma_exclusao = st.checkbox(
                f"Confirmo que desejo excluir permanentemente o cadastro de **{usr_dados['nome']}**."
            )

            if st.button(
                "🗑️ Excluir Cliente Definitivamente",
                type="primary",
                disabled=not confirma_exclusao,
                use_container_width=True,
            ):
                query_delete = text(
                    "DELETE FROM public.tb_usuarios WHERE id = CAST(:id AS UUID)"
                )
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            query_delete, {"id": str(usr_dados["id"])}
                        )

                    registrar_log(
                        engine,
                        acao="EXCLUSAO_CLIENTE",
                        usuario_email=user["email"],
                        usuario_id=str(user["id"]),
                        detalhes=f"Excluiu permanentemente o cliente '{usr_dados['nome']}' ({usr_dados['email']})",
                    )

                    st.success("Cliente removido do sistema com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir cliente: {e}")