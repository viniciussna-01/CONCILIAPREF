# app.py
import streamlit as st
import pandas as pd
import io
import unicodedata

# ── Config ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CONCILIA PREFEITURA",
    page_icon="🔍",
    layout="wide"
)

# ── Estilos ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        border-left: 5px solid #ccc;
    }
    .card-verde  { border-left-color: #28a745; }
    .card-vermelho { border-left-color: #dc3545; }
    .card-amarelo { border-left-color: #ffc107; }
    .card-azul   { border-left-color: #007bff; }
    .card-titulo { font-size: 14px; color: #666; margin-bottom: 4px; }
    .card-valor  { font-size: 32px; font-weight: bold; }
    .status-ok   { color: #28a745; font-weight: bold; }
    .status-err  { color: #dc3545; font-weight: bold; }
    .status-warn { color: #ffc107; font-weight: bold; }
    .status-div  { color: #fd7e14; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ── Funções ──────────────────────────────────────────────────────────────────
def clean_valor(v):
    """Converte valores de texto (CSV) para float. Retorna 0 se inválido."""
    if pd.isna(v) or v == '': 
        return 0.0
    try:
        v = str(v).strip()
        v = v.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        result = float(v)
        return max(result, 0.0)  # Garante valores não-negativos
    except:
        return 0.0

def status_badge(s):
    cores = {
        'Conciliado':              '<span class="status-ok">✅ Conciliado</span>',
        'Divergência de Valor':    '<span class="status-div">🔶 Divergência de Valor</span>',
        'Ausente na Prefeitura':   '<span class="status-err">❌ Ausente na Prefeitura</span>',
        'Ausente no OMIE':         '<span class="status-warn">⚠️ Ausente no OMIE</span>',
    }
    return cores.get(s, s)

def normalize_col_name(name):
    text = str(name).strip().lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('-', ' ').replace('_', ' ')
    text = ' '.join(text.split())
    return text

def resolve_columns(df, required_map, source_name):
    normalized_to_original = {
        normalize_col_name(col): col
        for col in df.columns
    }

    resolved = {}
    missing = []
    for target_col, aliases in required_map.items():
        found = None
        for alias in aliases:
            normalized_alias = normalize_col_name(alias)
            if normalized_alias in normalized_to_original:
                found = normalized_to_original[normalized_alias]
                break
        if found is None:
            missing.append(target_col)
        else:
            resolved[target_col] = found

    if missing:
        available = ', '.join(str(col) for col in df.columns)
        expected = ', '.join(missing)
        raise ValueError(
            f"Arquivo {source_name}: não encontrei as colunas obrigatórias ({expected}). "
            f"Colunas disponíveis: {available}"
        )

    return resolved


OMIE_REQUIRED_COLUMNS = {
    'NFE': ['Número da NFS-e', 'Numero da NFS-e', 'NFS-e', 'NFS e', 'Numero NFS-e'],
    'Nome_OMIE': ['Cliente (Nome Fantasia)', 'Cliente', 'Nome Fantasia', 'Razão Social'],
    'Valor_OMIE': ['Valor Líquido', 'Valor Liquido', 'Valor', 'Valor Total'],
}

PREF_REQUIRED_COLUMNS = {
    'NFE': ['Nº NFS-e', 'N° NFS-e', 'Numero NFS-e', 'Número NFS-e', 'NFS-e'],
    'Nome_Pref': ['Razão Social do Tomador', 'Razao Social do Tomador', 'Tomador', 'Razão Social'],
    'Valor_Pref': [' Valor dos Serviços ', 'Valor dos Serviços', 'Valor dos Servicos', 'Valor Serviço', 'Valor Servico'],
}

def processar_omie(file):
    """Processa arquivo Excel do OMIE com validações robustas."""
    df = pd.read_excel(file)
    cols = resolve_columns(df, OMIE_REQUIRED_COLUMNS, 'OMIE')

    # Filtra linhas com NFE válidas
    df = df[df[cols['NFE']].notna()].copy()
    df[cols['NFE']] = pd.to_numeric(df[cols['NFE']], errors='coerce')
    df = df[df[cols['NFE']].notna()].copy()
    
    if len(df) == 0:
        raise ValueError("Nenhuma NFE válida encontrada no arquivo OMIE")
    
    # Converte NFE para int
    df[cols['NFE']] = df[cols['NFE']].astype(int)
    
    # Garante que Valor_OMIE é numérico
    df[cols['Valor_OMIE']] = pd.to_numeric(df[cols['Valor_OMIE']], errors='coerce')
    df[cols['Valor_OMIE']] = df[cols['Valor_OMIE']].fillna(0).astype(float)

    # Agrupa por NFE (soma valores se houver múltiplas linhas por NFE)
    agg = df.groupby(cols['NFE']).agg(
        Nome_OMIE=(cols['Nome_OMIE'], 'first'),
        Valor_OMIE=(cols['Valor_OMIE'], 'sum'),
    ).reset_index()
    agg.columns = ['NFE', 'Nome_OMIE', 'Valor_OMIE']
    
    # Remove valores NaN finais
    agg['Valor_OMIE'] = agg['Valor_OMIE'].fillna(0).astype(float)
    
    return agg

def processar_pref(file):
    """Processa arquivo CSV da Prefeitura com validações robustas."""
    try:
        df = pd.read_csv(file, encoding='latin-1', sep=None, engine='python')
    except Exception:
        try:
            df = pd.read_csv(file, encoding='utf-8', sep=None, engine='python')
        except Exception as e:
            raise ValueError(f"Não consegui ler o arquivo CSV da Prefeitura. Erro: {e}")
    
    cols = resolve_columns(df, PREF_REQUIRED_COLUMNS, 'Prefeitura')

    # Filtra linhas com NFE válidas
    df = df[df[cols['NFE']].notna()].copy()
    df[cols['NFE']] = pd.to_numeric(df[cols['NFE']], errors='coerce')
    df = df[df[cols['NFE']].notna()].copy()
    
    if len(df) == 0:
        raise ValueError("Nenhuma NFE válida encontrada no arquivo da Prefeitura")
    
    # Converte NFE para int
    df[cols['NFE']] = df[cols['NFE']].astype(int)
    
    # Limpa e converte valores
    df[cols['Valor_Pref']] = df[cols['Valor_Pref']].apply(clean_valor).astype(float)

    return df[[cols['NFE'], cols['Nome_Pref'], cols['Valor_Pref']]].rename(columns={
        cols['NFE']: 'NFE',
        cols['Nome_Pref']: 'Nome_Pref',
        cols['Valor_Pref']: 'Valor_Pref'
    })

def conciliar(omie, pref):
    """Realiza merge entre OMIE e Prefeitura, identificando divergências."""
    if omie.empty or pref.empty:
        raise ValueError("Um dos arquivos após processamento ficou vazio")
    
    merged = omie.merge(pref, on='NFE', how='outer', indicator=True)
    
    # Garante tipos corretos
    merged['Valor_OMIE'] = merged['Valor_OMIE'].fillna(0).astype(float)
    merged['Valor_Pref'] = merged['Valor_Pref'].fillna(0).astype(float)
    merged['Dif_Valor'] = (merged['Valor_OMIE'] - merged['Valor_Pref']).round(2)

    def get_status(row):
        if row['_merge'] == 'left_only':  
            return 'Ausente na Prefeitura'
        if row['_merge'] == 'right_only': 
            return 'Ausente no OMIE'
        if abs(row['Dif_Valor']) < 0.01:  
            return 'Conciliado'
        return 'Divergência de Valor'

    merged['Status'] = merged.apply(get_status, axis=1)
    merged = merged.drop(columns=['_merge'])
    merged = merged.sort_values('NFE').reset_index(drop=True)
    
    return merged

def to_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Conciliação')
    return buf.getvalue()

# ── Header ───────────────────────────────────────────────────────────────────
st.title("🔍 Conciliação OMIE × Prefeitura")
st.markdown("Faça o upload dos dois arquivos e clique em **Conciliar** para identificar divergências automaticamente.")
st.subheader("Feito por: Vinícius Sena")
st.markdown("Qualquer Erro ou problema, pode me chamar no TEAMS!")

st.divider()

# ── Upload ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 Arquivo OMIE")
    file_omie = st.file_uploader("Selecione o Excel do OMIE", type=["xlsx", "xls"], key="omie")
    if file_omie:
        st.success(f"✅ {file_omie.name} carregado!")

with col2:
    st.subheader("🏛️ Extrato da Prefeitura")
    file_pref = st.file_uploader("Selecione o CSV da Prefeitura", type=["csv"], key="pref")
    if file_pref:
        st.success(f"✅ {file_pref.name} carregado!")

st.divider()

# ── Conciliar ─────────────────────────────────────────────────────────────────
if file_omie and file_pref:
    if st.button("🚀 Conciliar Agora", type="primary", use_container_width=True):

        with st.spinner("Processando conciliação..."):
            try:
                omie = processar_omie(file_omie)
                st.success(f"✅ OMIE processado: {len(omie)} NFEs válidas")
                
                pref = processar_pref(file_pref)
                st.success(f"✅ Prefeitura processado: {len(pref)} NFEs válidas")
                
                resultado = conciliar(omie, pref)
                st.session_state['resultado'] = resultado
                st.success(f"✅ Conciliação completa: {len(resultado)} registros processados")
                
            except ValueError as e:
                st.error(f"❌ Erro nos dados: {e}")
            except Exception as e:
                st.error(f"❌ Erro inesperado: {e}")
                st.info("💡 Dica: Verifique se os arquivos têm as colunas esperadas e se os dados estão formatados corretamente.")

elif not file_omie or not file_pref:
    st.info("⬆️ Faça o upload dos dois arquivos para habilitar a conciliação.")

# ── Resultado ─────────────────────────────────────────────────────────────────
if 'resultado' in st.session_state:
    resultado = st.session_state['resultado']
    total     = len(resultado)
    ok        = (resultado['Status'] == 'Conciliado').sum()
    div_val   = (resultado['Status'] == 'Divergência de Valor').sum()
    aus_pref  = (resultado['Status'] == 'Ausente na Prefeitura').sum()
    aus_omie  = (resultado['Status'] == 'Ausente no OMIE').sum()

    st.subheader("📊 Resumo da Conciliação")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""<div class="metric-card card-azul">
            <div class="card-titulo">Total de NFEs</div>
            <div class="card-valor">{total}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="metric-card card-verde">
            <div class="card-titulo">✅ Conciliadas</div>
            <div class="card-valor" style="color:#28a745">{ok}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="metric-card card-vermelho">
            <div class="card-titulo">🔶 Divergência Valor</div>
            <div class="card-valor" style="color:#fd7e14">{div_val}</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="metric-card card-vermelho">
            <div class="card-titulo">❌ Ausente na Pref.</div>
            <div class="card-valor" style="color:#dc3545">{aus_pref}</div>
        </div>""", unsafe_allow_html=True)
    with c5:
        st.markdown(f"""<div class="metric-card card-amarelo">
            <div class="card-titulo">⚠️ Ausente no OMIE</div>
            <div class="card-valor" style="color:#ffc107">{aus_omie}</div>
        </div>""", unsafe_allow_html=True)

    # Barra de progresso
    pct = int((ok / total) * 100) if total > 0 else 0
    st.markdown(f"<br>**Taxa de conciliação: {pct}%**", unsafe_allow_html=True)
    st.progress(pct / 100)

    st.divider()

    # ── Filtros ───────────────────────────────────────────────────────────────
    st.subheader("🔎 Detalhamento das NFEs")
    col_f1, col_f2 = st.columns([1, 3])
    with col_f1:
        filtro = st.selectbox("Filtrar por status:", [
            "Todos", "Conciliado", "Divergência de Valor",
            "Ausente na Prefeitura", "Ausente no OMIE"
        ])
    with col_f2:
        busca = st.text_input("Buscar por NFE ou nome do cliente:")

    df_view = resultado.copy()
    if filtro != "Todos":
        df_view = df_view[df_view['Status'] == filtro]
    if busca:
        mask = (
            df_view['NFE'].astype(str).str.contains(busca, case=False, na=False) |
            df_view['Nome_OMIE'].astype(str).str.contains(busca, case=False, na=False) |
            df_view['Nome_Pref'].astype(str).str.contains(busca, case=False, na=False)
        )
        df_view = df_view[mask]

    # Renderizar tabela com badges HTML
    df_html = df_view.copy()
    df_html['Status'] = df_html['Status'].apply(status_badge)
    df_html['Valor_OMIE'] = df_html['Valor_OMIE'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    df_html['Valor_Pref'] = df_html['Valor_Pref'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    df_html['Dif_Valor']  = df_html['Dif_Valor'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if pd.notna(x) else '-')

    df_html = df_html.rename(columns={
        'NFE': 'Nº NFE',
        'Nome_OMIE': 'Cliente (OMIE)',
        'Nome_Pref': 'Tomador (Prefeitura)',
        'Valor_OMIE': 'Valor OMIE',
        'Valor_Pref': 'Valor Prefeitura',
        'Dif_Valor': 'Diferença',
    })

    st.markdown(
        df_html.to_html(escape=False, index=False),
        unsafe_allow_html=True
    )

    st.caption(f"Mostrando {len(df_view)} de {total} registros.")

    # ── Export ────────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📥 Exportar Resultado")
    col_e1, col_e2 = st.columns(2)
    with col_e1:
        st.download_button(
            label="⬇️ Baixar Excel completo",
            data=to_excel(resultado),
            file_name="conciliacao_resultado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    with col_e2:
        erros = resultado[resultado['Status'] != 'Conciliado']
        st.download_button(
            label="⬇️ Baixar apenas erros/divergências",
            data=to_excel(erros),
            file_name="conciliacao_erros.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            disabled=(len(erros) == 0)
        )
else:
    st.markdown("""
    ### 📌 Como usar
    1. Faça o upload do **Excel do OMIE** (colunas: Número da NFS-e, Cliente, Valor Líquido)
    2. Faça o upload do **CSV da Prefeitura** (colunas: Nº NFS-e, Razão Social do Tomador, Valor dos Serviços)
    3. Clique em **🚀 Conciliar Agora**
    4. Veja o resultado e exporte o relatório
    """)
