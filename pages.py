import time
import streamlit as st
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from config import HOT_SYMBOLS, PRESET_STRATEGIES
from utils import get_tushare_data, run_backtest, parse_strategy_to_signal
from agents import committee, generate_stock_comment


# 全局配置校验
def check_config() -> bool:
    from config import DEEPSEEK_APIKEY, TUSHARE_TOKEN

    config_ok = True
    if not DEEPSEEK_APIKEY:
        st.error("❌ DEEPSEEK_API_KEY 未配置，请检查 .env 文件")
        config_ok = False
    if not TUSHARE_TOKEN:
        st.error("❌ TUSHARE_TOKEN 未配置，请检查 .env 文件")
        config_ok = False

    return config_ok


# 页面1：多Agent辩论投研系统
def main_report():
    st.markdown("""
    <h1 style="text-align: center; color: #4CAF50; font-size: 36px;">
        🧠 多Agent辩论投研系统
    </h1>
    """, unsafe_allow_html=True)
    st.divider()

    config_ok = check_config()

    # 侧边栏参数
    with st.sidebar:
        st.header("⚙️ 配置参数")
        rounds = st.slider("辩论轮数", 1, 3, 2)
        st.divider()
        st.info("ℹ️ Agent已自动获取最新市场信息进行分析")
        st.info("ℹ️ 策略回测请使用「自然语言策略解析器」")

    # 输入区域 + 热门标的快速选择
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        symbol = st.text_input("标的代码（如 600519.SH）", value="600519.SH")

        st.markdown("**热门标的快速选择**")
        hot_cols = st.columns(4)
        for i, hot_symbol in enumerate(HOT_SYMBOLS):
            if hot_cols[i % 4].button(hot_symbol, use_container_width=True):
                symbol = hot_symbol
                st.rerun()

        run_btn = st.button("🚀 开始多Agent辩论投研", type="primary", use_container_width=True, disabled=not config_ok)

    # 会话状态
    if "report_result" not in st.session_state:
        st.session_state.report_result = None

    # 运行Agent辩论
    if run_btn and symbol.strip():
        with st.spinner("🚀 正在执行多Agent辩论投研..."):
            progress_bar = st.progress(0)
            status_text = st.empty()
            res = committee(symbol, debate_rounds=rounds, progress_bar=progress_bar, status_text=status_text)
            st.session_state.report_result = res
        st.rerun()

    # 结果展示
    if st.session_state.report_result and st.session_state.report_result["success"]:
        res = st.session_state.report_result
        tabs = st.tabs(["📊 综合评分仪表盘", "🎙️ Agent辩论记录", "⚖️ 综合裁判结论", "📋 投资要点摘要"])

        agent_names = {
            "mood": "市场情绪",
            "news": "热点资讯",
            "risk": "风险评估",
            "trend": "技术趋势",
            "value": "基本面价值"
        }

        with tabs[0]:
            st.subheader(f"{res['symbol']} 多维度评分")

            final_score = res["final_score"]
            score_class = "score-high" if final_score >= 7 else "score-medium" if final_score >= 4 else "score-low"
            st.markdown(f"""
            <div style="text-align: center; margin: 30px 0;">
                <h2>最终综合评分</h2>
                <div class="{score_class}">{final_score}/10</div>
            </div>
            """, unsafe_allow_html=True)

            st.subheader("各维度详细评分")
            cols = st.columns(5)
            for i, (agent, score) in enumerate(res["avg_scores"].items()):
                with cols[i]:
                    s_class = "score-high" if score >= 7 else "score-medium" if score >= 4 else "score-low"
                    st.markdown(f"""
                    <div class="agent-score-card">
                        <h4>{agent_names[agent]}</h4>
                        <div class="{s_class}">{score}/10</div>
                    </div>
                    """, unsafe_allow_html=True)

        with tabs[1]:
            st.subheader("多Agent辩论详情")
            for round_data in res["debate_history"]:
                st.markdown(f"### 第 {round_data['round']} 轮辩论")
                for name, content in round_data["opinions"].items():
                    st.markdown(f"**{agent_names[name].upper()}Agent观点：**")
                    st.markdown(f"> {content}")
                st.divider()

        with tabs[2]:
            st.subheader("综合裁判结论")
            st.markdown(res["judge_conclusion"])

        with tabs[3]:
            st.subheader("核心投资要点")
            conclusion = res["judge_conclusion"]
            lines = conclusion.split('\n')
            points = []
            for line in lines:
                if line.strip().startswith(('1.', '2.', '3.', '4.', '5.')):
                    points.append(line.strip())

            if points:
                for point in points:
                    st.markdown(f"- {point}")
            else:
                st.info("暂无提炼的投资要点，请查看综合裁判结论")

            st.subheader("操作建议")
            if final_score >= 8:
                st.success("✅ 强烈建议买入，可适当重仓")
            elif final_score >= 6:
                st.info("ℹ️ 建议买入，可分批建仓")
            elif final_score >= 4:
                st.warning("⚠️ 建议观望，等待更好时机")
            else:
                st.error("❌ 建议卖出，规避风险")

    else:
        if st.session_state.report_result and not st.session_state.report_result["success"]:
            st.error(f"❌ 执行失败: {st.session_state.report_result['msg']}")
        else:
            st.info("👈 请输入标的或点击热门标的，点击【开始多Agent辩论投研】")


# 页面2：自然语言策略解析器
def main_nl_strategy():
    st.markdown("""
    <h1 style="text-align: center; color: #FF9800; font-size: 36px;">
        ✍️ 自然语言 → 策略解析 + 自动回测
    </h1>
    """, unsafe_allow_html=True)
    st.divider()

    config_ok = check_config()

    if "nl_strategy_result" not in st.session_state:
        st.session_state.nl_strategy_result = None

    # 回测时间范围选择
    col_time1, col_time2 = st.columns(2)
    with col_time1:
        default_start = datetime.now() - timedelta(days=90)
        start_date = st.date_input("回测开始日期", value=default_start)
    with col_time2:
        end_date = st.date_input("回测结束日期", value=datetime.now())

    start_date_str = start_date.strftime('%Y%m%d')
    end_date_str = end_date.strftime('%Y%m%d')

    col1, col2 = st.columns([3, 1])
    with col1:
        nl_strategy = st.text_area(
            "输入你的交易想法（仅使用均线/价格形态）",
            value="5日均线上穿10日均线买入，5日均线下穿10日均线卖出，亏损3%止损，盈利7%止盈",
            height=120
        )
    with col2:
        nl_symbol = st.text_input("标的代码", value="600519.SH")
        run_nl_btn = st.button("🚀 解析并回测", type="primary", use_container_width=True, disabled=not config_ok)

    if run_nl_btn and nl_strategy.strip() and nl_symbol.strip():
        with st.spinner("🚀 正在解析自然语言策略并回测..."):
            df = get_tushare_data(nl_symbol, start_date=start_date_str, end_date=end_date_str)
            df_signal, parse_msg, quant_code = parse_strategy_to_signal(df, nl_strategy, nl_symbol)
            nl_res = {
                "success": True,
                "parsed_strategy": nl_strategy,
                "quant_code": quant_code,
                "backtest": run_backtest(df_signal)
            }
            st.session_state.nl_strategy_result = nl_res
        st.success(f"✅ 解析完成 | {parse_msg}")

    if st.session_state.nl_strategy_result and st.session_state.nl_strategy_result["success"]:
        nl_res = st.session_state.nl_strategy_result
        st.subheader("当前策略")
        st.text_area("策略原文", nl_res["parsed_strategy"], height=180)

        st.download_button(
            label="📋 一键复制可运行的量化代码",
            data=nl_res["quant_code"],
            file_name=f"quant_strategy_{time.strftime('%Y%m%d')}.py",
            mime="text/python",
            use_container_width=True
        )

        st.divider()

        st.subheader("回测结果")
        bt = nl_res["backtest"]
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("年化收益", f"{bt['annual_return']}%")
        col_b.metric("夏普比率", f"{bt['sharpe']}")
        col_c.metric("最大回撤", f"{bt['max_drawdown']}%")
        col_d.metric("胜率", f"{bt['win_rate']}%")

        st.subheader("信号统计")
        col_e, col_f, col_g = st.columns(3)
        col_e.metric("买入信号次数", bt["buy_signals"])
        col_f.metric("卖出信号次数", bt["sell_signals"])
        col_g.metric("实际成交次数", bt["actual_trades"])

        if bt["actual_trades"] == 0:
            st.warning("""
            ⚠️ **回测期间未触发任何买卖信号**
            可能原因：
            1. 策略条件过于严格（如要求同时站上多条均线）
            2. 回测时间段内标的处于下跌趋势，未满足买入条件
            3. 策略描述可能存在歧义，建议简化条件
            """)

        # ✅ 彻底删除所有图表文字，只保留曲线和买卖点
        df = bt["df"]
        plt.rcParams['axes.unicode_minus'] = False

        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(df["date"], df["标的收益(%)"], color="#2196F3", linewidth=2)
        ax.plot(df["date"], df["策略收益(%)"], color="#F44336", linewidth=2)

        buy_points = df[df["buy_signal"] == 1]
        sell_points = df[df["sell_signal"] == 1]
        ax.scatter(buy_points["date"], buy_points["标的收益(%)"], color="green", marker="^", s=100)
        ax.scatter(sell_points["date"], sell_points["标的收益(%)"], color="red", marker="v", s=100)

        # 🔴 彻底删除所有文字：标题、坐标轴标签、图例
        ax.grid(True, alpha=0.3)
        ax.set_xticks([])  # 连x轴日期也删掉
        ax.set_yticks([])  # 连y轴刻度也删掉
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)

        st.pyplot(fig)

        trade_count = len(df[df["strategy_return"] != 0])
        long_count = len(df[df["position"] == 1])
        st.info(f"📊 回测统计：总交易日 {len(df)} | 交易次数 {trade_count} | 持仓天数 {long_count}")
    else:
        if st.session_state.nl_strategy_result and not st.session_state.nl_strategy_result["success"]:
            st.error(f"❌ 解析失败: {st.session_state.nl_strategy_result['msg']}")


# 页面3：Agent智能股评生成器
def main_stock_comment():
    st.markdown("""
    <h1 style="text-align: center; color: #9C27B0; font-size: 36px;">
        📝 Agent智能股评生成器
    </h1>
    """, unsafe_allow_html=True)
    st.divider()

    config_ok = check_config()

    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        symbol = st.text_input("输入股票代码（如 600519.SH）", value="600519.SH")
        generate_btn = st.button("🚀 生成专业股评", type="primary", use_container_width=True, disabled=not config_ok)

    if generate_btn and symbol.strip():
        with st.spinner("📊 正在获取数据并生成股评..."):
            try:
                comment = generate_stock_comment(symbol)
                st.markdown(comment)

                st.download_button(
                    label="📋 复制股评到剪贴板",
                    data=comment,
                    file_name=f"{symbol}_股评报告_{time.strftime('%Y%m%d')}.md",
                    mime="text/markdown",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"❌ 生成股评失败: {e}")