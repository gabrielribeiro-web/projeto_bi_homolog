import streamlit as st
from auth import alterar_senha_primeiro_acesso, autenticar_usuario, registrar_log
from database import get_engine

st.set_page_config(
    page_title="Portal Dashboard. - Grupo Querino", page_icon="📊", layout="wide"
)

if "usuario_logado" not in st.session_state:
    st.session_state["usuario_logado"] = None


def tela_login():
    # --- CSS CUSTOMIZADO EXCLUSIVO PARA A TELA DE LOGIN ---
    # Este CSS só existe enquanto esta tela estiver aberta. Após o login, ele desaparece.
    st.markdown(
        """
        <style>
        /* Oculta a barra lateral e o cabeçalho padrão do Streamlit */
        [data-testid="stSidebar"] {display: none;}
        [data-testid="stHeader"] {display: none;}
        
        /* Força o fundo escuro elegante APENAS nesta tela */
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%) !important;
        }
        
        /* Força as labels (E-mail, Senha, Abas) a ficarem brancas/cinzas claras.
           Isso evita que o texto fique preto e suma caso o PC do usuário seja tema Claro. */
        .stApp p, .stApp label, [data-baseweb="tab"] p, .stMarkdown p {
            color: #f8fafc !important;
        }
        
        /* Ajuste estético para as abas (Tabs) do Login */
        .stTabs [data-baseweb="tab-list"] {
            justify-content: center;
            background-color: transparent;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Cria colunas para centralizar a caixa de login no meio da tela
    col1, col2, col3 = st.columns([1, 1.2, 1])

    with col2:
        # Espaçamento no topo para não ficar colado
        st.write("")
        st.write("")
        st.write("")
        st.write("")

        # --- LOGO DA EMPRESA ---
        col_espaco1, col_logo, col_espaco2 = st.columns([1, 2, 1])
        with col_logo:
            import os
            if os.path.exists("logo.png"):
                st.image("logo.png", use_container_width=True)
            else:
                st.markdown("<h2 style='text-align: center; color: #f8fafc;'>📊 Portal Dashboard.</h2>", unsafe_allow_html=True)
        
        st.write("") # Espaço entre a logo e a caixa de login

        # CASO 1: Usuário logado precisando alterar a senha no PRIMEIRO ACESSO
        user = st.session_state.get("usuario_logado")
        if user and user.get("primeiro_acesso") == 1:
            st.warning("🔒 **Primeiro Acesso Detectado**")
            st.caption("Por motivos de segurança, altere a senha provisória fornecida para continuar.")

            with st.form("form_troca_obrigatoria"):
                senha_atual = st.text_input("Senha Provisória Atual", type="password")
                nova_senha = st.text_input("Nova Senha", type="password")
                confirma_senha = st.text_input("Confirme a Nova Senha", type="password")
                btn_alterar = st.form_submit_button("Salvar Nova Senha e Continuar", use_container_width=True)

                if btn_alterar:
                    if not senha_atual or not nova_senha or not confirma_senha:
                        st.error("Preencha todos os campos.")
                    elif nova_senha != confirma_senha:
                        st.error("A nova senha e a confirmação não coincidem.")
                    elif len(nova_senha) < 6:
                        st.error("A nova senha deve ter no mínimo 6 caracteres.")
                    else:
                        sucesso, msg = alterar_senha_primeiro_acesso(user["id"], senha_atual, nova_senha, user["email"])
                        if sucesso:
                            st.session_state["usuario_logado"]["primeiro_acesso"] = 0
                            st.success("Senha atualizada! Redirecionando...")
                            st.rerun()
                        else:
                            st.error(msg)
            return

        # CASO 2: Tela de Login Convencional
        st.markdown("<h4 style='text-align: center; color: #f8fafc;'>Acesso ao Portal de Dashboard</h4>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #94a3b8; font-size: 14px;'>Insira suas credenciais</p>", unsafe_allow_html=True)

        aba_login, aba_esqueci = st.tabs(["Entrar", "❓ Esqueci minha senha"])

        with aba_login:
            with st.form("form_login"):
                email_input = st.text_input("E-mail")
                senha_input = st.text_input("Senha", type="password")
                botao_submit = st.form_submit_button("Entrar", use_container_width=True)

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
            st.caption("Para garantir a segurança dos dados, as redefinições são auditadas.")
            email_recupera = st.text_input("E-mail de Cadastro", key="recup_email")
            grupo_recupera = st.text_input("Grupo / Empresa", key="recup_grupo")
            
            if st.button("Gravar Solicitação", use_container_width=True):
                if email_recupera and grupo_recupera:
                    engine = get_engine()
                    registrar_log(
                        engine,
                        "SOLICITACAO_REDEFINICAO_SENHA",
                        email_recupera,
                        None,
                        f"Solicitou redefinição. Grupo: {grupo_recupera}",
                    )
                    st.success("✅ Solicitação gravada no sistema.")
                    
                    st.info("**Próximo passo:** Clique abaixo para notificar nossa equipe de suporte.")
                    
                    # --- CONFIGURAÇÃO WHATSAPP ---
                    numero_whatsapp = "5519999999999" # Mude para o número real
                    msg_zap = f"Olá! Acabei de registrar no Portal um pedido de redefinição de senha para o e-mail: {email_recupera} (Grupo: {grupo_recupera})"
                    link_whatsapp = f"https://wa.me/{numero_whatsapp}?text={msg_zap.replace(' ', '%20')}"
                    
                    st.link_button("📱 Notificar via WhatsApp", link_whatsapp, use_container_width=True)
                else:
                    st.warning("Informe seu E-mail e o nome do Grupo/Empresa.")


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