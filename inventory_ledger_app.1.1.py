# inventory_ledger_app

import os
import datetime
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="棚卸台帳", layout="wide")
st.title("📦 棚卸台帳")

# ====== 設定 ======
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1npMB1wdR9EVgQ9NWZbE8Z21dmEzlnKY1vQi1FVSEXz8"   # ← あなたのID
SHEET_NAME     = "棚卸台帳"

# ====== 認証（Cloud→secrets / Local→JSON の順で試す）======
def get_gspread_client():
    # 1) Cloud / ローカルどちらでも st.secrets があれば優先
    try:
        if "gspread_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                st.secrets["gspread_service_account"], scopes=SCOPES
            )
            st.info("認証: st.secrets[gspread_service_account] を使用", icon="🔐")
            return gspread.authorize(creds)
    except Exception as e:
        st.warning(f"secrets 認証失敗: {e}", icon="⚠️")

    # 2) ローカルの JSON をフォールバック
    try:
        # app.py と同階層に置いた json を探す
        json_path = os.path.join(os.path.dirname(__file__), "gspread_service_account.json")
        creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
        st.info("認証: ローカル gspread_service_account.json を使用", icon="💻")
        return gspread.authorize(creds)
    except Exception as e:
        st.error(
            "認証に失敗しました。Cloud では Secrets を、ローカルでは "
            "app と同階層に gspread_service_account.json を配置してください。\n\n"
            f"詳細: {e}"
        )
        return None

client = get_gspread_client()
if not client:
    st.stop()

# ====== シート読み込み ======
try:
    ws = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    data = ws.get_all_values()
    if not data:
        raise RuntimeError("シートが空です")
    df = pd.DataFrame(data[1:], columns=data[0])
    st.success(f"読み込み成功: {SHEET_NAME}", icon="✅")
except Exception as e:
    st.error(f"Sheets 読み込み失敗: {e}", icon="❌")
    df = pd.DataFrame(columns=["No", "号機", "GT", "BLサイズ", "保留日", "回数", "備考"])

# ====== サイドバー（新規登録）======
st.sidebar.subheader("📝 新規記録")
with st.sidebar.form("create", clear_on_submit=True):
    in_no   = st.number_input("No", min_value=1, step=1, value=1)
    in_unit = st.text_input("号機")
    in_gt   = st.text_input("GT")
    in_bl   = st.text_input("BLサイズ")
    in_date = st.date_input("保留日", value=datetime.date.today())
    in_cnt  = st.number_input("回数", min_value=0, step=1, value=0)
    in_note = st.text_input("備考")
    submitted = st.form_submit_button("記録")

if submitted:
    try:
        new_row = [
            str(in_no),
            in_unit,
            in_gt,
            in_bl,
            in_date.strftime("%m/%d"),
            str(in_cnt),
            in_note,
        ]
        ws.append_row(new_row)
        st.success("新規記録を追加しました。", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"記録追加に失敗: {e}", icon="❌")

# ====== 表示・編集 ======
st.subheader("📊 表示・編集")
edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")

if st.button("編集を保存"):
    try:
        ws.clear()
        ws.append_row(edited.columns.tolist())
        if len(edited) > 0:
            ws.append_rows(edited.values.tolist())
        st.success("編集内容を保存しました。", icon="✅")
    except Exception as e:
        st.error(f"保存失敗: {e}", icon="❌")
