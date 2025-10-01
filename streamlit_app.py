import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
from io import BytesIO
import time
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side
except ImportError:
    st.error("pip install openpyxl")

st.set_page_config(page_title="Auditor", page_icon="🤖", layout="wide")

st.markdown("""
<style>
.audit-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 2rem; border-radius: 15px; color: white;
    margin-bottom: 2rem; text-align: center;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="audit-header"><h1>🤖 Auditor v6.2</h1></div>', unsafe_allow_html=True)

if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None

TIENDAS_CONFIG = {
    "ICBC": {
        "columnas_busqueda": ["ICBC", "icbc"],
        "selector_titulo": "h1[itemprop='name']",
        "selector_precio": "p.monto",
        "selector_precio_tachado": "p.precio-anterior",
        "selector_descuento": "p.descuento",
        "selector_categoria": "span.breadcrumb-span[itemprop='title']"
    },
    "Supervielle": {
        "columnas_busqueda": ["Supervielle", "supervielle"],
        "selector_titulo": "h1[itemprop='name']",
        "selector_precio": "span#our_price_display",
        "selector_precio_tachado": "span.price",
        "selector_descuento": "span#reduction_percent_display",
        "selector_categoria": "span[itemprop='title']"
    },
    "Galicia": {
        "columnas_busqueda": ["Galicia", "galicia"],
        "selector_titulo": "h1.productTitle",
        "selector_precio": "div.productPrice span",
        "selector_descuento": "span.discount.discount-percentage",
        "selector_categoria": "span[itemprop='name']"
    },
    "Ciudad": {
        "columnas_busqueda": ["Ciudad", "ciudad"],
        "selector_titulo": "h1.name",
        "selector_precio": "span.amount",
        "selector_precio_tachado": "div[itemprop='offers'] span.amount",
        "selector_categoria": "a[href*='/catalog/']"
    },
    "Fravega": {
        "columnas_busqueda": ["Fravega", "fravega", "FVG"],
        "columnas_cuotas": ["Cuotas FVG", "CSI FVG"]
    }
}

def detectar_columnas_automaticamente(df, tienda):
    config = TIENDAS_CONFIG[tienda]
    resultado = {'url': None, 'precio': None, 'sku': None, 'cuotas': None}
    
    for col in df.columns:
        col_lower = col.lower()
        if resultado['url'] is None:
            for busqueda in config['columnas_busqueda']:
                if busqueda.lower() in col_lower and 'url' in col_lower:
                    resultado['url'] = col
                    break
        if resultado['precio'] is None:
            for busqueda in config['columnas_busqueda']:
                if busqueda.lower() in col_lower and 'precio' in col_lower:
                    resultado['precio'] = col
                    break
        if resultado['sku'] is None:
            if any(word in col_lower for word in ['sku', 'codigo', 'código']):
                resultado['sku'] = col
        if 'columnas_cuotas' in config and resultado['cuotas'] is None:
            for busqueda in config.get('columnas_cuotas', []):
                if busqueda.lower() in col_lower:
                    resultado['cuotas'] = col
                    break
    return resultado

def limpiar_precio(valor):
    if pd.isna(valor):
        return np.nan
    precio_str = str(valor).replace('$', '').replace(' ', '').strip()
    if '.' in precio_str and ',' in precio_str:
        precio_str = precio_str.replace('.', '').replace(',', '.')
    elif '.' in precio_str:
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
    
    def scrape_fravega_playwright(self, url):
        if not url.startswith('http'):
            return {
                'url': url, 'titulo': None, 'precio_web': None, 'precio_tachado': None,
                'descuento_%': None, 'categoria': None, 'cuotas': None,
                'estado_producto': 'Error - URL incompleta', 'error': 'URL debe tener https://',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        resultado = {
            'url': url, 'titulo': None, 'precio_web': None, 'precio_tachado': None,
            'descuento_%': None, 'categoria': None, 'cuotas': None,
            'estado_producto': 'Activo', 'error': None,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until='networkidle', timeout=30000)
                page.wait_for_timeout(3000)
                
                # Verificar inhabilitado
                try:
                    boton = page.locator("button[data-test-id='product-buy-button']").first
                    boton.wait_for(timeout=5000)
                    if boton.is_disabled() or boton.get_attribute('disabled'):
                        resultado['estado_producto'] = 'A corregir - Inhabilitado'
                        resultado['cuotas'] = None
                except:
                    pass
                
                # Título
                try:
                    resultado['titulo'] = page.locator("h1[data-test-id='product-title']").text_content(timeout=5000).strip()
                except:
                    pass
                
                # Categoría
                try:
                    cats = page.locator("span[itemprop='name']").all()
                    validas = [c.text_content().strip() for c in cats if c.text_content().strip().lower() not in ['frávega', 'fravega', 'inicio']]
                    if validas:
                        resultado['categoria'] = validas[-1]
                except:
                    pass
                
                if resultado['estado_producto'] != 'Activo':
                    browser.close()
                    return resultado
                
                # Precios
                try:
                    resultado['precio_web'] = limpiar_precio(page.locator("span.sc-1d9b1d9e-0.sc-faa1a185-3").first.text_content(timeout=5000))
                except:
                    pass
                try:
                    resultado['precio_tachado'] = limpiar_precio(page.locator("span.sc-e081bce1-0.sc-faa1a185-4").first.text_content(timeout=5000))
                except:
                    pass
                try:
                    desc = page.locator("span.sc-e2aca368-0").first.text_content(timeout=5000)
                    m = re.search(r'(\d+)', desc)
                    if m:
                        resultado['descuento_%'] = float(m.group(1))
                except:
                    pass
                
                # Cuotas - CRÍTICO
                try:
                    html = page.content()
                    soup = BeautifulSoup(html, 'html.parser')
                    divs = soup.find_all('div', class_=lambda x: x and 'sc-3cba7521-0' in x)
                    
                    for div in divs:
                        span = div.find('span', class_=lambda x: x and 'sc-3cba7521-10' in x)
                        if not span:
                            continue
                        
                        texto = span.get_text()
                        match = re.search(r'(\d+)\s*cuotas', texto, re.IGNORECASE)
                        if not match:
                            continue
                        
                        num = int(match.group(1))
                        img_div = div.find('div', class_=lambda x: x and 'sc-3cba7521-3' in x)
                        
                        if img_div:
                            imgs = img_div.find_all('img', src=True)
                            visa = any('d91d7904a8578' in img.get('src', '') for img in imgs)
                            master = any('54c0d769ece1b' in img.get('src', '') for img in imgs)
                            
                            if visa and master:
                                resultado['cuotas'] = num
                                break
                    
                    if not resultado.get('cuotas'):
                        resultado['cuotas'] = 1
                except Exception as e:
                    resultado['cuotas'] = 1
                    resultado['error'] = f"Cuotas: {str(e)}"
                
                browser.close()
        except Exception as e:
            resultado['error'] = f"Playwright: {str(e)}"
            resultado['estado_producto'] = 'Error - Scraping fallido'
        
        return resultado
    
    def scrape_url(self, url):
        if not url or not isinstance(url, str) or not url.startswith('http'):
            return {
                'url': url, 'titulo': None, 'precio_web': None, 'precio_tachado': None,
                'descuento_%': None, 'categoria': None, 'cuotas': None,
                'estado_producto': 'Error - URL inválida', 'error': 'URL incorrecta',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        if self.tienda == "Fravega" and PLAYWRIGHT_AVAILABLE:
            return self.scrape_fravega_playwright(url)
        
        resultado = {
            'url': url, 'titulo': None, 'precio_web': None, 'precio_tachado': None,
            'descuento_%': None, 'categoria': None, 'cuotas': None,
            'estado_producto': 'Activo', 'error': None,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 404:
                resultado['estado_producto'] = 'No disponible'
                return resultado
            
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            if 'no longer available' in soup.get_text().lower():
                resultado['estado_producto'] = 'No disponible'
                return resultado
            
            # Título
            if 'selector_titulo' in self.config:
                elem = soup.select_one(self.config['selector_titulo'])
                if elem:
                    resultado['titulo'] = elem.get_text(strip=True)
            
            # Precio
            if 'selector_precio' in self.config:
                elem = soup.select_one(self.config['selector_precio'])
                if elem:
                    resultado['precio_web'] = limpiar_precio(elem.get_text(strip=True))
            
            # Precio tachado
            if 'selector_precio_tachado' in self.config:
                elem = soup.select_one(self.config['selector_precio_tachado'])
                if elem:
                    resultado['precio_tachado'] = limpiar_precio(elem.get_text(strip=True))
            
            # Descuento
            if 'selector_descuento' in self.config:
                elem = soup.select_one(self.config['selector_descuento'])
                if elem:
                    texto = elem.get_text(strip=True)
                    m = re.search(r'(\d+)', texto)
                    if m:
                        resultado['descuento_%'] = float(m.group(1))
            
            # Categoría
            if 'selector_categoria' in self.config:
                elems = soup.select(self.config['selector_categoria'])
                validas = [e.get_text(strip=True) for e in elems if e.get_text(strip=True).lower() not in ['inicio', 'home', self.tienda.lower()]]
                if validas:
                    resultado['categoria'] = validas[-1]
            
            # Galicia: calcular tachado
            if self.tienda == "Galicia" and not resultado['precio_tachado'] and resultado['descuento_%'] and resultado['precio_web']:
                resultado['precio_tachado'] = resultado['precio_web'] / (1 - resultado['descuento_%'] / 100)
        
        except Exception as e:
            resultado['error'] = str(e)
        
        return resultado

def realizar_scraping(df, config, tienda, pb, st_text):
    scraper = WebScraper(config, tienda)
    resultados = []
    
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(scraper.scrape_url, row['url']): idx for idx, row in df.iterrows() if pd.notna(row.get('url'))}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            idx = futures[future]
            res = future.result()
            res['idx'] = idx
            resultados.append(res)
            pb.progress(min(completed / len(futures), 1.0))
            st_text.text(f"{completed}/{len(futures)}...")
    return resultados

def crear_excel(df, tienda):
    output = BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"
    
    ws['A1'] = f'AUDITORÍA {tienda.upper()} - {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    ws['A1'].font = Font(bold=True, size=14)
    
    if tienda in ["Fravega", "Megatone"]:
        cols = ['SKU', 'Título', 'Precio Maestro', 'Precio Web', 'Precio Tachado',
               'Descuento %', 'Variación %', 'Precio OK', 'Cuotas Web', 'Cuotas Maestro',
               'Cuotas OK', 'Categoría', 'Estado Producto', 'Estado Scraping', 'URL']
        ws.merge_cells('A1:O1')
    else:
        cols = ['SKU', 'Título', 'Precio Maestro', 'Precio Web', 'Precio Tachado',
               'Descuento %', 'Variación %', 'Precio OK', 'Categoría', 'Estado Producto',
               'Estado Scraping', 'URL']
        ws.merge_cells('A1:L1')
    
    ws.append([])
    ws.append(cols)
    
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
    
    for _, row in df.iterrows():
        if tienda in ["Fravega", "Megatone"]:
            data = [row.get('sku'), row.get('titulo'), row.get('precio_maestro'),
                   row.get('precio_web'), row.get('precio_tachado'), row.get('descuento_%'),
                   row.get('variacion_precio_%'), 'Sí' if row.get('precio_ok') else 'No',
                   row.get('cuotas'), row.get('cuotas_maestro'),
                   'Sí' if row.get('cuotas_correctas') else 'No',
                   row.get('categoria'), row.get('estado_producto'),
                   row.get('estado_scraping'), row.get('url')]
        else:
            data = [row.get('sku'), row.get('titulo'), row.get('precio_maestro'),
                   row.get('precio_web'), row.get('precio_tachado'), row.get('descuento_%'),
                   row.get('variacion_precio_%'), 'Sí' if row.get('precio_ok') else 'No',
                   row.get('categoria'), row.get('estado_producto'),
                   row.get('estado_scraping'), row.get('url')]
        ws.append(data)
    
    wb.save(output)
    output.seek(0)
    return output

with st.sidebar:
    st.markdown('<div style="text-align:center; padding:1rem; background:linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius:10px;"><h2 style="color:white;">⚙️ Panel</h2></div>', unsafe_allow_html=True)
    selected_store = st.selectbox("🏪 Tienda", list(TIENDAS_CONFIG.keys()))
    
    if selected_store == "Fravega" and not PLAYWRIGHT_AVAILABLE:
        st.error("Playwright requerido")
    
    price_threshold = st.slider("🎯 Tolerancia (%)", 0, 20, 5, 1)
    modo = st.radio("🚀 Modo", ["🧪 Prueba", "⚡ Rápida (10)", "📊 Completa"])
    
    if "Completa" in modo:
        max_prod = st.number_input("Límite:", 10, 1000, 100, 10)
    else:
        max_prod = 10

tab1, tab2, tab3 = st.tabs(["📁 Cargar", "📊 Resultados", "📈 Dashboard"])

with tab1:
    st.markdown("### 📝 Auditoría")
    uploaded = st.file_uploader("Excel", type=['xlsx', 'xls'])
    
    if uploaded:
        df_maestro = pd.read_excel(uploaded)
        col1, col2, col3 = st.columns(3)
        col1.metric("Archivo", uploaded.name[:15])
        col2.metric("Filas", len(df_maestro))
        col3.metric("Columnas", len(df_maestro.columns))
        
        cols_det = detectar_columnas_automaticamente(df_maestro, selected_store)
        
        st.markdown("### Columnas")
        col1, col2 = st.columns(2)
        
        with col1:
            url_col = cols_det['url'] if cols_det['url'] else st.selectbox("URL:", df_maestro.columns)
            sku_col = cols_det['sku'] if cols_det['sku'] else st.selectbox("SKU:", df_maestro.columns)
        
        with col2:
            precio_col = cols_det['precio'] if cols_det['precio'] else st.selectbox("Precio:", df_maestro.columns)
            cuotas_col = None
            if selected_store in ["Fravega", "Megatone"]:
                cuotas_col = cols_det['cuotas'] if cols_det['cuotas'] else st.selectbox("Cuotas:", df_maestro.columns)
        
        df_t = df_maestro[df_maestro[url_col].notna()].copy()
        rename = {url_col: 'url', sku_col: 'sku', precio_col: 'precio_maestro'}
        if cuotas_col:
            rename[cuotas_col] = 'cuotas_maestro'
        df_t = df_t.rename(columns=rename)
        df_t['precio_maestro'] = df_t['precio_maestro'].apply(limpiar_precio)
        if 'cuotas_maestro' in df_t.columns:
            df_t['cuotas_maestro'] = pd.to_numeric(df_t['cuotas_maestro'], errors='coerce')
        
        df_t = df_t.head(max_prod if "Completa" in modo else 10)
        
        if st.button("🚀 INICIAR", type="primary", use_container_width=True):
            if "Prueba" in modo:
                pb = st.progress(0)
                status = st.empty()
                res = []
                for i, (idx, row) in enumerate(df_t.iterrows()):
                    var = np.random.uniform(-10, 10)
                    pm = row.get('precio_maestro', 10000)
                    if pd.isna(pm):
                        pm = 10000
                    pw = float(pm * (1 + var/100))
                    res.append({
                        'idx': idx, 'url': row['url'],
                        'titulo': f"Producto {row.get('sku', i+1)}",
                        'precio_web': pw, 'precio_tachado': pw * 1.3,
                        'descuento_%': np.random.randint(10, 40),
                        'categoria': "Prueba",
                        'cuotas': np.random.choice([1, 3, 6, 9, 12]) if selected_store == "Fravega" else None,
                        'estado_producto': 'Activo', 'error': None
                    })
                    pb.progress((i + 1) / len(df_t))
                    status.text(f"{i + 1}/{len(df_t)}")
                    time.sleep(0.05)
                pb.empty()
                status.empty()
            else:
                pb = st.progress(0)
                status = st.empty()
                res = realizar_scraping(df_t, TIENDAS_CONFIG[selected_store], selected_store, pb, status)
                pb.empty()
                status.empty()
            
            for r in res:
                idx = r['idx']
                df_t.loc[idx, 'titulo'] = r.get('titulo')
                df_t.loc[idx, 'precio_web'] = r.get('precio_web')
                df_t.loc[idx, 'precio_tachado'] = r.get('precio_tachado')
                df_t.loc[idx, 'descuento_%'] = r.get('descuento_%')
                df_t.loc[idx, 'categoria'] = r.get('categoria')
                df_t.loc[idx, 'cuotas'] = r.get('cuotas')
                df_t.loc[idx, 'estado_producto'] = r.get('estado_producto')
                df_t.loc[idx, 'error_scraping'] = r.get('error')
            
            df_t['variacion_precio_%'] = 0.0
            mask = (df_t['precio_web'].notna()) & (df_t['precio_maestro'].notna()) & (df_t['precio_maestro'] != 0)
            
            if mask.any():
                df_t.loc[mask, 'precio_web'] = pd.to_numeric(df_t.loc[mask, 'precio_web'], errors='coerce')
                df_t.loc[mask, 'precio_maestro'] = pd.to_numeric(df_t.loc[mask, 'precio_maestro'], errors='coerce')
                mask = (df_t['precio_web'].notna()) & (df_t['precio_maestro'].notna()) & (df_t['precio_maestro'] != 0)
                if mask.any():
                    df_t.loc[mask, 'variacion_precio_%'] = ((df_t.loc[mask, 'precio_web'] - df_t.loc[mask, 'precio_maestro']) / df_t.loc[mask, 'precio_maestro'] * 100).round(2)
            
            df_t['precio_ok'] = False
            df_t.loc[mask, 'precio_ok'] = abs(df_t.loc[mask, 'variacion_precio_%']) <= price_threshold
            
            if selected_store in ["Fravega", "Megatone"] and 'cuotas_maestro' in df_t.columns:
                df_t['cuotas_correctas'] = False
                mask_c = df_t['cuotas'].notna()
                df_t.loc[mask_c, 'cuotas_correctas'] = df_t.loc[mask_c, 'cuotas'] == df_t.loc[mask_c, 'cuotas_maestro']
            else:
                df_t['cuotas_correctas'] = True
            
            def eval_scrap(r):
                if pd.notna(r.get('error_scraping')):
                    return '❌ Error'
                estado = r.get('estado_producto', 'Activo')
                if 'Error' in estado:
                    return '❌ Error'
                if 'Inhabilitado' in estado:
                    return '⚠️ Parcial (Inhabilitado)' if pd.notna(r.get('titulo')) else '⚠️ Incompleto'
                if 'No disponible' in estado:
                    return '⚠️ No disponible'
                if pd.notna(r.get('titulo')) and pd.notna(r.get('precio_web')) and pd.notna(r.get('categoria')):
                    return '✅ Completo'
                elif pd.notna(r.get('precio_web')):
                    return '⚠️ Parcial'
                else:
                    return '❌ Fallido'
            
            df_t['estado_scraping'] = df_t.apply(eval_scrap, axis=1)
            st.session_state.audit_results = df_t
            st.success(f"✅ Completado: {len(df_t)} productos")

with tab2:
    if st.session_state.audit_results is not None:
        df_r = st.session_state.audit_results
        st.markdown("### Resultados")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            filtros = ["Todos", "Errores", "No disponibles"]
            if selected_store in ["Fravega", "Megatone"]:
                filtros.append("Cuotas incorrectas")
            filtro = st.selectbox("Filtrar:", filtros)
        
        df_m = df_r.copy()
        if filtro == "Errores":
            df_m = df_m[(df_m['precio_ok'] == False) & df_m['precio_web'].notna()]
        elif filtro == "No disponibles":
            df_m = df_m[df_m['estado_producto'].str.contains('No disponible', na=False)]
        elif filtro == "Cuotas incorrectas":
            df_m = df_m[df_m['cuotas_correctas'] == False]
        
        cols_m = ['sku', 'titulo', 'precio_maestro', 'precio_web', 'precio_tachado',
                 'descuento_%', 'variacion_precio_%', 'precio_ok', 'categoria',
                 'estado_producto', 'estado_scraping']
        
        if selected_store in ["Fravega", "Megatone"]:
            cols_m.insert(8, 'cuotas_maestro')
            cols_m.insert(9, 'cuotas')
            cols_m.insert(10, 'cuotas_correctas')
        
        cols_ex = [c for c in cols_m if c in df_m.columns]
        df_disp = df_m[cols_ex].copy()
        
        nombres = {
            'sku': 'SKU', 'titulo': 'Título', 'precio_maestro': 'Precio Maestro',
            'precio_web': 'Precio Web', 'precio_tachado': 'Precio Tachado',
            'descuento_%': 'Descuento %', 'variacion_precio_%': 'Variación %',
            'precio_ok': 'Precio OK', 'cuotas_maestro': 'Cuotas Maestro',
            'cuotas': 'Cuotas Web', 'cuotas_correctas': 'Cuotas OK',
            'categoria': 'Categoría', 'estado_producto': 'Estado Producto',
            'estado_scraping': 'Estado Scraping'
        }
        
        df_disp = df_disp.rename(columns=nombres)
        if 'Precio OK' in df_disp.columns:
            df_disp['Precio OK'] = df_disp['Precio OK'].map({True: '✅', False: '❌'})
        if 'Cuotas OK' in df_disp.columns:
            df_disp['Cuotas OK'] = df_disp['Cuotas OK'].map({True: '✅', False: '❌'})
        
        st.dataframe(df_disp, use_container_width=True, height=500)
        
        st.markdown("### Exportar")
        col1, col2 = st.columns(2)
        with col1:
            excel = crear_excel(df_r, selected_store)
            st.download_button("📊 Excel", excel, f"Audit_{selected_store}_{datetime.now().strftime('%Y%m%d')}.xlsx", use_container_width=True)
    else:
        st.info("Ejecuta auditoría primero")

with tab3:
    if st.session_state.audit_results is not None:
        df = st.session_state.audit_results
        if 'precio_ok' in df.columns:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total", len(df))
            ok = len(df[df['precio_ok'] == True])
            col2.metric("✅ OK", ok)
            err = len(df[(df['precio_ok'] == False) & df['precio_web'].notna()])
            col3.metric("❌ Errores", err)
    else:
        st.info("Ejecuta auditoría primero")

st.markdown(f'<div style="text-align:center; color:gray;">v6.2 | {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>', unsafe_allow_html=True)
