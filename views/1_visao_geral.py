import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from components import renderizar_filtros, get_hover_style
from queries import (
    buscar_grafico_nrs, 
    buscar_distribuicao_tipo, 
    buscar_investimento_mensal, 
    buscar_proximas_turmas,
    buscar_motor_faturamento
)

engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros()
hover_style = get_hover_style()

# MOTOR DAS REGRAS (RF01 a RF35)
df_motor = buscar_motor_faturamento(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

# Buscas para os gráficos da parte inferior
df_nrs = buscar_grafico_nrs(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
df_tipo = buscar_distribuicao_tipo(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
df_mes = buscar_investimento_mensal(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)
df_proximas = buscar_proximas_turmas(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

st.markdown(f"#### 💼 Visão Executiva (Consolidado) - {modo_visao}")
st.caption("Visão 100% alinhada com as regras de Faturamento (Pontual/Medição) e Exclusividade de Indicadores.")

if not df_motor.empty:
    # ==============================================================
    # CÁLCULOS DOS 10 INDICADORES (Item 16.1)
    # ==============================================================
    
    # 1. Previsão de Receita (RF06, RF30)
    df_previsao = df_motor[df_motor['status_operacional'].isin(['Em Programação', 'Confirmado'])]
    
    # 2. Valor Cobrável (RF31 - Turmas que atingiram a data e são cobráveis na hora)
    df_cobravel = df_motor[df_motor['status_medicao'] == 'Cobrável em D']

    # 3. Medição em Processamento (SLA Querino)
    df_med_proc = df_motor[df_motor['status_medicao'] == 'Medição em processamento']

    # 4. Aguardando Cliente (Validação da Medição)
    df_med_cli = df_motor[df_motor['status_medicao'] == 'Aguardando validação do cliente']

    # 5. Medição em Atraso (RF18)
    df_med_atraso = df_motor[df_motor['status_medicao'] == 'Medição em atraso cliente']

    # 6. Faturamento Pendente - Prazo Vencido (Cobrança Pontual atrasada)
    df_fat_pend = df_motor[df_motor['status_medicao'] == 'Faturamento pendente - prazo vencido']

    # 7. Aguardando Emissão de NF
    df_ag_nf = df_motor[df_motor['status_pagamento'] == 'Aguardando emissão de NF']

    # 8. Faturado / A Vencer
    df_a_vencer = df_motor[df_motor['status_pagamento'] == 'A vencer / Em aberto']

    # 9. Pagamento em Atraso (Inadimplência)
    df_inad = df_motor[df_motor['status_pagamento'] == 'Pagamento em Atraso']

    # 10. Pago no Prazo / Atraso
    df_pago = df_motor[df_motor['status_pagamento'].str.contains('Pago', na=False)]

    # ==============================================================
    # DEFINIÇÃO DE NOMENCLATURAS DINÂMICAS (ADMIN VS CLIENTE)
    # ==============================================================
    is_admin = user["perfil"] == "admin"
    
    lbl_previsao = "Previsão de Receita" if is_admin else "Previsão de Investimento"
    lbl_med_interno = "Medição (Interno)" if is_admin else "Em Processamento"
    lbl_aguardando_cli = "Aguardando Cliente" if is_admin else "Pendente"
    lbl_recebido = "Recebido (Pago)" if is_admin else "Faturas Pagas"
    lbl_grafico_mes = "Faturamento Mensal (Real vs Projetado)" if is_admin else "Investimento Mensal (Real vs Projetado)"

    # ==============================================================
    # RENDERIZANDO OS CARDS (Item 16.1)
    # ==============================================================
    
    st.markdown("##### 📍 Linha do Tempo Operacional e Validações")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(lbl_previsao, f"R$ {df_previsao['valor_total'].sum():,.2f}", f"{len(df_previsao)} processos", delta_color="off")
    c2.metric("Valor", f"R$ {df_cobravel['valor_total'].sum():,.2f}", f"{len(df_cobravel)} processos", delta_color="off")
    c3.metric(lbl_med_interno, f"R$ {df_med_proc['valor_total'].sum():,.2f}", f"{len(df_med_proc)} processos", delta_color="off")
    c4.metric(lbl_aguardando_cli, f"R$ {df_med_cli['valor_total'].sum():,.2f}", f"{len(df_med_cli)} processos", delta_color="off")
    
    maior_atraso_med = df_med_atraso['dias_atraso_medicao'].max() if not df_med_atraso.empty else 0
    c5.metric("Medição em Atraso", f"R$ {df_med_atraso['valor_total'].sum():,.2f}", f"{len(df_med_atraso)} parc. (Até {maior_atraso_med} dias)", delta_color="inverse")

    st.write("") # Espaço em branco

    st.markdown("##### 💳 Linha do Tempo de Cobrança e Recebimento")
    c6, c7, c8, c9, c10 = st.columns(5)
    
    maior_atraso_fat = df_fat_pend['dias_atraso_medicao'].max() if not df_fat_pend.empty else 0
    c6.metric("Fat. Pendente", f"R$ {df_fat_pend['valor_total'].sum():,.2f}", f"{len(df_fat_pend)} proc. (Até {maior_atraso_fat} dias)", delta_color="inverse")
    
    c7.metric("Aguardando NF", f"R$ {df_ag_nf['valor_total'].sum():,.2f}", f"{len(df_ag_nf)} processos", delta_color="off")
    c8.metric("Faturado / A Vencer", f"R$ {df_a_vencer['valor_total'].sum():,.2f}", f"{len(df_a_vencer)} processos", delta_color="off")
    
    maior_atraso_pag = df_inad['dias_atraso_pagamento'].max() if not df_inad.empty else 0
    c9.metric("Pagamento em Atraso", f"R$ {df_inad['valor_total'].sum():,.2f}", f"{len(df_inad)} proc. (Até {maior_atraso_pag} dias)", delta_color="inverse")
    
    c10.metric(lbl_recebido, f"R$ {df_pago['valor_total'].sum():,.2f}", f"{len(df_pago)} processos", delta_color="normal")

else:
    st.info("Nenhum dado encontrado para os filtros informados.")

st.divider()

# ==============================================================
# GRÁFICOS INFERIORES E AGENDA 
# ==============================================================
g1, g2, g3 = st.columns([1.2, 1, 1.5])
with g1:
    fig_nrs = px.bar(df_nrs.head(10), x="quantidade", y="nr", orientation="h", title="Top 10 Normas (NRs)", text="quantidade", color_discrete_sequence=["#84cc16"])
    fig_nrs.update_layout(yaxis={"categoryorder": "total ascending"}, hoverlabel=hover_style, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_nrs, use_container_width=True)

with g2:
    fig_pie = px.pie(df_tipo, values="quantidade", names="tipo", hole=0.5, title="Distribuição por Tipo", color_discrete_sequence=["#84cc16", "#38bdf8", "#a855f7"])
    fig_pie.update_layout(hoverlabel=hover_style, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_pie, use_container_width=True)

with g3:
    fig_mes = go.Figure()
    if "Faturamento Realizado" in df_mes.columns:
        fig_mes.add_trace(go.Bar(x=df_mes["mes_ano"], y=df_mes["Faturamento Realizado"], name="Realizado (R$)", marker_color="#84cc16"))
        fig_mes.add_trace(go.Scatter(x=df_mes["mes_ano"], y=df_mes["Faturamento Projetado"], name="Projetado (R$)", line=dict(color="#38bdf8", width=3, dash="dot")))
        fig_mes.update_layout(title=lbl_grafico_mes, yaxis=dict(title="R$"), hoverlabel=hover_style, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_mes, use_container_width=True)

st.divider()
st.subheader("📅 Próximas Turmas Agendadas")
st.dataframe(df_proximas, use_container_width=True, hide_index=True, column_config={"valor": st.column_config.NumberColumn("Valor Contratado", format="R$ %.2f")})