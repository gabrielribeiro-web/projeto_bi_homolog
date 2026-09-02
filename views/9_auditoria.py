import pandas as pd
import streamlit as st
from sqlalchemy import text
from components import renderizar_filtros

def renderizar_pagina():
    # 1. Aplica a identidade visual padrão, filtros globais e pega a conexão do banco
    engine, user, grupo_sel, unidade_sel, dt_inicio, dt_fim, modo_visao = renderizar_filtros(mostrar_filtros=False)

    st.markdown("<br>", unsafe_allow_html=True)
    
    # 2. Configuração do título específico da página
    st.title("🕰️ Auditoria e Histórico")
    st.markdown("Acompanhe o histórico de alterações operacionais e financeiras dos processos.")
    st.divider()

    # 3. Campo de busca para o ID do Processo
    col_busca, _ = st.columns([1, 2])
    with col_busca:
        id_busca = st.text_input("🔍 Buscar por ID do Processo:", placeholder="Ex: SP2496-26")

    # 4. Processamento da Busca
    if id_busca:
        id_busca = id_busca.strip().upper()
        
        try:
            # Busca o histórico do processo específico
            query = text("""
                SELECT 
                    id_processo, 
                    tipo_status, 
                    status_anterior, 
                    status_novo, 
                    data_mudanca
                FROM public.tb_historico_processos
                WHERE UPPER(id_processo) = :id_processo
                ORDER BY data_mudanca DESC
            """)
            
            df_historico = pd.read_sql_query(query, engine, params={"id_processo": id_busca})

            if df_historico.empty:
                st.warning(f"Nenhum histórico encontrado para o processo **{id_busca}**.")
            else:
                st.success(f"Histórico localizado para: **{id_busca}**")
                
                # -------------------------------------------------------------
                # 🛠️ TRATAMENTO DOS DADOS (Fuso horário e Nomenclaturas)
                # -------------------------------------------------------------
                
                # Traduz "NOVO PROCESSO" para algo que faça sentido lógico como status anterior
                df_historico["status_anterior"] = df_historico["status_anterior"].replace("NOVO PROCESSO", "Registro Inicial")
                
                # Converte para formato de data do Pandas e ajusta o Fuso Horário (-3h)
                df_historico["data_mudanca"] = pd.to_datetime(df_historico["data_mudanca"])
                df_historico["data_mudanca"] = df_historico["data_mudanca"] - pd.Timedelta(hours=3)
                df_historico["data_mudanca"] = df_historico["data_mudanca"].dt.strftime("%d/%m/%Y %H:%M:%S")

                # -------------------------------------------------------------
                # 🏷️ RENOMEANDO AS COLUNAS PARA A INTERFACE
                # -------------------------------------------------------------
                df_historico = df_historico.rename(columns={
                    "id_processo": "Processo",
                    "tipo_status": "Categoria",
                    "status_anterior": "De (Status Anterior)",
                    "status_novo": "Para (Novo Status)",
                    "data_mudanca": "Data e Hora da Atualização"
                })

                # Exibe a tabela formatada e sem o índice
                st.dataframe(
                    df_historico, 
                    use_container_width=True, 
                    hide_index=True
                )

        except Exception as e:
            st.error(f"Erro ao buscar o histórico: {e}")
    else:
        st.info("👆 Digite o ID de um processo acima para visualizar a linha do tempo de alterações.")

# Executa a função principal da página
renderizar_pagina()