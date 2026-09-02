import streamlit as st
import pandas as pd
from components import renderizar_filtros, get_hover_style
from queries import buscar_motor_faturamento
from database import get_engine

engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros()
hover_style = get_hover_style()

df_motor = buscar_motor_faturamento(engine, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao)

# ==============================================================
# SINCRONIZAÇÃO COM A MÁQUINA DO TEMPO (RF34)
# ==============================================================
try:
    data_sistema_db = pd.read_sql("SELECT data_referencia FROM tb_parametros WHERE id = 1", engine).iloc[0, 0]
    hoje = pd.to_datetime(data_sistema_db).date()
except:
    hoje = pd.Timestamp.now().date()

# ==============================================================
# LEITURA DA TABELA DE FATURAMENTO PARA VISÃO UNIFICADA
# ==============================================================
try:
    df_faturamento = pd.read_sql("SELECT processo, status_financeiro FROM fato_faturamento", engine)
    dict_faturamento = dict(zip(df_faturamento['processo'], df_faturamento['status_financeiro']))
except:
    dict_faturamento = {}

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
    # Recálculo dos dias de atraso
    if 'data_envio_estimada' in df_motor.columns:
        df_motor['data_envio_calc'] = pd.to_datetime(df_motor['data_envio_estimada'], errors='coerce')
        
        df_motor['dias_atraso_medicao'] = df_motor.apply(
            lambda x: (hoje - x['data_envio_calc'].date()).days 
            if pd.notnull(x['data_envio_calc']) and x['data_envio_calc'].date() < hoje 
            else 0, 
            axis=1
        )
    
    # 🔄 Atualização inteligente de status (Operação + Financeiro)
    def atualizar_status_unificado(row):
        proc_id = row['id_processo']
        
        if proc_id in dict_faturamento:
            status_fin = dict_faturamento[proc_id]
            if status_fin == 'AGUARDA PAGAMENTO':
                return pd.Series(['Aguardando Pagamento (Nota Emitida)', 'Cliente', 0])
            elif status_fin == 'PAGO':
                return pd.Series(['Finalizado (Pago)', 'Nenhum', 0])
            else:
                return pd.Series([f'Financeiro: {status_fin}', 'Financeiro', 0])
        
        return pd.Series([row['status_medicao'], row['responsavel_acao'], row.get('dias_atraso_medicao', 0)])

    df_motor[['status_medicao', 'responsavel_acao', 'dias_atraso_medicao']] = df_motor.apply(atualizar_status_unificado, axis=1)

    # Filtra cancelados, reagendados e os já pagos
    df_pendentes = df_motor[
        (~df_motor['status_operacional'].str.contains('Cancelado', na=False)) &
        (df_motor['status_operacional'] != 'Reagendado') &
        (df_motor['status_medicao'] != 'Finalizado (Pago)')
    ].copy()
    
    if df_pendentes.empty:
        st.success("🎉 Excelente! Nenhum processo pendente de validação.")
    else:
        # 1. Resumo de Responsabilidades
        st.markdown("##### 📊 Resumo de Responsabilidades")
        op1, op2, op3 = st.columns(3)
        
        df_interno_kpi = df_pendentes[df_pendentes['responsavel_acao'].str.contains('Interno|Querino', na=False, case=False)]
        df_cliente_kpi = df_pendentes[df_pendentes['responsavel_acao'].str.contains('Cliente', na=False, case=False)]
        
        op1.metric(lbl_interno, f"R$ {df_interno_kpi['valor_total'].sum():,.2f}", f"{len(df_interno_kpi)} processos", delta_color="inverse" if is_admin else "off")
        op2.metric(lbl_cliente, f"R$ {df_cliente_kpi['valor_total'].sum():,.2f}", f"{len(df_cliente_kpi)} processos", delta_color="inverse")
        
        maior_atraso = df_pendentes['dias_atraso_medicao'].max()
        op3.metric("Maior Atraso Identificado", f"{maior_atraso} dias", "Foco prioritário", delta_color="inverse" if maior_atraso > 0 else "off")
        
        st.divider()
        
        # 2. Carteira de Pendências Operacionais
        st.markdown(lbl_carteira)
        
        def checar_docs(row):
            falta = []
            if pd.isna(row['pedido_compra']) or str(row['pedido_compra']).strip() == '': falta.append("PC")
            if pd.isna(row['folha_servico']) or str(row['folha_servico']).strip() == '': falta.append("FS")
            return " / ".join(falta) if falta else "OK"
            
        df_pendentes['docs_faltantes'] = df_pendentes.apply(checar_docs, axis=1)

        def formatar_cliente_grupo(row):
            grupo = str(row.get('grupo', '')).strip()
            cliente = str(row.get('cliente', '')).strip()
            if grupo and grupo.upper() not in ['NAN', 'NONE', ''] and grupo.upper() != cliente.upper():
                return f"{cliente} (Grupo: {grupo})"
            return cliente

        df_pendentes['cliente_grupo'] = df_pendentes.apply(formatar_cliente_grupo, axis=1)
        
        df_exibir = df_pendentes[[
            'cliente_grupo', 'unidade', 'id_processo', 'data_inicio', 'valor_total', 'tipo_faturamento', 
            'status_medicao', 'responsavel_acao', 'dias_atraso_medicao', 'docs_faltantes'
        ]].sort_values(by=['dias_atraso_medicao', 'valor_total'], ascending=[False, False])

        # Se for perfil cliente: ajusta termos e oculta colunas restritas
        if not is_admin:
            df_exibir['responsavel_acao'] = df_exibir['responsavel_acao'].replace({
                'Gestão de Contratos / Interno': 'Equipe Querino',
                'Financeiro Querino': 'Equipe Querino',
                'Cliente': 'Sua Empresa',
                'Cliente (Financeiro)': 'Sua Empresa (Financeiro)'
            })
            cols_remover = [c for c in ['cliente_grupo', 'tipo_faturamento'] if c in df_exibir.columns]
            df_exibir = df_exibir.drop(columns=cols_remover)

        # 🔍 Filtro Rápido
        col_f1, _ = st.columns([2, 1])
        with col_f1:
            texto_busca = st.text_input("🔎 Filtrar processos rápidos (Digite Cliente, Unidade ou Processo):")
        
        if texto_busca:
            termo = texto_busca.lower()
            if is_admin:
                mascara = (
                    df_exibir['cliente_grupo'].str.lower().str.contains(termo, na=False) |
                    df_exibir['unidade'].str.lower().str.contains(termo, na=False) |
                    df_exibir['id_processo'].str.lower().str.contains(termo, na=False) |
                    df_exibir['status_medicao'].str.lower().str.contains(termo, na=False)
                )
            else:
                mascara = (
                    df_exibir['unidade'].str.lower().str.contains(termo, na=False) |
                    df_exibir['id_processo'].str.lower().str.contains(termo, na=False) |
                    df_exibir['status_medicao'].str.lower().str.contains(termo, na=False)
                )
            df_exibir = df_exibir[mascara]

        # Configuração das Colunas
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
        
        if is_admin:
            col_config["cliente_grupo"] = st.column_config.TextColumn("Cliente (Grupo)", width="medium")

        st.dataframe(
            df_exibir,
            use_container_width=True,
            hide_index=True,
            column_config=col_config,
            height=400
        )