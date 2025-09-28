import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import time
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

# Configuración de la página
st.set_page_config(
    page_title="Auditor Automático de Publicaciones",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado mejorado
st.markdown("""
    <style>
    /* Estilos generales */
    .main {
        padding: 0rem 1rem;
    }
    
    /* Header principal con gradiente */
    .audit-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        text-align: center;
    }
    
    /* Métricas personalizadas */
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 2px solid #e9ecef;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0px;
        transition: transform 0.2s;
    }
    
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    
    /* Botones mejorados */
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
        border-radius: 8px;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
    
    /* Tabs mejorados */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f8f9fa;
        padding: 4px;
        border-radius: 10px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: #495057;
        font-weight: 500;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #667eea;
        color: white;
    }
    
    /* Alertas mejoradas */
    .stAlert {
        border-radius: 10px;
        border-left: 4px solid;
        margin-top: 1rem;
    }
    
    /* Progress bar personalizado */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Sidebar mejorado */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);
    }
    
    /* Headers de sección */
    .section-header {
        background: linear-gradient(90deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #667eea;
    }
    
    /* Tabla de resultados */
    .dataframe {
        font-size: 14px;
    }
    
    /* Precio OK */
    .price-ok {
        color: #28a745;
        font-weight: bold;
    }
    
    /* Precio con error */
    .price-error {
        color: #dc3545;
        font-weight: bold;
    }
    
    /* Sin stock */
    .no-stock {
        background-color: #fff3cd;
        color: #856404;
    }
    </style>
    """, unsafe_allow_html=True)

# Título principal
st.markdown("""
    <div class="audit-header">
        <h1 style="text-align: center; color: white;">🤖 Sistema de Auditoría Automática</h1>
        <p style="text-align: center; color: white; margin-top: 10px;">
            Web Scraping Automático de Precios y Stock en Tiendas
        </p>
    </div>
    """, unsafe_allow_html=True)

# Inicializar estado de sesión
if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None
if 'scraping_progress' not in st.session_state:
    st.session_state.scraping_progress = 0

# CONFIGURACIÓN DE TIENDAS Y SCRAPING
TIENDAS_CONFIG = {
    "Tienda Ciudad": {
        "base_url": "https://tiendaciudad.com.ar",
        "selector_precio": [
            "span.price",
            "span.precio-actual",
            "div.price-now",
            "meta[property='product:price:amount']"
        ],
        "selector_stock": [
            "span.stock-disponible",
            "div.availability",
            "meta[property='product:availability']"
        ],
        "formato_precio": "con_puntos",  # 15.000,00
        "columna_url": "URL Ciudad"
    },
    "ICBC": {
        "base_url": "https://mall.icbc.com.ar",
        "selector_precio": [
            "span.price-now",
            "div.precio-final",
            "span.price"
        ],
        "selector_stock": [
            "span.stock-qty",
            "div.stock-disponible"
        ],
        "formato_precio": "sin_puntos",  # 15000
        "columna_url": "URL ICBC"
    },
    "Supervielle": {
        "base_url": "https://tienda.supervielle.com.ar",
        "selector_precio": [
            "span.price",
            "div.precio"
        ],
        "selector_stock": [
            "div.stock",
            "span.disponibilidad"
        ],
        "formato_precio": "sin_puntos",
        "columna_url": "URL Supervielle"
    },
    "Galicia": {
        "base_url": "https://tienda.galicia.com.ar",
        "selector_precio": [
            "span.precio",
            "div.price-box"
        ],
        "selector_stock": [
            "span.stock",
            "div.availability"
        ],
        "formato_precio": "sin_puntos",
        "columna_url": "URL Galicia"
    },
    "Tienda BNA": {
        "base_url": "https://tiendabna.com.ar",
        "selector_precio": ["span.price"],
        "selector_stock": ["span.stock"],
        "formato_precio": "con_puntos",
        "columna_url": "URL BNA"
    },
    "Fravega": {
        "base_url": "https://www.fravega.com",
        "selector_precio": [
            "span.PriceLayout__Main",
            "span[data-test-id='price-value']"
        ],
        "selector_stock": ["button.AddToCart"],
        "formato_precio": "sin_puntos",
        "columna_url": "URL Fravega"
    },
    "Megatone": {
        "base_url": "https://www.megatone.net",
        "selector_precio": ["span.price"],
        "selector_stock": ["div.stock"],
        "formato_precio": "sin_puntos",
        "columna_url": "URL Megatone"
    }
}

# Lista de todas las tiendas
TODAS_LAS_TIENDAS = list(TIENDAS_CONFIG.keys())

class WebScraper:
    """Clase para hacer web scraping de las tiendas"""
    
    def __init__(self, tienda_config):
        self.config = tienda_config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def limpiar_precio(self, precio_texto, formato):
        """Limpia y convierte el precio a número"""
        if not precio_texto:
            return None
        
        # Eliminar símbolos de moneda y espacios
        precio_texto = re.sub(r'[$\s]', '', precio_texto)
        
        if formato == "con_puntos":
            # Formato: 15.000,00 o 15.000
            precio_texto = precio_texto.replace('.', '').replace(',', '.')
        else:
            # Formato: 15000 o 15000.00
            precio_texto = precio_texto.replace(',', '')
        
        try:
            return float(re.sub(r'[^\d.]', '', precio_texto))
        except:
            return None
    
    def scrape_url(self, url):
        """Scrapea una URL específica"""
        resultado = {
            'url': url,
            'precio_web': None,
            'stock_web': None,
            'error': None,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Buscar precio
            for selector in self.config['selector_precio']:
                if selector.startswith('meta'):
                    # Buscar en meta tags
                    meta = soup.find('meta', property=selector.split("'")[1])
                    if meta and meta.get('content'):
                        precio_texto = meta['content']
                        resultado['precio_web'] = self.limpiar_precio(precio_texto, self.config['formato_precio'])
                        break
                else:
                    elemento = soup.select_one(selector)
                    if elemento:
                        precio_texto = elemento.get_text(strip=True)
                        resultado['precio_web'] = self.limpiar_precio(precio_texto, self.config['formato_precio'])
                        break
            
            # Buscar stock
            for selector in self.config['selector_stock']:
                if selector.startswith('meta'):
                    meta = soup.find('meta', property=selector.split("'")[1])
                    if meta:
                        content = meta.get('content', '').lower()
                        resultado['stock_web'] = 'Si' if 'instock' in content or 'available' in content else 'No'
                        break
                else:
                    elemento = soup.select_one(selector)
                    if elemento:
                        texto = elemento.get_text(strip=True).lower()
                        if 'sin stock' in texto or 'agotado' in texto or 'no disponible' in texto:
                            resultado['stock_web'] = 'No'
                        elif 'disponible' in texto or 'stock' in texto:
                            resultado['stock_web'] = 'Si'
                        else:
                            # Si existe el botón de agregar al carrito, hay stock
                            resultado['stock_web'] = 'Si' if elemento else 'No'
                        break
            
            # Si no se encontró stock, buscar botón de compra
            if not resultado['stock_web']:
                buy_button = soup.select_one('button[class*="add"], button[class*="comprar"], button[class*="cart"]')
                resultado['stock_web'] = 'Si' if buy_button else 'Desconocido'
            
        except requests.exceptions.RequestException as e:
            resultado['error'] = f"Error de conexión: {str(e)}"
        except Exception as e:
            resultado['error'] = f"Error: {str(e)}"
        
        return resultado

def realizar_scraping(df_tienda, tienda_config, progress_bar, status_text):
    """Realiza el scraping de todas las URLs de una tienda"""
    scraper = WebScraper(tienda_config)
    resultados = []
    total_urls = len(df_tienda)
    
    # Usar ThreadPoolExecutor para scraping paralelo (más rápido)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scraper.scrape_url, row['url']): idx 
                  for idx, row in df_tienda.iterrows() if pd.notna(row.get('url'))}
        
        completed = 0
        total_futures = len(futures)  # Usar el total real de futures
        
        for future in as_completed(futures):
            completed += 1
            idx = futures[future]
            
            # Actualizar progreso - asegurar que esté entre 0.0 y 1.0
            progress = min(completed / total_futures, 1.0)  # Limitar a 1.0 máximo
            progress_bar.progress(progress)
            status_text.text(f"Escaneando URL {completed}/{total_futures}...")
            
            try:
                resultado = future.result()
                resultado['idx'] = idx
                resultados.append(resultado)
            except Exception as e:
                resultados.append({
                    'idx': idx,
                    'url': df_tienda.loc[idx, 'url'],
                    'error': str(e)
                })
    
    return resultados

# Sidebar mejorado
with st.sidebar:
    # Logo o título
    st.markdown("""
        <div style='text-align: center; padding: 1rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    border-radius: 10px; margin-bottom: 1rem;'>
            <h2 style='color: white; margin: 0;'>⚙️ Panel de Control</h2>
        </div>
    """, unsafe_allow_html=True)
    
    # Selección de tienda
    st.markdown("### 🏪 Tienda a Auditar")
    selected_store = st.selectbox(
        "Selecciona la tienda:",
        TODAS_LAS_TIENDAS,
        help="El sistema hará scraping automático de los precios en esta tienda",
        label_visibility="collapsed"
    )
    
    # Información de la tienda
    if selected_store in TIENDAS_CONFIG:
        config = TIENDAS_CONFIG[selected_store]
        
        # Badge informativo
        if config['columna_url'] in ['URL Ciudad', 'URL ICBC', 'URL Supervielle', 'URL Galicia']:
            st.success("✅ Tienda configurada y lista")
        else:
            st.warning("⚠️ Configuración básica")
        
        with st.expander("📋 Detalles de configuración", expanded=False):
            st.markdown(f"""
            **Base URL:** `{config['base_url']}`  
            **Columna en Excel:** `{config['columna_url']}`  
            **Formato precio:** {config['formato_precio']}  
            """)
    
    st.markdown("---")
    
    # Parámetros de control
    st.markdown("### 📊 Parámetros de Auditoría")
    
    price_threshold = st.slider(
        "🎯 Tolerancia de precio (%)",
        min_value=0,
        max_value=20,
        value=5,
        step=1,
        help="Los precios con variación mayor a este % se marcarán como error"
    )
    
    # Mostrar indicador visual
    if price_threshold <= 2:
        st.info("🔍 Modo estricto: detectará cambios mínimos")
    elif price_threshold <= 5:
        st.success("✅ Modo balanceado: ideal para la mayoría de casos")
    else:
        st.warning("⚠️ Modo permisivo: solo detectará grandes diferencias")
    
    st.markdown("---")
    
    # Modo de operación
    st.markdown("### 🚀 Modo de Ejecución")
    
    modo_operacion = st.radio(
        "Selecciona el modo:",
        [
            "🧪 Modo Prueba (simulado)",
            "⚡ Auditoría Rápida (10 productos)", 
            "📊 Auditoría Completa"
        ],
        help="Prueba: simula resultados | Rápida: primeros 10 | Completa: todos"
    )
    
    # Simplificar el nombre del modo para el código
    if "Prueba" in modo_operacion:
        modo_operacion = "Modo Prueba (simular)"
    elif "Rápida" in modo_operacion:
        modo_operacion = "Auditoría Rápida (primeros 10)"
    else:
        modo_operacion = "Auditoría Completa"
    
    if modo_operacion == "Auditoría Completa":
        max_productos = st.number_input(
            "Límite de productos:",
            min_value=10,
            max_value=1000,
            value=100,
            step=10,
            help="Para evitar sobrecarga, limita la cantidad"
        )
    else:
        max_productos = 100
    
    st.markdown("---")
    
    # Información de ayuda
    with st.expander("❓ ¿Cómo funciona?", expanded=False):
        st.markdown("""
        1. **Carga tu archivo** Auditoria General.xlsx
        2. **Selecciona las columnas** correspondientes
        3. **Ejecuta la auditoría** (botón verde)
        4. El sistema **visita cada URL** automáticamente
        5. **Compara precios** y detecta errores
        6. **Exporta el reporte** con los hallazgos
        
        **Tiempos estimados:**
        - 🧪 Prueba: instantáneo
        - ⚡ Rápida: ~30 segundos
        - 📊 Completa: 2-5 minutos
        """)
    
    # Footer del sidebar
    st.markdown("---")
    st.markdown("""
        <div style='text-align: center; color: #6c757d; font-size: 12px;'>
            <p>Sistema v1.0 | {}</p>
        </div>
    """.format(datetime.now().strftime("%H:%M")), unsafe_allow_html=True)

# Área principal
# Header informativo según tienda seleccionada
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown(f"""
        <div style='text-align: center; padding: 1rem; background: #f8f9fa; 
                    border-radius: 10px; border: 2px solid #667eea;'>
            <h2 style='color: #495057; margin: 0;'>Auditando: {selected_store}</h2>
            <p style='color: #6c757d; margin: 5px 0 0 0;'>Sistema de verificación automática de precios</p>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Tabs principales con iconos mejorados
tab1, tab2, tab3, tab4 = st.tabs([
    "📁 **1. Cargar y Ejecutar**", 
    "📊 **2. Ver Resultados**", 
    "📈 **3. Dashboard**", 
    "⚙️ **4. Configuración Avanzada**"
])

with tab1:
    # Instrucciones claras al inicio
    st.markdown("""
        <div class='section-header'>
            <h3 style='margin: 0;'>📝 Proceso de Auditoría en 3 Pasos</h3>
        </div>
    """, unsafe_allow_html=True)
    
    # Paso 1
    st.markdown("### Paso 1️⃣: Cargar tu archivo maestro")
    
    uploaded_file = st.file_uploader(
        "Selecciona Auditoria General.xlsx",
        type=['xlsx', 'xls'],
        help="Este archivo contiene SKUs, URLs y precios correctos de todos tus productos",
        label_visibility="collapsed"
    )
    
    if uploaded_file:
        try:
            # Cargar el archivo con loading spinner
            with st.spinner('📖 Leyendo archivo...'):
                df_maestro = pd.read_excel(uploaded_file)
            
            # Mostrar confirmación con métricas
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📄 Archivo", uploaded_file.name[:20] + "...")
            with col2:
                st.metric("📊 Total filas", f"{len(df_maestro):,}")
            with col3:
                st.metric("📋 Columnas", len(df_maestro.columns))
            
            # Vista previa mejorada
            with st.expander("👀 Ver estructura del archivo", expanded=False):
                # Tabs dentro del expander
                tab_preview, tab_columns = st.tabs(["Vista previa", "Información de columnas"])
                
                with tab_preview:
                    st.dataframe(df_maestro.head(10), use_container_width=True)
                
                with tab_columns:
                    col_info = pd.DataFrame({
                        'Columna': df_maestro.columns,
                        'Tipo': df_maestro.dtypes.astype(str),
                        'No nulos': df_maestro.count(),
                        '% Completo': (df_maestro.count() / len(df_maestro) * 100).round(1)
                    })
                    st.dataframe(col_info, use_container_width=True)
            
            st.markdown("---")
            
            # Paso 2
            st.markdown("### Paso 2️⃣: Verificar mapeo de columnas")
            
            # Detección automática mejorada con indicadores visuales
            columna_esperada = TIENDAS_CONFIG[selected_store]['columna_url']
            
            # Crear dos columnas para el mapeo
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**📍 Columnas de identificación**")
                
                # URL
                url_detectada = False
                if columna_esperada in df_maestro.columns:
                    url_column = columna_esperada
                    url_detectada = True
                    st.success(f"✅ URL detectada: `{url_column}`")
                else:
                    posibles_url = [col for col in df_maestro.columns if 'url' in col.lower() or selected_store.lower() in col.lower()]
                    if posibles_url:
                        url_column = st.selectbox("⚠️ Selecciona columna de URLs:", posibles_url, key="url_col")
                    else:
                        url_column = st.selectbox("❌ Columna de URLs no detectada:", df_maestro.columns, key="url_col_manual")
                
                # SKU
                sku_columns = [col for col in df_maestro.columns if 'sku' in col.lower() or 'codigo' in col.lower() or 'id' in col.lower()]
                if sku_columns:
                    sku_column = st.selectbox("🔢 SKU/Código:", sku_columns, key="sku_col")
                else:
                    sku_column = st.selectbox("🔢 SKU/Código:", df_maestro.columns, key="sku_col_manual")
            
            with col2:
                st.markdown("**💰 Columnas de valores**")
                
                # Precio
                precio_columns = [col for col in df_maestro.columns if 'precio' in col.lower() or 'price' in col.lower()]
                if precio_columns:
                    precio_column = st.selectbox("💵 Precio correcto:", precio_columns, key="precio_col")
                else:
                    precio_column = st.selectbox("💵 Precio correcto:", df_maestro.columns, key="precio_col_manual")
                
                # Stock
                stock_columns = [col for col in df_maestro.columns if 'stock' in col.lower() or 'cantidad' in col.lower()]
                if stock_columns:
                    stock_column = st.selectbox("📦 Stock:", stock_columns, key="stock_col")
                else:
                    stock_column = st.selectbox("📦 Stock:", df_maestro.columns, key="stock_col_manual")
            
            # Filtrar solo productos de la tienda seleccionada (que tengan URL)
            df_tienda = df_maestro[df_maestro[url_column].notna()].copy()
            
            # Renombrar columnas
            df_tienda = df_tienda.rename(columns={
                url_column: 'url',
                precio_column: 'precio_maestro',
                sku_column: 'sku',
                stock_column: 'stock_maestro'
            })
            
            # Convertir precio_maestro a numérico (limpiando caracteres no numéricos)
            if 'precio_maestro' in df_tienda.columns:
                # Limpiar columna de precio
                df_tienda['precio_maestro'] = df_tienda['precio_maestro'].astype(str)
                # Remover símbolos de moneda, espacios, puntos de miles
                df_tienda['precio_maestro'] = df_tienda['precio_maestro'].str.replace('$', '', regex=False)
                df_tienda['precio_maestro'] = df_tienda['precio_maestro'].str.replace('.', '', regex=False)
                df_tienda['precio_maestro'] = df_tienda['precio_maestro'].str.replace(',', '.', regex=False)
                df_tienda['precio_maestro'] = df_tienda['precio_maestro'].str.strip()
                # Convertir a float
                df_tienda['precio_maestro'] = pd.to_numeric(df_tienda['precio_maestro'], errors='coerce')
            
            # Convertir stock_maestro a numérico
            if 'stock_maestro' in df_tienda.columns:
                df_tienda['stock_maestro'] = pd.to_numeric(df_tienda['stock_maestro'], errors='coerce')
            
            # Aplicar límite según modo
            if modo_operacion == "Auditoría Rápida (primeros 10)":
                df_tienda = df_tienda.head(10)
                limite_texto = "10 productos (modo rápido)"
            elif modo_operacion == "Auditoría Completa":
                df_tienda = df_tienda.head(max_productos)
                limite_texto = f"{min(len(df_tienda), max_productos)} productos"
            else:
                df_tienda = df_tienda.head(10)
                limite_texto = "10 productos (simulación)"
            
            # Mostrar información clara sobre lo que se va a auditar
            st.markdown("---")
            
            # Resumen de la auditoría
            col1, col2, col3 = st.columns(3)
            with col1:
                st.info(f"**🏪 Tienda:** {selected_store}")
            with col2:
                st.info(f"**📊 Productos a auditar:** {len(df_tienda)}")
            with col3:
                st.info(f"**⚡ Modo:** {modo_operacion.split('(')[0].strip()}")
            
            # Vista previa de productos a auditar
            with st.expander(f"📋 Ver productos que se auditarán ({len(df_tienda)} items)", expanded=False):
                preview_df = df_tienda[['sku', 'url', 'precio_maestro', 'stock_maestro']].head(20)
                # Formatear precios para mejor visualización
                preview_df['precio_maestro'] = preview_df['precio_maestro'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) else "N/A")
                preview_df['stock_maestro'] = preview_df['stock_maestro'].fillna(0).astype(int)
                st.dataframe(preview_df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # Paso 3 - Botón de ejecución
            st.markdown("### Paso 3️⃣: Ejecutar auditoría")
            
            # Información según el modo
            if "Prueba" in modo_operacion:
                st.info("🧪 **Modo Prueba:** Se simularán resultados sin hacer scraping real (útil para verificar que todo funcione)")
            elif "Rápida" in modo_operacion:
                st.info("⚡ **Modo Rápido:** Se auditarán solo 10 productos para una verificación rápida")
            else:
                st.warning(f"📊 **Modo Completo:** Se auditarán hasta {max_productos} productos. Esto puede tomar varios minutos.")
            
            # Centrar el botón
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                execute_button = st.button(
                    f"🚀 **INICIAR AUDITORÍA**", 
                    type="primary", 
                    use_container_width=True,
                    help=f"Ejecutar auditoría de {limite_texto}"
                )
            
            if execute_button:
                # Contenedor para mensajes de progreso
                progress_container = st.container()
                
                with progress_container:
                    if modo_operacion == "Modo Prueba (simular)":
                        # Modo simulación para pruebas
                        st.markdown("#### 🧪 Ejecutando simulación...")
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # Simular resultados
                        resultados = []
                        total_items = len(df_tienda)
                        
                        for i, (idx, row) in enumerate(df_tienda.iterrows()):
                            # Simular variación de precio aleatoria
                            variacion = np.random.uniform(-10, 10)
                            precio_maestro_val = row['precio_maestro'] if pd.notna(row['precio_maestro']) else 10000
                            precio_web = precio_maestro_val * (1 + variacion/100)
                            
                            resultados.append({
                                'idx': idx,
                                'url': row['url'],
                                'precio_web': precio_web,
                                'stock_web': np.random.choice(['Si', 'No', 'Si', 'Si']),  # 75% con stock
                                'error': None if np.random.random() > 0.1 else "Error simulado",
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })
                            
                            # Progreso entre 0.0 y 1.0
                            progress = min((i + 1) / total_items, 1.0)
                            progress_bar.progress(progress)
                            status_text.text(f"Simulando producto {i + 1}/{total_items}...")
                            time.sleep(0.05)  # Pausa más corta para simulación
                        
                        progress_bar.empty()
                        status_text.empty()
                        
                    else:
                        # Modo real con web scraping
                        st.markdown("#### 🌐 Ejecutando web scraping real...")
                        st.warning("⏳ Esto puede tomar algunos minutos. Por favor espera...")
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # Realizar scraping
                        tienda_config = TIENDAS_CONFIG[selected_store]
                        resultados = realizar_scraping(df_tienda, tienda_config, progress_bar, status_text)
                        
                        progress_bar.empty()
                        status_text.empty()
                    
                    # Procesar resultados
                    st.success(f"✅ **¡Auditoría completada!** Se analizaron {len(resultados)} productos")
                    
                    # Agregar resultados al dataframe
                    for resultado in resultados:
                        idx = resultado['idx']
                        df_tienda.loc[idx, 'precio_web'] = resultado.get('precio_web')
                        df_tienda.loc[idx, 'stock_web'] = resultado.get('stock_web')
                        df_tienda.loc[idx, 'error_scraping'] = resultado.get('error')
                        df_tienda.loc[idx, 'timestamp'] = resultado.get('timestamp')
                    
                    # Calcular variaciones de forma segura
                    df_tienda['variacion_precio_%'] = 0.0
                    
                    # Calcular solo donde hay datos válidos
                    mask = (df_tienda['precio_web'].notna()) & (df_tienda['precio_maestro'].notna()) & (df_tienda['precio_maestro'] != 0)
                    df_tienda.loc[mask, 'variacion_precio_%'] = (
                        (df_tienda.loc[mask, 'precio_web'] - df_tienda.loc[mask, 'precio_maestro']) / 
                        df_tienda.loc[mask, 'precio_maestro'] * 100
                    ).round(2)
                    
                    # Determinar si el precio está OK
                    df_tienda['precio_ok'] = False
                    df_tienda.loc[mask, 'precio_ok'] = df_tienda.loc[mask, 'variacion_precio_%'].abs() <= price_threshold
                    
                    # Marcar productos que requieren acción
                    df_tienda['requiere_accion'] = (
                        (~df_tienda['precio_ok'] & df_tienda['precio_web'].notna()) | 
                        (df_tienda['stock_web'] == 'No') |
                        (df_tienda['error_scraping'].notna())
                    )
                    
                    # Guardar en sesión
                    st.session_state.audit_results = df_tienda
                    
                    # Mostrar resumen con diseño mejorado
                    st.markdown("---")
                    st.markdown("### 📊 Resumen de Resultados")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        total = len(df_tienda)
                        st.metric("📋 Total Auditados", f"{total:,}")
                    
                    with col2:
                        errores_precio = len(df_tienda[(df_tienda['precio_ok'] == False) & df_tienda['precio_web'].notna()])
                        color = "🔴" if errores_precio > 0 else "🟢"
                        st.metric(f"{color} Errores de Precio", errores_precio, 
                                 delta=f"-{(errores_precio/total*100):.1f}%" if errores_precio > 0 else "OK")
                    
                    with col3:
                        sin_stock = len(df_tienda[df_tienda['stock_web'] == 'No'])
                        color = "🔴" if sin_stock > 0 else "🟢"
                        st.metric(f"{color} Sin Stock", sin_stock,
                                 delta=f"-{(sin_stock/total*100):.1f}%" if sin_stock > 0 else "OK")
                    
                    with col4:
                        errores_scraping = len(df_tienda[df_tienda['error_scraping'].notna()])
                        if errores_scraping > 0:
                            st.metric("⚠️ Errores Técnicos", errores_scraping)
                        else:
                            st.metric("✅ Sin Errores", "0")
                    
                    # Mensaje de siguiente paso
                    st.markdown("---")
                    st.success("✨ **¡Listo!** Ve a la pestaña **'2. Ver Resultados'** para analizar el detalle completo")
            
        except Exception as e:
            st.error(f"Error al procesar el archivo: {str(e)}")

with tab2:
    st.markdown("### 📊 Resultados Detallados de Auditoría")
    
    if st.session_state.audit_results is not None:
        df_results = st.session_state.audit_results
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        
        with col1:
            filtro = st.selectbox(
                "Filtrar por:",
                ["Todos", "Solo errores de precio", "Solo sin stock", "Requieren acción"]
            )
        
        with col2:
            orden = st.selectbox(
                "Ordenar por:",
                ["Variación de precio", "SKU", "Stock"]
            )
        
        with col3:
            if st.button("🔄 Refrescar"):
                st.rerun()
        
        # Aplicar filtros
        df_filtrado = df_results.copy()
        
        if filtro == "Solo errores de precio":
            df_filtrado = df_filtrado[(df_filtrado['precio_ok'] == False) & df_filtrado['precio_web'].notna()]
        elif filtro == "Solo sin stock":
            df_filtrado = df_filtrado[df_filtrado['stock_web'] == 'No']
        elif filtro == "Requieren acción":
            df_filtrado = df_filtrado[df_filtrado['requiere_accion'] == True]
        
        # Ordenar
        if orden == "Variación de precio":
            # Ordenar por valor absoluto de variación, poniendo NaN al final
            df_filtrado['abs_variacion'] = df_filtrado['variacion_precio_%'].abs()
            df_filtrado = df_filtrado.sort_values('abs_variacion', ascending=False, na_position='last')
            df_filtrado = df_filtrado.drop('abs_variacion', axis=1)
        elif orden == "SKU":
            df_filtrado = df_filtrado.sort_values('sku', na_position='last')
        elif orden == "Stock":
            df_filtrado = df_filtrado.sort_values('stock_web', na_position='last')
        
        # Mostrar tabla con formato
        st.dataframe(
            df_filtrado[[
                'sku', 
                'precio_maestro', 
                'precio_web', 
                'variacion_precio_%',
                'precio_ok',
                'stock_maestro',
                'stock_web',
                'requiere_accion',
                'url'
            ]].style.applymap(
                lambda x: 'background-color: #ffcccc' if x == False else 'background-color: #ccffcc' if x == True else '',
                subset=['precio_ok']
            ).applymap(
                lambda x: 'background-color: #ffcccc' if x == 'No' else '',
                subset=['stock_web']
            ).format({
                'precio_maestro': '${:,.0f}',
                'precio_web': '${:,.0f}',
                'variacion_precio_%': '{:.1f}%'
            }),
            use_container_width=True,
            height=500
        )
        
        # Exportar resultados
        st.markdown("### 💾 Exportar Resultados")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Excel completo
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_results.to_excel(writer, sheet_name='Auditoría Completa', index=False)
                
                # Hoja de errores
                df_errores = df_results[df_results['requiere_accion'] == True]
                if not df_errores.empty:
                    df_errores.to_excel(writer, sheet_name='Requieren Acción', index=False)
            
            output.seek(0)
            
            st.download_button(
                label="📊 Descargar Excel Completo",
                data=output,
                file_name=f"Auditoria_{selected_store}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col2:
            # CSV de errores
            df_errores = df_filtrado[df_filtrado['requiere_accion'] == True]
            if not df_errores.empty:
                csv = df_errores.to_csv(index=False)
                st.download_button(
                    label="📄 Descargar Solo Errores (CSV)",
                    data=csv,
                    file_name=f"Errores_{selected_store}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No hay errores para exportar")
        
        with col3:
            # Reporte resumen
            # Contar elementos correctamente
            errores_precio_count = len(df_results[(df_results['precio_ok'] == False) & df_results['precio_web'].notna()])
            sin_stock_count = len(df_results[df_results['stock_web'] == 'No'])
            requieren_accion_count = len(df_results[df_results['requiere_accion'] == True])
            
            # Obtener DataFrames filtrados
            df_errores_precio = df_results[(df_results['precio_ok'] == False) & df_results['precio_web'].notna()][
                ['sku', 'precio_maestro', 'precio_web', 'variacion_precio_%']
            ]
            df_sin_stock = df_results[df_results['stock_web'] == 'No'][['sku', 'url']]
            
            resumen = f"""
REPORTE DE AUDITORÍA - {selected_store}
Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}
=====================================

RESUMEN:
- Total de productos auditados: {len(df_results)}
- Errores de precio: {errores_precio_count}
- Productos sin stock: {sin_stock_count}
- Requieren acción inmediata: {requieren_accion_count}

PRODUCTOS CON ERRORES DE PRECIO:
{df_errores_precio.to_string() if not df_errores_precio.empty else "No hay errores de precio"}

PRODUCTOS SIN STOCK:
{df_sin_stock.to_string() if not df_sin_stock.empty else "Todos los productos tienen stock"}
            """
            
            st.download_button(
                label="📝 Descargar Reporte TXT",
                data=resumen,
                file_name=f"Reporte_{selected_store}_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )
    
    else:
        st.info("👆 Primero ejecuta una auditoría en la pestaña '1. Cargar y Ejecutar'")

with tab3:
    st.markdown("### 📈 Dashboard de Auditoría")
    
    if st.session_state.audit_results is not None:
        df = st.session_state.audit_results
        
        # Métricas principales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # Calcular accuracy solo con valores válidos
            precios_validos = df[df['precio_web'].notna()]
            if len(precios_validos) > 0:
                accuracy = (len(precios_validos[precios_validos['precio_ok'] == True]) / len(precios_validos) * 100)
            else:
                accuracy = 0
            
            st.metric(
                "Precisión de Precios",
                f"{accuracy:.1f}%",
                delta="Bueno" if accuracy > 90 else "Regular" if accuracy > 80 else "Malo"
            )
        
        with col2:
            disponibilidad = (len(df[df['stock_web'] == 'Si']) / len(df) * 100) if len(df) > 0 else 0
            st.metric(
                "Disponibilidad",
                f"{disponibilidad:.1f}%",
                delta="Óptimo" if disponibilidad > 95 else "Aceptable" if disponibilidad > 85 else "Crítico"
            )
        
        with col3:
            # Calcular variación promedio solo con valores válidos
            variaciones_validas = df['variacion_precio_%'].dropna()
            if len(variaciones_validas) > 0:
                variacion_promedio = variaciones_validas.abs().mean()
            else:
                variacion_promedio = 0
                
            st.metric(
                "Variación Promedio",
                f"{variacion_promedio:.1f}%",
                delta="Excelente" if variacion_promedio < 2 else "Bueno" if variacion_promedio < 5 else "Alto"
            )
        
        with col4:
            health_score = ((accuracy * 0.6) + (disponibilidad * 0.4))
            st.metric(
                "Health Score",
                f"{health_score:.0f}/100",
                delta="⭐" if health_score > 90 else "✓" if health_score > 75 else "⚠️"
            )
        
        # Gráficos
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Gráfico de distribución de variaciones
            df_para_histograma = df[df['variacion_precio_%'].notna()]
            
            if not df_para_histograma.empty:
                fig_hist = px.histogram(
                    df_para_histograma,
                    x='variacion_precio_%',
                    title='Distribución de Variaciones de Precio',
                    labels={'variacion_precio_%': 'Variación (%)', 'count': 'Cantidad'},
                    color_discrete_sequence=['#764ba2']
                )
                fig_hist.add_vline(x=-price_threshold, line_dash="dash", line_color="red")
                fig_hist.add_vline(x=price_threshold, line_dash="dash", line_color="red")
                st.plotly_chart(fig_hist, use_container_width=True)
            else:
                st.info("No hay datos de variación para mostrar")
        
        with col2:
            # Gráfico de pie de estados
            estados = pd.DataFrame({
                'Estado': ['Precio OK', 'Error Precio', 'Sin Stock', 'OK Total'],
                'Cantidad': [
                    len(df[(df['precio_ok'] == True) & df['precio_web'].notna()]),
                    len(df[(df['precio_ok'] == False) & df['precio_web'].notna()]),
                    len(df[df['stock_web'] == 'No']),
                    len(df[(df['precio_ok'] == True) & (df['stock_web'] != 'No') & df['precio_web'].notna()])
                ]
            })
            
            fig_pie = px.pie(
                estados,
                values='Cantidad',
                names='Estado',
                title='Estado de Productos',
                color_discrete_map={
                    'OK Total': '#00CC00',
                    'Precio OK': '#90EE90',
                    'Error Precio': '#FFA500',
                    'Sin Stock': '#FF4444'
                }
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        # Top productos con mayor variación
        st.markdown("---")
        st.subheader("🔴 Top 10 Productos con Mayor Variación")
        
        # Filtrar solo los que tienen variación válida
        df_con_variacion = df[df['variacion_precio_%'].notna() & (df['variacion_precio_%'].abs() > 0)]
        
        if not df_con_variacion.empty:
            top_variaciones = df_con_variacion.nlargest(10, 'variacion_precio_%', keep='all')[
                ['sku', 'precio_maestro', 'precio_web', 'variacion_precio_%', 'url']
            ]
            
            st.dataframe(
                top_variaciones.style.format({
                    'precio_maestro': '${:,.0f}',
                    'precio_web': '${:,.0f}',
                    'variacion_precio_%': '{:.1f}%'
                }),
                use_container_width=True
            )
        else:
            st.info("No hay productos con variación de precio detectada")
        
        # Timeline de auditoría
        if 'timestamp' in df.columns:
            st.markdown("---")
            st.subheader("📅 Timeline de Auditoría")
            st.info(f"Última actualización: {df['timestamp'].iloc[0] if not df.empty else 'N/A'}")
    
    else:
        st.info("👆 Primero ejecuta una auditoría para ver el dashboard")

with tab4:
    st.markdown("### ⚙️ Configuración de Scraping")
    
    st.warning("⚠️ Esta sección es para usuarios avanzados")
    
    # Mostrar configuración actual
    st.subheader(f"Configuración actual para {selected_store}")
    
    if selected_store in TIENDAS_CONFIG:
        config = TIENDAS_CONFIG[selected_store]
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Selectores de Precio:**")
            for selector in config['selector_precio']:
                st.code(selector)
            
            st.markdown("**Formato de Precio:**")
            st.info(config['formato_precio'])
        
        with col2:
            st.markdown("**Selectores de Stock:**")
            for selector in config['selector_stock']:
                st.code(selector)
            
            st.markdown("**URL Base:**")
            st.info(config['base_url'])
    
    # Instrucciones para agregar nuevas tiendas
    with st.expander("📚 Cómo agregar una nueva tienda"):
        st.markdown("""
        Para agregar una nueva tienda, necesitas:
        
        1. **Inspeccionar el HTML** de la página del producto
        2. **Identificar los selectores CSS** para precio y stock
        3. **Determinar el formato** del precio (con o sin puntos/comas)
        4. **Agregar la configuración** al diccionario TIENDAS_CONFIG
        
        Ejemplo:
        ```python
        "NuevaTienda": {
            "base_url": "https://nuevatienda.com",
            "selector_precio": ["span.price", "div.precio"],
            "selector_stock": ["span.stock"],
            "formato_precio": "con_puntos",
            "columna_url": "URL NuevaTienda"
        }
        ```
        """)
    
    # Test de scraping
    st.markdown("---")
    st.subheader("🧪 Test de Scraping")
    
    test_url = st.text_input("URL de prueba:", placeholder="https://tienda.com/producto")
    
    if st.button("Probar Scraping") and test_url:
        with st.spinner("Probando..."):
            scraper = WebScraper(TIENDAS_CONFIG[selected_store])
            resultado = scraper.scrape_url(test_url)
            
            if resultado['error']:
                st.error(f"Error: {resultado['error']}")
            else:
                st.success("✅ Scraping exitoso!")
                st.json(resultado)

# Footer
st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center; color: gray; padding: 20px;'>
        <p>🤖 Sistema de Auditoría Automática con Web Scraping v1.0 | 
        {selected_store} | 
        {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>
        <p style='font-size: 12px;'>⚡ Powered by BeautifulSoup + Requests</p>
    </div>
    """,
    unsafe_allow_html=True
)
