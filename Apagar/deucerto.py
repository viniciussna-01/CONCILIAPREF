# app.py
import streamlit as st
import pandas as pd
import io

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
    if pd.isna(v): return 0.0
    v = str(v).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try: return float(v)
    except: return 0.0

def status_badge(s):
    cores = {
        'Conciliado':              '<span class="status-ok">✅ Conciliado</span>',
        'Divergência de Valor':    '<span class="status-div">🔶 Divergência de Valor</span>',
        'Ausente na Prefeitura':   '<span class="status-err">❌ Ausente na Prefeitura</span>',
        'Ausente no OMIE':         '<span class="status-warn">⚠️ Ausente no OMIE</span>',
    }
    return cores.get(s, s)

@st.cache_data
def processar_omie(file):
    df = pd.read_excel(file)
    df = df[df['Número da NFS-e'].notna()]
    df['Número da NFS-e'] = df['Número da NFS-e'].astype(int)
    agg = df.groupby('Número da NFS-e').agg(
        Nome_OMIE=('Cliente (Nome Fantasia)', 'first'),
        Valor_OMIE=('Valor Líquido', 'sum'),
    ).reset_index()
    agg.columns = ['NFE', 'Nome_OMIE', 'Valor_OMIE']
    return agg

@st.cache_data
def processar_pref(file):
    try:
        df = pd.read_csv(file, encoding='latin-1', sep=None, engine='python')
    except Exception:
        df = pd.read_csv(file, encoding='utf-8', sep=None, engine='python')
    df = df[df['Nº NFS-e'].notna()].copy()
    df['Nº NFS-e'] = df['Nº NFS-e'].astype(int)
    df[' Valor dos Serviços '] = df[' Valor dos Serviços '].apply(clean_valor)
    return df[['Nº NFS-e', 'Razão Social do Tomador', ' Valor dos Serviços ']].rename(columns={
        'Nº NFS-e': 'NFE',
        'Razão Social do Tomador': 'Nome_Pref',
        ' Valor dos Serviços ': 'Valor_Pref'
    })

def conciliar(omie, pref):
    merged = omie.merge(pref, on='NFE', how='outer', indicator=True)
    merged['Valor_OMIE']  = merged['Valor_OMIE'].fillna(0)
    merged['Valor_Pref']  = merged['Valor_Pref'].fillna(0)
    merged['Dif_Valor']   = (merged['Valor_OMIE'] - merged['Valor_Pref']).round(2)

    def get_status(row):
        if row['_merge'] == 'left_only':  return 'Ausente na Prefeitura'
        if row['_merge'] == 'right_only': return 'Ausente no OMIE'
        if abs(row['Dif_Valor']) < 0.01:  return 'Conciliado'
        return 'Divergência de Valor'

    merged['Status'] = merged.apply(get_status, axis=1)
    merged = merged.drop(columns=['_merge'])
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
            omie = processar_omie(file_omie)
            pref = processar_pref(file_pref)
            resultado = conciliar(omie, pref)

        st.session_state['resultado'] = resultado

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
