import streamlit as st
import pandas as pd
from database import get_engine
from components import renderizar_filtros

# ==============================================================
# 1. APLICAÇÃO DO PADRÃO VISUAL (CSS, Logo e Sidebar)
# ==============================================================
engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros(mostrar_filtros=False)

st.markdown("### 🚨 Painel de Inconsistências")
st.caption("Acompanhamento de processos com erros de cadastro que impedem o fluxo financeiro e operacional.")

# Trava de Segurança: Apenas perfis autorizados
if not user or user.get("perfil") != "admin":
    st.error("Acesso restrito a Administradores.")
    st.stop()

# ==============================================================
# 2. MOTOR DE BUSCA DE INCONSISTÊNCIAS
# ==============================================================
@st.cache_data(ttl=60)
def carregar_inconsistencias():
    engine_db = get_engine()
    query = """
        SELECT 
            id_processo AS "Processo",
            cliente AS "Cliente",
            status_comercial AS "Status Comercial",
            validacao AS "Validação",
            CASE 
                WHEN tipo_faturamento = 'INCONSISTENTE' THEN 'Cadastro Incompleto'
                WHEN status_financeiro = '🛑 Bloqueado por Saldo de OC' THEN 'Saldo de OC Estourado'
                ELSE tipo_faturamento 
            END AS "Erro Principal",
            CASE 
                WHEN tipo_faturamento = 'INCONSISTENTE' THEN '⚠️ Preencher o "Tipo de Faturamento" (Medição ou Pontual) na planilha de cadastro do cliente.'
                WHEN status_financeiro = '🛑 Bloqueado por Saldo de OC' THEN '🛑 O valor do serviço ultrapassou o saldo da Ordem de Compra. Solicite aditivo ao cliente ou ajuste os valores.'
                ELSE '🔍 Verificar preenchimento na planilha de origem.'
            END AS "Ação Recomendada"
        FROM vw_motor_faturamento
        WHERE tipo_faturamento = 'INCONSISTENTE'
           OR status_financeiro = '🛑 Bloqueado por Saldo de OC'
        ORDER BY id_processo DESC
    """
    return pd.read_sql(query, engine_db)

try:
    df_erros = carregar_inconsistencias()
    
    if df_erros.empty:
        st.success("🎉 Excelente! Não há nenhuma inconsistência de cadastro na base neste momento.")
        st.balloons()
    else:
        st.warning(f"⚠️ Encontramos {len(df_erros)} processos com pendências de cadastro que precisam de correção na origem.")
        
        # Filtro rápido
        erro_selecionado = st.selectbox("Filtrar por tipo de erro:", ["Todos"] + list(df_erros["Erro Principal"].unique()))
        
        if erro_selecionado != "Todos":
            df_erros = df_erros[df_erros["Erro Principal"] == erro_selecionado]
            
        st.dataframe(
            df_erros, 
            use_container_width=True,
            hide_index=True
        )
        
        st.info("💡 **O que fazer?** Corrija os dados em branco na planilha origem (ex: preencha o Tipo de Faturamento do cliente). O sistema atualizará esta lista automaticamente na próxima sincronização.")

except Exception as e:
    st.error(f"Erro ao carregar inconsistências: {e}")