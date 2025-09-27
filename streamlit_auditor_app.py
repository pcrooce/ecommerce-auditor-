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
    page_title="Auditor eCommerce",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
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
    </style>
    """, unsafe_allow_html=True)

# Título principal con emoji y estilo
st.title("🔍 Auditor de Publicaciones eCommerce")
st.markdown("---")

# Inicializar estado de sesión
if 'audit_completed' not in st.session_state:
    st.session_state.audit_completed = False
if 'results' not in st.session_state:
    st.session_state.results = None

# Sidebar para configuración
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # Umbrales de auditoría
    st.subheader("Umbrales de Análisis")
    price_threshold = st.slider(
        "Variación de precio máxima (%)",
        min_value=1,
        max_value=20,
        value=5,
        help="Porcentaje máximo aceptable de variación en precios"
    )
    
    stock_minimum = st.number_input(
        "Stock mínimo recomendado",
        min_value=1,
        max_value=100,
        value=5,
        help="Cantidad mínima de stock para no generar alerta"
    )
    
    st.markdown("---")
    st.subheader("🏪 Marketplace")
    marketplace = st.selectbox(
        "Selecciona el marketplace",
        ["MercadoLibre", "Amazon", "Shopify", "WooCommerce", "Otro"]
    )
    
    st.markdown("---")
    st.info("💡 **Tip**: Ajusta los umbrales según tu tipo de negocio")

# Área principal - Carga de archivos
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Datos del Marketplace")
    marketplace_file = st.file_uploader(
        "Sube el archivo del marketplace",
        type=['csv', 'xlsx', 'xls'],
        help="Archivo con los datos actuales de tus publicaciones"
    )
    
    if marketplace_file:
        st.success(f"✅ {marketplace_file.name} cargado")

with col2:
    st.subheader("💾 Base de Datos Local")
    database_file = st.file_uploader(
        "Sube tu base de datos",
        type=['csv', 'xlsx', 'xls'],
        help="Archivo con los datos de tu sistema interno"
    )
    
    if database_file:
        st.success(f"✅ {database_file.name} cargado")

# Función para cargar datos
@st.cache_data
def load_data(file):
    """Cargar archivo CSV o Excel"""
    try:
        if file.name.endswith('.csv'):
            return pd.read_csv(file)
        else:
            return pd.read_excel(file)
    except Exception as e:
        st.error(f"Error al cargar archivo: {str(e)}")
        return None

# Función de auditoría principal
def perform_audit(mp_df, db_df, price_threshold, stock_minimum):
    """Realizar auditoría comparativa"""
    results = {
        'summary': {},
        'price_issues': [],
        'stock_issues': [],
        'missing_products': [],
        'data_quality': {}
    }
    
    # Progreso
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 1. Análisis de productos
    status_text.text("Analizando productos...")
    progress_bar.progress(20)
    
    results['summary']['total_marketplace'] = len(mp_df)
    results['summary']['total_database'] = len(db_df)
    
    # Detectar columnas comunes
    common_cols = list(set(mp_df.columns) & set(db_df.columns))
    
    # 2. Análisis de precios
    status_text.text("Verificando precios...")
    progress_bar.progress(40)
    
    if 'price' in mp_df.columns and 'price' in db_df.columns and 'id' in mp_df.columns:
        merged = pd.merge(mp_df[['id', 'price']], db_df[['id', 'price']], 
                         on='id', suffixes=('_mp', '_db'), how='outer')
        
        # Calcular variaciones
        merged['variation'] = abs((merged['price_mp'] - merged['price_db']) / merged['price_db'] * 100)
        
        # Identificar problemas
        price_issues = merged[merged['variation'] > price_threshold].dropna()
        results['price_issues'] = price_issues.to_dict('records')
        results['summary']['price_inconsistencies'] = len(price_issues)
        
        # Productos faltantes
        missing = merged[merged['price_db'].isna()]
        results['missing_products'] = missing['id'].tolist()
        results['summary']['missing_in_db'] = len(missing)
    
    # 3. Análisis de stock
    status_text.text("Verificando niveles de stock...")
    progress_bar.progress(60)
    
    if 'stock' in mp_df.columns:
        low_stock = mp_df[mp_df['stock'] < stock_minimum]
        out_of_stock = mp_df[mp_df['stock'] == 0]
        
        results['stock_issues'] = low_stock.to_dict('records')
        results['summary']['low_stock'] = len(low_stock)
        results['summary']['out_of_stock'] = len(out_of_stock)
    
    # 4. Calidad de datos
    status_text.text("Evaluando calidad de datos...")
    progress_bar.progress(80)
    
    # Verificar valores nulos
    null_counts_mp = mp_df.isnull().sum()
    null_counts_db = db_df.isnull().sum()
    
    results['data_quality']['nulls_marketplace'] = null_counts_mp.to_dict()
    results['data_quality']['nulls_database'] = null_counts_db.to_dict()
    
    # Verificar duplicados
    results['data_quality']['duplicates_marketplace'] = mp_df.duplicated().sum()
    results['data_quality']['duplicates_database'] = db_df.duplicated().sum()
    
    # 5. Calcular score de salud
    status_text.text("Calculando puntuación final...")
    progress_bar.progress(100)
    
    # Score basado en problemas encontrados
    total_issues = (
        results['summary'].get('price_inconsistencies', 0) +
        results['summary'].get('low_stock', 0) +
        results['summary'].get('out_of_stock', 0) +
        results['summary'].get('missing_in_db', 0)
    )
    
    max_products = max(results['summary']['total_marketplace'], results['summary']['total_database'])
    if max_products > 0:
        health_score = max(0, 100 - (total_issues / max_products * 100))
    else:
        health_score = 100
    
    results['summary']['health_score'] = round(health_score, 1)
    
    time.sleep(0.5)  # Pausa dramática
    progress_bar.empty()
    status_text.empty()
    
    return results

# Botón de ejecutar auditoría
if marketplace_file and database_file:
    st.markdown("---")
    
    if st.button("🎯 Ejecutar Auditoría", type="primary", use_container_width=True):
        # Cargar datos
        with st.spinner("Cargando archivos..."):
            mp_df = load_data(marketplace_file)
            db_df = load_data(database_file)
        
        if mp_df is not None and db_df is not None:
            # Realizar auditoría
            results = perform_audit(mp_df, db_df, price_threshold, stock_minimum)
            st.session_state.results = results
            st.session_state.audit_completed = True
            st.success("✅ ¡Auditoría completada!")
            st.balloons()

# Mostrar resultados si la auditoría fue completada
if st.session_state.audit_completed and st.session_state.results:
    results = st.session_state.results
    
    st.markdown("---")
    st.header("📊 Resultados de la Auditoría")
    
    # Métricas principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        health_score = results['summary']['health_score']
        delta_color = "normal" if health_score > 80 else "inverse" if health_score > 60 else "off"
        st.metric(
            label="🏆 Puntuación de Salud",
            value=f"{health_score}%",
            delta=f"{'Excelente' if health_score > 80 else 'Regular' if health_score > 60 else 'Necesita atención'}",
            delta_color=delta_color
        )
    
    with col2:
        st.metric(
            label="📦 Productos Totales",
            value=results['summary']['total_marketplace'],
            delta=f"{results['summary']['total_database']} en BD"
        )
    
    with col3:
        st.metric(
            label="⚠️ Problemas de Precio",
            value=results['summary'].get('price_inconsistencies', 0),
            delta=f"Umbral: {price_threshold}%",
            delta_color="inverse" if results['summary'].get('price_inconsistencies', 0) > 0 else "normal"
        )
    
    with col4:
        st.metric(
            label="📉 Stock Bajo/Agotado",
            value=results['summary'].get('low_stock', 0) + results['summary'].get('out_of_stock', 0),
            delta=f"{results['summary'].get('out_of_stock', 0)} sin stock",
            delta_color="inverse" if results['summary'].get('out_of_stock', 0) > 0 else "normal"
        )
    
    # Tabs para diferentes vistas
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Visualizaciones", "⚠️ Problemas Detectados", "📋 Calidad de Datos", "💾 Exportar"])
    
    with tab1:
        st.subheader("Visualizaciones del Análisis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Gráfico de pie para distribución de problemas
            if any([results['summary'].get('price_inconsistencies', 0),
                   results['summary'].get('low_stock', 0),
                   results['summary'].get('out_of_stock', 0)]):
                
                fig_pie = go.Figure(data=[go.Pie(
                    labels=['Problemas de Precio', 'Stock Bajo', 'Sin Stock'],
                    values=[
                        results['summary'].get('price_inconsistencies', 0),
                        results['summary'].get('low_stock', 0),
                        results['summary'].get('out_of_stock', 0)
                    ],
                    hole=.3,
                    marker_colors=['#FF6B6B', '#FDD835', '#E53935']
                )])
                fig_pie.update_layout(
                    title="Distribución de Problemas",
                    height=350
                )
                st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            # Gauge chart para health score
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=results['summary']['health_score'],
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "Salud del Catálogo"},
                delta={'reference': 80},
                gauge={
                    'axis': {'range': [None, 100]},
                    'bar': {'color': "darkgreen" if results['summary']['health_score'] > 80 else "orange" if results['summary']['health_score'] > 60 else "red"},
                    'steps': [
                        {'range': [0, 60], 'color': "lightgray"},
                        {'range': [60, 80], 'color': "lightyellow"},
                        {'range': [80, 100], 'color': "lightgreen"}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': 90
                    }
                }
            ))
            fig_gauge.update_layout(height=350)
            st.plotly_chart(fig_gauge, use_container_width=True)
    
    with tab2:
        st.subheader("Problemas Detectados")
        
        # Problemas de precio
        if results['price_issues']:
            st.warning(f"⚠️ Se encontraron {len(results['price_issues'])} productos con variación de precio superior al {price_threshold}%")
            
            price_df = pd.DataFrame(results['price_issues'])
            if not price_df.empty:
                # Mostrar solo las columnas relevantes
                display_cols = ['id', 'price_mp', 'price_db', 'variation']
                if all(col in price_df.columns for col in display_cols):
                    price_df['variation'] = price_df['variation'].round(2)
                    st.dataframe(
                        price_df[display_cols].head(20),
                        use_container_width=True,
                        hide_index=True
                    )
        
        # Problemas de stock
        if results['stock_issues']:
            st.error(f"📦 Se encontraron {len(results['stock_issues'])} productos con stock bajo")
            
            stock_df = pd.DataFrame(results['stock_issues'])
            if not stock_df.empty and 'stock' in stock_df.columns:
                # Crear visualización de stock
                fig_stock = px.bar(
                    stock_df.head(20),
                    x='id' if 'id' in stock_df.columns else stock_df.index,
                    y='stock',
                    title="Productos con Stock Bajo",
                    color='stock',
                    color_continuous_scale=['red', 'yellow', 'green']
                )
                fig_stock.add_hline(y=stock_minimum, line_dash="dash", line_color="red",
                                   annotation_text=f"Stock mínimo: {stock_minimum}")
                st.plotly_chart(fig_stock, use_container_width=True)
        
        # Productos faltantes
        if results['missing_products']:
            st.info(f"🔍 Se encontraron {len(results['missing_products'])} productos en el marketplace que no están en la base de datos")
            with st.expander("Ver productos faltantes"):
                st.write(results['missing_products'][:50])  # Mostrar primeros 50
    
    with tab3:
        st.subheader("Análisis de Calidad de Datos")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**📊 Marketplace**")
            st.write(f"Registros duplicados: {results['data_quality'].get('duplicates_marketplace', 0)}")
            
            nulls_mp = results['data_quality'].get('nulls_marketplace', {})
            if nulls_mp:
                null_df = pd.DataFrame(list(nulls_mp.items()), columns=['Columna', 'Valores Nulos'])
                null_df = null_df[null_df['Valores Nulos'] > 0]
                if not null_df.empty:
                    st.dataframe(null_df, use_container_width=True, hide_index=True)
        
        with col2:
            st.write("**💾 Base de Datos**")
            st.write(f"Registros duplicados: {results['data_quality'].get('duplicates_database', 0)}")
            
            nulls_db = results['data_quality'].get('nulls_database', {})
            if nulls_db:
                null_df = pd.DataFrame(list(nulls_db.items()), columns=['Columna', 'Valores Nulos'])
                null_df = null_df[null_df['Valores Nulos'] > 0]
                if not null_df.empty:
                    st.dataframe(null_df, use_container_width=True, hide_index=True)
    
    with tab4:
        st.subheader("Exportar Resultados")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Exportar como Excel
            if st.button("📊 Descargar Excel", use_container_width=True):
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Resumen
                    summary_df = pd.DataFrame([results['summary']])
                    summary_df.to_excel(writer, sheet_name='Resumen', index=False)
                    
                    # Problemas de precio
                    if results['price_issues']:
                        price_df = pd.DataFrame(results['price_issues'])
                        price_df.to_excel(writer, sheet_name='Problemas_Precio', index=False)
                    
                    # Problemas de stock
                    if results['stock_issues']:
                        stock_df = pd.DataFrame(results['stock_issues'])
                        stock_df.to_excel(writer, sheet_name='Problemas_Stock', index=False)
                
                output.seek(0)
                st.download_button(
                    label="💾 Descargar Excel",
                    data=output,
                    file_name=f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        with col2:
            # Exportar como CSV
            if st.button("📄 Descargar CSV", use_container_width=True):
                summary_df = pd.DataFrame([results['summary']])
                csv = summary_df.to_csv(index=False)
                st.download_button(
                    label="💾 Descargar CSV",
                    data=csv,
                    file_name=f"audit_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col3:
            # Generar reporte de recomendaciones
            if st.button("📝 Generar Recomendaciones", use_container_width=True):
                recommendations = []
                
                if results['summary'].get('out_of_stock', 0) > 0:
                    recommendations.append(f"🔴 URGENTE: Reponer {results['summary']['out_of_stock']} productos sin stock")
                
                if results['summary'].get('price_inconsistencies', 0) > 5:
                    recommendations.append(f"🟡 IMPORTANTE: Revisar {results['summary']['price_inconsistencies']} productos con variación de precio")
                
                if results['summary'].get('missing_in_db', 0) > 0:
                    recommendations.append(f"🟢 RECOMENDADO: Agregar {results['summary']['missing_in_db']} productos a la base de datos")
                
                if results['summary']['health_score'] < 60:
                    recommendations.append("🔴 CRÍTICO: La salud del catálogo requiere atención inmediata")
                
                if recommendations:
                    st.write("### 📋 Recomendaciones de Acción:")
                    for rec in recommendations:
                        st.write(rec)
                else:
                    st.success("✅ ¡Tu catálogo está en excelente estado!")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
        <p>Desarrollado con ❤️ usando Streamlit | 
        <a href='https://github.com/tu-usuario/ecommerce-auditor' target='_blank'>GitHub</a> | 
        Última actualización: {}</p>
    </div>
    """.format(datetime.now().strftime("%Y-%m-%d")),
    unsafe_allow_html=True
)

# Sidebar con información adicional
with st.sidebar:
    st.markdown("---")
    st.subheader("📚 Ayuda")
    with st.expander("¿Cómo usar esta herramienta?"):
        st.write("""
        1. **Carga los archivos**: Sube el CSV/Excel del marketplace y tu base de datos
        2. **Ajusta los umbrales**: Configura los parámetros según tu negocio
        3. **Ejecuta la auditoría**: Click en el botón para analizar
        4. **Revisa los resultados**: Explora las visualizaciones y problemas
        5. **Exporta el reporte**: Descarga los resultados en Excel o CSV
        """)
    
    with st.expander("Formatos aceptados"):
        st.write("""
        - **CSV**: Separado por comas
        - **Excel**: .xlsx, .xls
        
        **Columnas recomendadas**:
        - `id`: Identificador del producto
        - `price`: Precio del producto
        - `stock`: Cantidad en stock
        - `title`: Nombre del producto
        - `status`: Estado de la publicación
        """)
    
    st.markdown("---")
    st.info("💡 **Tip del día**: Ejecuta auditorías semanalmente para mantener tu catálogo optimizado")
