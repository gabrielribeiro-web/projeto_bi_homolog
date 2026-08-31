import streamlit as st
import plotly.express as px
from components import renderizar_filtros, get_hover_style
from queries import buscar_ranking_vendedores

engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros()
hover_style = get_hover_style()

df_vendedores = buscar_ranking_vendedores(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

st.markdown("### 📈 Desempenho da Equipe Comercial")
if df_vendedores.empty:
    st.info("Nenhum dado comercial encontrado.")
else:
    v1, v2 = st.columns([1.5, 1])
    with v1:
        fig_vend = px.bar(df_vendedores.head(10).sort_values(by="valor_total_vendido", ascending=True), x="valor_total_vendido", y="executivo", orientation="h", title="Top Executivos por Faturamento (R$)", text_auto=".2s", color_discrete_sequence=["#84cc16"])
        fig_vend.update_layout(hoverlabel=hover_style, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_vend, use_container_width=True)
    with v2:
        st.dataframe(df_vendedores, use_container_width=True, hide_index=True, column_config={"executivo": "Executivo", "turmas_vendidas": "Turmas", "valor_total_vendido": st.column_config.NumberColumn("Faturamento", format="R$ %.2f")}, height=350)