import streamlit as st
import plotly.express as px
from components import renderizar_filtros, get_hover_style
from queries import buscar_kpis, buscar_ranking_instrutores, buscar_lista_participantes

engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros()
hover_style = get_hover_style()

df_kpis = buscar_kpis(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
df_instrutores = buscar_ranking_instrutores(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
df_participantes = buscar_lista_participantes(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

st.markdown(f"#### 🎓 Entregas e Qualidade Técnica")
if user["perfil"] == "admin":
    c5, c6, c7, c8, c9 = st.columns(5)
    c5.metric("Turmas Realizadas", f"{int(df_kpis['turmas_realizadas'].iloc[0]):,}".replace(",", "."))
    c6.metric("Horas Treinamento", f"{int(df_kpis['horas_realizadas'].iloc[0]):,}h".replace(",", "."))
    c7.metric("Pessoas Treinadas", f"{int(df_kpis['pessoas_treinadas'].iloc[0]):,}".replace(",", "."))
    c8.metric("Aproveitamento Médio", f"{df_kpis['aproveitamento_medio'].iloc[0] or 0:.2f} ⭐")
    c9.metric("Unidades Atendidas", f"{int(df_kpis['unidades_atendidas'].iloc[0]):,}".replace(",", "."))
else:
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Turmas Realizadas", f"{int(df_kpis['turmas_realizadas'].iloc[0]):,}".replace(",", "."))
    c6.metric("Pessoas Treinadas", f"{int(df_kpis['pessoas_treinadas'].iloc[0]):,}".replace(",", "."))
    c7.metric("Carga Horária Consumida", f"{int(df_kpis['horas_realizadas'].iloc[0]):,}h".replace(",", "."))
    c8.metric("Nota Média (Qualidade)", f"{df_kpis['aproveitamento_medio'].iloc[0] or 0:.2f} ⭐")

st.divider()

def renderizar_alunos():
    st.subheader("👥 Relação de Colaboradores Treinados")
    if df_participantes.empty:
        st.info("Nenhum participante encontrado.")
    else:
        pesq = st.text_input("🔍 Buscar por Nome ou CPF:", key="busca_aluno")
        df_ex = df_participantes.copy()
        if pesq: df_ex = df_ex[df_ex["Nome do Participante"].astype(str).str.contains(pesq, case=False, na=False) | df_ex["CPF"].astype(str).str.contains(pesq, na=False)]
        df_ex["CPF"] = df_ex["CPF"].apply(lambda cpf: f"***.{str(cpf).replace('.','').replace('-','').strip()[3:6]}.{str(cpf).replace('.','').replace('-','').strip()[6:9]}-**" if len(str(cpf).replace('.','').replace('-','').strip())==11 else "***.***.***-**")
        if user["perfil"] != "admin" and "Grupo" in df_ex.columns: df_ex = df_ex.drop(columns=["Grupo"])
        st.dataframe(df_ex, use_container_width=True, hide_index=True, height=350, column_config={"CPF": st.column_config.TextColumn("CPF (Protegido)")})

def renderizar_instrutores():
    st.subheader("👨‍🏫 Desempenho por Instrutor")
    if not df_instrutores.empty:
        o1, o2 = st.columns([1.5, 1])
        with o1:
            fig_inst = px.bar(df_instrutores.head(10).sort_values(by="turmas_realizadas", ascending=True), x="turmas_realizadas", y="instrutor", orientation="h", text="turmas_realizadas", color_discrete_sequence=["#38bdf8"])
            fig_inst.update_layout(hoverlabel=hover_style, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_inst, use_container_width=True)
        with o2:
            st.dataframe(df_instrutores, use_container_width=True, hide_index=True, column_config={"instrutor": "Instrutor", "turmas_realizadas": st.column_config.NumberColumn("Turmas", format="%d"), "pessoas_treinadas": st.column_config.NumberColumn("Alunos", format="%d"), "nota_media": st.column_config.NumberColumn("Nota Média", format="%.2f ⭐")}, height=350)

if user["perfil"] == "admin":
    renderizar_instrutores()
    st.divider()
    renderizar_alunos() 
else:
    renderizar_alunos()
    st.divider()
    renderizar_instrutores()