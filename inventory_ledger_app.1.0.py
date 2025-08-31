# inventory_ledger_app

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# -----------------------------
# Google Sheets 接続設定
# -----------------------------
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = "C:/INVENTORY_LEDGER_APP/gspread_service_account.json"
SPREADSHEET_ID = "1npMB1wdR9EVgQ9NWZbE8Z21dmEzlnKY1vQi1FVSEXz8"
SHEET_NAME = "棚卸台帳"

# Streamlit の表示設定
st.set_page_config(page_title="棚卸台帳", layout="wide")

st.title("📦 棚卸台帳")
st.info("認証: ローカル gspread_service_account.json を使用")

# -----------------------------
# Google Sheets へ接続
# -----------------------------
try:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(SHEET_NAME)
    rows = worksheet.get_all_values()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    st.success(f"✅ 読み込み成功: {SHEET_NAME}")
except Exception as e:
    st.error(f"❌ Sheets読み込み失敗: {e}")
    df = pd.DataFrame(columns=["No", "号機", "GT", "BLサイズ", "保留日", "回数", "備考"])

# -----------------------------
# 入力フォーム（左サイドバー）
# -----------------------------
st.sidebar.header("📝 新規記録")
with st.sidebar.form("entry_form", clear_on_submit=True):
    no = st.number_input("No", min_value=1, step=1)
    unit = st.text_input("号機")
    gt = st.text_input("GT")
    bl_size = st.text_input("BLサイズ")
    date = st.date_input("保留日", format="YYYY/MM/DD")
    count = st.number_input("回数", min_value=0, step=1)
    note = st.text_input("備考")
    submitted = st.form_submit_button("記録")

# -----------------------------
# 新規追加処理
# -----------------------------
if submitted:
    new_row = [str(no), unit, gt, bl_size, date.strftime("%m/%d"), str(count), note]
    try:
        worksheet.append_row(new_row)
        st.success("✅ 記録を追加しました")
        st.rerun()
    except Exception as e:
        st.error(f"❌ 記録の追加に失敗しました: {e}")

# -----------------------------
# データ表示・編集
# -----------------------------
st.subheader("📊 表示・編集")
edited_df = st.data_editor(df, num_rows="dynamic")

# -----------------------------
# 編集保存処理
# -----------------------------
if st.button("編集を保存"):
    try:
        worksheet.clear()
        worksheet.append_row(edited_df.columns.tolist())
        worksheet.append_rows(edited_df.values.tolist())
        st.success("✅ 編集内容を保存しました")
    except Exception as e:
        st.error(f"❌ 編集の保存に失敗しました: {e}")
