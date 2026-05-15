import io
import unicodedata
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(page_title="CONCILIA PREFEITURA", page_icon="🔍", layout="wide")

st.markdown(
    """
<style>
.metric-card { background:#f8f9fa; border-radius:12px; padding:20px; text-align:center; border-left:5px solid #ccc; }
.card-verde { border-left-color:#28a745; }
.card-vermelho { border-left-color:#dc3545; }
.card-amarelo { border-left-color:#ffc107; }
.card-azul { border-left-color:#007bff; }
.card-roxo { border-left-color:#6f42c1; }
.card-titulo { font-size:14px; color:#666; margin-bottom:4px; }
.card-valor { font-size:32px; font-weight:bold; }
.status-ok { color:#28a745; font-weight:bold; }
.status-err { color:#dc3545; font-weight:bold; }
.status-warn { color:#ffc107; font-weight:bold; }
.status-div { color:#fd7e14; font-weight:bold; }
</style>
""",
    unsafe_allow_html=True,
)


# ==========================
# SESSION
# ==========================
def init_session():
    defaults = {
        "logado": False,
        "usuario": None,
        "nome_exibicao": None,
        "perfil": None,
        "resultado": None,
    }

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ==========================
# SUPABASE
# ==========================
def get_supabase_config():
    return {
        "url": st.secrets["supabase"]["url"].rstrip("/"),
        "key": st.secrets["supabase"]["key"],
    }


def sb_headers(prefer=None):
    cfg = get_supabase_config()

    headers = {
        "apikey": cfg["key"],
        "Authorization": f"Bearer {cfg['key']}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


def sb_table_url(table_name):
    cfg = get_supabase_config()
    return f"{cfg['url']}/rest/v1/{table_name}"


def sb_insert(table_name, payload, return_representation=True):
    prefer = "return=representation" if return_representation else "return=minimal"

    resp = requests.post(
        sb_table_url(table_name),
        headers=sb_headers(prefer=prefer),
        json=payload,
        timeout=30,
    )

    if not resp.ok:
        raise RuntimeError(
            f"Erro Supabase INSERT em {table_name}: {resp.status_code} - {resp.text}"
        )

    if return_representation:
        data = resp.json()
        return data if isinstance(data, list) else [data]

    return []


def sb_select(table_name, query="select=*"):
    resp = requests.get(
        f"{sb_table_url(table_name)}?{query}",
        headers=sb_headers(),
        timeout=30,
    )

    if not resp.ok:
        raise RuntimeError(
            f"Erro Supabase SELECT em {table_name}: {resp.status_code} - {resp.text}"
        )

    return resp.json()


# ==========================
# LOGIN
# ==========================
def autenticar(username, password):
    usuarios = {
        st.secrets["auth"]["admin_user"]: {
            "nome_exibicao": st.secrets["auth"]["admin_name"],
            "senha": st.secrets["auth"]["admin_password"],
            "perfil": "admin",
        },
        st.secrets["auth"]["daniela_user"]: {
            "nome_exibicao": "Daniela",
            "senha": st.secrets["auth"]["daniela_password"],
            "perfil": "user",
        },
        st.secrets["auth"]["victor_user"]: {
            "nome_exibicao": "Victor",
            "senha": st.secrets["auth"]["victor_password"],
            "perfil": "user",
        },
        st.secrets["auth"]["suelen_user"]: {
            "nome_exibicao": "Suelen",
            "senha": st.secrets["auth"]["suelen_password"],
            "perfil": "user",
        },
    }

    user = usuarios.get(username)
    if user and password == user["senha"]:
        return {
            "username": username,
            "nome_exibicao": user["nome_exibicao"],
            "perfil": user["perfil"],
        }

    return None


# ==========================
# HISTORICO
# ==========================
def salvar_historico(resultado, usuario, perfil, empresa, arquivo_omie, arquivo_pref):
    payload_conc = {
        "usuario": usuario,
        "perfil": perfil,
        "empresa": empresa,
        "arquivo_omie": arquivo_omie,
        "arquivo_pref": arquivo_pref,
        "total_nfes": int(len(resultado)),
        "conciliadas": int((resultado["Status"] == "Conciliado").sum()),
        "divergencia_valor": int((resultado["Status"] == "Divergência de Valor").sum()),
        "ausente_prefeitura": int((resultado["Status"] == "Ausente na Prefeitura").sum()),
        "ausente_omie": int((resultado["Status"] == "Ausente no OMIE").sum()),
        "criado_em": datetime.now(timezone.utc).isoformat(),
    }

    inserted = sb_insert("conciliacoes", payload_conc, return_representation=True)
    conciliacao_id = inserted[0]["id"]

    itens = []
    for _, r in resultado.iterrows():
        valor_pref = r.get("Valor_Final_Pref", r.get("Valor_Pref", 0))

        itens.append(
            {
                "conciliacao_id": conciliacao_id,
                "nfe": str(r["NFE"]) if pd.notna(r["NFE"]) else None,
                "nome_omie": None if pd.isna(r.get("Nome_OMIE")) else str(r["Nome_OMIE"]),
                "nome_pref": None if pd.isna(r.get("Nome_Pref")) else str(r["Nome_Pref"]),
                "valor_omie": float(r["Valor_OMIE"]) if pd.notna(r["Valor_OMIE"]) else 0,
                "valor_pref": float(valor_pref) if pd.notna(valor_pref) else 0,
                "dif_valor": float(r["Dif_Valor"]) if pd.notna(r["Dif_Valor"]) else 0,
                "status": str(r["Status"]),
                "empresa": empresa,
                "criado_em": datetime.now(timezone.utc).isoformat(),
            }
        )

    if itens:
        sb_insert("conciliacao_itens", itens, return_representation=False)


def carregar_historico():
    data = sb_select("conciliacoes", "select=*&order=criado_em.desc")
    return pd.DataFrame(data)


def carregar_estudo_empresas():
    data = sb_select("conciliacao_itens", "select=empresa,status&status=neq.Conciliado")
    df = pd.DataFrame(data)

    if df.empty:
        return df

    df = df[df["empresa"].notna() & (df["empresa"].astype(str).str.strip() != "")].copy()
    if df.empty:
        return df

    estudo = (
        df.groupby("empresa")
        .agg(
            total_itens_problema=("empresa", "count"),
            divergencia_valor=("status", lambda x: (x == "Divergência de Valor").sum()),
            ausente_prefeitura=("status", lambda x: (x == "Ausente na Prefeitura").sum()),
            ausente_omie=("status", lambda x: (x == "Ausente no OMIE").sum()),
            nota_cancelada=("status", lambda x: (x == "NOTA CANCELADA").sum()),
        )
        .reset_index()
        .sort_values(["total_itens_problema", "empresa"], ascending=[False, True])
    )

    return estudo


# ==========================
# HELPERS
# ==========================
def normalize_col_name(name):
    text = str(name).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("-", " ").replace("_", " ")
    text = " ".join(text.split())
    return text


def clean_valor(v):
    if pd.isna(v) or v == "":
        return 0.0

    try:
        if not isinstance(v, str):
            return float(v)

        text = v.strip()
        text = text.replace("R$", "")
        text = text.replace(" ", "")

        # Trata formatos BR e EN sem inflar decimal em 100x.
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "")
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")

        return float(text)

    except Exception:
        return 0.0


def clean_documento(doc):
    if pd.isna(doc):
        return ""

    return "".join(filter(str.isdigit, str(doc)))


def identificar_tipo_documento(doc):
    if pd.isna(doc):
        return "POSSIVELMENTE ESTRANGEIRO"

    doc = "".join(filter(str.isdigit, str(doc)))

    if doc == "":
        return "POSSIVELMENTE ESTRANGEIRO"

    if set(doc) == {"0"}:
        return "POSSIVELMENTE ESTRANGEIRO"

    if len(doc) == 11:
        return "CPF"

    if len(doc) == 14:
        return "CNPJ"

    return "ESTRANGEIRO"


def resolve_columns(df, required_map, source_name):
    normalized_to_original = {normalize_col_name(col): col for col in df.columns}

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
        available = ", ".join(str(col) for col in df.columns)
        expected = ", ".join(missing)
        raise ValueError(
            f"Arquivo {source_name}: nao encontrei as colunas obrigatorias ({expected}). Colunas disponiveis: {available}"
        )

    return resolved


def find_column_by_aliases(columns, aliases):
    normalized_to_original = {normalize_col_name(col): col for col in columns}

    for alias in aliases:
        normalized_alias = normalize_col_name(alias)
        if normalized_alias in normalized_to_original:
            return normalized_to_original[normalized_alias]

    return None


def status_badge(s):
    cores = {
        "Conciliado": '<span class="status-ok">✅ Conciliado</span>',
        "Divergência de Valor": '<span class="status-div">🔶 Divergencia de Valor</span>',
        "Ausente na Prefeitura": '<span class="status-err">❌ Ausente na Prefeitura</span>',
        "Ausente no OMIE": '<span class="status-warn">⚠️ Ausente no OMIE</span>',
        "NOTA CANCELADA": '<span class="status-err">🚫 Nota Cancelada</span>',
        "POSSIVELMENTE ESTRANGEIRO": '<span class="status-warn">🌎 Possivelmente Estrangeiro</span>',
        "ESTRANGEIRO": '<span class="status-warn">🌍 Estrangeiro</span>',
    }

    return cores.get(s, s)


def format_brl(value):
    if pd.isna(value):
        return "-"

    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ==========================
# COLUNAS
# ==========================
OMIE_REQUIRED_COLUMNS = {
    "NFE": [
        "Número da NFS-e",
        "Numero da NFS-e",
        "NFS-e",
        "NFS e",
        "Numero NFS-e",
    ],
    "Nome_OMIE": [
        "Cliente (Nome Fantasia)",
        "Cliente (Razão Social)",
        "Cliente",
        "Nome Fantasia",
        "Razão Social",
    ],
    "Valor_OMIE": ["Valor Líquido", "Valor Liquido", "Valor", "Valor Total"],
}

PREF_REQUIRED_COLUMNS = {
    "NFE": [
        "Número (nNFSe)",
        "Numero (nNFSe)",
        "nNFSe",
        "Nº NFS-e",
        "N° NFS-e",
        "Numero NFS-e",
        "Número NFS-e",
        "NFS-e",
    ],
    "Nome_Pref": [
        "Tomador (xNome)",
        "xNome",
        "Razão Social do Tomador",
        "Razao Social do Tomador",
        "Tomador",
        "Razão Social",
    ],
    "Valor_Pref": [
        "Valor Líquido (R$) (vLiq)",
        "Valor Liquido (R$) (vLiq)",
        "vLiq",
        "Valor Serviço (R$) (vServ)",
        "vServ",
        " Valor dos Serviços ",
        "Valor dos Serviços",
        "Valor dos Servicos",
        "Valor Serviço",
        "Valor Servico",
    ],
}


# ==========================
# PROCESSAMENTO
# ==========================
def processar_omie(file):
    raw = pd.read_excel(file, header=None)
    header_row = None

    required_aliases = [
        alias for aliases in OMIE_REQUIRED_COLUMNS.values() for alias in aliases
    ]

    for i in range(min(50, len(raw))):
        row_values = [str(v).strip() for v in raw.iloc[i].tolist()]
        normalized = [normalize_col_name(v) for v in row_values]

        matches = sum(
            1 for alias in required_aliases if normalize_col_name(alias) in normalized
        )

        if matches >= 2:
            header_row = i
            break

    if header_row is None:
        preview_rows = []
        for i in range(min(10, len(raw))):
            row_values = [str(v).strip() for v in raw.iloc[i].tolist()]
            preview_rows.append(" | ".join(v for v in row_values if v and v != "nan"))

        raise ValueError(
            "Cabecalho do OMIE nao encontrado. Verifique se o arquivo eh a exportacao correta. "
            f"Primeiras linhas: {preview_rows}"
        )

    file.seek(0)
    df = pd.read_excel(file, header=header_row)

    cols = resolve_columns(df, OMIE_REQUIRED_COLUMNS, "OMIE")

    df = df[df[cols["NFE"]].notna()].copy()
    df[cols["NFE"]] = pd.to_numeric(df[cols["NFE"]], errors="coerce")
    df = df[df[cols["NFE"]].notna()].copy()

    if len(df) == 0:
        raise ValueError("Nenhuma NFE valida encontrada no arquivo OMIE")

    df[cols["NFE"]] = df[cols["NFE"]].astype(int)
    df[cols["Valor_OMIE"]] = pd.to_numeric(df[cols["Valor_OMIE"]], errors="coerce").fillna(0)

    agg = (
        df.groupby(cols["NFE"])
        .agg(Nome_OMIE=(cols["Nome_OMIE"], "first"), Valor_OMIE=(cols["Valor_OMIE"], "sum"))
        .reset_index()
    )

    agg.columns = ["NFE", "Nome_OMIE", "Valor_OMIE"]
    agg["Valor_OMIE"] = agg["Valor_OMIE"].fillna(0).astype(float)

    return agg


def processar_pref(file):
    file_name = str(getattr(file, "name", "")).lower()

    if file_name.endswith((".xlsx", ".xls")):
        try:
            df = pd.read_excel(file)
        except Exception as e:
            raise ValueError(f"Nao consegui ler o arquivo Excel da Prefeitura. Erro: {e}")
    else:
        try:
            df = pd.read_csv(file, encoding="utf-8-sig", sep=";")
        except Exception:
            try:
                file.seek(0)
                df = pd.read_csv(file, encoding="latin-1", sep=";")
            except Exception:
                try:
                    file.seek(0)
                    df = pd.read_csv(file, encoding="utf-8", sep=";")
                except Exception as e:
                    raise ValueError(f"Nao consegui ler o arquivo da Prefeitura (CSV/Excel). Erro: {e}")

    df.columns = [str(c).strip() for c in df.columns]

    if "Tipo de Registro" in df.columns:
        df = df[df["Tipo de Registro"].astype(str).str.strip().str.lower() != "total"].copy()

    cols = resolve_columns(df, PREF_REQUIRED_COLUMNS, "Prefeitura")

    cpf_cnpj_col = find_column_by_aliases(
        df.columns,
        [
            "Tomador (CNPJ / CPF / NIF)",
            "CPF/CNPJ do Tomador",
            "CPF/CNPJ Tomador",
            "CPF CNPJ",
        ],
    )

    situacao_col = find_column_by_aliases(
        df.columns,
        [
            "Situação NFS-e (cStat)",
            "Situacao NFS-e (cStat)",
            "Situação NFS-e",
            "Situacao NFS-e",
            "cStat",
            "Situação da Nota Fiscal",
            "Situacao da Nota Fiscal",
        ],
    )

    data_cancelamento_col = find_column_by_aliases(
        df.columns,
        [
            "Data de Cancelamento (dhCanc)",
            "Data Cancelamento (dhCanc)",
            "dhCanc",
            "Data de Cancelamento",
            "Data Cancelamento",
        ],
    )

    df = df[df[cols["NFE"]].notna()].copy()
    df[cols["NFE"]] = pd.to_numeric(df[cols["NFE"]], errors="coerce")
    df = df[df[cols["NFE"]].notna()].copy()

    if len(df) == 0:
        raise ValueError("Nenhuma NFE valida encontrada no arquivo da Prefeitura")

    df[cols["NFE"]] = df[cols["NFE"]].astype(int)

    df[cols["Valor_Pref"]] = df[cols["Valor_Pref"]].apply(clean_valor).astype(float)
    df["Valor_Final_Pref"] = df[cols["Valor_Pref"]].copy()

    if cpf_cnpj_col is not None:
        df["CPF_CNPJ"] = df[cpf_cnpj_col].apply(clean_documento)
    else:
        df["CPF_CNPJ"] = ""

    df["Tipo_Pessoa"] = df["CPF_CNPJ"].apply(identificar_tipo_documento)

    cpf_mask = df["Tipo_Pessoa"] == "CPF"
    df.loc[cpf_mask, "CPF_CNPJ"] = df.loc[cpf_mask, "CPF_CNPJ"].astype(str).str.zfill(11)

    cancel_por_status = pd.Series(False, index=df.index)
    cancel_por_data = pd.Series(False, index=df.index)

    if situacao_col is not None:
        status_num = pd.to_numeric(df[situacao_col], errors="coerce")
        cancel_por_codigo = status_num.eq(2)

        cancel_por_status = (
            df[situacao_col]
            .astype(str)
            .str.strip()
            .str.contains(r"(^C$|cancel)", case=False, na=False, regex=True)
        ) | cancel_por_codigo

    if data_cancelamento_col is not None:
        cancel_por_data = (
            df[data_cancelamento_col].notna()
            & df[data_cancelamento_col].astype(str).str.strip().ne("")
        )

    df["Nota_Cancelada"] = cancel_por_status | cancel_por_data

    df = df.rename(
        columns={
            cols["NFE"]: "NFE",
            cols["Nome_Pref"]: "Nome_Pref",
            cols["Valor_Pref"]: "Valor_Pref",
        }
    )

    return df[
        [
            "NFE",
            "Nome_Pref",
            "Valor_Pref",
            "Valor_Final_Pref",
            "CPF_CNPJ",
            "Tipo_Pessoa",
            "Nota_Cancelada",
        ]
    ]


def conciliar(omie, pref):
    if omie.empty or pref.empty:
        raise ValueError("Um dos arquivos apos processamento ficou vazio")

    merged = omie.merge(pref, on="NFE", how="outer", indicator=True)

    merged["Valor_OMIE"] = merged["Valor_OMIE"].fillna(0).astype(float)
    merged["Valor_Final_Pref"] = merged["Valor_Final_Pref"].fillna(0).astype(float)

    merged["Dif_Valor"] = (merged["Valor_OMIE"] - merged["Valor_Final_Pref"]).round(2)

    def get_status(row):
        if row.get("Nota_Cancelada") is True:
            return "NOTA CANCELADA"

        if row["_merge"] == "left_only":
            return "Ausente na Prefeitura"

        if row["_merge"] == "right_only":
            return "Ausente no OMIE"

        if row.get("Tipo_Pessoa") == "POSSIVELMENTE ESTRANGEIRO":
            return "POSSIVELMENTE ESTRANGEIRO"

        if row.get("Tipo_Pessoa") == "ESTRANGEIRO":
            return "ESTRANGEIRO"

        if abs(row["Dif_Valor"]) < 0.01:
            return "Conciliado"

        return "Divergência de Valor"

    merged["Status"] = merged.apply(get_status, axis=1)

    merged = merged.drop(columns=["_merge"]).sort_values("NFE").reset_index(drop=True)

    return merged


# ==========================
# EXPORTACAO
# ==========================
def to_excel(df):
    buf = io.BytesIO()

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dados")

        if "Status" in df.columns:
            df[df["Status"] != "Conciliado"].to_excel(
                writer,
                index=False,
                sheet_name="Divergencias",
            )

        if "Tipo_Pessoa" in df.columns:
            df[df["Tipo_Pessoa"] == "CNPJ"].to_excel(
                writer,
                index=False,
                sheet_name="CNPJs",
            )

            df[df["Tipo_Pessoa"] == "POSSIVELMENTE ESTRANGEIRO"].to_excel(
                writer,
                index=False,
                sheet_name="Possivelmente Estrangeiro",
            )

        if "Nota_Cancelada" in df.columns:
            df[df["Nota_Cancelada"] == True].to_excel(
                writer,
                index=False,
                sheet_name="Notas Canceladas",
            )

    return buf.getvalue()


# ==========================
# APP
# ==========================
init_session()

if not st.session_state["logado"]:
    st.title("🔐 Login - Concilia Prefeitura")
    st.markdown("Acesse com seu usuario para usar o sistema.")

    with st.form("login_form"):
        usuarios_disponiveis = [
            st.secrets["auth"]["admin_user"],
            st.secrets["auth"]["daniela_user"],
            st.secrets["auth"]["victor_user"],
            st.secrets["auth"]["suelen_user"],
        ]

        username = st.selectbox("Selecione o usuario", usuarios_disponiveis)
        password = st.text_input("Senha", type="password")
        submit = st.form_submit_button("Entrar", use_container_width=True)

    if submit:
        user = autenticar(username, password)

        if user:
            st.session_state["logado"] = True
            st.session_state["usuario"] = user["username"]
            st.session_state["nome_exibicao"] = user["nome_exibicao"]
            st.session_state["perfil"] = user["perfil"]
            st.rerun()
        else:
            st.error("Usuario ou senha invalidos.")

    st.stop()

col_head1, col_head2 = st.columns([4, 1])
with col_head1:
    st.title("🔍 CONCILIA PREFEITURA 2.0")
    st.markdown(
        "Faça o upload dos dois arquivos e clique em Conciliar para identificar divergencias automaticamente."
    )
    st.subheader("Feito por: Vinicius Magalhaes de Souza Sena")
    st.markdown("Funciona com Prefeitura SP e layout nacional (nNFSe/Portal Nacional).")

with col_head2:
    st.write(f"Usuario: {st.session_state['nome_exibicao']}")
    st.write(f"Perfil: {st.session_state['perfil']}")

    if st.button("Sair", use_container_width=True):
        st.session_state["logado"] = False
        st.session_state["usuario"] = None
        st.session_state["nome_exibicao"] = None
        st.session_state["perfil"] = None
        st.session_state["resultado"] = None
        st.rerun()

st.divider()

abas = ["Conciliação", "Histórico"]
if st.session_state["perfil"] == "admin":
    abas.append("Estudo por Empresa")

aba = st.radio("Menu", abas, horizontal=True)

if aba == "Conciliação":
    empresa = st.text_input("Nome da empresa", placeholder="Ex.: Empresa XPTO")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Arquivo OMIE")
        file_omie = st.file_uploader(
            "Selecione o Excel do OMIE",
            type=["xlsx", "xls"],
            key="omie_20",
        )
        if file_omie:
            st.success(f"Arquivo carregado: {file_omie.name}")

    with col2:
        st.subheader("Extrato da Prefeitura")
        file_pref = st.file_uploader(
            "Selecione o arquivo da Prefeitura",
            type=["csv", "xlsx", "xls"],
            key="pref_20",
        )
        if file_pref:
            st.success(f"Arquivo carregado: {file_pref.name}")

    st.divider()

    if file_omie and file_pref:
        if st.button("🚀 Conciliar Agora", type="primary", use_container_width=True):
            if not empresa.strip():
                st.error("Informe o nome da empresa antes de conciliar.")
            else:
                with st.spinner("Processando conciliacao..."):
                    try:
                        omie = processar_omie(file_omie)
                        st.success(f"OMIE processado: {len(omie)} NFEs validas")

                        pref = processar_pref(file_pref)
                        st.success(f"Prefeitura processada: {len(pref)} NFEs validas")

                        resultado = conciliar(omie, pref)
                        st.session_state["resultado"] = resultado

                        salvar_historico(
                            resultado,
                            st.session_state["usuario"],
                            st.session_state["perfil"],
                            empresa.strip(),
                            file_omie.name,
                            file_pref.name,
                        )

                        st.success(
                            f"Concluido: {len(resultado)} registros processados e historico salvo"
                        )
                    except Exception as e:
                        st.error(f"Erro: {e}")
    else:
        st.info("Faça upload dos dois arquivos para habilitar a conciliacao.")

    if st.session_state["resultado"] is not None:
        resultado = st.session_state["resultado"]

        total = len(resultado)
        ok = (resultado["Status"] == "Conciliado").sum()
        div_val = (resultado["Status"] == "Divergência de Valor").sum()
        aus_pref = (resultado["Status"] == "Ausente na Prefeitura").sum()
        aus_omie = (resultado["Status"] == "Ausente no OMIE").sum()
        canceladas = (resultado["Status"] == "NOTA CANCELADA").sum()
        estr = (resultado["Tipo_Pessoa"] == "POSSIVELMENTE ESTRANGEIRO").sum()

        st.subheader("Resumo da Conciliação")
        c1, c2, c3, c4, c5, c6 = st.columns(6)

        with c1:
            st.markdown(
                f"<div class='metric-card card-azul'><div class='card-titulo'>Total de NFEs</div><div class='card-valor' style='color:#003f8a'>{total}</div></div>",
                unsafe_allow_html=True,
            )

        with c2:
            st.markdown(
                f"<div class='metric-card card-verde'><div class='card-titulo'>Conciliadas</div><div class='card-valor' style='color:#28a745'>{ok}</div></div>",
                unsafe_allow_html=True,
            )

        with c3:
            st.markdown(
                f"<div class='metric-card card-vermelho'><div class='card-titulo'>Divergencia Valor</div><div class='card-valor' style='color:#fd7e14'>{div_val}</div></div>",
                unsafe_allow_html=True,
            )

        with c4:
            st.markdown(
                f"<div class='metric-card card-vermelho'><div class='card-titulo'>Ausente na Pref.</div><div class='card-valor' style='color:#dc3545'>{aus_pref}</div></div>",
                unsafe_allow_html=True,
            )

        with c5:
            st.markdown(
                f"<div class='metric-card card-amarelo'><div class='card-titulo'>Ausente no OMIE</div><div class='card-valor' style='color:#ffc107'>{aus_omie}</div></div>",
                unsafe_allow_html=True,
            )

        with c6:
            st.markdown(
                f"<div class='metric-card card-roxo'><div class='card-titulo'>Canceladas</div><div class='card-valor' style='color:#6f42c1'>{canceladas}</div></div>",
                unsafe_allow_html=True,
            )

        pct = int((ok / total) * 100) if total > 0 else 0
        st.markdown(f"Taxa de conciliacao: {pct}%")
        st.progress(pct / 100)

        st.divider()

        labels = [
            "Conciliadas",
            "Divergencia de Valor",
            "Ausente na Pref.",
            "Ausente no OMIE",
            "Canceladas",
            "Poss. Estrangeiros",
        ]
        values = [ok, div_val, aus_pref, aus_omie, canceladas, estr]
        cores = ["#28a745", "#fd7e14", "#dc3545", "#ffc107", "#6f42c1", "#17a2b8"]

        fig = go.Figure(
            data=[
                go.Bar(
                    x=labels,
                    y=values,
                    marker_color=cores,
                    text=values,
                    textposition="outside",
                )
            ]
        )

        fig.update_layout(
            title=dict(text="Distribuicao das NFEs", font=dict(size=18)),
            yaxis=dict(title="Quantidade"),
            xaxis=dict(title=""),
            height=400,
            margin=dict(t=50, b=40),
            showlegend=False,
        )

        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("Detalhamento das NFEs")

        col_f1, col_f2, col_f3 = st.columns([1, 1, 2])

        with col_f1:
            status_opcoes = ["Todos"] + sorted(resultado["Status"].dropna().unique().tolist())
            filtro_status = st.selectbox("Filtrar por status", status_opcoes)

        with col_f2:
            tipo_opcoes = ["Todos", "CPF", "CNPJ", "POSSIVELMENTE ESTRANGEIRO", "ESTRANGEIRO"]
            filtro_tipo = st.selectbox("Filtrar por tipo doc", tipo_opcoes)

        with col_f3:
            busca = st.text_input("Buscar por NFE ou nome do cliente")

        df_view = resultado.copy()

        if filtro_status != "Todos":
            df_view = df_view[df_view["Status"] == filtro_status]

        if filtro_tipo != "Todos":
            df_view = df_view[df_view["Tipo_Pessoa"] == filtro_tipo]

        if busca:
            mask = (
                df_view["NFE"].astype(str).str.contains(busca, case=False, na=False)
                | df_view["Nome_OMIE"].astype(str).str.contains(busca, case=False, na=False)
                | df_view["Nome_Pref"].astype(str).str.contains(busca, case=False, na=False)
            )
            df_view = df_view[mask]

        df_html = df_view.copy()
        df_html["Status"] = df_html["Status"].apply(status_badge)
        df_html["Valor_OMIE"] = df_html["Valor_OMIE"].apply(format_brl)
        df_html["Valor_Final_Pref"] = df_html["Valor_Final_Pref"].apply(format_brl)
        df_html["Dif_Valor"] = df_html["Dif_Valor"].apply(format_brl)

        df_html = df_html.rename(
            columns={
                "NFE": "NFE",
                "Nome_OMIE": "Cliente (OMIE)",
                "Nome_Pref": "Tomador (Prefeitura)",
                "Valor_OMIE": "Valor OMIE",
                "Valor_Final_Pref": "Valor Prefeitura",
                "Dif_Valor": "Diferenca",
                "CPF_CNPJ": "CPF_CNPJ",
                "Tipo_Pessoa": "Tipo Pessoa",
                "Nota_Cancelada": "Nota Cancelada",
            }
        )

        st.markdown(df_html.to_html(escape=False, index=False), unsafe_allow_html=True)
        st.caption(f"Mostrando {len(df_view)} de {total} registros.")

        st.divider()
        st.subheader("Exportar Resultado")

        col_e1, col_e2 = st.columns(2)

        with col_e1:
            st.download_button(
                label="Baixar Excel completo",
                data=to_excel(resultado),
                file_name="conciliacao_resultado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        with col_e2:
            erros = resultado[resultado["Status"] != "Conciliado"]
            st.download_button(
                label="Baixar apenas erros/divergencias",
                data=to_excel(erros),
                file_name="conciliacao_erros.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                disabled=(len(erros) == 0),
            )

elif aba == "Histórico":
    st.subheader("Historico de Conciliações")

    try:
        hist = carregar_historico()

        if hist.empty:
            st.info("Nenhum historico encontrado ainda.")
        else:
            if st.session_state["perfil"] != "admin":
                hist = hist[hist["usuario"] == st.session_state["usuario"]]

            st.dataframe(hist, use_container_width=True)

            st.download_button(
                label="Baixar historico em Excel",
                data=to_excel(hist),
                file_name="historico_conciliacoes.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    except Exception as e:
        st.error(f"Erro ao carregar historico: {e}")

elif aba == "Estudo por Empresa":
    if st.session_state["perfil"] != "admin":
        st.error("Acesso restrito ao administrador.")
    else:
        st.subheader("Estudo de empresas com mais problemas")

        try:
            estudo = carregar_estudo_empresas()

            if estudo.empty:
                st.info("Ainda nao ha dados suficientes para analise por empresa.")
            else:
                st.dataframe(estudo, use_container_width=True)

                st.download_button(
                    label="Baixar estudo por empresa",
                    data=to_excel(estudo),
                    file_name="estudo_empresas_problemas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
        except Exception as e:
            st.error(f"Erro ao carregar estudo por empresa: {e}")
