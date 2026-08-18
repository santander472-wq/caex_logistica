import streamlit as st
import pandas as pd
import mysql.connector
from mysql.connector import Error
from datetime import date

st.set_page_config(page_title="CAEX - Control Última Milla", page_icon="📦", layout="wide")
st.title("📦 Control Operativo de Envíos - CAEX")

@st.cache_resource
def iniciar_conexion():
    try:
        conexion = mysql.connector.connect(
            host="gateway01.us-east-1.prod.aws.tidbcloud.com",
            port=4000,
            user="2GfuJL3tx7ytwVq.root",
            password="FqP5AOh3JjhsM0PV",
            database="caex_logistica"
        )
        return conexion
    except Error as e:
        st.error(f"Error conectando a TiDB Cloud: {e}")
        return None

conexion = iniciar_conexion()

def obtener_datos(query, params=None):
    return pd.read_sql(query, conexion, params=params)

if conexion:
    df_agencias = obtener_datos("SELECT id_agencia, nombre_agencia FROM agencias")
    df_mensajeros = obtener_datos("SELECT id_mensajero, nombre_completo FROM mensajeros")

    tab_verif, tab_cargue, tab_descargue, tab_reporte = st.tabs([
        "✅ 1. Verificación Clientes", 
        "📦 2. Cargue a Zona", 
        "📥 3. Descargue", 
        "📊 4. Reportes"
    ])
    
    with tab_verif:
        st.markdown("Módulo para constatar el ingreso físico de envíos masivos.")
        col1, col2, col3 = st.columns(3)
        with col1:
            fecha_verif = st.date_input("1. Seleccione Fecha:")
        with col2:
            cliente_sel = st.selectbox("2. Seleccione Cliente:", ["CADENA", "CARVAJAL"])
        with col3:
            agencia_verif = st.selectbox("3. Seleccionar Agencia:", df_agencias['nombre_agencia'].tolist(), key="ag_verif")
            id_agencia_verif = df_agencias.loc[df_agencias['nombre_agencia'] == agencia_verif, 'id_agencia'].values[0]

        guias_verif_input = st.text_area("4. Ingrese Guías (Escaneo Masivo):", height=150, key="text_verif")

        if st.button("✅ Registrar Verificación Físicamente", type="primary", use_container_width=True):
            if guias_verif_input.strip() != "":
                lista_guias_verif = list(set([g.strip() for g in guias_verif_input.split('\n') if g.strip() != ""]))
                valores_verif = [(fecha_verif.strftime("%Y-%m-%d"), cliente_sel, int(id_agencia_verif), g, "Verificado") for g in lista_guias_verif]
                
                cursor = conexion.cursor()
                query_verif = """
                    INSERT INTO verificaciones (fecha_ingreso, cliente, id_agencia, numero_guia, estado) 
                    VALUES (%s, %s, %s, %s, %s)
                """
                try:
                    cursor.executemany(query_verif, valores_verif)
                    conexion.commit()
                    st.success(f"✅ ¡Excelente! Se verificaron {len(lista_guias_verif)} guías de {cliente_sel} en {agencia_verif}.")
                except Error as e:
                    conexion.rollback()
                    st.error(f"❌ Error al registrar: {e}")
                finally:
                    cursor.close()
            else:
                st.warning("⚠️ No has ingresado ninguna guía para verificar.")

        st.markdown("---")
        st.subheader("📊 Reporte de Verificación por Agencia (Para Exportar)")
        
        query_repo_verif = """
            SELECT 
                v.fecha_ingreso AS 'Fecha de Ingreso',
                v.cliente AS 'Cliente',
                a.nombre_agencia AS 'Agencia',
                COUNT(v.numero_guia) AS 'Total Guías Verificadas'
            FROM verificaciones v
            JOIN agencias a ON v.id_agencia = a.id_agencia
            GROUP BY v.fecha_ingreso, v.cliente, a.nombre_agencia
            ORDER BY v.fecha_ingreso DESC
        """
        df_repo_verif = obtener_datos(query_repo_verif)
        st.dataframe(df_repo_verif, use_container_width=True, hide_index=True)
        
        if not df_repo_verif.empty:
            csv = df_repo_verif.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar Reporte en CSV",
                data=csv,
                file_name=f"reporte_verificacion_{date.today()}.csv",
                mime="text/csv",
            )

    with tab_cargue:
        st.markdown("Asignación de guías al mensajero. Quedarán en estado **En Zona**.")
        col1, col2 = st.columns(2)
        with col1:
            agencia_sel = st.selectbox("📍 Punto de Custodia:", df_agencias['nombre_agencia'].tolist(), key="ag_cargue")
            id_agencia = df_agencias.loc[df_agencias['nombre_agencia'] == agencia_sel, 'id_agencia'].values[0]
        with col2:
            mensajero_sel = st.selectbox("🚚 Mensajero:", df_mensajeros['nombre_completo'].tolist(), key="ms_cargue")
            id_mensajero = df_mensajeros.loc[df_mensajeros['nombre_completo'] == mensajero_sel, 'id_mensajero'].values[0]

        guias_input = st.text_area("Códigos de Barras (Cargue):", height=150, key="text_cargue")

        if st.button("🚀 Procesar Cargue a Zona", type="primary", use_container_width=True):
            if guias_input.strip() != "":
                lista_guias = list(set([g.strip() for g in guias_input.split('\n') if g.strip() != ""]))
                valores = [(g, int(id_mensajero), int(id_agencia), "En Zona") for g in lista_guias]
                cursor = conexion.cursor()
                query = "INSERT INTO cargues_envios (numero_guia, id_mensajero, id_agencia, estado) VALUES (%s, %s, %s, %s)"
                try:
                    cursor.executemany(query, valores)
                    conexion.commit()
                    st.success(f"✅ Se cargaron {len(lista_guias)} guías a {mensajero_sel} (En Zona).")
                except Error as e:
                    conexion.rollback()
                    st.error(f"❌ Error: {e}")
                finally:
                    cursor.close()

    with tab_descargue:
        st.markdown("Liquida los envíos gestionados. Lo no descargado seguirá en la cuenta del mensajero.")
        accion = st.radio(
            "Seleccione el resultado de la gestión:",
            ["✅ Entrega Efectiva", "❌ Devolución - Dirección errada", "❌ Devolución - No reside", 
             "❌ Devolución - Desconocido", "❌ Devolución - Rehusado", "❌ Devolución - Cerrado", 
             "🔄 Reenvío (Volver a Zona por Cerrado)"]
        )
        guias_descargue_input = st.text_area("Escanea las guías correspondientes:", height=150, key="text_descargue")
        
        if st.button("💾 Procesar Descargue", type="primary", use_container_width=True):
            if guias_descargue_input.strip() != "":
                if "Entrega Efectiva" in accion:
                    nuevo_estado, nuevo_subestado = "Entregado", "Entrega Efectiva"
                elif "Reenvío" in accion:
                    nuevo_estado, nuevo_subestado = "En Zona", "Reenvío - Cerrado"
                else:
                    nuevo_estado = "Devuelto"
                    nuevo_subestado = accion.replace("❌ Devolución - ", "")

                lista_guias_desc = list(set([g.strip() for g in guias_descargue_input.split('\n') if g.strip() != ""]))
                cursor = conexion.cursor()
                format_strings = ','.join(['%s'] * len(lista_guias_desc))
                query_update = f"UPDATE cargues_envios SET estado = %s, subestado = %s WHERE numero_guia IN ({format_strings})"
                parametros = [nuevo_estado, nuevo_subestado] + lista_guias_desc
                try:
                    cursor.execute(query_update, tuple(parametros))
                    conexion.commit()
                    st.success(f"✅ Liquidación exitosa: {cursor.rowcount} guías actualizadas a '{nuevo_estado} - {nuevo_subestado}'.")
                except Error as e:
                    conexion.rollback()
                    st.error(f"❌ Error en la liquidación: {e}")
                finally:
                    cursor.close()

    with tab_reporte:
        st.subheader("📊 Resumen Operativo por Mensajero")
        if st.button("🔄 Actualizar Datos"):
            st.rerun()

        query_resumen = """
            SELECT 
                DATE(c.fecha_cargue) AS 'Fecha de Cargue',
                m.nombre_completo AS 'Mensajero',
                COUNT(c.numero_guia) AS 'Total Cargados',
                SUM(CASE WHEN c.estado = 'Entregado' THEN 1 ELSE 0 END) AS 'Entregados',
                SUM(CASE WHEN c.estado = 'Devuelto' THEN 1 ELSE 0 END) AS 'Devueltos',
                SUM(CASE WHEN c.estado = 'En Zona' THEN 1 ELSE 0 END) AS 'En Zona (Pendientes)'
            FROM cargues_envios c
            JOIN mensajeros m ON c.id_mensajero = m.id_mensajero
            GROUP BY DATE(c.fecha_cargue), m.nombre_completo
            ORDER BY DATE(c.fecha_cargue) DESC, m.nombre_completo
        """
        df_resumen = obtener_datos(query_resumen)
        st.dataframe(df_resumen, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🔍 Detalle de Envíos Pendientes (En Zona)")
        if not df_resumen.empty and 'En Zona (Pendientes)' in df_resumen.columns:
            mensajeros_pendientes = df_resumen[df_resumen['En Zona (Pendientes)'] > 0]['Mensajero'].unique()
            
            if len(mensajeros_pendientes) > 0:
                mensajero_detalle = st.selectbox("Selecciona un mensajero para auditar sus guías:", mensajeros_pendientes)
                query_pendientes = """
                    SELECT 
                        c.numero_guia AS 'Número de Guía', 
                        c.fecha_cargue AS 'Hora de Cargue',
                        a.nombre_agencia AS 'Agencia Origen',
                        IFNULL(c.subestado, 'Recién Cargado') AS 'Historial / Subestado'
                    FROM cargues_envios c
                    JOIN mensajeros m ON c.id_mensajero = m.id_mensajero
                    JOIN agencias a ON c.id_agencia = a.id_agencia
                    WHERE m.nombre_completo = %s AND c.estado = 'En Zona'
                    ORDER BY c.fecha_cargue ASC
                """
                df_pendientes = obtener_datos(query_pendientes, params=(mensajero_detalle,))
                st.dataframe(df_pendientes, use_container_width=True, hide_index=True)
                st.info(f"El mensajero {mensajero_detalle} tiene {len(df_pendientes)} envíos pendientes por liquidar.")
            else:
                st.success("🎉 ¡Operación limpia! No hay envíos pendientes en zona en este momento.")
