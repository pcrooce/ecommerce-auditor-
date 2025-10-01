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

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except ImportError:
    st.error("Por favor instala openpyxl: pip install openpyxl")

st.set_page_config(
    page_title="Auditor Automático de Publicaciones",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
    <style>
    .main {padding: 0rem 1rem;}
    .audit-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2.5rem; border-radius: 15px; color: white;
        margin-bottom: 2rem; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        text-align: center;
    }
    div[data-testid="metric-container"] {
        background-color: #f8f9fa; border: 2px solid #e9ecef;
        padding: 15px; border-radius: 10px; margin: 10px 0px;
        transition: transform 0.2s;
    }
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white; border: none; padding: 0.5rem 1rem;
        font-weight: 600; border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("""
    <div class="audit-header">
        <h1>🤖 Sistema de Auditoría Automática v6.0</h1>
        <p>Verificación automática de precios con soporte completo para Frávega</p>
    </div>
""", unsafe_allow_html=True)

if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None

# CONFIGURACIÓN DE TIENDAS
TIENDAS_CONFIG = {
    "ICBC": {
        "columnas_busqueda": ["ICBC", "icbc"],
        "selector_titulo": "h1[itemprop='name']",
        "selector_precio": "p.monto",
        "selector_precio_tachado": "p.precio-anterior",
        "selector_descuento": "p.descuento",
        "selector_categoria": "span.breadcrumb-span[itemprop='title']",
        "selector_no_disponible": ["li:contains('no longer available')"]
    },
    "Supervielle": {
        "columnas_busqueda": ["Supervielle", "supervielle"],
        "selector_titulo": "h1[itemprop='name']",
        "selector_precio": "span#our_price_display",
        "selector_precio_tachado": "span.price",
        "selector_descuento": "span#reduction_percent_display",
        "selector_categoria": "span[itemprop='title']",
        "selector_no_disponible": ["li:contains('no longer available')"]
    },
    "Galicia": {
        "columnas_busqueda": ["Galicia", "galicia"],
        "selector_titulo": "h1.productTitle",
        "selector_precio": "div.productPrice span",
        "selector_descuento": "span.discount.discount-percentage",
        "selector_categoria": "span[itemprop='name']",
        "selector_no_disponible": ["li:contains('no longer available')"]
    },
    "Ciudad": {
        "columnas_busqueda": ["Ciudad", "ciudad"],
        "selector_titulo": "h1.name",
        "selector_precio": "span.amount",
        "selector_precio_tachado": "div[itemprop='offers'] span.amount",
        "selector_categoria": "a[href*='/catalog/']",
        "selector_no_disponible": ["li:contains('no longer available')"]
    },
    "Fravega": {
        "columnas_busqueda": ["Fravega", "fravega", "FVG"],
        "columnas_cuotas": ["Cuotas FVG", "CSI FVG", "Financiacion Fvg", "Financiación FVG"],
        "selector_titulo": "h1[data-test-id='product-title']",
        "selector_precio": "span.sc-1d9b1d9e-0.sc-faa1a185-3",
        "selector_precio_tachado": "span.sc-e081bce1-0.sc-faa1a185-4",
        "selector_descuento": "span.sc-e2aca368-0",
        "selector_categoria": "span[itemprop='name']",
        "selector_cuotas_container": "span.sc-3cba7521-10",
        "selector_no_disponible": ["div.product-not-found"],
        # URLs de imágenes específicas de Frávega para Visa/Mastercard
        "urls_visa_master": ["54c0d769ece1b", "d91d7904a8578", "visa", "mastercard", "master"]
    },
    "BNA": {
        "columnas_busqueda": ["BNA", "bna"],
        "selector_precio": "span.price",
        "selector_no_disponible": ["li:contains('no longer available')"]
    },
    "Megatone": {
        "columnas_busqueda": ["Megatone", "megatone", "MGT"],
        "columnas_cuotas": ["Cuotas MGT", "CSI MGT", "Financiacion Mgt"],
        "selector_precio": "span.price",
        "selector_no_disponible": ["div.product-not-found"]
    }
}

def detectar_columnas_automaticamente(df, tienda):
    """Detecta automáticamente las columnas según la tienda"""
    config = TIENDAS_CONFIG[tienda]
    resultado = {'url': None, 'precio': None, 'sku': None, 'cuotas': None}
    
    for col in df.columns:
        col_lower = col.lower()
        
        # URL
        if resultado['url'] is None:
            for busqueda in config['columnas_busqueda']:
                if busqueda.lower() in col_lower and 'url' in col_lower:
                    resultado['url'] = col
                    break
        
        # Precio
        if resultado['precio'] is None:
            for busqueda in config['columnas_busqueda']:
                if busqueda.lower() in col_lower and 'precio' in col_lower:
                    resultado['precio'] = col
                    break
        
        # SKU
        if resultado['sku'] is None:
            if any(word in col_lower for word in ['sku', 'codigo', 'código']):
                resultado['sku'] = col
        
        # Cuotas (solo Frávega/Megatone)
        if 'columnas_cuotas' in config and resultado['cuotas'] is None:
            for busqueda in config.get('columnas_cuotas', []):
                if busqueda.lower() in col_lower:
                    resultado['cuotas'] = col
                    break
    
    return resultado

def limpiar_precio(valor):
    """Convierte precio argentino a número"""
    if pd.isna(valor):
        return np.nan
    
    precio_str = str(valor).replace('$', '').replace(' ', '').strip()
    
    # Detectar formato
    if '.' in precio_str and ',' in precio_str:
        # Formato: 1.234,56 (argentino)
        precio_str = precio_str.replace('.', '').replace(',', '.')
    elif '.' in precio_str:
        # Si tiene punto seguido de 3 dígitos → separador miles
        if re.search(r'\.\d{3}', precio_str):
            precio_str = precio_str.replace('.', '')
        elif not re.search(r'\.\d{2}$', precio_str):
            precio_str = precio_str.replace('.', '')
    elif ',' in precio_str:
        if re.search(r',\d{2}$', precio_str):
            precio_str = precio_str.replace(',', '.')
        else:
            precio_str = precio_str.replace(',', '')
    
    try:
        return float(re.sub(r'[^\d.]', '', precio_str))
    except:
        return np.nan

class WebScraper:
    def __init__(self, tienda_config, tienda_nombre):
        self.config = tienda_config
        self.tienda = tienda_nombre
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extraer_cuotas_fravega(self, soup):
        """Extrae cuotas de Frávega buscando financiación Visa/Mastercard"""
        if 'selector_cuotas_container' not in self.config:
            return None
        
        cuotas_containers = soup.select(self.config['selector_cuotas_container'])
        
        for container in cuotas_containers:
            # Buscar en el contenedor y sus padres cercanos
            parent = container.find_parent()
            if not parent:
                parent = container
            
            # Buscar imágenes en el área cercana
            imagenes = parent.find_all('img', src=True, limit=10)
            
            tiene_visa_master = False
            for img in imagenes:
                src = img.get('src', '').lower()
                # Verificar si contiene URLs de Visa/Mastercard de Frávega
                if any(url_pattern in src for url_pattern in self.config.get('urls_visa_master', [])):
                    tiene_visa_master = True
                    break
            
            if tiene_visa_master:
                # Extraer número de cuotas del texto
                texto = container.get_text()
                match = re.search(r'(\d+)\s*cuotas?', texto, re.IGNORECASE)
                if match:
                    return int(match.group(1))
        
        # Si no encontró financiación con Visa/Master, es contado
        return 1
    
    def scrape_url(self, url):
        """Scrapea una URL específica"""
        resultado = {
            'url': url,
            'titulo': None,
            'precio_web': None,
            'precio_tachado': None,
            'descuento_%': None,
            'categoria': None,
            'cuotas': None,
            'estado_producto': 'Activo',
            'error': None,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 404:
                resultado['estado_producto'] = 'No disponible en el front'
                return resultado
            
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Verificar disponibilidad
            html_text = soup.get_text().lower()
            if 'no longer available' in html_text or 'no está disponible' in html_text:
                resultado['estado_producto'] = 'No disponible en el front'
                return resultado
            
            # Título
            if 'selector_titulo' in self.config:
                titulo_elem = soup.select_one(self.config['selector_titulo'])
                if titulo_elem:
                    resultado['titulo'] = titulo_elem.get_text(strip=True)
            
            # Precio principal
            if 'selector_precio' in self.config:
                precio_elem = soup.select_one(self.config['selector_precio'])
                if precio_elem:
                    resultado['precio_web'] = limpiar_precio(precio_elem.get_text(strip=True))
            
            # Precio tachado
            if 'selector_precio_tachado' in self.config:
                tachado_elem = soup.select_one(self.config['selector_precio_tachado'])
                if tachado_elem:
                    resultado['precio_tachado'] = limpiar_precio(tachado_elem.get_text(strip=True))
            
            # Descuento
            if 'selector_descuento' in self.config:
                desc_elem = soup.select_one(self.config['selector_descuento'])
                if desc_elem:
                    desc_text = desc_elem.get_text(strip=True)
                    match = re.search(r'(\d+)', desc_text)
                    if match:
                        resultado['descuento_%'] = float(match.group(1))
            
            # Categoría (última del breadcrumb)
            if 'selector_categoria' in self.config:
                categorias = soup.select(self.config['selector_categoria'])
                if len(categorias) > 0:
                    # Tomar la última categoría, ignorando "Inicio", "Home", nombre de tienda
                    categorias_validas = []
                    for cat in categorias:
                        texto = cat.get_text(strip=True)
                        if texto.lower() not in ['inicio', 'home', self.tienda.lower()]:
                            categorias_validas.append(texto)
                    if categorias_validas:
                        resultado['categoria'] = categorias_validas[-1]
            
            # Cuotas (solo Frávega)
            if self.tienda == "Fravega":
                resultado['cuotas'] = self.extraer_cuotas_fravega(soup)
            
            # Calcular precio tachado si no existe (solo Galicia)
            if self.tienda == "Galicia" and not resultado['precio_tachado'] and resultado['descuento_%'] and resultado['precio_web']:
                # precio_tachado = precio_final / (1 - descuento/100)
                descuento_decimal = resultado['descuento_%'] / 100
                resultado['precio_tachado'] = resultado['precio_web'] / (1 - descuento_decimal)
            
        except requests.exceptions.HTTPError as e:
            if '404' in str(e):
                resultado['estado_producto'] = 'No disponible en el front'
            else:
                resultado['error'] = str(e)
        except Exception as e:
            resultado['error'] = str(e)
        
        return resultado

def realizar_scraping(df_tienda, tienda_config, tienda_nombre, progress_bar, status_text):
    """Realiza el scraping con threads"""
    scraper = WebScraper(tienda_config, tienda_nombre)
    resultados = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scraper.scrape_url, row['url']): idx 
                  for idx, row in df_tienda.iterrows() if pd.notna(row.get('url'))}
        
        completed = 0
        total = len(futures)
        
        for future in as_completed(futures):
            completed += 1
            idx = futures[future]
            resultado = future.result()
            resultado['idx'] = idx
            resultados.append(resultado)
            
            progress_bar.progress(min(completed / total, 1.0))
            status_text.text(f"Escaneando {completed}/{total}...")
    
    return resultados

def crear_excel_formateado(df_results, tienda):
    """Crea Excel con formato profesional"""
    output = BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"
    
    # Título
    ws['A1'] = f'AUDITORÍA {tienda.upper()} - {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    ws['A1'].font = Font(bold=True, size=14)
    
    # Determinar columnas según tienda
    if tienda in ["Fravega", "Megatone"]:
        columnas = ['SKU', 'Título', 'Precio Maestro', 'Precio Web', 'Precio Tachado',
                   'Descuento %', 'Variación %', 'Precio OK', 'Cuotas Web', 'Cuotas Maestro',
                   'Cuotas OK', 'Categoría', 'Estado', 'URL']
        ws.merge_cells('A1:N1')
    else:
        columnas = ['SKU', 'Título', 'Precio Maestro', 'Precio Web', 'Precio Tachado',
                   'Descuento %', 'Variación %', 'Precio OK', 'Categoría', 'Estado', 'URL']
        ws.merge_cells('A1:K1')
    
    ws.append([])
    ws.append(columnas)
    
    # Formato headers
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
    
    # Datos
    for _, row in df_results.iterrows():
        if tienda in ["Fravega", "Megatone"]:
            row_data = [
                row.get('sku'), row.get('titulo'), row.get('precio_maestro'),
                row.get('precio_web'), row.get('precio_tachado'), row.get('descuento_%'),
                row.get('variacion_precio_%'), 'Sí' if row.get('precio_ok') else 'No',
                row.get('cuotas'), row.get('cuotas_maestro'),
                'Sí' if row.get('cuotas_correctas') else 'No',
                row.get('categoria'), row.get('estado_producto'), row.get('url')
            ]
        else:
            row_data = [
                row.get('sku'), row.get('titulo'), row.get('precio_maestro'),
                row.get('precio_web'), row.get('precio_tachado'), row.get('descuento_%'),
                row.get('variacion_precio_%'), 'Sí' if row.get('precio_ok') else 'No',
                row.get('categoria'), row.get('estado_producto'), row.get('url')
            ]
        ws.append(row_data)
    
    # Colores
    for row_num in range(4, ws.max_row + 1):
        precio_ok_col = 8
        estado_col = 13 if tienda in ["Fravega", "Megatone"] else 10
        
        # Precio OK
        cell = ws.cell(row=row_num, column=precio_ok_col)
        if cell.value == 'Sí':
            cell.fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
        else:
            cell.fill = PatternFill(start_color="FFB6C1", end_color="FFB6C1", fill_type="solid")
        
        # Cuotas OK (solo Frávega/Megatone)
        if tienda in ["Fravega", "Megatone"]:
            cell = ws.cell(row=row_num, column=11)
            if cell.value == 'Sí':
                cell.fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
            else:
                cell.fill = PatternFill(start_color="FFB6C1", end_color="FFB6C1", fill_type="solid")
    
    wb.save(output)
    output.seek(0)
    return output

# SIDEBAR
with st.sidebar:
    st.markdown("""
        <div style='text-align: center; padding: 1rem; 
             background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
             border-radius: 10px; margin-bottom: 1rem;'>
            <h2 style='color: white; margin: 0;'>⚙️ Panel de Control</h2>
        </div>
    """, unsafe_allow_html=True)
    
    selected_store = st.selectbox("🏪 Tienda", list(TIENDAS_CONFIG.keys()))
    
    price_threshold = st.slider("🎯 Tolerancia precio (%)", 0, 20, 5, 1)
    
    modo_operacion = st.radio("🚀 Modo", [
        "🧪 Prueba (simulado)",
        "⚡ Rápida (10 productos)", 
        "📊 Completa"
    ])
    
    if "Prueba" in modo_operacion:
        modo_operacion = "Modo Prueba (simular)"
    elif "Rápida" in modo_operacion:
        modo_operacion = "Auditoría Rápida (primeros 10)"
    else:
        modo_operacion = "Auditoría Completa"
        max_productos = st.number_input("Límite:", 10, 1000, 100, 10)
    
    if modo_operacion != "Auditoría Completa":
        max_productos = 100

# TABS
tab1, tab2, tab3 = st.tabs(["📁 Cargar y Ejecutar", "📊 Resultados", "📈 Dashboard"])

with tab1:
    st.markdown("### 📝 Proceso de Auditoría")
    
    uploaded_file = st.file_uploader("Cargar Excel", type=['xlsx', 'xls'])
    
    if uploaded_file:
        df_maestro = pd.read_excel(uploaded_file)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📄 Archivo", uploaded_file.name[:20] + "...")
        with col2:
            st.metric("📊 Filas", f"{len(df_maestro):,}")
        with col3:
            st.metric("📋 Columnas", len(df_maestro.columns))
        
        columnas_detectadas = detectar_columnas_automaticamente(df_maestro, selected_store)
        
        st.markdown("### ✅ Columnas detectadas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if columnas_detectadas['url']:
                st.success(f"✅ URL: `{columnas_detectadas['url']}`")
                url_column = columnas_detectadas['url']
            else:
                st.error("❌ URL no detectada")
                url_column = st.selectbox("URL:", df_maestro.columns)
            
            if columnas_detectadas['sku']:
                st.success(f"✅ SKU: `{columnas_detectadas['sku']}`")
                sku_column = columnas_detectadas['sku']
            else:
                st.warning("⚠️ Selecciona SKU")
                sku_column = st.selectbox("SKU:", df_maestro.columns)
        
        with col2:
            if columnas_detectadas['precio']:
                st.success(f"✅ Precio: `{columnas_detectadas['precio']}`")
                precio_column = columnas_detectadas['precio']
            else:
                st.warning("⚠️ Selecciona precio")
                precio_column = st.selectbox("Precio:", df_maestro.columns)
            
            # Cuotas (solo Frávega/Megatone)
            if selected_store in ["Fravega", "Megatone"]:
                if columnas_detectadas['cuotas']:
                    st.success(f"✅ Cuotas: `{columnas_detectadas['cuotas']}`")
                    cuotas_column = columnas_detectadas['cuotas']
                else:
                    st.warning("⚠️ Selecciona cuotas")
                    cuotas_column = st.selectbox("Cuotas:", df_maestro.columns)
            else:
                cuotas_column = None
        
        # Preparar datos
        df_tienda = df_maestro[df_maestro[url_column].notna()].copy()
        
        rename_dict = {
            url_column: 'url',
            sku_column: 'sku',
            precio_column: 'precio_maestro'
        }
        if cuotas_column:
            rename_dict[cuotas_column] = 'cuotas_maestro'
        
        df_tienda = df_tienda.rename(columns=rename_dict)
        df_tienda['precio_maestro'] = df_tienda['precio_maestro'].apply(limpiar_precio)
        
        if 'cuotas_maestro' in df_tienda.columns:
            df_tienda['cuotas_maestro'] = pd.to_numeric(df_tienda['cuotas_maestro'], errors='coerce')
        
        # Límites
        if modo_operacion == "Auditoría Rápida (primeros 10)":
            df_tienda = df_tienda.head(10)
        elif modo_operacion == "Auditoría Completa":
            df_tienda = df_tienda.head(max_productos)
        else:
            df_tienda = df_tienda.head(10)
        
        st.markdown("---")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🚀 INICIAR AUDITORÍA", type="primary", use_container_width=True):
                
                if modo_operacion == "Modo Prueba (simular)":
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    resultados = []
                    for i, (idx, row) in enumerate(df_tienda.iterrows()):
                        variacion = np.random.uniform(-10, 10)
                        precio_maestro_val = row.get('precio_maestro', 10000)
                        if pd.isna(precio_maestro_val):
                            precio_maestro_val = 10000
                        
                        precio_web = float(precio_maestro_val * (1 + variacion/100))
                        
                        resultados.append({
                            'idx': idx,
                            'url': row['url'],
                            'titulo': f"Producto simulado {i+1}",
                            'precio_web': precio_web,
                            'precio_tachado': precio_web * 1.3,
                            'descuento_%': np.random.randint(10, 40),
                            'categoria': "Categoría de prueba",
                            'cuotas': np.random.choice([1, 3, 6, 9, 12]) if selected_store == "Fravega" else None,
                            'estado_producto': 'Activo',
                            'error': None,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                        
                        progress_bar.progress(min((i + 1) / len(df_tienda), 1.0))
                        status_text.text(f"Producto {i + 1}/{len(df_tienda)}")
                        time.sleep(0.05)
                    
                    progress_bar.empty()
                    status_text.empty()
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    tienda_config = TIENDAS_CONFIG[selected_store]
                    resultados = realizar_scraping(df_tienda, tienda_config, selected_store, progress_bar, status_text)
                    
                    progress_bar.empty()
                    status_text.empty()
                
                # Procesar resultados
                for resultado in resultados:
                    idx = resultado['idx']
                    df_tienda.loc[idx, 'titulo'] = resultado.get('titulo')
                    df_tienda.loc[idx, 'precio_web'] = resultado.get('precio_web')
                    df_tienda.loc[idx, 'precio_tachado'] = resultado.get('precio_tachado')
                    df_tienda.loc[idx, 'descuento_%'] = resultado.get('descuento_%')
                    df_tienda.loc[idx, 'categoria'] = resultado.get('categoria')
                    df_tienda.loc[idx, 'cuotas'] = resultado.get('cuotas')
                    df_tienda.loc[idx, 'estado_producto'] = resultado.get('estado_producto')
                    df_tienda.loc[idx, 'error_scraping'] = resultado.get('error')
                
                # Calcular variaciones
                mask = (df_tienda['precio_web'].notna()) & (df_tienda['precio_maestro'].notna()) & (df_tienda['precio_maestro'] != 0)
                df_tienda['variacion_precio_%'] = 0.0
                
                if mask.any():
                    df_tienda.loc[mask, 'variacion_precio_%'] = (
                        (df_tienda.loc[mask, 'precio_web'] - df_tienda.loc[mask, 'precio_maestro']) / 
                        df_tienda.loc[mask, 'precio_maestro'] * 100
                    ).round(2)
                
                df_tienda['precio_ok'] = abs(df_tienda['variacion_precio_%']) <= price_threshold
                
                # Validar cuotas (solo Frávega/Megatone)
                if selected_store in ["Fravega", "Megatone"] and 'cuotas_maestro' in df_tienda.columns:
                    df_tienda['cuotas_correctas'] = df_tienda['cuotas'] == df_tienda['cuotas_maestro']
                else:
                    df_tienda['cuotas_correctas'] = True
                
                st.session_state.audit_results = df_tienda
                
                # Resumen
                st.success(f"✅ Auditoría completada: {len(df_tienda)} productos")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("📋 Total", len(df_tienda))
                
                with col2:
                    ok_count = len(df_tienda[df_tienda['precio_ok'] == True])
                    st.metric("✅ Precios OK", ok_count)
                
                with col3:
                    error_count = len(df_tienda[(df_tienda['precio_ok'] == False) & df_tienda['precio_web'].notna()])
                    st.metric("❌ Errores", error_count)
                
                with col4:
                    no_disp = len(df_tienda[df_tienda['estado_producto'] == 'No disponible en el front'])
                    st.metric("⚠️ No disponibles", no_disp)
                
                # Info cuotas para Frávega
                if selected_store in ["Fravega", "Megatone"]:
                    st.markdown("---")
                    col1, col2 = st.columns(2)
                    with col1:
                        cuotas_ok = len(df_tienda[df_tienda['cuotas_correctas'] == True])
                        st.metric("💳 Cuotas correctas", cuotas_ok)
                    with col2:
                        cuotas_error = len(df_tienda[df_tienda['cuotas_correctas'] == False])
                        st.metric("💳 Cuotas incorrectas", cuotas_error)

with tab2:
    if st.session_state.audit_results is not None:
        df_results = st.session_state.audit_results
        
        st.markdown("### 📊 Resultados de la Auditoría")
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        with col1:
            filtros = ["Todos", "Errores de precio", "No disponibles"]
            if selected_store in ["Fravega", "Megatone"]:
                filtros.append("Cuotas incorrectas")
            filtro = st.selectbox("Filtrar:", filtros)
        
        with col2:
            st.metric("Total", len(df_results))
        
        with col3:
            if st.button("🔄 Actualizar"):
                st.rerun()
        
        # Aplicar filtros
        df_mostrar = df_results.copy()
        
        if filtro == "Errores de precio":
            df_mostrar = df_mostrar[(df_mostrar['precio_ok'] == False) & df_mostrar['precio_web'].notna()]
        elif filtro == "No disponibles":
            df_mostrar = df_mostrar[df_mostrar['estado_producto'] == 'No disponible en el front']
        elif filtro == "Cuotas incorrectas":
            df_mostrar = df_mostrar[df_mostrar['cuotas_correctas'] == False]
        
        # Columnas a mostrar
        if selected_store in ["Fravega", "Megatone"]:
            columnas_mostrar = ['sku', 'titulo', 'precio_maestro', 'precio_web', 'precio_tachado',
                               'descuento_%', 'variacion_precio_%', 'precio_ok', 
                               'cuotas_maestro', 'cuotas', 'cuotas_correctas',
                               'categoria', 'estado_producto']
        else:
            columnas_mostrar = ['sku', 'titulo', 'precio_maestro', 'precio_web', 'precio_tachado',
                               'descuento_%', 'variacion_precio_%', 'precio_ok',
                               'categoria', 'estado_producto']
        
        if st.checkbox("🔧 Mostrar URLs"):
            columnas_mostrar.append('url')
        
        # Crear DataFrame para mostrar
        columnas_existentes = [col for col in columnas_mostrar if col in df_mostrar.columns]
        df_display = df_mostrar[columnas_existentes].copy()
        
        # Renombrar columnas (espacios en lugar de guiones bajos)
        nombres_columnas = {
            'sku': 'SKU',
            'titulo': 'Título',
            'precio_maestro': 'Precio Maestro',
            'precio_web': 'Precio Web',
            'precio_tachado': 'Precio Tachado',
            'descuento_%': 'Descuento %',
            'variacion_precio_%': 'Variación %',
            'precio_ok': 'Precio OK',
            'cuotas_maestro': 'Cuotas Maestro',
            'cuotas': 'Cuotas Web',
            'cuotas_correctas': 'Cuotas OK',
            'categoria': 'Categoría',
            'estado_producto': 'Estado',
            'url': 'URL'
        }
        
        df_display = df_display.rename(columns=nombres_columnas)
        
        # Reemplazar valores booleanos
        if 'Precio OK' in df_display.columns:
            df_display['Precio OK'] = df_display['Precio OK'].map({True: '✅ Sí', False: '❌ No'})
        
        if 'Cuotas OK' in df_display.columns:
            df_display['Cuotas OK'] = df_display['Cuotas OK'].map({True: '✅ Sí', False: '❌ No'})
        
        st.dataframe(df_display, use_container_width=True, height=500)
        
        # Exportar
        st.markdown("---")
        st.markdown("### 💾 Exportar Resultados")
        
        col1, col2 = st.columns(2)
        
        with col1:
            excel_file = crear_excel_formateado(df_results, selected_store)
            st.download_button(
                "📊 Descargar Excel Profesional",
                data=excel_file,
                file_name=f"Auditoria_{selected_store}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        with col2:
            csv = df_mostrar.to_csv(index=False)
            st.download_button(
                "📄 Descargar CSV",
                data=csv,
                file_name=f"Auditoria_{selected_store}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    else:
        st.info("👆 Ejecuta una auditoría primero en la pestaña 'Cargar y Ejecutar'")

with tab3:
    if st.session_state.audit_results is not None:
        df = st.session_state.audit_results
        
        st.markdown("### 📈 Dashboard de Análisis")
        
        # Métricas principales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total = len(df)
            st.metric("📦 Total Productos", total)
        
        with col2:
            validos = df[df['precio_web'].notna()]
            if len(validos) > 0:
                precision = len(validos[validos['precio_ok'] == True]) / len(validos) * 100
            else:
                precision = 0
            st.metric("✅ Precisión", f"{precision:.1f}%")
        
        with col3:
            disponibles = len(df[df['estado_producto'] == 'Activo'])
            disp_pct = (disponibles / total * 100) if total > 0 else 0
            st.metric("🟢 Disponibilidad", f"{disp_pct:.1f}%")
        
        with col4:
            var_prom = df['variacion_precio_%'].abs().mean() if not df['variacion_precio_%'].isna().all() else 0
            st.metric("📊 Var. Promedio", f"{var_prom:.1f}%")
        
        # Gráficos
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            # Distribución de variaciones
            df_graf = df[df['variacion_precio_%'].notna() & (df['variacion_precio_%'] != 0)]
            if not df_graf.empty:
                fig = px.histogram(
                    df_graf, 
                    x='variacion_precio_%',
                    nbins=20,
                    title='Distribución de Variaciones de Precio',
                    labels={'variacion_precio_%': 'Variación %', 'count': 'Cantidad'}
                )
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay datos de variación para graficar")
        
        with col2:
            # Estado de productos
            estados_data = {
                'Estado': ['✅ Precio OK', '❌ Error Precio', '⚠️ No disponible'],
                'Cantidad': [
                    len(df[df['precio_ok'] == True]),
                    len(df[(df['precio_ok'] == False) & df['precio_web'].notna()]),
                    len(df[df['estado_producto'] == 'No disponible en el front'])
                ]
            }
            
            fig = px.pie(
                estados_data,
                values='Cantidad',
                names='Estado',
                title='Estado de Productos',
                color_discrete_sequence=['#90EE90', '#FFB6C1', '#FFD700']
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Análisis de cuotas (solo Frávega/Megatone)
        if selected_store in ["Fravega", "Megatone"] and 'cuotas' in df.columns:
            st.markdown("---")
            st.markdown("### 💳 Análisis de Cuotas")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Distribución de cuotas
                df_cuotas = df[df['cuotas'].notna()]
                if not df_cuotas.empty:
                    cuotas_count = df_cuotas['cuotas'].value_counts().sort_index()
                    fig = px.bar(
                        x=cuotas_count.index,
                        y=cuotas_count.values,
                        title='Distribución de Cuotas en el Front',
                        labels={'x': 'Número de Cuotas', 'y': 'Cantidad de Productos'}
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Cuotas correctas vs incorrectas
                if 'cuotas_correctas' in df.columns:
                    cuotas_ok = len(df[df['cuotas_correctas'] == True])
                    cuotas_error = len(df[df['cuotas_correctas'] == False])
                    
                    fig = px.pie(
                        values=[cuotas_ok, cuotas_error],
                        names=['✅ Correctas', '❌ Incorrectas'],
                        title='Validación de Cuotas',
                        color_discrete_sequence=['#90EE90', '#FFB6C1']
                    )
                    st.plotly_chart(fig, use_container_width=True)
        
        # Top productos con mayor variación
        st.markdown("---")
        st.markdown("### 🔝 Top 10 Productos con Mayor Variación")
        
        df_top = df[df['precio_web'].notna()].copy()
        df_top['var_abs'] = df_top['variacion_precio_%'].abs()
        df_top = df_top.nlargest(10, 'var_abs')[['sku', 'titulo', 'precio_maestro', 'precio_web', 'variacion_precio_%']]
        
        if not df_top.empty:
            df_top = df_top.rename(columns={
                'sku': 'SKU',
                'titulo': 'Título',
                'precio_maestro': 'Precio Maestro',
                'precio_web': 'Precio Web',
                'variacion_precio_%': 'Variación %'
            })
            st.dataframe(df_top, use_container_width=True, hide_index=True)
        else:
            st.info("No hay suficientes datos para mostrar")
        
    else:
        st.info("👆 Ejecuta una auditoría primero")

# Footer
st.markdown("---")
st.markdown(
    f"""<div style='text-align: center; color: gray; font-size: 0.9em;'>
        Sistema de Auditoría v6.0 con Frávega | {datetime.now().strftime("%d/%m/%Y %H:%M")}
    </div>""",
    unsafe_allow_html=True
)
