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
    # Ajuste de nomenclaturas vindas do banco
    df_motor['status_medicao'] = df_motor['status_medicao'].replace(
        'Aguardando virada do mês', 'Aguardando virada do mês para fechar a medição'
    )

    # -------------------------------------------------------------
    # RF03 / RF07 / RF13: AJUSTE DE STATUS E DIAS DE ATRASO
    # -------------------------------------------------------------
    if 'data_envio_estimada' in df_motor.columns:
        df_motor['data_envio_calc'] = pd.to_datetime(df_motor['data_envio_estimada'], errors='coerce', dayfirst=True)
        
        df_motor['dias_atraso_medicao'] = df_motor.apply(
            lambda x: (hoje - x['data_envio_calc'].date()).days 
            if pd.notnull(x['data_envio_calc']) and x['data_envio_calc'].date() < hoje 
            else 0, 
            axis=1
        )
    
    def aplicar_regras_rf(row):
        valida = str(row.get('validacao', '')).strip().upper()
        dt_ini = pd.to_datetime(row.get('data_inicio'), errors='coerce', dayfirst=True)
        tipo_fat = str(row.get('tipo_faturamento', '')).strip().upper()
        
        # RF03: Validação Vazia ou se o SQL unificou como 'EM PROGRAMAÇÃO'
        if valida == 'EM PROGRAMAÇÃO' or not valida or valida in ['NAN', 'NONE', 'NULL', '']:
            row['status_medicao'] = 'Em Programação'
            row['responsavel_acao'] = 'Sistema'
        
        # REGRA REFORÇADA: Se Confirmado e data futura -> "Em Programação"
        elif valida == 'CONFIRMADO' and pd.notnull(dt_ini) and dt_ini.date() > hoje:
            row['status_medicao'] = 'Em Programação'
            row['responsavel_acao'] = 'Sistema'
            
        # RF07 e RF13: Pontual vencido em D+1
        elif tipo_fat == 'PONTUAL' and pd.notnull(dt_ini):
            dt_ini_date = dt_ini.date()
            if hoje > dt_ini_date and row['status_medicao'] not in ['Liberado para Faturamento', 'Faturado']:
                if 'Aguardando' not in row['status_medicao'] and 'Financeiro' not in row['status_medicao']:
                    row['status_medicao'] = 'Faturamento pendente - prazo vencido'
                    row['responsavel_acao'] = 'Gestão de Contratos / Interno'

        return row

    df_motor = df_motor.apply(aplicar_regras_rf, axis=1)

    # -------------------------------------------------------------
    # 🔄 ATUALIZAÇÃO INTELIGENTE DE STATUS (OPERAÇÃO + FINANCEIRO)
    # -------------------------------------------------------------
    def atualizar_status_unificado(row):
        proc_id = row['id_processo']
        status_med_atual = row['status_medicao']
        
        if proc_id in dict_faturamento:
            status_fin = str(dict_faturamento[proc_id]).strip().upper()
            
            # 1. Pago / Concluído
            if status_fin in ['PAGO', 'PAGAMENTO OK', 'OK', 'CONCLUIDO'] or 'PAGAMENTO OK' in status_fin or 'PAGO' in status_fin:
                return pd.Series(['Finalizado (Pago)', 'Nenhum', 0])
            
            # BLOQUEIO DE PROTEÇÃO: Se a operação ainda está "Em Programação" (futuro), ignoramos financeiro 
            if status_med_atual == 'Em Programação':
                return pd.Series([status_med_atual, 'Sistema', 0])
            
            # 2. Nota Emitida e Aguardando Pagamento do Cliente
            elif status_fin in ['AGUARDA PAGAMENTO', 'AGUARDANDO PAGAMENTO', 'ATRASO NO PAGAMENTO']:
                return pd.Series(['Aguardando Pagamento (Nota Emitida)', 'Cliente (Financeiro)', 0])
            
            # 3. Aguardando Autorização do Comercial (NF NÃO emitida ainda)
            elif 'AUTORIZA' in status_fin:
                return pd.Series(['Aguardando Autorização Comercial (NF Não Emitida)', 'Comercial Querino', row.get('dias_atraso_medicao', 0)])
            
            # 4. Outros status do financeiro
            else:
                return pd.Series([f'Financeiro: {status_fin}', 'Financeiro Querino', row.get('dias_atraso_medicao', 0)])
        
        return pd.Series([status_med_atual, row['responsavel_acao'], row.get('dias_atraso_medicao', 0)])

    df_motor[['status_medicao', 'responsavel_acao', 'dias_atraso_medicao']] = df_motor.apply(atualizar_status_unificado, axis=1)

    # -------------------------------------------------------------
    # 🧹 FILTRAGEM RIGOROSA DE PENDÊNCIAS OPERACIONAIS
    # -------------------------------------------------------------
    df_pendentes = df_motor[
        (~df_motor['status_operacional'].str.contains('Cancelado', na=False, case=False)) &
        (df_motor['status_operacional'] != 'Reagendado') &
        (~df_motor['status_medicao'].str.contains('Finalizado|Pago|PAGAMENTO OK', na=False, case=False))
    ].copy()
    
    if df_pendentes.empty:
        st.success("🎉 Excelente! Nenhum processo pendente de validação operacional.")
    else:
        # 1. Resumo de Responsabilidades
        st.markdown("##### 📊 Resumo de Responsabilidades")
        op1, op2, op3 = st.columns(3)
        
        df_interno_kpi = df_pendentes[df_pendentes['responsavel_acao'].str.contains('Interno|Querino|Comercial', na=False, case=False)]
        df_cliente_kpi = df_pendentes[df_pendentes['responsavel_acao'].str.contains('Cliente', na=False, case=False)]
        
        op1.metric(lbl_interno, f"R$ {df_interno_kpi['valor_total'].sum():,.2f}", f"{len(df_interno_kpi)} processos", delta_color="inverse" if is_admin else "off")
        op2.metric(lbl_cliente, f"R$ {df_cliente_kpi['valor_total'].sum():,.2f}", f"{len(df_cliente_kpi)} processos", delta_color="inverse")
        
        maior_atraso = df_pendentes['dias_atraso_medicao'].max()
        op3.metric("Maior Atraso Identificado", f"{maior_atraso} dias", "Foco prioritário", delta_color="inverse" if maior_atraso > 0 else "off")
        
        st.divider()
        
        # 2. Carteira de Pendências Operacionais
        st.markdown(lbl_carteira)
        
        # -------------------------------------------------------------
        # 📄 CHECAGEM DE DOCUMENTOS BASEADO EM EXIGÊNCIA DO CLIENTE
        # -------------------------------------------------------------
        def checar_docs(row):
            exigencia = str(row.get('exigencia_para_faturamento', '')).strip().upper()
            pc_vazio = pd.isna(row.get('pedido_compra')) or str(row.get('pedido_compra', '')).strip() in ['', 'NAN', 'NONE', 'NULL']
            fs_vazio = pd.isna(row.get('folha_servico')) or str(row.get('folha_servico', '')).strip() in ['', 'NAN', 'NONE', 'NULL']
            
            if exigencia in ['NÃO', 'NAO', 'ISENTO', 'NENHUM', 'NADA']:
                return "OK"
            
            falta = []
            if 'PEDIDO' in exigencia or 'PC' in exigencia:
                if pc_vazio:
                    falta.append("PC")
            
            if 'FOLHA' in exigencia or 'FS' in exigencia or 'SERVIÇO' in exigencia or 'SERVICO' in exigencia:
                if fs_vazio:
                    falta.append("FS")
            
            if not falta and (not exigencia or exigencia in ['NAN', 'NONE']):
                if pc_vazio: falta.append("PC")
                if fs_vazio: falta.append("FS")
                
            return " / ".join(falta) if falta else "OK"
            
        df_pendentes['docs_faltantes'] = df_pendentes.apply(checar_docs, axis=1)

        # -------------------------------------------------------------
        # 🏷️ SIMPLIFICAÇÃO DA COLUNA DE GRUPO E AJUSTE DE PERFIL
        # -------------------------------------------------------------
        def formatar_grupo(row):
            grupo = str(row.get('grupo', '')).strip()
            if grupo and grupo.upper() not in ['NAN', 'NONE', 'NULL', '']:
                return grupo
            return str(row.get('cliente', '')).strip()

        df_pendentes['grupo_exibicao'] = df_pendentes.apply(formatar_grupo, axis=1)
        
        if 'cod_treinamento' not in df_pendentes.columns:
            df_pendentes['cod_treinamento'] = '-'
        
        df_exibir = df_pendentes[[
            'grupo_exibicao', 'unidade', 'id_processo', 'cod_treinamento', 'data_inicio', 'valor_total', 'tipo_faturamento', 
            'status_medicao', 'responsavel_acao', 'dias_atraso_medicao', 'docs_faltantes'
        ]].sort_values(by=['dias_atraso_medicao', 'valor_total'], ascending=[False, False])

        if not is_admin:
            df_exibir['responsavel_acao'] = df_exibir['responsavel_acao'].replace({
                'Gestão de Contratos / Interno': 'Equipe Querino',
                'Comercial Querino': 'Equipe Querino',
                'Financeiro Querino': 'Equipe Querino',
                'Cliente': 'Sua Empresa',
                'Cliente (Financeiro)': 'Sua Empresa (Financeiro)',
                'Sistema': 'Sistema'
            })
            cols_remover = [c for c in ['grupo_exibicao', 'tipo_faturamento'] if c in df_exibir.columns]
            df_exibir = df_exibir.drop(columns=cols_remover)

        # -------------------------------------------------------------
        # 🔍 FILTROS DINÂMICOS (BUSCA RÁPIDA + STATUS)
        # -------------------------------------------------------------
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            texto_busca = st.text_input("🔎 Busca Rápida (Grupo, Unidade, Processo ou Cód. Treinamento):")
        
        with col_f2:
            opcoes_status = ["Todos"] + sorted(df_exibir['status_medicao'].unique().tolist())
            status_selecionado = st.selectbox("📌 Filtrar por Status:", opcoes_status)

        # Aplica filtro de Status (se selecionado)
        if status_selecionado != "Todos":
            df_exibir = df_exibir[df_exibir['status_medicao'] == status_selecionado]

        # Aplica filtro de Texto livre
        if texto_busca:
            termo = texto_busca.lower()
            if is_admin:
                mascara = (
                    df_exibir['grupo_exibicao'].str.lower().str.contains(termo, na=False) |
                    df_exibir['unidade'].str.lower().str.contains(termo, na=False) |
                    df_exibir['id_processo'].str.lower().str.contains(termo, na=False) |
                    df_exibir['cod_treinamento'].str.lower().str.contains(termo, na=False)
                )
            else:
                mascara = (
                    df_exibir['unidade'].str.lower().str.contains(termo, na=False) |
                    df_exibir['id_processo'].str.lower().str.contains(termo, na=False) |
                    df_exibir['cod_treinamento'].str.lower().str.contains(termo, na=False)
                )
            df_exibir = df_exibir[mascara]

        # -------------------------------------------------------------
        # RENDERIZAÇÃO DA TABELA
        # -------------------------------------------------------------
        col_config = {
            "id_processo": "Processo",
            "cod_treinamento": st.column_config.TextColumn("Cód. Treinamento", width="medium"),
            "unidade": st.column_config.TextColumn("Unidade", width="medium"),
            "data_inicio": st.column_config.DateColumn("Início", format="DD/MM/YYYY"),
            "valor_total": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f"),
            "tipo_faturamento": st.column_config.TextColumn("Tipo", width="small"),
            "status_medicao": st.column_config.TextColumn("Etapa Atual / Status", width="medium"),
            "responsavel_acao": "Responsável",
            "dias_atraso_medicao": st.column_config.NumberColumn("Dias Atraso", help="Dias de atraso na medição ou faturamento pontual"),
            "docs_faltantes": st.column_config.TextColumn("Falta PC/FS?", help="Valida pendência de Pedido (PC) ou Folha de Serviço (FS) conforme exigência do contrato no Comercial")
        }
        
        if is_admin:
            col_config["grupo_exibicao"] = st.column_config.TextColumn("Grupo", width="medium")

        st.dataframe(
            df_exibir,
            use_container_width=True,
            hide_index=True,
            column_config=col_config,
            height=400
        )