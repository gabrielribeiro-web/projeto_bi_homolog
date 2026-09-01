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
    # Filtra apenas os processos que já entraram na esteira financeira
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
            height=280
        )

    st.divider()

    # ==============================================================
    # 3. RANKING DE INADIMPLÊNCIA
    # ==============================================================
    st.markdown("##### 🚨 Ranking de Clientes Inadimplentes")
    if df_atraso.empty:
        st.success("Excelente! Nenhuma fatura vencida no momento.")
    else:
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
                }, height=320
            )

# ==============================================================
# 4. DRE OPERACIONAL E ANÁLISE DE CUSTOS (REGRAS DE COMPETÊNCIA)
# ==============================================================
st.divider()
st.subheader("📊 Análise de Lucratividade e Custos (DRE Operacional)")
st.caption("Visão de Faturamento Bruto vs Custos Discriminados (Honorários, KM, Hotel e Extras).")

df_margem_bruta = buscar_analise_margem(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

if df_margem_bruta.empty:
    st.info("Nenhum dado de custo/receita encontrado para os filtros selecionados.")
else:
    # 1. FILTRO DE RELEVÂNCIA: Remove linhas zeradas (sem receita e sem custo)
    df_margem = df_margem_bruta[(df_margem_bruta['receita'] > 0) | (df_margem_bruta['custo_total'] > 0)].copy()

    # 2. TRATAMENTO ROBUSTO DA DATA DE COMPETÊNCIA
    hoje = pd.Timestamp.now().date()
    
    if 'data_inicio_presencial' in df_margem.columns:
        datas_convertidas = pd.to_datetime(df_margem['data_inicio_presencial'], errors='coerce')
        df_margem['data_formatada'] = datas_convertidas.dt.date
        
        # Se for estritamente futura (> hoje), entra como Projetado. Caso contrário, é Realizado.
        df_margem['status_dre'] = df_margem['data_formatada'].apply(
            lambda d: '⏳ Projetado (Futuro)' if pd.notna(d) and d > hoje else '✅ Realizado'
        )
    else:
        df_margem['status_dre'] = '✅ Realizado'

    # 3. SELETORES DE VISÃO
    filtro_dre = st.radio(
        "Filtro de Competência:", 
        ["✅ Realizado (Até Hoje)", "⏳ Projetado (Futuro)", "📊 Visão Consolidada (Ambos)"], 
        horizontal=True
    )

    if filtro_dre == "✅ Realizado (Até Hoje)":
        df_dre = df_margem[df_margem['status_dre'] == '✅ Realizado']
    elif filtro_dre == "⏳ Projetado (Futuro)":
        df_dre = df_margem[df_margem['status_dre'] == '⏳ Projetado (Futuro)']
    else:
        df_dre = df_margem.copy()

    if df_dre.empty:
        st.info("Nenhum processo encontrado para esta categoria no período selecionado.")
    else:
        # Helpers para leitura segura das colunas
        def _obter_coluna(df, aliases, default_val=0):
            for alias in aliases:
                for col in df.columns:
                    if col.strip().lower() == alias.strip().lower():
                        return df[col]
            return pd.Series([default_val] * len(df))

        def _somar_coluna(df, aliases):
            return pd.to_numeric(_obter_coluna(df, aliases), errors='coerce').fillna(0).sum()

        # Agregações Financeiras
        c_km = _somar_coluna(df_dre, ['custo_km', 'km', 'valor_km'])
        c_hotel = _somar_coluna(df_dre, ['custo_hospedagem', 'hospedagem'])
        c_extras = _somar_coluna(df_dre, ['custo_extra', 'extras'])
        c_honorarios = _somar_coluna(df_dre, ['custo_honorario', 'honorarios'])

        receita_total = _somar_coluna(df_dre, ['receita', 'valor_total'])
        custo_total = _somar_coluna(df_dre, ['custo_total', 'custo_op'])

        if (c_honorarios + c_km + c_hotel + c_extras) == 0 and custo_total > 0:
            c_honorarios = custo_total

        lucro_total = receita_total - custo_total
        margem_perc = (lucro_total / receita_total * 100) if receita_total > 0 else 0

        # KPIs da Aba
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Faturamento (Receita)", f"R$ {receita_total:,.2f}")
        m2.metric("Custo Op. Total", f"R$ {custo_total:,.2f}", delta=f"{(custo_total/receita_total*100 if receita_total > 0 else 0):.1f}% da receita", delta_color="inverse")
        m3.metric("Margem Limpa", f"R$ {lucro_total:,.2f}")
        m4.metric("Margem de Lucro (%)", f"{'🟢' if margem_perc > 30 else ('🟡' if margem_perc > 15 else '🔴')} {margem_perc:.1f}%")

        st.write("")
        dk1, dk2, dk3, dk4 = st.columns(4)
        dk1.metric("Honorários Instrutores", f"R$ {c_honorarios:,.2f}")
        dk2.metric("Traslado & KM", f"R$ {c_km:,.2f}")
        dk3.metric("Hospedagem & Hotel", f"R$ {c_hotel:,.2f}")
        dk4.metric("Despesas Extras", f"R$ {c_extras:,.2f}")
        st.write("")

        c_graf, c_pie = st.columns([1.3, 1])
        with c_graf:
            df_instrutores_custo = df_dre.groupby(_obter_coluna(df_dre, ['instrutor', 'nome_instrutor'], 'Instrutor')).agg(
                custo_gerado=(_obter_coluna(df_dre, ['custo_total', 'custo']).name, 'sum')
            ).reset_index().sort_values(by='custo_gerado', ascending=False)
            df_instrutores_custo.columns = ['instrutor', 'custo_gerado']
            
            fig_custo = px.bar(
                df_instrutores_custo.head(10).sort_values(by="custo_gerado", ascending=True),
                x="custo_gerado", y="instrutor", orientation="h",
                title="Top 10 Custos por Instrutor", text_auto=".2s", color_discrete_sequence=["#da2c38"]
            )
            fig_custo.update_layout(hoverlabel=hover_style, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_custo, use_container_width=True)

        with c_pie:
            st.markdown("<p style='font-weight: 600; font-size: 16px; margin-bottom: 8px;'>Composição dos Custos</p>", unsafe_allow_html=True)
            if (c_km + c_hotel + c_extras) > 0:
                df_custos_pie = pd.DataFrame({
                    'Categoria': ['Honorários', 'KM / Traslado', 'Hospedagem', 'Extras'],
                    'Valor': [c_honorarios, c_km, c_hotel, c_extras]
                })
                fig_pie_custos = px.pie(
                    df_custos_pie, names='Categoria', values='Valor', hole=0.45,
                    color_discrete_sequence=['#1a1e38', '#aecb36', '#4b5563', '#da2c38']
                )
                fig_pie_custos.update_layout(margin=dict(l=10, r=10, t=20, b=10), hoverlabel=hover_style, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_pie_custos, use_container_width=True)
            else:
                st.info("Nenhuma despesa de viagem reportada neste período. 100% dos custos são honorários.")

        st.write("")
        st.markdown("##### 📋 Extrato de Rentabilidade por Turma")
        
        df_exibir_margem = pd.DataFrame()
        df_exibir_margem['status'] = _obter_coluna(df_dre, ['status_dre'])
        df_exibir_margem['processo'] = _obter_coluna(df_dre, ['processo', 'id_processo'])
        df_exibir_margem['cliente'] = _obter_coluna(df_dre, ['cliente', 'grupo'])
        df_exibir_margem['instrutor'] = _obter_coluna(df_dre, ['instrutor', 'nome_instrutor'])
        df_exibir_margem['receita'] = pd.to_numeric(_obter_coluna(df_dre, ['receita', 'valor_total']), errors='coerce').fillna(0)
        df_exibir_margem['custo_total'] = pd.to_numeric(_obter_coluna(df_dre, ['custo_total', 'custo_op']), errors='coerce').fillna(0)
        df_exibir_margem['margem_lucro'] = df_exibir_margem['receita'] - df_exibir_margem['custo_total']

        df_exibir_margem['margem_percentual'] = df_exibir_margem.apply(
            lambda row: (row['margem_lucro'] / row['receita'] * 100) if row['receita'] > 0 else 0.0, axis=1
        )

        st.dataframe(
            df_exibir_margem.sort_values(by='receita', ascending=False),
            use_container_width=True, hide_index=True,
            column_config={
                "status": "Status",
                "processo": "Processo", 
                "cliente": st.column_config.TextColumn("Cliente", width="medium"),
                "instrutor": st.column_config.TextColumn("Instrutor", width="medium"),
                "receita": st.column_config.NumberColumn("Receita (R$)", format="R$ %.2f"),
                "custo_total": st.column_config.NumberColumn("Custo Total (R$)", format="R$ %.2f"),
                "margem_lucro": st.column_config.NumberColumn("Lucro (R$)", format="R$ %.2f"),
                "margem_percentual": st.column_config.NumberColumn("Margem (%)", format="%.1f%%")
            }, height=350
        )