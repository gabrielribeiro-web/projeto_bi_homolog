import streamlit as st
import pandas as pd
from components import renderizar_filtros, get_hover_style
from queries import buscar_motor_faturamento

engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros()
hover_style = get_hover_style()

df_motor = buscar_motor_faturamento(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

# ==============================================================
# DEFINIÇÃO DE NOMENCLATURAS DINÂMICAS (ADMIN VS CLIENTE)
# ==============================================================
is_admin = user["perfil"] == "admin"

lbl_titulo = "### ⚙️ Operação: SLA e Liberações" if is_admin else "### ⚙️ Acompanhamento e Liberações"
lbl_interno = "Com a Operação (Interno)" if is_admin else "Em Análise pela Querino"
lbl_cliente = "Com o Cliente (Validação)" if is_admin else "Pendente de Sua Validação"
lbl_carteira = "##### 📋 Carteira de Pendências Operacionais" if is_admin else "##### 📋 Status dos Seus Processos"

st.markdown(lbl_titulo)
st.caption("Acompanhamento de medições, validações e status de documentos (PC/FS).")

if df_motor.empty:
    st.info("Nenhum dado encontrado para os filtros selecionados.")
else:
    # Filtra processos que AINDA NÃO foram para o financeiro e não estão cancelados
    df_pendentes = df_motor[
        (~df_motor['status_operacional'].str.contains('Cancelado', na=False)) &
        (df_motor['validacao'] != 'Liberado para Faturamento') &
        (df_motor['status_operacional'] != 'Reagendado')
    ].copy()
    
    if df_pendentes.empty:
        st.success("🎉 Excelente! Nenhum processo pendente de validação.")
    else:
        # ==============================================================
        # 1. RESUMO DE PENDÊNCIAS OPERACIONAIS
        # ==============================================================
        st.markdown("##### 📊 Resumo de Responsabilidades")
        op1, op2, op3 = st.columns(3)
        
        df_interno_kpi = df_pendentes[df_pendentes['responsavel_acao'].str.contains('Interno', na=False)]
        df_cliente_kpi = df_pendentes[df_pendentes['responsavel_acao'] == 'Cliente']
        
        # O Admin vê atraso interno em vermelho. O Cliente vê os próprios atrasos dele em vermelho.
        op1.metric(lbl_interno, f"R$ {df_interno_kpi['valor_total'].sum():,.2f}", f"{len(df_interno_kpi)} processos", delta_color="inverse" if is_admin else "off")
        op2.metric(lbl_cliente, f"R$ {df_cliente_kpi['valor_total'].sum():,.2f}", f"{len(df_cliente_kpi)} processos", delta_color="inverse")
        
        maior_atraso = df_pendentes['dias_atraso_medicao'].max()
        op3.metric("Maior Atraso Identificado", f"{maior_atraso} dias", "Foco prioritário", delta_color="inverse" if maior_atraso > 0 else "off")
        
        st.divider()
        
        # ==============================================================
        # 2. CARTEIRA DE PENDÊNCIAS COM GRUPO E UNIDADE
        # ==============================================================
        st.markdown(lbl_carteira)
        
        def checar_docs(row):
            falta = []
            if pd.isna(row['pedido_compra']) or str(row['pedido_compra']).strip() == '': falta.append("PC")
            if pd.isna(row['folha_servico']) or str(row['folha_servico']).strip() == '': falta.append("FS")
            return " / ".join(falta) if falta else "OK"
            
        df_pendentes['docs_faltantes'] = df_pendentes.apply(checar_docs, axis=1)

        # Lógica para mesclar Cliente e Grupo de forma inteligente
        def formatar_cliente_grupo(row):
            grupo = str(row.get('grupo', '')).strip()
            cliente = str(row.get('cliente', '')).strip()
            if grupo and grupo.upper() not in ['NAN', 'NONE', ''] and grupo.upper() != cliente.upper():
                return f"{cliente} (Grupo: {grupo})"
            return cliente

        df_pendentes['cliente_grupo'] = df_pendentes.apply(formatar_cliente_grupo, axis=1)
        
        # Selecionando as colunas (agora incluindo cliente_grupo e unidade)
        df_exibir = df_pendentes[[
            'cliente_grupo', 'unidade', 'id_processo', 'data_inicio', 'valor_total', 'tipo_faturamento', 
            'status_medicao', 'responsavel_acao', 'dias_atraso_medicao', 'docs_faltantes'
        ]].sort_values(by=['dias_atraso_medicao', 'valor_total'], ascending=[False, False])

        # Se for o cliente, traduzimos os nomes dos responsáveis e ocultamos a coluna 'cliente_grupo'
        # Mas mantemos a coluna 'Unidade' para o cliente saber de onde é a cobrança!
        if not is_admin:
            df_exibir['responsavel_acao'] = df_exibir['responsavel_acao'].replace({
                'Gestão de Contratos / Interno': 'Equipe Querino',
                'Cliente': 'Sua Empresa'
            })
            if 'cliente_grupo' in df_exibir.columns:
                df_exibir = df_exibir.drop(columns=['cliente_grupo'])
        
        # Configuração dinâmica das colunas
        col_config = {
            "id_processo": "Processo",
            "unidade": st.column_config.TextColumn("Unidade", width="medium"),
            "data_inicio": st.column_config.DateColumn("Início", format="DD/MM/YYYY"),
            "valor_total": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
            "tipo_faturamento": st.column_config.TextColumn("Tipo", width="small"),
            "status_medicao": st.column_config.TextColumn("Etapa Atual / Status", width="medium"),
            "responsavel_acao": "Responsável",
            "dias_atraso_medicao": st.column_config.NumberColumn("Dias Atraso", help="Dias de atraso na medição ou faturamento pontual"),
            "docs_faltantes": st.column_config.TextColumn("Falta PC/FS?", help="Indica se falta Pedido de Compra (PC) ou Folha de Serviço (FS) na planilha")
        }
        
        # Se for o Admin, mostramos a coluna com o Cliente e Grupo logo no início da tabela
        if is_admin:
            col_config["cliente_grupo"] = st.column_config.TextColumn("Cliente (Grupo)", width="medium")

        st.dataframe(
            df_exibir,
            use_container_width=True,
            hide_index=True,
            column_config=col_config,
            height=400
        )