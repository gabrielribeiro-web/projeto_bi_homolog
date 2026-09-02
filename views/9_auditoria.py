import streamlit as st
import pandas as pd
from sqlalchemy import text
from database import get_engine
from components import renderizar_filtros, get_hover_style

# ==============================================================
# 1. APLICAÇÃO DO PADRÃO VISUAL (CSS, Logo e Sidebar)
# ==============================================================
engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros(mostrar_filtros=False)
hover_style = get_hover_style()

st.markdown("### 🕰️ Auditoria e Histórico de Processos")
st.caption("Rastreabilidade completa de mudanças de status operacionais e financeiros (Regra RF32).")

# Trava de Segurança: Apenas perfis autorizados
if not user or user.get("perfil") != "admin":
    st.error("Acesso restrito a Administradores e Auditores.")
    st.stop()

# ==============================================================
# 2. MOTOR DE BUSCA
# ==============================================================
st.markdown("##### 🔍 Consultar Linha do Tempo")
col1, col2 = st.columns([1, 2])
with col1:
    processo_busca = st.text_input("Número do Processo (Ex: SP0165-26):", max_chars=50).strip().upper()

st.divider()

if processo_busca:
    query = """
        SELECT 
            tipo_status,
            status_anterior,
            status_novo,
            data_mudanca
        FROM tb_historico_processos
        WHERE UPPER(id_processo) = :id_proc
        ORDER BY data_mudanca ASC
    """
    
    try:
        with engine.connect() as conn:
            df_hist = pd.read_sql(text(query), conn, params={"id_proc": processo_busca})
        
        if df_hist.empty:
            st.warning(f"Nenhum histórico encontrado para o processo: **{processo_busca}**.")
            st.info("Dica: Verifique se o número foi digitado corretamente ou se este processo sofreu mudanças desde que o rastreio foi ativado.")
        else:
            st.success(f"✅ Histórico localizado para o processo: **{processo_busca}**")
            
            # Formata a data para padrão brasileiro
            df_hist['data_mudanca'] = pd.to_datetime(df_hist['data_mudanca']).dt.strftime('%d/%m/%Y às %H:%M')
            
            # Separa Operacional de Financeiro em abas
            aba_op, aba_fin = st.tabs(["⚙️ Histórico Operacional (SLA)", "💰 Histórico Financeiro"])
            
            with aba_op:
                df_op = df_hist[df_hist['tipo_status'] == 'OPERACIONAL'].copy()
                if df_op.empty:
                    st.info("Nenhuma mudança operacional registrada desde o início do rastreamento.")
                else:
                    st.dataframe(
                        df_op[['data_mudanca', 'status_anterior', 'status_novo']],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "data_mudanca": st.column_config.TextColumn("Data da Mudança", width="small"),
                            "status_anterior": st.column_config.TextColumn("Status Anterior (De)", width="medium"),
                            "status_novo": st.column_config.TextColumn("Status Novo (Para)", width="medium")
                        }
                    )
                    
            with aba_fin:
                df_fin = df_hist[df_hist['tipo_status'] == 'FINANCEIRO'].copy()
                if df_fin.empty:
                    st.info("Nenhuma mudança financeira registrada desde o início do rastreamento.")
                else:
                    st.dataframe(
                        df_fin[['data_mudanca', 'status_anterior', 'status_novo']],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "data_mudanca": st.column_config.TextColumn("Data da Mudança", width="small"),
                            "status_anterior": st.column_config.TextColumn("Status Anterior (De)", width="medium"),
                            "status_novo": st.column_config.TextColumn("Status Novo (Para)", width="medium")
                        }
                    )
    except Exception as e:
        st.error(f"Erro ao buscar histórico no banco de dados: {e}")
else:
    st.info("👆 Digite o número de um processo no campo acima para visualizar sua jornada completa.")