import streamlit as st
import plotly.express as px
import pandas as pd
from components import renderizar_filtros, get_hover_style
from queries import buscar_motor_faturamento, buscar_analise_margem

engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros()
hover_style = get_hover_style()

# Busca os dados do motor central
df_motor = buscar_motor_faturamento(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

st.markdown("### 💰 Faturamento e Contas a Receber")
st.caption("Controle de emissão de Notas Fiscais, inadimplência e rentabilidade da operação.")

if df_motor.empty:
    st.info("Nenhum dado encontrado para os filtros selecionados.")
else:
    # Filtra apenas os processos que já entraram na esteira financeira (Liberados ou com NF)
    df_fin = df_motor[df_motor['status_pagamento'].isin([
        'Aguardando emissão de NF',
        'A vencer / Em aberto',
        'Pagamento em Atraso'
    ])].copy()

    # ==============================================================
    # 1. RESUMO FINANCEIRO (KPIs)
    # ==============================================================
    f1, f2, f3 = st.columns(3)
    df_ag_nf = df_fin[df_fin['status_pagamento'] == 'Aguardando emissão de NF']
    df_a_vencer = df_fin[df_fin['status_pagamento'] == 'A vencer / Em aberto']
    df_atraso = df_fin[df_fin['status_pagamento'] == 'Pagamento em Atraso']

    f1.metric("Aguardando Emissão de NF", f"R$ {df_ag_nf['valor_total'].sum():,.2f}", f"{len(df_ag_nf)} processos", delta_color="off")
    f2.metric("A Vencer / Em Aberto", f"R$ {df_a_vencer['valor_total'].sum():,.2f}", f"{len(df_a_vencer)} faturas", delta_color="off")
    
    maior_atraso_pg = df_atraso['dias_atraso_pagamento'].max() if not df_atraso.empty else 0
    f3.metric("Inadimplência (Vencidas)", f"R$ {df_atraso['valor_total'].sum():,.2f}", f"Atraso de até {maior_atraso_pg} dias", delta_color="inverse")

    st.divider()

    # ==============================================================
    # 2. CARTEIRA DE CONTAS A RECEBER E PENDÊNCIAS
    # ==============================================================
    st.markdown("##### 📋 Carteira de Contas a Receber (Fila de Trabalho)")
    if df_fin.empty:
        st.success("Tudo em dia! Nenhuma pendência financeira ou fatura em aberto.")
    else:
        # Lógica para mesclar Cliente e Grupo sem poluir a tabela
        def formatar_cliente_grupo(row):
            grupo = str(row.get('grupo', '')).strip()
            cliente = str(row.get('cliente', '')).strip()
            if grupo and grupo.upper() not in ['NAN', 'NONE', ''] and grupo.upper() != cliente.upper():
                return f"{cliente} (Grupo: {grupo})"
            return cliente

        df_fin['cliente_grupo'] = df_fin.apply(formatar_cliente_grupo, axis=1)

        df_exibir_fin = df_fin[[
            'cliente_grupo', 'id_processo', 'nota_fiscal', 'data_emissao', 'data_vencimento',
            'valor_total', 'status_pagamento', 'responsavel_acao', 'dias_atraso_pagamento'
        ]].sort_values(by=['dias_atraso_pagamento', 'valor_total'], ascending=[False, False])

        st.dataframe(
            df_exibir_fin,
            use_container_width=True,
            hide_index=True,
            column_config={
                "cliente_grupo": st.column_config.TextColumn("Cliente (Grupo)", width="medium"),
                "id_processo": "Processo",
                "nota_fiscal": "NF",
                "data_emissao": "Emissão",
                "data_vencimento": "Vencimento",
                "valor_total": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
                "status_pagamento": st.column_config.TextColumn("Status Financeiro", width="medium"),
                "responsavel_acao": "Responsável (Cobrança)",
                "dias_atraso_pagamento": st.column_config.NumberColumn("Dias Atraso")
            },
            height=300
        )

    st.divider()

# ==============================================================
    # 3. RANKING DE INADIMPLÊNCIA (Item 17 do Documento)
    # ==============================================================
    st.markdown("##### 🚨 Ranking de Clientes Inadimplentes")
    if df_atraso.empty:
        st.success("Excelente! Nenhuma fatura vencida no momento.")
    else:
        # Aplica a mesma lógica de formatação de nome para o Ranking não ficar confuso
        df_atraso['cliente_grupo'] = df_atraso.apply(formatar_cliente_grupo, axis=1)
        
        rk1, rk2 = st.columns([1.5, 1])
        df_rk = df_atraso.groupby('cliente_grupo').agg(
            valor_devido=('valor_total', 'sum'),
            qtd_faturas=('id_processo', 'count'),
            maior_atraso=('dias_atraso_pagamento', 'max')
        ).reset_index().sort_values(by='valor_devido', ascending=False)

        with rk1:
            fig_rk = px.bar(
                df_rk.head(10).sort_values(by="valor_devido", ascending=True),
                x="valor_devido", y="cliente_grupo", orientation="h",
                title="Top 10 Maiores Devedores (Volume em R$)", text_auto=".2s", color_discrete_sequence=["#da2c38"]
            )
            # Ajuste de layout para garantir que nomes grandes não fiquem cortados
            fig_rk.update_layout(yaxis={'title': ''}, hoverlabel=hover_style, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_rk, use_container_width=True)

        with rk2:
            st.dataframe(
                df_rk, use_container_width=True, hide_index=True,
                column_config={
                    "cliente_grupo": "Cliente (Grupo)",
                    "valor_devido": st.column_config.NumberColumn("Dívida Total (R$)", format="R$ %.2f"),
                    "qtd_faturas": "Qtd Faturas",
                    "maior_atraso": "Maior Atraso (Dias)"
                }, height=350
            )

# ==============================================================
# 4. DRE OPERACIONAL (Bônus Analítico da Querino)
# ==============================================================
st.divider()
st.subheader("📊 Análise de Lucratividade e Custos (DRE Operacional)")
st.caption("Visão de Faturamento Bruto vs Custos com Instrutores (Honorários, KM, Hotel e Extras).")
df_margem = buscar_analise_margem(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

if df_margem.empty:
    st.info("Nenhum dado de custo/receita encontrado para os filtros selecionados.")
else:
    receita_total = df_margem['receita'].sum()
    custo_total = df_margem['custo_total'].sum()
    lucro_total = df_margem['margem_lucro'].sum()
    margem_perc = (lucro_total / receita_total * 100) if receita_total > 0 else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Faturamento Bruto (Receita)", f"R$ {receita_total:,.2f}")
    m2.metric("Custo Op. (Instrutores)", f"R$ {custo_total:,.2f}", delta=f"{(custo_total/receita_total*100 if receita_total > 0 else 0):.1f}% da receita", delta_color="inverse")
    m3.metric("Margem de Contribuição", f"R$ {lucro_total:,.2f}")
    cor_margem = "🟢" if margem_perc > 30 else ("🟡" if margem_perc > 15 else "🔴")
    m4.metric("Margem de Lucro (%)", f"{cor_margem} {margem_perc:.1f}%")

    c_graf, c_tab = st.columns([1, 1.5])
    with c_graf:
        df_instrutores_custo = df_margem.groupby('instrutor').agg(
            custo_gerado=('custo_total', 'sum')
        ).reset_index().sort_values(by='custo_gerado', ascending=False)
        fig_custo = px.bar(df_instrutores_custo.head(10).sort_values(by="custo_gerado", ascending=True), x="custo_gerado", y="instrutor", orientation="h", title="Top 10 Instrutores (Custo Total)", text_auto=".2s", color_discrete_sequence=["#da2c38"])
        fig_custo.update_layout(hoverlabel=hover_style, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_custo, use_container_width=True)

    with c_tab:
        st.write("**Extrato de Rentabilidade por Turma**")
        df_exibir_margem = df_margem[['processo', 'cliente', 'instrutor', 'receita', 'custo_total', 'margem_lucro', 'margem_percentual']].copy()
        st.dataframe(
            df_exibir_margem.sort_values(by='margem_lucro', ascending=True),
            use_container_width=True, hide_index=True,
            column_config={
                "processo": "Processo", 
                "cliente": st.column_config.TextColumn("Cliente", width="medium"),
                "instrutor": st.column_config.TextColumn("Instrutor", width="medium"),
                "receita": st.column_config.NumberColumn("Receita (R$)", format="R$ %.2f"),
                "custo_total": st.column_config.NumberColumn("Custo (R$)", format="R$ %.2f"),
                "margem_lucro": st.column_config.NumberColumn("Lucro Limpo (R$)", format="R$ %.2f"),
                "margem_percentual": st.column_config.NumberColumn("Margem (%)", format="%.1f%%")
            }, height=350
        )