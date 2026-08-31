import streamlit as st
from auth import alterar_senha_primeiro_acesso, autenticar_usuario, registrar_log
from database import get_engine

st.set_page_config(
    page_title="Portal Dashboard - Grupo Querino", page_icon="📊", layout="wide"
)

if "usuario_logado" not in st.session_state:
    st.session_state["usuario_logado"] = None

def tela_login():
    # --- CSS CUSTOMIZADO EXCLUSIVO PARA A TELA DE LOGIN ---
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display: none;}
        [data-testid="stHeader"] {display: none;}
        
        /* Fundo da tela Escuro e Elegante */
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #1a1e38 100%) !important;
        }
        
        /* Deixa todos os textos brancos (labels, abas, parágrafos) */
        .stApp p, .stApp label, [data-baseweb="tab"] p, .stMarkdown p {
            color: #fdfdfd !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            justify-content: center;
            background-color: transparent;
        }
        
        /* 🟩 BLINDAGEM DO BOTÃO: Força todos os botões de formulário a ficarem Verdes */
        button[kind="formSubmit"], 
        button[kind="secondary"],
        div[data-testid="stFormSubmitButton"] > button {
            background-color: #aecb36 !important; 
            border: none !important;
            border-radius: 8px !important;
        }
        
        /* ⬛ Letras do Botão: Força a ficarem Azul Escuro */
        button[kind="formSubmit"] *, 
        button[kind="secondary"] *,
        div[data-testid="stFormSubmitButton"] > button * {
            color: #1a1e38 !important;
            font-weight: bold !important;
        }
        
        /* Efeito de Hover (passar o mouse) */
        button[kind="formSubmit"]:hover, 
        div[data-testid="stFormSubmitButton"] > button:hover {
            background-color: #fdfdfd !important;
        }
        
        /* Ajuste dos inputs (Caixas de texto de E-mail e Senha) */
        div[data-baseweb="input"] {
            background-color: rgba(253, 253, 253, 0.1) !important;
            border: 1px solid rgba(253, 253, 253, 0.2) !important;
        }
        div[data-baseweb="input"] input {
            color: #fdfdfd !important;
            -webkit-text-fill-color: #fdfdfd !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.2, 1])

    with col2:
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
                st.markdown("<h2 style='text-align: center; color: #fdfdfd;'>📊 Portal Dashboard.</h2>", unsafe_allow_html=True)
        
        st.write("")

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
        st.markdown("<h4 style='text-align: center; color: #fdfdfd;'>Acesso ao Portal de Dashboard</h4>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #8e8e8e; font-size: 14px;'>Insira suas credenciais</p>", unsafe_allow_html=True)

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
                    
                    numero_whatsapp = "5519999999999" # Mude para o número
                    msg_zap = f"Olá! Acabei de registrar no Portal um pedido de redefinição de senha para o e-mail: {email_recupera} (Grupo: {grupo_recupera})"
                    link_whatsapp = f"https://wa.me/{numero_whatsapp}?text={msg_zap.replace(' ', '%20')}"
                    
                    st.link_button("📱 Notificar via WhatsApp", link_whatsapp, use_container_width=True)
                else:
                    st.warning("Informe seu E-mail e o nome do Grupo/Empresa.")

# ==========================================
# GESTÃO DE ROTEAMENTO (NAVEGAÇÃO SEGURA)
# ==========================================

user = st.session_state.get("usuario_logado")

if not user or user.get("primeiro_acesso") == 1:
    pg_login = st.Page(tela_login, title="Login", icon="🔑")
    pg = st.navigation([pg_login], position="hidden")

else:
    # ==============================================================
    # 1. PERFIL NO TOPO DA BARRA LATERAL (Antes do Menu)
    # ==============================================================
    st.sidebar.markdown(
        f"""
        <div style="background-color: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #aecb36;">
            <p style="margin: 0; font-weight: bold; color: #fdfdfd; font-size: 15px;">👤 {user['nome']}</p>
            <p style="margin: 0; font-size: 11px; color: #aecb36; font-weight: bold; letter-spacing: 1px; margin-top: 3px;">PERFIL: {user['perfil'].upper()}</p>
        </div>
        """, unsafe_allow_html=True
    )

    visao_geral = st.Page("views/1_visao_geral.py", title="Visão Executiva", icon="📊")
    qualidade = st.Page("views/2_qualidade.py", title="Qualidade e Entregas", icon="🎓")
    operacao = st.Page("views/3_operacao.py", title="Operação", icon="⚙️") 
    
    paginas_cliente = [visao_geral, qualidade, operacao]

    if user["perfil"] == "admin":
        comercial = st.Page("views/4_comercial.py", title="Vendas e Comercial", icon="📈")
        financeiro = st.Page("views/5_financeira.py", title="Faturamento e Inadimplência", icon="💰")
        usuarios = st.Page("views/6_usuarios.py", title="Usuários e Acessos", icon="👥")
        
        pg = st.navigation({
            "📊 Análises e Operação": paginas_cliente,
            "💼 Comercial e Financeiro": [comercial, financeiro], # <- NOVO NOME AQUI
            "🛠️ Configurações do Sistema": [usuarios]
        })
    else:
        pg = st.navigation({"📊 Acompanhamento Operacional": paginas_cliente})

    # ==============================================================
    # 2. BOTÃO DE SAIR NO FUNDO DA BARRA LATERAL (Depois do Menu)
    # ==============================================================
    if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
        st.session_state["usuario_logado"] = None
        st.rerun()

pg.run()