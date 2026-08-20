import streamlit as st
from auth import alterar_senha_primeiro_acesso, autenticar_usuario, registrar_log
from database import get_engine

st.set_page_config(
    page_title="Portal Dashboard. - Grupo Querino", page_icon="📊", layout="wide"
)

if "usuario_logado" not in st.session_state:
    st.session_state["usuario_logado"] = None


def tela_login():
    st.markdown(
        "<style>[data-testid='stSidebar'] {display: none;}</style>",
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.5, 1])

    with col2:
        st.write("")
        st.write("")

        # CASO 1: Usuário logado precisando alterar a senha no PRIMEIRO ACESSO
        user = st.session_state.get("usuario_logado")
        if user and user.get("primeiro_acesso") == 1:
            st.warning("🔒 **Primeiro Acesso Detectado**")
            st.caption(
                "Por motivos de segurança, altere a senha provisória fornecida para continuar."
            )

            with st.form("form_troca_obrigatoria"):
                senha_atual = st.text_input(
                    "Senha Provisória Atual", type="password"
                )
                nova_senha = st.text_input("Nova Senha", type="password")
                confirma_senha = st.text_input(
                    "Confirme a Nova Senha", type="password"
                )
                btn_alterar = st.form_submit_button(
                    "Salvar Nova Senha e Continuar", use_container_width=True
                )

                if btn_alterar:
                    if not senha_atual or not nova_senha or not confirma_senha:
                        st.error("Preencha todos os campos.")
                    elif nova_senha != confirma_senha:
                        st.error("A nova senha e a confirmação não coincidem.")
                    elif len(nova_senha) < 6:
                        st.error(
                            "A nova senha deve ter no mínimo 6 caracteres."
                        )
                    else:
                        sucesso, msg = alterar_senha_primeiro_acesso(
                            user["id"], senha_atual, nova_senha, user["email"]
                        )
                        if sucesso:
                            st.session_state["usuario_logado"][
                                "primeiro_acesso"
                            ] = 0
                            st.success(
                                "Senha atualizada! Redirecionando..."
                            )
                            st.rerun()
                        else:
                            st.error(msg)
            return

        # CASO 2: Tela de Login Convencional
        st.subheader("🔑 Acesso ao Portal de Dashboard.")
        st.caption("Insira suas credenciais para continuar.")

        aba_login, aba_esqueci = st.tabs(
            ["Entrar", "❓ Esqueci minha senha"]
        )

        with aba_login:
            with st.form("form_login"):
                email_input = st.text_input("E-mail")
                senha_input = st.text_input("Senha", type="password")
                botao_submit = st.form_submit_button(
                    "Entrar", use_container_width=True
                )

                if botao_submit:
                    if not email_input or not senha_input:
                        st.warning("Preencha todos os campos.")
                    else:
                        usuario = autenticar_usuario(email_input, senha_input)
                        if usuario:
                            st.session_state["usuario_logado"] = usuario
                            st.rerun()
                        else:
                            st.error("E-mail ou senha incorretos.")

        with aba_esqueci:
            st.write(
                "Para garantir a segurança dos dados corporativos, as redefinições de acesso são auditadas."
            )
            email_recupera = st.text_input(
                "Informe seu E-mail de Cadastro", key="recup_email"
            )
            
            if st.button("Gravar Solicitação", use_container_width=True):
                if email_recupera:
                    engine = get_engine()
                    registrar_log(
                        engine,
                        "SOLICITACAO_REDEFINICAO_SENHA",
                        email_recupera,
                        None,
                        "Solicitou redefinição pela tela inicial",
                    )
                    st.success("✅ Solicitação de redefinição gravada com segurança em nosso sistema.")
                    
                    st.info(
                        "**Próximo passo:**\n"
                        "Para agilizar o seu atendimento, clique no botão abaixo e notifique o administrador ou o comercial do Grupo Querino via WhatsApp."
                    )
                    
                    # Número de suporte/comercial para onde o cliente será direcionado (Ex: 55 + DDD + Numero)
                    numero_whatsapp = "551921442321" 
                    mensagem = f"Olá! Acabei de registrar no Portal um pedido de redefinição de senha para o e-mail: {email_recupera}"
                    link_whatsapp = f"https://wa.me/{numero_whatsapp}?text={mensagem.replace(' ', '%20')}"
                    
                    st.link_button("📱 Notificar Suporte (WhatsApp)", link_whatsapp, use_container_width=True)
                    
                else:
                    st.warning("Por favor, informe seu e-mail de cadastro primeiro.")


# --- Configuração das Páginas e Navegação ---
pg_login = st.Page(tela_login, title="Login", icon="🔑")
pg_dash = st.Page("pages/Dashboard.py", title="Dashboard", icon="📊")
pg_users = st.Page("pages/Usuarios.py", title="Gestão de Clientes", icon="👤")

user = st.session_state.get("usuario_logado")

# Se não estiver logado OU se for o primeiro acesso (que exige troca de senha), mantém na tela de login
if not user or user.get("primeiro_acesso") == 1:
    pg = st.navigation([pg_login], position="hidden")
else:
    if user["perfil"] == "admin":
        pg = st.navigation({"Painel Principal": [pg_dash, pg_users]})
    else:
        pg = st.navigation({"Painel Principal": [pg_dash]})

pg.run()