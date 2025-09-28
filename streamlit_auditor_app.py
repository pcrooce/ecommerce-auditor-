import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import time
import re

# Configuración de la página
st.set_page_config(
    page_title="Auditor de Publicaciones - Sistema Bancario",
    page_icon="🏦",
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
    .bank-header {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

# Título principal
st.markdown("""
    <div class="bank-header">
        <h1 style="text-align: center; color: white;">🏦 Sistema de Auditoría de Publicaciones</h1>
        <p style="text-align: center; color: white; margin-top: 10px;">
            Control y Validación de Catálogos para Tiendas Bancarias y Retail
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

# CONFIGURACIÓN DE TIENDAS Y FORMATOS
TIENDAS_CONFIG = {
    "APER": {
        "tiendas": ["ICBC", "Supervielle", "Galicia"],
        "formato": "APER",
        "columnas_requeridas": {
            'SKU padre': 'sku_padre',
            'SKU': 'sku',
            'Titulo de publicacion': 'titulo',
            'Precio': 'precio',
            'Stock': 'stock',
            'Pausar': 'pausar',
            'Cuotas': 'cuotas',
            'Cuotas sin interes': 'cuotas_sin_interes'
        },
        "validaciones": {
            "precio_formato": "sin_decimales",  # Los precios van sin decimales
            "sku_formato": "numerico",
            "pausar_valores": ["SI", "NO"],
            "titulo_max_length": 60
        }
    },
    "Ciudad": {
        "tiendas": ["Tienda Ciudad"],
        "formato": "Ciudad",
        "columnas_requeridas": {
            'Identificador de URL': 'url_id',
            'Nombre': 'nombre',
            'Identificador de producto de item': 'product_item_id',
            'Precio': 'precio',
            'Precio de lista': 'precio_lista',
            'Disponibilidad': 'disponibilidad',
            'Marca': 'marca'
        },
        "validaciones": {
            "precio_formato": "con_decimales",
            "disponibilidad_valores": ["in stock", "out of stock"],
            "url_formato": "alphanumerico_guiones"
        }
    },
    "BNA": {
        "tiendas": ["Tienda BNA"],
        "formato": "PorDefinir",
        "columnas_requeridas": {},
        "validaciones": {}
    },
    "Retail": {
        "tiendas": ["Fravega", "Megatone"],
        "formato": "PorDefinir",
        "columnas_requeridas": {},
        "validaciones": {}
    },
    "Bapro": {
        "tiendas": ["Banco Provincia (Bapro)"],
        "formato": "PorDefinir",
        "columnas_requeridas": {},
        "validaciones": {}
    },
    "OnCity": {
        "tiendas": ["OnCity"],
        "formato": "PorDefinir",
        "columnas_requeridas": {},
        "validaciones": {}
    }
}

# Lista plana de todas las tiendas
TODAS_LAS_TIENDAS = []
for config in TIENDAS_CONFIG.values():
    TODAS_LAS_TIENDAS.extend(config["tiendas"])

# Sidebar para configuración
with st.sidebar:
    st.header("⚙️ Configuración de Auditoría")
    
    # Selección de tienda
    st.subheader("🏪 Seleccionar Tienda")
    selected_store = st.selectbox(
        "Tienda a auditar:",
        TODAS_LAS_TIENDAS,
        help="Selecciona la tienda que deseas auditar"
    )
    
    st.session_state.selected_store = selected_store
    
    # Identificar formato de la tienda seleccionada
    formato_tienda = None
    config_tienda = None
    for formato, config in TIENDAS_CONFIG.items():
        if selected_store in config["tiendas"]:
            formato_tienda = config["formato"]
            config_tienda = config
            break
    
    # Mostrar información del formato
    if formato_tienda:
        st.markdown("---")
        st.info(f"📋 **Formato:** {formato_tienda}")
        
        if formato_tienda == "APER":
            st.success("✅ Formato APER configurado")
            st.caption("Columnas: SKU padre, SKU, Título, Precio (sin decimales), etc.")
        elif formato_tienda == "Ciudad":
            st.success("✅ Formato Ciudad configurado")
            st.caption("Columnas: URL, Nombre, Product Item ID, Precio (con decimales), etc.")
        else:
            st.warning("⚠️ Formato pendiente de configuración")
            st.caption("Esta tienda aún no tiene formato definido")
    
    st.markdown("---")
    
    # Parámetros de auditoría
    st.subheader("📊 Parámetros de Control")
    
    price_threshold = st.slider(
        "Variación de precio máxima (%)",
        min_value=1,
        max_value=20,
        value=5,
        help="Diferencia máxima aceptable"
    )
    
    stock_minimum = st.number_input(
        "Stock mínimo recomendado",
        min_value=1,
        max_value=100,
        value=5,
        help="Cantidad mínima antes de alerta"
    )
    
    st.markdown("---")
    
    # Información de ayuda específica por formato
    st.subheader("📚 Formato Esperado")
    
    if formato_tienda == "APER":
        with st.expander("Ver formato APER"):
            st.write("""
            **Columnas requeridas:**
            - `SKU padre`: Código padre del producto
            - `SKU`: Código único del producto
            - `Titulo de publicacion`: Max 60 caracteres
            - `Precio`: Sin decimales (ej: 15000)
            - `Stock`: Cantidad disponible
            - `Pausar`: SI/NO
            - `Cuotas`: Cantidad de cuotas
            - `Cuotas sin interes`: Cantidad
            """)
    
    elif formato_tienda == "Ciudad":
        with st.expander("Ver formato Ciudad"):
            st.write("""
            **Columnas requeridas:**
            - `Identificador de URL`: Slug del producto
            - `Nombre`: Nombre del producto
            - `Identificador de producto de item`: ID único
            - `Precio`: Con decimales (ej: 15000.00)
            - `Precio de lista`: Precio sin descuento
            - `Disponibilidad`: "in stock" / "out of stock"
            - `Marca`: Marca del producto
            """)
    
    st.markdown("---")
    st.success(f"🏦 **Auditando:** {selected_store}")

# Funciones específicas para cada formato
def validar_formato_aper(df):
    """Validar formato APER (ICBC, Supervielle, Galicia)"""
    errores = []
    advertencias = []
    
    # Verificar columnas requeridas
    columnas_requeridas = ['SKU padre', 'SKU', 'Titulo de publicacion', 'Precio', 'Stock', 'Pausar']
    columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]
    
    if columnas_faltantes:
        errores.append(f"Columnas faltantes: {', '.join(columnas_faltantes)}")
    
    # Validar formato de precio (sin decimales)
    if 'Precio' in df.columns:
        precios_con_decimal = df[df['Precio'].astype(str).str.contains(r'\.')]['SKU'].tolist()
        if precios_con_decimal:
            advertencias.append(f"Precios con decimales detectados (deben ser enteros): {len(precios_con_decimal)} productos")
    
    # Validar valores de Pausar
    if 'Pausar' in df.columns:
        valores_invalidos = df[~df['Pausar'].isin(['SI', 'NO'])]['SKU'].tolist()
        if valores_invalidos:
            errores.append(f"Valores inválidos en columna 'Pausar': {len(valores_invalidos)} productos")
    
    # Validar longitud de títulos
    if 'Titulo de publicacion' in df.columns:
        titulos_largos = df[df['Titulo de publicacion'].str.len() > 60]['SKU'].tolist()
        if titulos_largos:
            advertencias.append(f"Títulos muy largos (>60 caracteres): {len(titulos_largos)} productos")
    
    return errores, advertencias

def validar_formato_ciudad(df):
    """Validar formato Ciudad"""
    errores = []
    advertencias = []
    
    # Verificar columnas requeridas
    columnas_requeridas = ['Identificador de URL', 'Nombre', 'Precio', 'Disponibilidad']
    columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]
    
    if columnas_faltantes:
        errores.append(f"Columnas faltantes: {', '.join(columnas_faltantes)}")
    
    # Validar disponibilidad
    if 'Disponibilidad' in df.columns:
        valores_validos = ['in stock', 'out of stock']
        valores_invalidos = df[~df['Disponibilidad'].isin(valores_validos)]
        if not valores_invalidos.empty:
            errores.append(f"Valores inválidos en 'Disponibilidad': {len(valores_invalidos)} productos")
    
    # Validar formato de URL
    if 'Identificador de URL' in df.columns:
        urls_invalidas = df[df['Identificador de URL'].str.contains(r'[^a-z0-9\-]', na=False)]
        if not urls_invalidas.empty:
            advertencias.append(f"URLs con caracteres especiales: {len(urls_invalidas)} productos")
    
    return errores, advertencias

def perform_audit_bancaria(store_df, db_df, store_name, formato_tienda, config_tienda, price_threshold, stock_minimum):
    """Realizar auditoría específica para tiendas bancarias"""
    results = {
        'store_name': store_name,
        'formato': formato_tienda,
        'audit_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'summary': {},
        'validacion_formato': {'errores': [], 'advertencias': []},
        'price_issues': [],
        'stock_issues': [],
        'missing_products': [],
        'format_issues': [],
        'recommendations': []
    }
    
    # Barra de progreso
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 1. Validación de formato según tienda
    status_text.text(f"Validando formato {formato_tienda}...")
    progress_bar.progress(20)
    
    if formato_tienda == "APER":
        errores, advertencias = validar_formato_aper(store_df)
        results['validacion_formato']['errores'] = errores
        results['validacion_formato']['advertencias'] = advertencias
    elif formato_tienda == "Ciudad":
        errores, advertencias = validar_formato_ciudad(store_df)
        results['validacion_formato']['errores'] = errores
        results['validacion_formato']['advertencias'] = advertencias
    
    # 2. Análisis general
    status_text.text(f"Analizando catálogo de {store_name}...")
    progress_bar.progress(40)
    
    results['summary']['total_productos_tienda'] = len(store_df)
    results['summary']['total_productos_bd'] = len(db_df)
    
    # 3. Comparación con base de datos (adaptado por formato)
    status_text.text("Comparando con base de datos maestra...")
    progress_bar.progress(60)
    
    # Identificar columna de ID según formato
    if formato_tienda == "APER":
        id_col_tienda = 'SKU'
        price_col_tienda = 'Precio'
        stock_col_tienda = 'Stock'
    elif formato_tienda == "Ciudad":
        id_col_tienda = 'Identificador de producto de item'
        price_col_tienda = 'Precio'
        stock_col_tienda = None  # Ciudad usa "Disponibilidad" en lugar de stock numérico
    else:
        # Formato genérico
        id_col_tienda = next((col for col in store_df.columns if 'sku' in col.lower() or 'id' in col.lower()), None)
        price_col_tienda = next((col for col in store_df.columns if 'precio' in col.lower() or 'price' in col.lower()), None)
        stock_col_tienda = next((col for col in store_df.columns if 'stock' in col.lower()), None)
    
    # Buscar columna equivalente en BD
    id_col_bd = next((col for col in db_df.columns if 'sku' in col.lower() or 'id' in col.lower()), None)
    price_col_bd = next((col for col in db_df.columns if 'precio' in col.lower() or 'price' in col.lower()), None)
    
    if id_col_tienda and id_col_bd and id_col_tienda in store_df.columns and id_col_bd in db_df.columns:
        # Merge de dataframes
        merged = pd.merge(
            store_df[[col for col in [id_col_tienda, price_col_tienda, stock_col_tienda] if col and col in store_df.columns]], 
            db_df[[col for col in [id_col_bd, price_col_bd] if col and col in db_df.columns]], 
            left_on=id_col_tienda,
            right_on=id_col_bd,
            how='outer',
            indicator=True
        )
        
        # Productos no encontrados
        only_in_store = merged[merged['_merge'] == 'left_only']
        only_in_db = merged[merged['_merge'] == 'right_only']
        
        results['summary']['productos_no_en_bd'] = len(only_in_store)
        results['summary']['productos_no_publicados'] = len(only_in_db)
        results['missing_products'] = only_in_store[id_col_tienda].head(100).tolist()
        
        # Comparación de precios
        if price_col_tienda and price_col_bd:
            both = merged[merged['_merge'] == 'both'].copy()
            
            # Convertir precios según formato
            if formato_tienda == "APER":
                # APER usa precios sin decimales
                both[price_col_tienda] = pd.to_numeric(both[price_col_tienda], errors='coerce')
                both[price_col_bd] = pd.to_numeric(both[price_col_bd], errors='coerce')
            elif formato_tienda == "Ciudad":
                # Ciudad usa precios con decimales
                both[price_col_tienda] = pd.to_numeric(both[price_col_tienda], errors='coerce')
                both[price_col_bd] = pd.to_numeric(both[price_col_bd], errors='coerce')
            
            # Calcular variación
            both['variacion_%'] = ((both[price_col_tienda] - both[price_col_bd]) / both[price_col_bd] * 100).abs()
            
            # Identificar problemas
            price_issues = both[both['variacion_%'] > price_threshold].copy()
            if not price_issues.empty:
                price_issues['diferencia_$'] = price_issues[price_col_tienda] - price_issues[price_col_bd]
                results['price_issues'] = price_issues[[id_col_tienda, price_col_tienda, price_col_bd, 'variacion_%', 'diferencia_$']].head(100).to_dict('records')
            
            results['summary']['productos_con_precio_incorrecto'] = len(price_issues)
    
    # 4. Análisis específico por formato
    status_text.text(f"Aplicando validaciones específicas de {formato_tienda}...")
    progress_bar.progress(80)
    
    if formato_tienda == "APER":
        # Verificar productos pausados
        if 'Pausar' in store_df.columns:
            pausados = store_df[store_df['Pausar'] == 'SI']
            results['summary']['productos_pausados'] = len(pausados)
            
            if len(pausados) > 0:
                results['recommendations'].append({
                    'prioridad': 'MEDIA',
                    'tipo': 'Estado',
                    'accion': f"Revisar {len(pausados)} productos pausados en {store_name}"
                })
        
        # Verificar stock
        if stock_col_tienda and stock_col_tienda in store_df.columns:
            sin_stock = store_df[store_df[stock_col_tienda] == 0]
            stock_bajo = store_df[store_df[stock_col_tienda] < stock_minimum]
            
            results['summary']['productos_sin_stock'] = len(sin_stock)
            results['summary']['productos_stock_bajo'] = len(stock_bajo)
            
            if len(sin_stock) > 0:
                results['stock_issues'] = sin_stock[id_col_tienda].head(50).tolist()
                results['recommendations'].append({
                    'prioridad': 'ALTA',
                    'tipo': 'Stock',
                    'accion': f"URGENTE: Reponer {len(sin_stock)} productos sin stock"
                })
    
    elif formato_tienda == "Ciudad":
        # Verificar disponibilidad
        if 'Disponibilidad' in store_df.columns:
            sin_stock = store_df[store_df['Disponibilidad'] == 'out of stock']
            results['summary']['productos_sin_stock'] = len(sin_stock)
            
            if len(sin_stock) > 0:
                results['recommendations'].append({
                    'prioridad': 'ALTA',
                    'tipo': 'Disponibilidad',
                    'accion': f"Actualizar {len(sin_stock)} productos marcados como 'out of stock'"
                })
    
    # 5. Generar recomendaciones finales
    status_text.text("Generando recomendaciones...")
    progress_bar.progress(90)
    
    # Agregar recomendaciones basadas en errores de formato
    if results['validacion_formato']['errores']:
        results['recommendations'].insert(0, {
            'prioridad': 'CRITICA',
            'tipo': 'Formato',
            'accion': f"CORREGIR ERRORES DE FORMATO: {len(results['validacion_formato']['errores'])} problemas críticos detectados"
        })
    
    # Calcular health score
    total_productos = results['summary'].get('total_productos_tienda', 1)
    problemas = (
        len(results['validacion_formato']['errores']) * 10 +  # Errores de formato son críticos
        results['summary'].get('productos_sin_stock', 0) * 2 +
        results['summary'].get('productos_con_precio_incorrecto', 0) +
        len(results['validacion_formato']['advertencias']) * 0.5
    )
    
    health_score = max(0, 100 - (problemas / total_productos * 100))
    results['summary']['health_score'] = round(health_score, 1)
    
    progress_bar.progress(100)
    time.sleep(0.5)
    progress_bar.empty()
    status_text.empty()
    
    return results

# Área principal
st.header(f"📋 Auditoría de {selected_store}")

# Información del formato
if formato_tienda and formato_tienda != "PorDefinir":
    st.info(f"📐 Esta tienda utiliza el formato **{formato_tienda}**")
elif formato_tienda == "PorDefinir":
    st.warning("⚠️ Esta tienda aún no tiene un formato definido. La auditoría funcionará en modo genérico.")

# Tabs principales
tab1, tab2, tab3, tab4 = st.tabs(["📁 Carga de Datos", "📊 Resultados", "📈 Validación de Formato", "📚 Documentación"])

with tab1:
    st.markdown("### Cargar archivos para auditoría")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**📊 Archivo de {selected_store}**")
        store_file = st.file_uploader(
            f"Excel con publicaciones actuales",
            type=['xlsx', 'xls', 'csv'],
            key="store_file",
            help=f"Archivo en formato {formato_tienda if formato_tienda != 'PorDefinir' else 'estándar'}"
        )
        
        if store_file:
            try:
                if store_file.name.endswith('.csv'):
                    df_preview = pd.read_csv(store_file)
                else:
                    df_preview = pd.read_excel(store_file)
                
                st.success(f"✅ {store_file.name} cargado - {len(df_preview)} filas")
                
                # Vista previa con información de columnas
                with st.expander("Ver estructura del archivo"):
                    col_info = pd.DataFrame({
                        'Columna': df_preview.columns,
                        'Tipo de dato': df_preview.dtypes.astype(str),
                        'Valores únicos': [df_preview[col].nunique() for col in df_preview.columns],
                        'Valores nulos': [df_preview[col].isnull().sum() for col in df_preview.columns]
                    })
                    st.dataframe(col_info, use_container_width=True)
                    
                    st.write("**Primeras 5 filas:**")
                    st.dataframe(df_preview.head(), use_container_width=True)
                    
            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")
    
    with col2:
        st.markdown("**💾 Base de Datos Maestra (Auditoria General.xlsx)**")
        database_file = st.file_uploader(
            "Excel con información maestra",
            type=['xlsx', 'xls'],
            key="database_file",
            help="Archivo 'Auditoria General.xlsx' con todos los productos"
        )
        
        if database_file:
            try:
                df_bd = pd.read_excel(database_file)
                st.success(f"✅ {database_file.name} cargado - {len(df_bd)} productos")
                
                with st.expander("Ver estructura de BD"):
                    st.write("**Columnas disponibles:**")
                    st.write(", ".join(df_bd.columns.tolist()))
                    st.write(f"\n**Total de productos:** {len(df_bd)}")
                    
            except Exception as e:
                st.error(f"Error al leer la base de datos: {str(e)}")

# Botón de ejecutar auditoría
with tab1:
    if store_file and database_file:
        st.markdown("---")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button(f"🔍 Ejecutar Auditoría de {selected_store}", 
                        type="primary", 
                        use_container_width=True):
                
                with st.spinner(f"Procesando auditoría de {selected_store}..."):
                    try:
                        # Cargar archivos
                        if store_file.name.endswith('.csv'):
                            store_df = pd.read_csv(store_file)
                        else:
                            store_df = pd.read_excel(store_file)
                        
                        db_df = pd.read_excel(database_file)
                        
                        # Realizar auditoría
                        results = perform_audit_bancaria(
                            store_df, 
                            db_df, 
                            selected_store,
                            formato_tienda,
                            config_tienda,
                            price_threshold, 
                            stock_minimum
                        )
                        
                        st.session_state.results = results
                        st.session_state.audit_completed = True
                        st.success(f"✅ Auditoría completada exitosamente")
                        st.balloons()
                        
                    except Exception as e:
                        st.error(f"❌ Error durante la auditoría: {str(e)}")
                        st.exception(e)

# Tab de resultados
with tab2:
    if st.session_state.audit_completed and st.session_state.results:
        results = st.session_state.results
        
        # Header
        st.markdown(f"""
        ### 📊 Resultados de Auditoría
        **Tienda:** {results['store_name']} | **Formato:** {results['formato']} | **Fecha:** {results['audit_date']}
        """)
        
        # Métricas principales
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
            errores_formato = len(results['validacion_formato'].get('errores', []))
            color = "🔴" if errores_formato > 0 else "🟢"
            st.metric(
                label=f"{color} Errores de Formato",
                value=errores_formato,
                delta="Crítico" if errores_formato > 0 else "OK"
            )
        
        with col4:
            sin_stock = results['summary'].get('productos_sin_stock', 0)
            color = "🔴" if sin_stock > 0 else "🟢"
            st.metric(
                label=f"{color} Sin Stock",
                value=sin_stock,
                delta="Reponer" if sin_stock > 0 else "OK"
            )
        
        # Mostrar errores y advertencias de formato
        if results['validacion_formato']['errores'] or results['validacion_formato']['advertencias']:
            st.markdown("---")
            st.subheader("⚠️ Validación de Formato")
            
            if results['validacion_formato']['errores']:
                st.error("**Errores Críticos (corregir antes de publicar):**")
                for error in results['validacion_formato']['errores']:
                    st.write(f"• {error}")
            
            if results['validacion_formato']['advertencias']:
                st.warning("**Advertencias (revisar):**")
                for advertencia in results['validacion_formato']['advertencias']:
                    st.write(f"• {advertencia}")
        
        # Recomendaciones
        if results.get('recommendations'):
            st.markdown("---")
            st.subheader("💡 Recomendaciones de Acción")
            
            for rec in sorted(results['recommendations'], 
                           key=lambda x: {'CRITICA': 0, 'ALTA': 1, 'MEDIA': 2, 'BAJA': 3}.get(x['prioridad'], 4)):
                if rec['prioridad'] == 'CRITICA':
                    st.error(f"🔴 **{rec['prioridad']}** - {rec['tipo']}: {rec['accion']}")
                elif rec['prioridad'] == 'ALTA':
                    st.error(f"🔴 **{rec['prioridad']}** - {rec['tipo']}: {rec['accion']}")
                elif rec['prioridad'] == 'MEDIA':
                    st.warning(f"🟡 **{rec['prioridad']}** - {rec['tipo']}: {rec['accion']}")
                else:
                    st.info(f"🔵 **{rec['prioridad']}** - {rec['tipo']}: {rec['accion']}")
        
        # Detalles de problemas
        st.markdown("---")
        
        # Tabs para diferentes análisis
        analysis_tabs = st.tabs(["💰 Precios", "📦 Stock", "📋 Productos Faltantes"])
        
        with analysis_tabs[0]:
            st.subheader("Análisis de Precios")
            if results.get('price_issues'):
                st.warning(f"⚠️ {len(results['price_issues'])} productos con variación superior al {price_threshold}%")
                
                price_df = pd.DataFrame(results['price_issues'])
                st.dataframe(price_df, use_container_width=True, hide_index=True)
            else:
                st.success("✅ Todos los precios están dentro del rango aceptable")
        
        with analysis_tabs[1]:
            st.subheader("Análisis de Stock")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Sin Stock", results['summary'].get('productos_sin_stock', 0))
            with col2:
                st.metric("Stock Bajo", results['summary'].get('productos_stock_bajo', 0))
            
            if results.get('stock_issues'):
                st.error(f"Productos sin stock (primeros 50):")
                st.write(results['stock_issues'][:50])
        
        with analysis_tabs[2]:
            st.subheader("Productos No Encontrados")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("No están en BD", results['summary'].get('productos_no_en_bd', 0))
            with col2:
                st.metric("No publicados", results['summary'].get('productos_no_publicados', 0))
            
            if results.get('missing_products'):
                st.info(f"Productos en {selected_store} que no están en la BD (primeros 20):")
                st.write(results['missing_products'][:20])
        
        # Exportación
        st.markdown("---")
        st.subheader("📥 Exportar Resultados")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Generar Excel completo
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Resumen
                summary_df = pd.DataFrame([results['summary']])
                summary_df.to_excel(writer, sheet_name='Resumen', index=False)
                
                # Errores de formato
                if results['validacion_formato']['errores'] or results['validacion_formato']['advertencias']:
                    formato_df = pd.DataFrame({
                        'Tipo': ['Error'] * len(results['validacion_formato']['errores']) + 
                                ['Advertencia'] * len(results['validacion_formato']['advertencias']),
                        'Descripción': results['validacion_formato']['errores'] + 
                                      results['validacion_formato']['advertencias']
                    })
                    formato_df.to_excel(writer, sheet_name='Validación_Formato', index=False)
                
                # Problemas de precio
                if results.get('price_issues'):
                    price_df = pd.DataFrame(results['price_issues'])
                    price_df.to_excel(writer, sheet_name='Problemas_Precio', index=False)
                
                # Recomendaciones
                if results.get('recommendations'):
                    rec_df = pd.DataFrame(results['recommendations'])
                    rec_df.to_excel(writer, sheet_name='Recomendaciones', index=False)
            
            output.seek(0)
            
            st.download_button(
                label=f"📊 Descargar Reporte Excel",
                data=output,
                file_name=f"Auditoria_{selected_store.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col2:
            if st.button("🔄 Nueva Auditoría", use_container_width=True):
                st.session_state.audit_completed = False
                st.session_state.results = None
                st.rerun()

# Tab de validación de formato
with tab3:
    st.subheader("📋 Validación de Formato")
    
    if formato_tienda == "APER":
        st.info("📐 Formato APER - Usado por ICBC, Supervielle y Galicia")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**✅ Formato Correcto:**")
            st.code("""
SKU padre | SKU    | Titulo de publicacion | Precio | Stock | Pausar
1001      | 1001-A | Producto ejemplo      | 15000  | 10    | NO
1001      | 1001-B | Producto ejemplo XL   | 18000  | 5     | NO
            """)
        
        with col2:
            st.markdown("**❌ Errores Comunes:**")
            st.write("""
            • Precio con decimales (15000.00)
            • Pausar con valores incorrectos (si/no en minúsculas)
            • Títulos > 60 caracteres
            • SKU no numérico
            """)
    
    elif formato_tienda == "Ciudad":
        st.info("📐 Formato Ciudad - Tienda Ciudad")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**✅ Formato Correcto:**")
            st.code("""
Identificador de URL | Nombre        | Precio   | Disponibilidad
producto-ejemplo     | Producto Test | 15000.00 | in stock
producto-ejemplo-xl  | Producto XL   | 18000.00 | out of stock
            """)
        
        with col2:
            st.markdown("**❌ Errores Comunes:**")
            st.write("""
            • URL con espacios o caracteres especiales
            • Disponibilidad != "in stock" / "out of stock"
            • Precio sin decimales
            • Falta columna Marca
            """)
    
    else:
        st.warning("⚠️ Esta tienda aún no tiene un formato definido")
        st.info("""
        **Para configurar el formato de esta tienda necesitamos:**
        1. Un archivo Excel de ejemplo de la tienda
        2. Identificar las columnas requeridas
        3. Definir las validaciones necesarias
        """)

# Tab de documentación
with tab4:
    st.subheader("📚 Documentación del Sistema")
    
    # Estado de cada tienda
    st.markdown("### 🏦 Estado de Configuración por Tienda")
    
    status_data = []
    for formato, config in TIENDAS_CONFIG.items():
        for tienda in config["tiendas"]:
            status_data.append({
                "Tienda": tienda,
                "Formato": config["formato"],
                "Estado": "✅ Configurado" if config["formato"] != "PorDefinir" else "⏳ Pendiente",
                "Validaciones": len(config.get("validaciones", {}))
            })
    
    status_df = pd.DataFrame(status_data)
    st.dataframe(status_df, use_container_width=True, hide_index=True)
    
    # Información detallada
    with st.expander("🔍 Ver detalles de formatos configurados"):
        st.markdown("""
        ### Formato APER (ICBC, Supervielle, Galicia)
        
        **Columnas requeridas:**
        - `SKU padre`: Agrupa variantes del mismo producto
        - `SKU`: Identificador único
        - `Titulo de publicacion`: Máximo 60 caracteres
        - `Precio`: Sin decimales (15000 en lugar de 15000.00)
        - `Stock`: Cantidad disponible
        - `Pausar`: SI/NO en mayúsculas
        - `Cuotas`: Número de cuotas disponibles
        - `Cuotas sin interes`: Número de cuotas sin interés
        
        **Validaciones aplicadas:**
        - Precio debe ser entero
        - Pausar solo acepta SI/NO
        - Título máximo 60 caracteres
        - SKU debe ser numérico
        
        ---
        
        ### Formato Ciudad
        
        **Columnas requeridas:**
        - `Identificador de URL`: Slug del producto (solo letras, números y guiones)
        - `Nombre`: Nombre del producto
        - `Identificador de producto de item`: ID único
        - `Precio`: Con decimales (15000.00)
        - `Precio de lista`: Precio sin descuento
        - `Disponibilidad`: "in stock" o "out of stock"
        - `Marca`: Marca del producto
        
        **Validaciones aplicadas:**
        - URL sin caracteres especiales
        - Disponibilidad valores específicos
        - Precios con formato decimal
        """)
    
    # Guía de uso
    with st.expander("📖 Guía de Uso"):
        st.markdown("""
        ### Cómo realizar una auditoría:
        
        1. **Seleccionar la tienda** en el sidebar
        2. **Cargar el archivo de la tienda** (formato específico según tienda)
        3. **Cargar Auditoria General.xlsx** (base de datos maestra)
        4. **Ejecutar la auditoría**
        5. **Revisar resultados** y validaciones de formato
        6. **Exportar el reporte** en Excel
        
        ### Interpretación de resultados:
        
        - 🟢 **Health Score > 80%**: Catálogo en buen estado
        - 🟡 **Health Score 60-80%**: Requiere atención
        - 🔴 **Health Score < 60%**: Crítico, acción inmediata
        
        ### Prioridad de acciones:
        
        1. **CRÍTICA**: Errores de formato (impiden publicación)
        2. **ALTA**: Productos sin stock, precios incorrectos
        3. **MEDIA**: Productos pausados, faltantes en BD
        4. **BAJA**: Advertencias, optimizaciones
        """)
    
    # Roadmap
    with st.expander("🚀 Roadmap - Próximas Funcionalidades"):
        st.markdown("""
        ### En desarrollo:
        
        - [ ] Configuración formato **Tienda BNA**
        - [ ] Configuración formato **Fravega**
        - [ ] Configuración formato **Megatone**
        - [ ] Configuración formato **Banco Provincia (Bapro)**
        - [ ] Configuración formato **OnCity** (cuando esté activa)
        
        ### Funcionalidades futuras:
        
        - [ ] Generación automática de archivos para carga
        - [ ] Histórico de auditorías
        - [ ] Comparación entre períodos
        - [ ] Dashboard con métricas en tiempo real
        - [ ] Alertas automáticas por email
        - [ ] API para integración con sistemas
        """)

# Footer
st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: gray; padding: 20px;'>
        <p>🏦 Sistema de Auditoría Bancaria v2.0 | 
        Formatos configurados: APER (ICBC, Supervielle, Galicia) y Ciudad |
        {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
    </div>
    """,
    unsafe_allow_html=True
)
