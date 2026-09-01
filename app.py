import os
import random
import streamlit as st
from database import get_engine
from auth import (
    autenticar_usuario,
    verificar_token,
    alterar_senha_primeiro_acesso,
    registrar_log,
)

# ==============================================================
# 1. CONFIGURAÇÃO GERAL DA PÁGINA (Efeito Anti-Fantasma)
# ==============================================================
st.set_page_config(
    page_title="Portal Dashboard - Grupo Querino",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",  # Previne o carregamento inicial da sidebar no login
)


# ==============================================================
# 2. DESIGN CUSTOMIZADO E RESPONSIVO (TELA DE LOGIN)
# ==============================================================
def tela_login():
    # CSS de alta prioridade com suporte nativo para Smartphones (Media Queries)
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }
        
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #1a1e38 100%) !important;
        }
        
        .stApp p, .stApp label, [data-baseweb="tab"] p, .stMarkdown p {
            color: #fdfdfd !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            justify-content: center;
            background-color: transparent;
        }
        
        /* 🟩 BOTÃO DE LOGIN VERDE QUERINO */
        button[kind="formSubmit"], 
        button[kind="secondary"],
        div[data-testid="stFormSubmitButton"] > button {
            background-color: #aecb36 !important; 
            border: none !important;
            border-radius: 8px !important;
        }
        
        button[kind="formSubmit"] *, 
        button[kind="secondary"] *,
        div[data-testid="stFormSubmitButton"] > button * {
            color: #1a1e38 !important;
            font-weight: bold !important;
        }
        
        button[kind="formSubmit"]:hover, 
        div[data-testid="stFormSubmitButton"] > button:hover {
            background-color: #fdfdfd !important;
        }
        
        /* ⬜ BLINDAGEM TOTAL DOS INPUTS (E-mail e Senha 100% Brancos) */
        div[data-testid="stTextInput"] div[data-baseweb="input"],
        div[data-testid="stTextInput"] div[data-baseweb="input"] > div,
        div[data-testid="stTextInput"] input {
            background-color: #ffffff !important;
            background: #ffffff !important;
        }
        
        div[data-testid="stTextInput"] div[data-baseweb="input"] {
            border: 1px solid #cccccc !important;
            border-radius: 8px !important;
        }
        
        div[data-testid="stTextInput"] input {
            color: #1a1e38 !important;
            -webkit-text-fill-color: #1a1e38 !important;
            font-weight: 500 !important;
        }
        
        div[data-testid="stTextInput"] button {
            background-color: transparent !important;
            border: none !important;
        }
        
        div[data-testid="stTextInput"] svg {
            fill: #1a1e38 !important;
            color: #1a1e38 !important;
        }

        /* 📱 RESPONSIVIDADE ADAPTATIVA PARA NAVEGADORES MOBILE (CELULARES) */
        @media (max-width: 768px) {
            .main .block-container {
                padding-left: 0.8rem !important;
                padding-right: 0.8rem !important;
                padding-top: 1rem !important;
            }
            
            /* Força o formulário a ocupar 100% da largura em telas pequenas */
            div[data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 100% !important;
            }

            h2 { font-size: 1.3rem !important; }
            h4 { font-size: 1.1rem !important; }

            /* Melhora o espaçamento de toque nos botões e abas no mobile */
            button {
                min-height: 44px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.2, 1])

    with col2:
        st.write("")
        st.write("")

        col_espaco1, col_logo, col_espaco2 = st.columns([1, 2, 1])
        with col_logo:
            if os.path.exists("logo.png"):
                st.image("logo.png", use_container_width=True)
            else:
                st.markdown(
                    "<h2 style='text-align: center; color: #fdfdfd;'>📊 Portal Dashboard.</h2>",
                    unsafe_allow_html=True,
                )

        st.write("")

        # Tratamento de Primeiro Acesso
        primeiro_acesso_check = st.session_state.get("primeiro_acesso")
        if primeiro_acesso_check == 1:
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
                        usuario_id = st.session_state.get("usuario_id")
                        usuario_email = st.session_state.get("usuario_email")
                        sucesso, msg = alterar_senha_primeiro_acesso(
                            usuario_id, senha_atual, nova_senha, usuario_email
                        )
                        if sucesso:
                            st.session_state["primeiro_acesso"] = 0
                            st.success("Senha atualizada! Redirecionando...")
                            st.rerun()
                        else:
                            st.error(msg)
            return

        st.markdown(
            "<h4 style='text-align: center; color: #fdfdfd;'>Acesso ao Portal de Dashboard</h4>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align: center; color: #8e8e8e; font-size: 14px;'>Insira suas credenciais</p>",
            unsafe_allow_html=True,
        )

        aba_login, aba_esqueci = st.tabs(["Entrar", "❓ Esqueci minha senha"])

        with aba_login:
            if (
                "captcha_n1" not in st.session_state
                or "captcha_n2" not in st.session_state
            ):
                st.session_state["captcha_n1"] = random.randint(1, 9)
                st.session_state["captcha_n2"] = random.randint(1, 9)

            n1 = st.session_state["captcha_n1"]
            n2 = st.session_state["captcha_n2"]

            if "msg_erro_captcha" in st.session_state:
                st.error(st.session_state["msg_erro_captcha"])
                del st.session_state["msg_erro_captcha"]

            with st.form("form_login"):
                email_input = st.text_input("E-mail")
                senha_input = st.text_input("Senha", type="password")

                st.markdown(
                    f"<p style='color:#8e8e8e; font-size:12px; margin-bottom: 0px;'>🤖 Verificação de Segurança: <b>Quanto é {n1} + {n2}?</b></p>",
                    unsafe_allow_html=True,
                )
                resposta_captcha = st.text_input(
                    "Resultado",
                    key="captcha_input",
                    label_visibility="collapsed",
                )

                st.write("")
                botao_submit = st.form_submit_button(
                    "Entrar", use_container_width=True
                )

                if botao_submit:
                    try:
                        val_digitado = (
                            int(resposta_captcha.strip())
                            if resposta_captcha
                            else None
                        )
                    except ValueError:
                        val_digitado = None

                    if val_digitado != (n1 + n2):
                        st.session_state["captcha_n1"] = random.randint(1, 9)
                        st.session_state["captcha_n2"] = random.randint(1, 9)
                        st.session_state["msg_erro_captcha"] = (
                            "❌ Resposta de segurança incorreta. Tente novamente."
                        )
                        st.rerun()

                    usuario_dados, msg = autenticar_usuario(
                        email_input, senha_input
                    )
                    if usuario_dados:
                        st.success("Acesso autorizado!")
                        st.rerun()
                    else:
                        st.error(msg)

        with aba_esqueci:
            st.caption(
                "Para garantir a segurança dos dados, as redefinições são auditadas."
            )
            email_recupera = st.text_input("E-mail de Cadastro")
            grupo_recupera = st.text_input("Grupo / Empresa")

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
                    st.info(
                        "**Próximo passo:** Clique abaixo para notificar nossa equipe de suporte."
                    )

                    numero_whatsapp = "5519999999999"
                    msg_zap = f"Olá! Acabei de registrar no Portal um pedido de redefinição de senha para o e-mail: {email_recupera} (Grupo: {grupo_recupera})"
                    link_whatsapp = f"https://wa.me/{numero_whatsapp}?text={msg_zap.replace(' ', '%20')}"

                    st.link_button(
                        "📱 Notificar via WhatsApp",
                        link_whatsapp,
                        use_container_width=True,
                    )
                else:
                    st.warning("Informe seu E-mail e o nome do Grupo/Empresa.")


# ==============================================================
# 3. GESTÃO DE ROTEAMENTO (ISOLAMENTO ANTI-FANTASMA)
# ==============================================================

# Se NÃO houver um Token JWT válido, força a ocultação da UI e encerra a execução antes de renderizar rotas
if not verificar_token():
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="stHeader"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    pg_login = st.Page(tela_login, title="Login", icon="🔑")
    pg = st.navigation([pg_login], position="hidden")
    pg.run()
    st.stop()

# Fluxo Autenticado
nome_usuario = st.session_state.get("usuario_nome")
perfil_usuario = st.session_state.get("perfil")

st.sidebar.markdown(
    f"""
    <div id="profile-card" style="background-color: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #aecb36;">
        <p style="margin: 0; font-weight: bold; color: #1a1e38; font-size: 15px;">👤 {nome_usuario}</p>
        <p style="margin: 0; font-size: 11px; color: #aecb36; font-weight: bold; letter-spacing: 1px; margin-top: 3px;">PERFIL: {str(perfil_usuario).upper()}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

visao_geral = st.Page("views/1_visao_geral.py", title="Visão Executiva", icon="📊")
qualidade = st.Page(
    "views/2_qualidade.py", title="Qualidade e Entregas", icon="🎓"
)
operacao = st.Page("views/3_operacao.py", title="Operação", icon="⚙️")

paginas_cliente = [visao_geral, qualidade, operacao]

if perfil_usuario == "admin":
    comercial = st.Page(
        "views/4_comercial.py", title="Vendas e Comercial", icon="📈"
    )
    financeiro = st.Page(
        "views/5_financeira.py",
        title="Faturamento e Inadimplência",
        icon="💰",
    )
    importacao = st.Page(
        "views/7_importacao.py", title="Sincronizar Dados", icon="🔄"
    )
    usuarios = st.Page(
        "views/6_usuarios.py", title="Usuários e Acessos", icon="👥"
    )

    pg = st.navigation({
        "📊 Análises e Operação": paginas_cliente,
        "💼 Comercial e Financeiro": [comercial, financeiro],
        "🛠️ Configurações do Sistema": [importacao, usuarios],
    })
else:
    pg = st.navigation({"📊 Acompanhamento Operacional": paginas_cliente})

if st.sidebar.button("🚪 Sair (Logout)", use_container_width=True):
    st.session_state.clear()
    st.rerun()

pg.run()