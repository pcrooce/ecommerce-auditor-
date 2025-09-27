import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import time

# Configuración de la página
st.set_page_config(
    page_title="Auditor de Tiendas",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado con colores corporativos
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
    div[data-testid="metric-container"] {
        background-color: #f0f2f6;
        border: 1px solid #c3c3c3;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0px;
    }
    .store-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

# Título principal con información de tiendas
st.markdown("""
    <div class="store-header">
        <h1 style="text-align: center; color: white;">🏪 Sistema de Auditoría de Tiendas</h1>
        <p style="text-align: center; color: white; margin-top: 10px;">
            Análisis y control de publicaciones para optimización de ventas
        </p>
    </div>
    """, unsafe_allow_html=True)

# Inicializar estado de sesión
if 'audit_completed' not in st.session_state:
    st.session_state.audit_completed = False
if 'results' not in st.session_state:
    st.session_state.results = None
if 'selected_store' not in st.session_state:
    st.session_state.selected_store = None

# Lista de tiendas que mencionaste
TIENDAS_DISPONIBLES = [
    "Avenida",
    "Falabella", 
    "Paris",
    "Ripley",
    "La Polar",
    "Hites",
    "Otro (Especificar)"
]

# Sidebar para configuración
with st.sidebar:
    st.header("⚙️ Configuración de Auditoría")
    
    # Selección de tienda
    st.subheader("🏬 Seleccionar Tienda")
    selected_store = st.selectbox(
        "Tienda a auditar:",
        TIENDAS_DISPONIBLES,
        help="Selecciona la tienda que deseas auditar"
    )
    
    if selected_store == "Otro (Especificar)":
        custom_store = st.text_input("Nombre de la tienda:")
        if custom_store:
            selected_store = custom_store
    
    st.session_state.selected_store = selected_store
    
    st.markdown("---")
    
    # Parámetros de auditoría
    st.subheader("📊 Parámetros de Control")
    
    price_threshold = st.slider(
        "Variación de precio máxima (%)",
        min_value=1,
        max_value=20,
        value=5,
        help="Diferencia máxima aceptable entre precio publicado y base de datos"
    )
    
    stock_minimum = st.number_input(
        "Stock mínimo recomendado",
        min_value=1,
        max_value=100,
        value=5,
        help="Cantidad mínima antes de generar alerta"
    )
    
    dias_sin_venta = st.number_input(
        "Días sin venta para alerta",
        min_value=7,
        max_value=90,
        value=30,
        help="Productos sin movimiento en este período serán marcados"
    )
    
    st.markdown("---")
    
    # Información de ayuda
    st.subheader("📚 Guía Rápida")
    with st.expander("¿Cómo realizar la auditoría?"):
        st.write("""
        1. **Selecciona la tienda** a auditar
        2. **Carga el Excel de la tienda** con las publicaciones actuales
        3. **Carga tu base de datos** con la información maestra
        4. **Ejecuta la auditoría** para ver resultados
        5. **Exporta el reporte** con los hallazgos
        """)
    
    with st.expander("Formato de archivos Excel"):
        st.write("""
        **Columnas requeridas:**
        - `SKU` o `ID`: Código del producto
        - `Nombre` o `Titulo`: Descripción
        - `Precio`: Precio publicado
        - `Stock`: Cantidad disponible
        - `Estado`: Activo/Pausado/Inactivo
        - `Categoria`: Categoría del producto
        - `Ultima_Venta`: Fecha última venta (opcional)
        """)
    
    st.markdown("---")
    st.info(f"🏪 **Auditando:** {selected_store}")

# Área principal - Sistema de carga de archivos
st.header(f"📋 Auditoría de {selected_store}")

# Crear tabs para mejor organización
tab1, tab2, tab3 = st.tabs(["📁 Carga de Datos", "📊 Resultados", "📈 Histórico"])

with tab1:
    st.markdown("### Cargar archivos para auditoría")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**📊 Archivo de {selected_store}**")
        store_file = st.file_uploader(
            f"Excel con publicaciones de {selected_store}",
            type=['xlsx', 'xls', 'csv'],
            key="store_file",
            help=f"Archivo descargado desde el panel de {selected_store}"
        )
        
        if store_file:
            st.success(f"✅ {store_file.name} cargado correctamente")
            # Preview de datos
            with st.expander("Ver primeras filas"):
                df_preview = pd.read_excel(store_file) if store_file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(store_file)
                st.dataframe(df_preview.head(), use_container_width=True)
    
    with col2:
        st.markdown("**💾 Base de Datos Maestra**")
        database_file = st.file_uploader(
            "Excel con información de productos",
            type=['xlsx', 'xls', 'csv'],
            key="database_file",
            help="Tu base de datos con precios y stock correctos"
        )
        
        if database_file:
            st.success(f"✅ {database_file.name} cargado correctamente")
            # Preview de datos
            with st.expander("Ver primeras filas"):
                df_preview = pd.read_excel(database_file) if database_file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(database_file)
                st.dataframe(df_preview.head(), use_container_width=True)

# Función mejorada de auditoría
def perform_store_audit(store_df, db_df, store_name, price_threshold, stock_minimum):
    """Realizar auditoría específica para la tienda"""
    results = {
        'store_name': store_name,
        'audit_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'summary': {},
        'price_issues': [],
        'stock_issues': [],
        'missing_products': [],
        'inactive_products': [],
        'recommendations': []
    }
    
    # Barra de progreso
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Normalizar nombres de columnas
    store_df.columns = store_df.columns.str.lower().str.strip()
    db_df.columns = db_df.columns.str.lower().str.strip()
    
    # 1. Análisis general
    status_text.text(f"Analizando catálogo de {store_name}...")
    progress_bar.progress(20)
    
    results['summary']['total_productos_tienda'] = len(store_df)
    results['summary']['total_productos_bd'] = len(db_df)
    
    # Buscar columna de ID (puede ser 'sku', 'id', 'codigo', etc.)
    id_columns = ['sku', 'id', 'codigo', 'cod', 'product_id']
    id_col = None
    for col in id_columns:
        if col in store_df.columns and col in db_df.columns:
            id_col = col
            break
    
    if not id_col:
        st.error("⚠️ No se encontró columna de identificación común (SKU, ID, etc.)")
        return results
    
    # 2. Análisis de precios
    status_text.text("Verificando consistencia de precios...")
    progress_bar.progress(40)
    
    price_columns = ['precio', 'price', 'precio_venta', 'pvp']
    price_col = None
    for col in price_columns:
        if col in store_df.columns:
            price_col = col
            break
    
    if price_col and price_col in db_df.columns:
        # Merge de dataframes
        merged = pd.merge(
            store_df[[id_col, price_col]], 
            db_df[[id_col, price_col]], 
            on=id_col, 
            suffixes=('_tienda', '_bd'),
            how='outer',
            indicator=True
        )
        
        # Productos solo en tienda (no en BD)
        only_in_store = merged[merged['_merge'] == 'left_only']
        results['missing_products'] = only_in_store[id_col].tolist()
        results['summary']['productos_no_en_bd'] = len(only_in_store)
        
        # Productos solo en BD (no publicados)
        only_in_db = merged[merged['_merge'] == 'right_only']
        results['summary']['productos_no_publicados'] = len(only_in_db)
        
        # Comparar precios
        both = merged[merged['_merge'] == 'both'].copy()
        if not both.empty:
            both['variacion_%'] = ((both[f'{price_col}_tienda'] - both[f'{price_col}_bd']) / both[f'{price_col}_bd'] * 100).abs()
            
            # Identificar problemas de precio
            price_issues = both[both['variacion_%'] > price_threshold].copy()
            if not price_issues.empty:
                price_issues['diferencia_$'] = price_issues[f'{price_col}_tienda'] - price_issues[f'{price_col}_bd']
                results['price_issues'] = price_issues[[id_col, f'{price_col}_tienda', f'{price_col}_bd', 'variacion_%', 'diferencia_$']].to_dict('records')
            
            results['summary']['productos_con_precio_incorrecto'] = len(price_issues)
            results['summary']['productos_precio_ok'] = len(both) - len(price_issues)
    
    # 3. Análisis de stock
    status_text.text("Analizando niveles de stock...")
    progress_bar.progress(60)
    
    stock_columns = ['stock', 'cantidad', 'inventory', 'disponible']
    stock_col = None
    for col in stock_columns:
        if col in store_df.columns:
            stock_col = col
            break
    
    if stock_col:
        # Stock bajo o agotado
        low_stock = store_df[store_df[stock_col] < stock_minimum].copy()
        out_of_stock = store_df[store_df[stock_col] == 0].copy()
        
        if not low_stock.empty:
            results['stock_issues'] = low_stock[[id_col, stock_col]].to_dict('records')
        
        results['summary']['productos_sin_stock'] = len(out_of_stock)
        results['summary']['productos_stock_bajo'] = len(low_stock) - len(out_of_stock)
    
    # 4. Análisis de estado
    status_text.text("Verificando estados de publicación...")
    progress_bar.progress(80)
    
    estado_columns = ['estado', 'status', 'activo', 'state']
    estado_col = None
    for col in estado_columns:
        if col in store_df.columns:
            estado_col = col
            break
    
    if estado_col:
        # Contar por estado
        estados = store_df[estado_col].value_counts()
        results['summary']['distribucion_estados'] = estados.to_dict()
        
        # Productos inactivos/pausados
        inactive_keywords = ['pausado', 'inactivo', 'paused', 'inactive', 'desactivado']
        inactive = store_df[store_df[estado_col].str.lower().str.contains('|'.join(inactive_keywords), na=False)]
        if not inactive.empty:
            results['inactive_products'] = inactive[id_col].tolist()
            results['summary']['productos_inactivos'] = len(inactive)
    
    # 5. Generar recomendaciones
    status_text.text("Generando recomendaciones...")
    progress_bar.progress(90)
    
    # Recomendaciones automáticas basadas en hallazgos
    if results['summary'].get('productos_sin_stock', 0) > 0:
        results['recommendations'].append({
            'prioridad': 'ALTA',
            'tipo': 'Stock',
            'accion': f"Reponer urgentemente {results['summary']['productos_sin_stock']} productos sin stock"
        })
    
    if results['summary'].get('productos_con_precio_incorrecto', 0) > 0:
        results['recommendations'].append({
            'prioridad': 'ALTA',
            'tipo': 'Precio',
            'accion': f"Actualizar {results['summary']['productos_con_precio_incorrecto']} productos con precios incorrectos"
        })
    
    if results['summary'].get('productos_no_publicados', 0) > 10:
        results['recommendations'].append({
            'prioridad': 'MEDIA',
            'tipo': 'Catálogo',
            'accion': f"Publicar {results['summary']['productos_no_publicados']} productos disponibles en BD pero no en tienda"
        })
    
    if results['summary'].get('productos_inactivos', 0) > 0:
        results['recommendations'].append({
            'prioridad': 'BAJA',
            'tipo': 'Estado',
            'accion': f"Revisar {results['summary']['productos_inactivos']} productos pausados/inactivos"
        })
    
    # Calcular score de salud
    total_productos = results['summary'].get('total_productos_tienda', 1)
    problemas = (
        results['summary'].get('productos_sin_stock', 0) * 2 +  # Peso doble para sin stock
        results['summary'].get('productos_con_precio_incorrecto', 0) +
        results['summary'].get('productos_stock_bajo', 0) * 0.5
    )
    
    health_score = max(0, 100 - (problemas / total_productos * 100))
    results['summary']['health_score'] = round(health_score, 1)
    
    progress_bar.progress(100)
    time.sleep(0.5)
    progress_bar.empty()
    status_text.empty()
    
    return results

# Botón de ejecutar auditoría
with tab1:
    if store_file and database_file:
        st.markdown("---")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button(f"🔍 Ejecutar Auditoría de {selected_store}", 
                        type="primary", 
                        use_container_width=True):
                
                # Cargar datos
                with st.spinner(f"Procesando datos de {selected_store}..."):
                    try:
                        # Cargar archivos
                        if store_file.name.endswith('.csv'):
                            store_df = pd.read_csv(store_file)
                        else:
                            store_df = pd.read_excel(store_file)
                        
                        if database_file.name.endswith('.csv'):
                            db_df = pd.read_csv(database_file)
                        else:
                            db_df = pd.read_excel(database_file)
                        
                        # Realizar auditoría
                        results = perform_store_audit(
                            store_df, 
                            db_df, 
                            selected_store,
                            price_threshold, 
                            stock_minimum
                        )
                        
                        st.session_state.results = results
                        st.session_state.audit_completed = True
                        st.success(f"✅ Auditoría de {selected_store} completada exitosamente")
                        st.balloons()
                        
                    except Exception as e:
                        st.error(f"❌ Error al procesar los archivos: {str(e)}")
                        st.info("Verifica que los archivos tengan el formato correcto")

# Mostrar resultados en Tab 2
with tab2:
    if st.session_state.audit_completed and st.session_state.results:
        results = st.session_state.results
        
        # Header con información de la auditoría
        st.markdown(f"""
        ### 📊 Resultados de Auditoría - {results['store_name']}
        **Fecha:** {results['audit_date']}
        """)
        
        # Métricas principales con colores
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            health = results['summary'].get('health_score', 0)
            color = "🟢" if health > 80 else "🟡" if health > 60 else "🔴"
            st.metric(
                label=f"{color} Salud del Catálogo",
                value=f"{health}%",
                delta="Excelente" if health > 80 else "Regular" if health > 60 else "Crítico"
            )
        
        with col2:
            total = results['summary'].get('total_productos_tienda', 0)
            st.metric(
                label="📦 Total Productos",
                value=f"{total:,}",
                delta=f"{results['summary'].get('total_productos_bd', 0):,} en BD"
            )
        
        with col3:
            sin_stock = results['summary'].get('productos_sin_stock', 0)
            color = "🔴" if sin_stock > 0 else "🟢"
            st.metric(
                label=f"{color} Sin Stock",
                value=sin_stock,
                delta="Crítico" if sin_stock > 0 else "OK"
            )
        
        with col4:
            precio_mal = results['summary'].get('productos_con_precio_incorrecto', 0)
            color = "🔴" if precio_mal > 5 else "🟡" if precio_mal > 0 else "🟢"
            st.metric(
                label=f"{color} Precios Incorrectos",
                value=precio_mal,
                delta=f">{price_threshold}% variación"
            )
        
        # Tabs para diferentes análisis
        analysis_tab1, analysis_tab2, analysis_tab3, analysis_tab4 = st.tabs([
            "💰 Precios", 
            "📦 Stock", 
            "📊 Estados",
            "💡 Recomendaciones"
        ])
        
        with analysis_tab1:
            st.subheader("Análisis de Precios")
            
            if results.get('price_issues'):
                st.warning(f"⚠️ {len(results['price_issues'])} productos con variación de precio superior al {price_threshold}%")
                
                # Crear DataFrame para mostrar
                price_df = pd.DataFrame(results['price_issues'])
                
                # Formatear columnas
                for col in price_df.columns:
                    if 'precio' in col.lower() or 'price' in col.lower() or 'diferencia_$' in col:
                        price_df[col] = price_df[col].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "")
                    elif 'variacion_%' in col:
                        price_df[col] = price_df[col].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) else "")
                
                st.dataframe(
                    price_df,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Gráfico de variaciones
                if len(results['price_issues']) > 0:
                    fig = px.bar(
                        price_df.head(20),
                        x=price_df.columns[0],  # SKU/ID
                        y='variacion_%',
                        title="Top 20 Productos con Mayor Variación de Precio",
                        color='variacion_%',
                        color_continuous_scale=['yellow', 'orange', 'red']
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.success("✅ Todos los precios están dentro del rango aceptable")
        
        with analysis_tab2:
            st.subheader("Análisis de Stock")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Gráfico de distribución de stock
                stock_data = {
                    'Estado': ['Sin Stock', 'Stock Bajo', 'Stock OK'],
                    'Cantidad': [
                        results['summary'].get('productos_sin_stock', 0),
                        results['summary'].get('productos_stock_bajo', 0),
                        results['summary'].get('total_productos_tienda', 0) - 
                        results['summary'].get('productos_sin_stock', 0) - 
                        results['summary'].get('productos_stock_bajo', 0)
                    ]
                }
                
                fig = px.pie(
                    stock_data,
                    values='Cantidad',
                    names='Estado',
                    title="Distribución de Stock",
                    color_discrete_map={
                        'Sin Stock': '#FF4444',
                        'Stock Bajo': '#FFA500',
                        'Stock OK': '#00CC00'
                    }
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                if results.get('stock_issues'):
                    st.error(f"📦 {len(results['stock_issues'])} productos requieren reposición")
                    
                    stock_df = pd.DataFrame(results['stock_issues'])
                    st.dataframe(
                        stock_df.head(20),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.success("✅ Todos los productos tienen stock adecuado")
        
        with analysis_tab3:
            st.subheader("Estados de Publicación")
            
            if results['summary'].get('distribucion_estados'):
                estados = results['summary']['distribucion_estados']
                
                # Gráfico de estados
                fig = px.bar(
                    x=list(estados.keys()),
                    y=list(estados.values()),
                    title="Distribución de Estados de Publicación",
                    labels={'x': 'Estado', 'y': 'Cantidad'},
                    color=list(estados.values()),
                    color_continuous_scale='viridis'
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # Tabla resumen
                estado_df = pd.DataFrame(estados.items(), columns=['Estado', 'Cantidad'])
                estado_df['Porcentaje'] = (estado_df['Cantidad'] / estado_df['Cantidad'].sum() * 100).round(1)
                estado_df['Porcentaje'] = estado_df['Porcentaje'].apply(lambda x: f"{x}%")
                
                st.dataframe(estado_df, use_container_width=True, hide_index=True)
        
        with analysis_tab4:
            st.subheader("💡 Recomendaciones de Acción")
            
            if results.get('recommendations'):
                for rec in results['recommendations']:
                    if rec['prioridad'] == 'ALTA':
                        st.error(f"🔴 **{rec['prioridad']}** - {rec['tipo']}: {rec['accion']}")
                    elif rec['prioridad'] == 'MEDIA':
                        st.warning(f"🟡 **{rec['prioridad']}** - {rec['tipo']}: {rec['accion']}")
                    else:
                        st.info(f"🔵 **{rec['prioridad']}** - {rec['tipo']}: {rec['accion']}")
            else:
                st.success("✅ No hay recomendaciones urgentes. El catálogo está en buen estado.")
        
        # Sección de exportación
        st.markdown("---")
        st.subheader("📥 Exportar Resultados")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Generar Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Hoja de resumen
                summary_df = pd.DataFrame([results['summary']])
                summary_df.to_excel(writer, sheet_name='Resumen', index=False)
                
                # Hoja de problemas de precio
                if results.get('price_issues'):
                    price_df = pd.DataFrame(results['price_issues'])
                    price_df.to_excel(writer, sheet_name='Problemas_Precio', index=False)
                
                # Hoja de problemas de stock
                if results.get('stock_issues'):
                    stock_df = pd.DataFrame(results['stock_issues'])
                    stock_df.to_excel(writer, sheet_name='Problemas_Stock', index=False)
                
                # Hoja de recomendaciones
                if results.get('recommendations'):
                    rec_df = pd.DataFrame(results['recommendations'])
                    rec_df.to_excel(writer, sheet_name='Recomendaciones', index=False)
            
            output.seek(0)
            
            st.download_button(
                label="📊 Descargar Reporte Excel",
                data=output,
                file_name=f"Auditoria_{selected_store}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col2:
            # CSV resumido
            summary_df = pd.DataFrame([results['summary']])
            csv = summary_df.to_csv(index=False)
            
            st.download_button(
                label="📄 Descargar Resumen CSV",
                data=csv,
                file_name=f"Resumen_{selected_store}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
        with col3:
            # Botón para nueva auditoría
            if st.button("🔄 Nueva Auditoría", use_container_width=True):
                st.session_state.audit_completed = False
                st.session_state.results = None
                st.rerun()

# Tab de histórico
with tab3:
    st.subheader("📈 Histórico de Auditorías")
    st.info("Esta sección mostrará el histórico de auditorías realizadas (próximamente)")
    
    # Placeholder para futuras mejoras
    st.markdown("""
    **Funcionalidades futuras:**
    - 📊 Gráficos de tendencias
    - 📅 Comparación entre períodos
    - 🎯 KPIs históricos
    - 📈 Evolución de la salud del catálogo
    """)

# Footer
st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: gray; padding: 20px;'>
        <p>Sistema de Auditoría de Tiendas v1.0 | 
        Última actualización: {datetime.now().strftime("%d/%m/%Y %H:%M")} |
        Desarrollado para optimización de catálogos retail</p>
    </div>
    """,
    unsafe_allow_html=True
)
