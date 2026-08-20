import os
from datetime import date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from database import get_engine
from sqlalchemy import text
from queries import (
    buscar_distribuicao_tipo,
    buscar_grafico_nrs,
    buscar_investimento_mensal,
    buscar_kpis,
    buscar_proximas_turmas,
    buscar_ranking_instrutores,
    buscar_detalhamento_financeiro,
    buscar_lista_participantes,
)

st.set_page_config(
    page_title="Dashboard - Grupo Querino", page_icon="📊", layout="wide"
)

user = st.session_state.get("usuario_logado")
if not user:
    st.warning("Acesso negado. Por favor, faça login.")
    st.stop()

# Sidebar de perfil
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

engine = get_engine()

# Cabeçalho
col_tit, col_logo = st.columns([3, 1])
with col_tit:
    st.title("📊 Portal de Dashboard")
    st.caption("Visão Consolidada de Treinamentos e Indicadores Financeiros")
with col_logo:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=180)

# --- PAINEL DE FILTROS SUPERIOR ---
st.subheader("🔍 Filtros de Visualização")
f1, f2, f3, f4 = st.columns([1.5, 1.2, 1, 1])

with f1:
    if user["perfil"] == "admin":
        df_grupos = pd.read_sql_query(
            "SELECT DISTINCT grupo FROM dim_clientes WHERE grupo IS NOT NULL ORDER BY grupo",
            engine,
        )
        grupo_sel = st.selectbox(
            "Grupo / Cliente:", ["Todos"] + df_grupos["grupo"].tolist()
        )
    else:
        grupo_sel = user.get("grupo")
        st.info(f"Grupo: **{grupo_sel}**")

# FILTRO DE UNIDADE
with f2:
    if grupo_sel and grupo_sel != "Todos":
        query_unidades = text(
            "SELECT DISTINCT unidade FROM public.fato_comercial WHERE unidade IS NOT NULL AND unidade != '' AND grupo = :grupo ORDER BY unidade"
        )
        df_unidades = pd.read_sql_query(
            query_unidades, engine, params={"grupo": grupo_sel}
        )
    else:
        query_unidades = text(
            "SELECT DISTINCT unidade FROM public.fato_comercial WHERE unidade IS NOT NULL AND unidade != '' ORDER BY unidade"
        )
        df_unidades = pd.read_sql_query(query_unidades, engine)

    unidade_sel = st.selectbox(
        "Unidade / Planta:", ["Todas"] + df_unidades["unidade"].tolist()
    )

with f3:
    dt_inicio = st.date_input("Data Inicial:", value=date(2026, 1, 1))
with f4:
    dt_fim = st.date_input("Data Final:", value=date(2026, 12, 31))

# Carregamento de dados com TODOS os filtros
df_kpis = buscar_kpis(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_nrs = buscar_grafico_nrs(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_tipo = buscar_distribuicao_tipo(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_mes = buscar_investimento_mensal(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_proximas = buscar_proximas_turmas(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_instrutores = buscar_ranking_instrutores(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_financeiro = buscar_detalhamento_financeiro(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)
df_participantes = buscar_lista_participantes(
    engine, grupo_cliente=grupo_sel, unidade=unidade_sel, data_inicio=dt_inicio, data_fim=dt_fim
)

st.divider()

# --- ESTRUTURA DE EXIBIÇÃO (ABAS PARA ADMIN, PÁGINA ÚNICA PARA CLIENTE) ---
if user["perfil"] == "admin":
    tabs = st.tabs(["📊 Visão Geral", "🎓 Operação", "💰 Financeira"])
    container_executiva = tabs[0]
    container_operacional = tabs[1]
    container_financeira = tabs[2]
else:
    # Se for cliente, cria blocos em branco um embaixo do outro
    container_executiva = st.container()
    container_operacional = st.container()
    container_financeira = None  # Cliente não vê posição financeira interna

# Estilo de Tooltips
hover_style = dict(
    bgcolor="#ffffff",
    font_size=13,
    font_color="#09090b",
    font_family="Arial",
)

# ==========================================
# BLOCO 1: VISÃO EXECUTIVA
# ==========================================
with container_executiva:
    
    if user["perfil"] == "admin":
        st.markdown("#### 💼 Financeiro")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Faturamento Realizado", f"R$ {df_kpis['total_faturado'].iloc[0]:,.2f}")
        c2.metric("Futuro Agendado", f"R$ {df_kpis['futuro_agendado'].iloc[0]:,.2f}")
        c3.metric("Futuro Lançado", f"R$ {df_kpis['futuro_lancado'].iloc[0]:,.2f}")
        c4.metric("Pendências (Gargalo)", f"R$ {df_kpis['total_pendencia'].iloc[0]:,.2f}")
    else:
        st.markdown("#### 💼 Investimento")
        c1, c2, c3 = st.columns(3)
        c1.metric("Investimento Realizado (Turmas Concluídas)", f"R$ {df_kpis['total_faturado'].iloc[0]:,.2f}")
        investimento_futuro = df_kpis['futuro_agendado'].iloc[0] + df_kpis['futuro_lancado'].iloc[0]
        c2.metric("Investimento Agendado (Próximas Turmas)", f"R$ {investimento_futuro:,.2f}")
        c3.metric("Unidades Atendidas", f"{df_kpis['unidades_atendidas'].iloc[0]:,}")

    st.divider()

    # O erro de indentação começava aqui. Agora está tudo alinhado dentro do 'with container_executiva:'
    st.markdown("#### ⚙️ Entregas e Qualidade (Realizado)")
    
    if user["perfil"] == "admin":
        c5, c6, c7, c8, c9 = st.columns(5)
        turmas_fmt = f"{int(df_kpis['turmas_realizadas'].iloc[0]):,}".replace(",", ".")
        horas_fmt = f"{int(df_kpis['horas_realizadas'].iloc[0]):,}".replace(",", ".")
        pessoas_fmt = f"{int(df_kpis['pessoas_treinadas'].iloc[0]):,}".replace(",", ".")
        unidades_fmt = f"{int(df_kpis['unidades_atendidas'].iloc[0]):,}".replace(",", ".")
        
        c5.metric("Turmas Realizadas", turmas_fmt)
        c6.metric("Horas Treinamento", f"{horas_fmt}h")
        c7.metric("Pessoas Treinadas", pessoas_fmt)
        c8.metric("Aproveitamento Médio", f"{df_kpis['aproveitamento_medio'].iloc[0] or 0:.2f} ⭐")
        c9.metric("Unidades Atendidas", unidades_fmt)
    else:
        c5, c6, c7, c8 = st.columns(4)
        turmas_fmt = f"{int(df_kpis['turmas_realizadas'].iloc[0]):,}".replace(",", ".")
        pessoas_fmt = f"{int(df_kpis['pessoas_treinadas'].iloc[0]):,}".replace(",", ".")
        horas_fmt = f"{int(df_kpis['horas_realizadas'].iloc[0]):,}".replace(",", ".")
        
        c5.metric("Turmas Realizadas", turmas_fmt)
        c6.metric("Pessoas Treinadas (Certificados)", pessoas_fmt)
        c7.metric("Carga Horária Consumida", f"{horas_fmt}h")
        c8.metric("Nota Média (Qualidade)", f"{df_kpis['aproveitamento_medio'].iloc[0] or 0:.2f} ⭐")

    st.divider()

    g1, g2, g3 = st.columns([1.2, 1, 1.5])
    with g1:
        fig_nrs = px.bar(
            df_nrs, x="contagem", y="cod_treinamento", orientation="h",
            title="Volume de Turmas por Norma (Top 5)", text="contagem",
            color_discrete_sequence=["#84cc16"]
        )
        fig_nrs.update_layout(yaxis={"categoryorder": "total ascending"}, hoverlabel=hover_style)
        st.plotly_chart(fig_nrs, use_container_width=True)

    with g2:
        fig_pie = px.pie(
            df_tipo, values="qtd", names="tipo", hole=0.5,
            title="Distribuição por Tipo",
            color_discrete_sequence=["#84cc16", "#38bdf8", "#a855f7"]
        )
        fig_pie.update_layout(hoverlabel=hover_style)
        st.plotly_chart(fig_pie, use_container_width=True)

    with g3:
        fig_mes = go.Figure()
        fig_mes.add_trace(go.Bar(x=df_mes["mes_ano"], y=df_mes["turmas"], name="Turmas", marker_color="#84cc16"))
        fig_mes.add_trace(go.Scatter(x=df_mes["mes_ano"], y=df_mes["investimento"], name="Investimento (R$)", yaxis="y2", line=dict(color="#38bdf8", width=3)))
        fig_mes.update_layout(
            title="Turmas e Investimento por Mês",
            yaxis=dict(title="Qtd Turmas"),
            yaxis2=dict(title="Investimento (R$)", overlaying="y", side="right"),
            legend=dict(x=0, y=1.1, orientation="h"),
            hoverlabel=hover_style,
        )
        st.plotly_chart(fig_mes, use_container_width=True)

    st.divider()

    st.subheader("📅 Próximas Turmas Agendadas")
    st.dataframe(
        df_proximas,
        use_container_width=True,
        hide_index=True,
        column_config={
            "inicio": "Data Início",
            "grupo": "Grupo / Cliente",
            "treinamento": "Treinamento / Norma",
            "unidade": "Unidade",
            "instrutor": "Instrutor",
            "valor": st.column_config.NumberColumn("Valor Contratado", format="R$ %.2f"),
        },
    )

# ==========================================
# BLOCO 2: QUALIDADE & OPERAÇÃO
# ==========================================
with container_operacional:
    
    if user["perfil"] != "admin":
        st.divider()
        st.markdown("### 🎓 Qualidade Operacional")
        
    # --- 1. RELAÇÃO DE ALUNOS (AGORA NO TOPO) ---
    st.subheader("👥 Relação de Colaboradores Treinados")
    st.caption("Lista consolidada de todos os participantes que concluíram os treinamentos.")

    if 'df_participantes' not in locals() or df_participantes.empty:
        st.info("Nenhum participante encontrado para os filtros selecionados.")
    else:
        pesquisa_nome = st.text_input("🔍 Buscar participante por Nome ou CPF (digite apenas os números):", placeholder="Ex: João ou 12345678900")
        
        df_exibir = df_participantes.copy()
        
        # 1. Aplica o filtro de pesquisa na base original (antes de mascarar)
        if pesquisa_nome:
            mascara = df_exibir["Nome do Participante"].astype(str).str.contains(pesquisa_nome, case=False, na=False) | \
                      df_exibir["CPF"].astype(str).str.contains(pesquisa_nome, na=False)
            df_exibir = df_exibir[mascara]
            
        # 2. Função para aplicar a máscara LGPD (***.456.789-**)
        def aplicar_mascara_lgpd(cpf):
            # Limpa qualquer ponto ou traço que possa vir do banco
            cpf_str = str(cpf).replace('.', '').replace('-', '').strip()
            
            if len(cpf_str) == 11:
                return f"***.{cpf_str[3:6]}.{cpf_str[6:9]}-**"
            elif cpf_str and cpf_str.lower() != 'nan' and cpf_str.lower() != 'none':
                # Se o CPF não tiver 11 dígitos, esconde tudo por segurança
                return "***.***.***-**" 
            return ""

        # 3. Substitui a coluna CPF pela versão protegida para exibição
        df_exibir["CPF"] = df_exibir["CPF"].apply(aplicar_mascara_lgpd)
            
        st.dataframe(
            df_exibir,
            use_container_width=True,
            hide_index=True,
            height=400,
            column_config={
                "CPF": st.column_config.TextColumn("CPF (Protegido)") 
            }
        )

    st.divider()
        
    # --- 2. INSTRUTORES (AGORA EMBAIXO) ---
    st.subheader("👨‍🏫 Desempenho e Volume por Instrutor")
    st.caption("Acompanhe o volume de turmas realizadas e as notas médias de avaliação técnica.")
    
    if df_instrutores.empty:
        st.info("Nenhum dado de operação encontrado para os filtros selecionados.")
    else:
        df_top_instrutores = df_instrutores.head(10).sort_values(by="turmas_realizadas", ascending=True)
        
        o1, o2 = st.columns([1.5, 1])
        
        with o1:
            fig_inst = px.bar(
                df_top_instrutores, x="turmas_realizadas", y="instrutor", orientation="h",
                title="Top 10 Instrutores (Por Volume de Turmas)", text="turmas_realizadas",
                color_discrete_sequence=["#38bdf8"]
            )
            fig_inst.update_layout(hoverlabel=hover_style)
            st.plotly_chart(fig_inst, use_container_width=True)
            
        with o2:
            st.write("**Tabela Geral de Qualidade**")
            st.dataframe(
                df_instrutores,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "instrutor": "Nome do Instrutor",
                    "turmas_realizadas": st.column_config.NumberColumn("Turmas", format="%d"),
                    "pessoas_treinadas": st.column_config.NumberColumn("Alunos", format="%d"),
                    "nota_media": st.column_config.NumberColumn("Nota Média", format="%.2f ⭐", help="Média técnica calculada por aluno."),
                },
                height=350
            )

# ==========================================
# BLOCO 3: POSIÇÃO FINANCEIRA
# ==========================================
if container_financeira:
    with container_financeira:
        st.subheader("💰 Gestão de Faturamento e Pendências")
        st.caption("Acompanhe o detalhamento financeiro e utilize os filtros para focar nas cobranças.")
        
        if df_financeiro.empty:
            st.info("Nenhum dado financeiro encontrado para os filtros globais selecionados.")
        else:
# --- 1. CRIANDO A BARRA DE FILTROS ESPECÍFICA DA ABA ---
            st.markdown("##### 🔍 Filtros Financeiros")
            
            def extrair_mes_ano(dt):
                if pd.isna(dt) or not isinstance(dt, str) or len(dt.strip()) < 10:
                    return "Sem Data"
                return dt.strip()[3:10]
                
            df_financeiro["Mes_Ano"] = df_financeiro["Data Término"].apply(extrair_mes_ano)
            
            cf1, cf2, cf3 = st.columns(3)
            
            with cf1:
                status_opcoes = sorted(df_financeiro["Status Comercial"].dropna().unique().tolist())
                status_selecionados = st.multiselect(
                    "Status Comercial (Vazio = Todos):",
                    options=status_opcoes,
                    default=[] # <-- Vazio por padrão para não poluir a tela
                )
                
            with cf2:
                grupo_opcoes = sorted(df_financeiro["Grupo"].dropna().unique().tolist())
                grupo_selecionados = st.multiselect(
                    "Grupo / Cliente (Vazio = Todos):",
                    options=grupo_opcoes,
                    default=[] # <-- Vazio por padrão
                )
                
            with cf3:
                mes_opcoes = sorted(df_financeiro["Mes_Ano"].unique().tolist())
                mes_selecionados = st.multiselect(
                    "Mês / Ano do Término (Vazio = Todos):",
                    options=mes_opcoes,
                    default=[] # <-- Vazio por padrão
                )

# --- 2. APLICANDO OS FILTROS AO DATAFRAME ---
            # Começamos com a base completa
            df_fin_filtrado = df_financeiro.copy()
            
            # Só aplicamos o filtro se o usuário escolheu algo na caixinha
            if status_selecionados:
                df_fin_filtrado = df_fin_filtrado[df_fin_filtrado["Status Comercial"].isin(status_selecionados)]
                
            if grupo_selecionados:
                df_fin_filtrado = df_fin_filtrado[df_fin_filtrado["Grupo"].isin(grupo_selecionados)]
                
            if mes_selecionados:
                df_fin_filtrado = df_fin_filtrado[df_fin_filtrado["Mes_Ano"].isin(mes_selecionados)]
            
            st.divider()

            # --- 3. EXIBINDO GRÁFICOS E TABELA COM OS DADOS FILTRADOS ---
            mascara_pendencia = (
                df_fin_filtrado["Validação (Operação)"].isin(['FATURAR', 'CANCELADO DIA', 'CANCELADO 24H']) & 
                (df_fin_filtrado["Status Comercial"] != 'OK')
            )
            df_pendencias = df_fin_filtrado[mascara_pendencia]
            
            f1, f2 = st.columns([1, 1.8])
            
            with f1:
                st.markdown("##### Resumo")
                if df_fin_filtrado.empty:
                    st.warning("Sem dados para este filtro.")
                else:
                    resumo_status = df_fin_filtrado.groupby("Status Comercial")["Valor (R$)"].sum().reset_index()
                    resumo_status = resumo_status.sort_values(by="Valor (R$)", ascending=True)
                    
                    fig_status = px.bar(
                        resumo_status,
                        y="Status Comercial",
                        x="Valor (R$)",
                        orientation="h",
                        text_auto=".2s",
                        color="Status Comercial",
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    fig_status.update_layout(showlegend=False, xaxis_title="Valor (R$)", yaxis_title="")
                    st.plotly_chart(fig_status, use_container_width=True)
                
            with f2:
                st.markdown(f"##### ⚠️ Fila de Cobrança (Gargalo: {len(df_pendencias)} processos)")
                if df_pendencias.empty:
                    st.success("Tudo certo! Nenhuma pendência de faturamento encontrada para os filtros aplicados.")
                else:
                    st.dataframe(
                        df_pendencias.drop(columns=["Mes_Ano"]),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Processo": st.column_config.TextColumn("Processo", width="small"),
                            "Data Término": st.column_config.TextColumn("Término", width="small"),
                            "Valor (R$)": st.column_config.NumberColumn("Valor", format="R$ %.2f")
                        },
                        height=350
                    )