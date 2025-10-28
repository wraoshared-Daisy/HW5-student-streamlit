import streamlit as st
import pandas as pd
import numpy as np
import io
import altair as alt

# ===== 教师设置 =====
TRUTH_FILE = "Raw_Occ.xlsx"
SHEET_NAME = 0
INDEX_COL = 0
ACCESS_CODE = "Feb-2025-Homework5"
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
                col_idx = df_truth.columns.get_loc(col_label)

                if np.issubdtype(idx.dtype, np.datetime64):
                    # 情况 1：索引是时间戳，比如 2025-04-08 00:15:00
                    # 步骤：取“最大误差那一整天”的数据
                    target_day = pd.to_datetime(row_label).strftime("%Y-%m-%d")
                    mask = idx.strftime("%Y-%m-%d") == target_day

                    truth_slice = df_truth.loc[mask, col_label]
                    stud_slice = df_student.loc[mask, col_label]

                    # 如果这一整天不是正好96行（有缺/多），我们截到最多96个点
                    truth_slice = truth_slice.iloc[:DAY_ROWS]
                    stud_slice = stud_slice.iloc[:DAY_ROWS]

                else:
                    # 情况 2：索引不是时间戳（很常见：你的索引可能是字符串的 "0:00","0:15",... 重复多天，
                    # 或者根本不是时间，可能是 0,1,2,3,...）
                    # 我们假设数据是按天拼起来的，每天有固定 96 行
                    # 思路：拿最大误差这行属于哪一天 -> 把这一整天的96行切出来

                    center_iloc = df_truth.index.get_loc(row_label)  # 误差最大点的行号
                    day_start = (center_iloc // DAY_ROWS) * DAY_ROWS
                    day_end = min(day_start + DAY_ROWS, len(df_truth))

                    truth_slice = df_truth.iloc[day_start:day_end, col_idx]
                    stud_slice = df_student.iloc[day_start:day_end, col_idx]

                # 现在我们统一构建一个干净的对比 DataFrame
                compare_df = pd.DataFrame({
                    "答案": truth_slice.to_numpy(),
                    "你提交的": stud_slice.to_numpy()
                })
                compare_df["Order"] = np.arange(1, len(compare_df) + 1)

                # 这个版本留给展示页使用
                plot_df = compare_df[["Order", "答案", "你提交的"]].copy()

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

    st.markdown(
        f"""
        <div style="font-size:1.6rem; font-weight:600; margin-bottom:0.25rem;">📍 最大误差出现位置：</div>
        <div style="font-size:2.5rem; margin-left:1rem;">
            时间索引: <span style="font-weight:600;">{rpt['row_label']}</span><br>
            列名: <span style="font-weight:600;">{rpt['col_label']}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.subheader("📈 当天对比曲线（96个时刻）")

    plot_df = st.session_state.col_compare  # 包含列: Order, 答案, 你提交的

    # 为了画多条线，先把列 pivot 成 "name / value" 结构
    plot_long = plot_df.melt(
        id_vars="Order",
        value_vars=["答案", "你提交的"],
        var_name="系列",
        value_name="数值"
    )

    # 颜色映射：答案=红色， 你提交的=蓝色
    color_scale = alt.Scale(
        domain=["答案", "你提交的"],
        range=["red", "steelblue"]
    )

    chart = (
        alt.Chart(plot_long)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("Order:Q", title="时序点 (1→96)"),
            y=alt.Y("数值:Q", title="人数"),
            color=alt.Color("系列:N", scale=color_scale, title=None),
            tooltip=[
                alt.Tooltip("Order:Q", title="序号"),
                alt.Tooltip("系列:N", title="曲线"),
                alt.Tooltip("数值:Q", title="值")
            ]
        )
        .properties(
            width=600,
            height=300
        )
    )

    st.altair_chart(chart, use_container_width=True)

    st.divider()
    st.info("修改Excel后，可重新提交：")
    if st.button("🔁 重新提交"):
        st.session_state.graded = False
        st.session_state.report = None
        st.session_state.col_compare = None
        st.rerun()

st.caption("提示：请只修正异常值，保持数据结构不变。")

