import streamlit as st
import pandas as pd
import numpy as np
import io


# ===== 教师设置 =====
TRUTH_FILE = "Raw_Occ.xlsx"
SHEET_NAME = 0
INDEX_COL = 0
ACCESS_CODE = "ZDM-2025-Homework5"
MAX_FILE_SIZE_MB = 2
DAY_ROWS = 96  # 一天96个时间步
# ===================

st.set_page_config(page_title="异常值修复作业评分系统", layout="centered")
st.title("课堂小作业 5-2 自动评分系统")

# ===== 初始化状态 =====
if "graded" not in st.session_state:
    st.session_state.graded = False
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
if "report" not in st.session_state:
    st.session_state.report = None
if "col_compare" not in st.session_state:
    st.session_state.col_compare = None
if "df_truth" not in st.session_state:
    st.session_state.df_truth = None
if "df_student" not in st.session_state:
    st.session_state.df_student = None

@st.cache_data
def load_truth():
    return pd.read_excel(TRUTH_FILE, sheet_name=SHEET_NAME, index_col=[0])

df_truth = load_truth()
st.session_state.df_truth = df_truth

# ===== 口令验证 =====
if not st.session_state.auth_ok:
    code = st.text_input("请输入课堂口令", type="password")
    if st.button("验证口令"):
        if code == ACCESS_CODE:
            st.session_state.auth_ok = True
            st.success("口令正确 ✅")
        else:
            st.error("口令错误，请重新输入。")
    st.stop()

st.success("口令验证通过 ✅")
st.divider()

# ===== 上传区 =====
if not st.session_state.graded:
    st.subheader("上传作业文件")

    uploaded_file = st.file_uploader(
        "⬇️ 上传你的修正后文件 (.xlsx, 请保持与 output_modified.xlsx 同样的行列结构)",
        type=["xlsx"]
    )

    if uploaded_file is not None:
        size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            st.error(f"文件太大 ({size_mb:.2f} MB)，请压缩或删除无关内容。")
            st.stop()

        if st.button("提交并评分 ✅"):
            try:
                # 读取学生文件
                df_student = pd.read_excel(io.BytesIO(uploaded_file.read()),
                                           sheet_name=SHEET_NAME,
                                           index_col=[0])

                # 对齐索引和列
                df_student = df_student.reindex(df_truth.index)
                if not df_truth.columns.equals(df_student.columns):
                    st.error("❌ 列名不一致！请保持与原始数据一致。")
                    st.stop()

                # 计算误差
                truth_vals = df_truth.to_numpy(dtype=float)
                stud_vals = df_student.to_numpy(dtype=float)
                diff = stud_vals - truth_vals
                abs_diff = np.abs(diff)

                total_err = float(np.sum(abs_diff))
                max_err = float(np.max(abs_diff))

                n_rows, n_cols = abs_diff.shape
                max_flat = int(np.argmax(abs_diff))
                r_idx, c_idx = divmod(max_flat, n_cols)

                rpt = {
                    "total_err": total_err,
                    "max_err": max_err,
                    "row_label": df_truth.index[r_idx],
                    "col_label": df_truth.columns[c_idx],
                }

                # ---- 自动提取当天96行 ----
                idx = df_truth.index
                col_label = rpt["col_label"]
                row_label = rpt["row_label"]

                if np.issubdtype(idx.dtype, np.datetime64):
                    # 如果是时间索引，按天筛选
                    day_str = pd.to_datetime(row_label).strftime("%Y-%m-%d")
                    mask = idx.strftime("%Y-%m-%d") == day_str
                    compare_df = pd.DataFrame({
                        "Truth(老师标准)": df_truth.loc[mask, col_label],
                        "Yours(你提交的)": df_student.loc[mask, col_label]
                    })
                    compare_df["Order"] = np.arange(1, len(compare_df) + 1)
                    plot_df = compare_df.set_index("Order")[["Truth(老师标准)", "Yours(你提交的)"]]
                else:
                    # 非时间索引，取误差点附近 ±48行
                    center = df_truth.index.get_loc(row_label)
                    lo = max(0, center)
                    hi = min(len(df_truth), center + 96)
                    compare_df = pd.DataFrame({
                        "Truth(老师标准)": df_truth.iloc[lo:hi, df_truth.columns.get_loc(col_label)],
                        "Yours(你提交的)": df_student.iloc[lo:hi, df_student.columns.get_loc(col_label)]
                    })
                    compare_df["Order"] = np.arange(1, len(compare_df) + 1)
                    plot_df = compare_df.set_index("Order")[["Truth(老师标准)", "Yours(你提交的)"]]

                # 保存状态
                st.session_state.report = rpt
                st.session_state.col_compare = plot_df
                st.session_state.df_student = df_student
                st.session_state.graded = True
                st.rerun()

            except Exception as e:
                st.error(f"评分过程中出错：{e}")
                st.stop()

# ===== 成绩展示页 =====
else:
    rpt = st.session_state.report
    st.subheader("评分结果")

    c1, c2 = st.columns(2)
    with c1:
        st.metric("总绝对误差", f"{rpt['total_err']:.2f}")
    with c2:
        st.metric("最大误差", f"{rpt['max_err']:.2f}")

    st.write("📍 最大误差出现位置：")
    st.write(f"- 时间索引: `{rpt['row_label']}`")
    st.write(f"- 列名: `{rpt['col_label']}`")

    st.subheader("📈 当天对比曲线（96个时刻）")
    st.line_chart(st.session_state.col_compare)

    st.divider()
    st.info("修改Excel后，可重新提交：")
    if st.button("🔁 重新提交"):
        st.session_state.graded = False
        st.session_state.report = None
        st.session_state.col_compare = None
        st.rerun()

st.caption("提示：请只修正异常值，保持数据结构不变。")
