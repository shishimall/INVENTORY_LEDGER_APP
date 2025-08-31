# inventory_ledger_app

# 棚卸台帳（Streamlit × Google Sheets）
# - 並べ替え後の順番を保持し、そのまま .xlsx ダウンロード
# - GT/BLサイズは既存値を即選択 or 新規入力を切替
# - スマホ対応：レ点で行削除 → ボタンで一括削除（行ズレ防止）
# - 保留日は date_input → mm/dd 自動整形
# - 上下に .xlsx ダウンロードボタン
# - 認証は Secrets 優先、なければローカルJSONをフォールバック
# - ワークシート取得は SPREADSHEET_ID / SHEET_NAME をキャッシュキーに含める
# - 失敗時のエラーは repr で内容を必ず可視化
# - キャッシュ全消しボタン付き

import os
import datetime
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from io import BytesIO

st.set_page_config(page_title="棚卸台帳", layout="wide")
st.title("📦 棚卸台帳")

# ====== 設定 ======
# ※必要に応じて書き換えてください（URLが https://docs.google.com/spreadsheets/d/<ここ>/edit の <ここ>）
SPREADSHEET_ID = "1npMB1wdR9EVgQ9NWZbE8Z21dmEzlnKY1vQi1FVSEXz8"  # ← あなたのIDに合わせる
SHEET_NAME     = "棚卸台帳"   # シート名（タブ名）
HEADER_ROW     = 1            # 見出しは1行目、本文は2行目〜

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ====== キャッシュ全消し（失敗状態を掴んだ時のために）======
with st.sidebar:
    if st.button("🔄 キャッシュをクリアして再試行", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

# ====== 認証（Cloud→secrets / Local→JSON の順で試す）======
@st.cache_resource
def get_gspread_client():
    # 1) Cloud / ローカル共通: secrets 優先
    if "gspread_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gspread_service_account"]), scopes=SCOPES
        )
        st.info("認証: st.secrets['gspread_service_account'] を使用", icon="🔐")
        return gspread.authorize(creds)

    # 2) ローカル: app と同階層の JSON
    json_path = os.path.join(os.path.dirname(__file__), "gspread_service_account.json")
    creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
    st.info("認証: ローカル gspread_service_account.json を使用", icon="💻")
    return gspread.authorize(creds)

try:
    client = get_gspread_client()
except Exception as e:
    st.error(
        "認証に失敗しました。Cloud では Secrets を、ローカルでは "
        "アプリと同階層に gspread_service_account.json を配置してください。\n\n"
        f"詳細: {repr(e)}"
    )
    st.stop()

# ====== ワークシート取得（キャッシュキーにID/タブ名を含める）======
@st.cache_resource
def open_worksheet(_client, spreadsheet_id: str, sheet_name: str):
    return _client.open_by_key(spreadsheet_id).worksheet(sheet_name)

try:
    ws = open_worksheet(client, SPREADSHEET_ID, SHEET_NAME)
except Exception as e:
    st.error(f"Sheets 読み込み失敗: {repr(e)}", icon="❌")
    # 診断の助けになる情報
    with st.expander("🩺 診断情報を表示"):
        st.write("SPREADSHEET_ID:", SPREADSHEET_ID)
        st.write("SHEET_NAME:", SHEET_NAME)
        if "gspread_service_account" in st.secrets:
            st.write("SA client_email:", st.secrets["gspread_service_account"].get("client_email"))
    st.stop()

# ====== 読み込み（行番号を保持）======
def load_df_with_rowno():
    vals = ws.get_all_values()
    if not vals:
        # 空のとき：想定ヘッダーで生成（必要に応じて列名を調整）
        headers = ["No", "号機", "GT", "BLサイズ", "保留日", "回数", "備考"]
        return pd.DataFrame(columns=headers), []
    headers = vals[0]
    rows = vals[1:]
    df = pd.DataFrame(rows, columns=headers)
    # シート実行行番号（削除時に使用）
    rownos = list(range(HEADER_ROW + 1, HEADER_ROW + 1 + len(df)))
    return df, rownos

df, sheet_row_numbers = load_df_with_rowno()
st.success(f"読み込み成功: {SHEET_NAME}", icon="✅")

# 並べ替え順保持用に位置列を付与（初回のみ）
if "_pos" not in df.columns:
    df["_pos"] = list(range(len(df)))  # 元の順序（0..n-1）

# ====== セッションに“表示用データ”を保持（並べ替え後の順を維持）======
if "view_df" not in st.session_state:
    st.session_state["view_df"] = df.copy()
if "view_rows" not in st.session_state:
    st.session_state["view_rows"] = sheet_row_numbers.copy()

# ====== XLSX ダウンロード（関数）======
def to_xlsx_bytes(_df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    # engine は openpyxl を優先（ローカル/Cloudの両方で入りやすい）
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        _df.to_excel(xw, index=False, sheet_name="data")
    bio.seek(0)
    return bio.read()

# ====== XLSX ダウンロード（上：表示順のまま）======
st.download_button(
    "⬇️ Excel(.xlsx) をダウンロード（上）",
    data=to_xlsx_bytes(st.session_state["view_df"].drop(columns=["_pos"], errors="ignore")),
    file_name="棚卸台帳.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.markdown("---")

# ====== サイドバー（新規登録：押すまでリロードしない）======
st.sidebar.subheader("📝 新規記録")

# 既存選択の候補（空白は除外）
uniq_gt = sorted([
    x for x in st.session_state["view_df"].get("GT", pd.Series(dtype=str)).dropna().unique().tolist()
    if str(x).strip() != ""
])
uniq_bl = sorted([
    x for x in st.session_state["view_df"].get("BLサイズ", pd.Series(dtype=str)).dropna().unique().tolist()
    if str(x).strip() != ""
])

def _safe_next_no(df_no: pd.Series) -> int:
    if df_no.empty:
        return 1
    s = pd.to_numeric(df_no.astype(str).str.extract(r"(\d+)")[0], errors="coerce").fillna(0).astype(int)
    return int(s.max() + 1)

with st.sidebar.form("create", clear_on_submit=True):
    next_no = _safe_next_no(st.session_state["view_df"].get("No", pd.Series(dtype=str)))
    in_no   = st.number_input("No", min_value=1, step=1, value=next_no)
    in_unit = st.text_input("号機")

    gt_mode = st.radio("GTの入力方法", ["既存から選ぶ", "新規入力"], horizontal=True)
    gt_sel  = st.selectbox("GT（既存）", options=uniq_gt, index=None, placeholder="選択してください") if gt_mode=="既存から選ぶ" else None
    gt_new  = st.text_input("GT（新規手入力）") if gt_mode=="新規入力" else None
    gt_val  = gt_sel if gt_mode=="既存から選ぶ" else gt_new

    bl_mode = st.radio("BLサイズの入力方法", ["既存から選ぶ", "新規入力"], horizontal=True)
    bl_sel  = st.selectbox("BLサイズ（既存）", options=uniq_bl, index=None, placeholder="選択してください") if bl_mode=="既存から選ぶ" else None
    bl_new  = st.text_input("BLサイズ（新規手入力）") if bl_mode=="新規入力" else None
    bl_val  = bl_sel if bl_mode=="既存から選ぶ" else bl_new

    # 保留日：カレンダー→ mm/dd 自動変換
    in_date = st.date_input("保留日", value=datetime.date.today())
    in_cnt  = st.number_input("回数", min_value=0, step=1, value=0)
    in_note = st.text_input("備考")
    submitted = st.form_submit_button("記録")

if submitted:
    try:
        new_row = [
            str(in_no),
            in_unit,
            gt_val or "",
            bl_val or "",
            in_date.strftime("%m/%d"),   # ← 自動で mm/dd
            str(in_cnt),
            in_note,
        ]
        ws.append_row(new_row, value_input_option="USER_ENTERED")
        st.success("新規記録を追加しました。", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"記録追加に失敗: {repr(e)}", icon="❌")

# ====== 表示・編集（ソート＋削除UI）======
st.subheader("📊 表示・編集")

# ① ソート（列選択＋昇降）…“表示順（view_df）”を更新
with st.expander("↕️ ソート"):
    candidate_cols = [c for c in st.session_state["view_df"].columns if c != "_pos"]
    if not candidate_cols:
        candidate_cols = st.session_state["view_df"].columns.tolist()
    sort_col = st.selectbox("ソートする列", options=candidate_cols, index=0)
    sort_asc = st.toggle("昇順（OFFで降順）", value=True)
    if st.button("ソートを適用"):
        # _pos を持ったまま安定ソート（同値の順番が安定）
        sorted_view = st.session_state["view_df"].sort_values(
            by=sort_col, ascending=sort_asc, kind="mergesort"
        ).reset_index(drop=True)
        st.session_state["view_df"] = sorted_view.copy()

        # 表示順→実シート行への対応を更新
        pos_order = sorted_view["_pos"].tolist()
        if len(pos_order) == len(sheet_row_numbers):
            st.session_state["view_rows"] = [sheet_row_numbers[i] for i in pos_order]
        else:
            st.session_state["view_rows"] = sheet_row_numbers.copy()

# ② 削除チェック列を追加（ユーザー表示用）
view_df = st.session_state["view_df"].copy()
work = view_df.drop(columns=["_pos"], errors="ignore").copy()
work.insert(0, "🗑削除", False)

# 表示（この順のまま見える/編集する/保存する/ダウンロードする）
edited = st.data_editor(
    work,
    hide_index=True,
    use_container_width=True,
    num_rows="fixed",  # 表側で行追加はさせない
)

# ③ 編集保存（画面表示順のまま全置換保存）
if st.button("編集を保存"):
    try:
        save_df = edited.drop(columns=["🗑削除"], errors="ignore")
        ws.clear()
        ws.append_row(save_df.columns.tolist())
        if len(save_df) > 0:
            ws.append_rows(save_df.values.tolist())
        st.success("編集内容を保存しました。", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"保存失敗: {repr(e)}", icon="❌")

# ④ チェックした行を削除（表示順→実シート行番号に変換し、下から削除）
if st.button("🗑 チェックした行を削除", type="primary"):
    try:
        flags = edited["🗑削除"].tolist() if "🗑削除" in edited.columns else []
        view_rows = st.session_state["view_rows"]
        to_delete_rows = [view_rows[i] for i, v in enumerate(flags) if v]
        if to_delete_rows:
            to_delete_rows.sort(reverse=True)  # 上から消すと行ズレ、必ず下から
            for r in to_delete_rows:
                ws.delete_rows(r)
            st.success(f"{len(to_delete_rows)} 行を削除しました。", icon="✅")
            st.rerun()
        else:
            st.warning("削除にチェックが入っていません。", icon="⚠️")
    except Exception as e:
        st.error(f"削除失敗: {repr(e)}", icon="❌")

# ====== XLSX ダウンロード（下：表示順のまま）======
st.download_button(
    "⬇️ Excel(.xlsx) をダウンロード（下）",
    data=to_xlsx_bytes(st.session_state["view_df"].drop(columns=["_pos"], errors="ignore")),
    file_name="棚卸台帳.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# ====== 任意：接続診断（必要時だけ開く）======
with st.expander("🩺 接続診断（必要な時だけ開いてOK）", expanded=False):
    try:
        if "gspread_service_account" in st.secrets:
            st.write("SA client_email:", st.secrets["gspread_service_account"].get("client_email"))
        st.write("SPREADSHEET_ID:", SPREADSHEET_ID)
        st.write("SHEET_NAME:", SHEET_NAME)
        ss = client.open_by_key(SPREADSHEET_ID)
        titles = [w.title for w in ss.worksheets()]
        st.write("存在するシート名一覧:", titles)
    except Exception as e:
        st.error(f"診断失敗: {repr(e)}")
