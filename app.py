import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler
from config import GLOBAL_STYLE, WECOM_WEBHOOK, PRESET_STRATEGIES
from utils import get_tushare_data, parse_strategy_to_signal, send_wecom_message
from pages import main_report, main_nl_strategy, main_stock_comment


# 每日定时信号推送任务
def daily_signal_check():
    if not WECOM_WEBHOOK:
        return

    watch_list = ["600519.SH", "000001.SZ", "300750.SZ", "601318.SH"]
    default_strategy = PRESET_STRATEGIES["5/10均线金叉死叉策略（默认）"]

    messages = ["📊 每日量化交易信号推送"]
    messages.append(f"策略：5/10均线金叉死叉策略")
    messages.append(f"时间：{time.strftime('%Y-%m-%d %H:%M')}")
    messages.append("---")

    for symbol in watch_list:
        try:
            df = get_tushare_data(symbol, start_date='20260101', end_date=time.strftime('%Y%m%d'))
            df_signal, _, _ = parse_strategy_to_signal(df, default_strategy, symbol)
            last_signal = df_signal.iloc[-1]

            if last_signal["buy_signal"] == 1:
                messages.append(f"✅ **{symbol}**：触发买入信号，现价 {last_signal['close']:.2f}")
            elif last_signal["sell_signal"] == 1:
                messages.append(f"❌ **{symbol}**：触发卖出信号，现价 {last_signal['close']:.2f}")
            else:
                pos_text = "持仓" if last_signal["position"] == 1 else "空仓"
                messages.append(f"⏸️ **{symbol}**：无信号，当前{pos_text}，现价 {last_signal['close']:.2f}")
        except Exception as e:
            messages.append(f"⚠️ **{symbol}**：数据获取失败")

    messages.append("---")
    messages.append("⚠️ 以上信号仅供参考，不构成投资建议")

    send_wecom_message("\n\n".join(messages))


def main():
    st.set_page_config(page_title="多Agent投研系统", layout="wide")

    # 应用全局样式
    st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

    # 启动定时任务
    if "scheduler_started" not in st.session_state:
        try:
            scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
            scheduler.add_job(daily_signal_check, "cron", hour=9, minute=25)
            scheduler.start()
            st.session_state.scheduler_started = True
            st.success("✅ 每日信号推送任务已启动")
        except Exception as e:
            st.warning(f"⚠️ 定时任务启动失败: {e}")

    # 侧边栏功能选择
    with st.sidebar:
        st.header("📋 功能选择")
        btn_report = st.button("🧠 多Agent辩论投研系统", use_container_width=True)
        btn_nl = st.button("✍️ 自然语言策略解析器", use_container_width=True)
        btn_comment = st.button("📝 Agent智能股评生成器", use_container_width=True)
        st.divider()
        st.info("ℹ️ Agent仅做投研分析，策略为独立预设规则")
        if WECOM_WEBHOOK:
            st.success("✅ 企业微信推送已启用")
        else:
            st.warning("⚠️ 企业微信推送未配置")

    # 初始化当前功能状态
    if "current_app" not in st.session_state:
        st.session_state.current_app = "report"

    # 切换功能
    if btn_report:
        st.session_state.nl_strategy_result = None
        st.session_state.comment_result = None
        st.session_state.current_app = "report"
        st.rerun()
    if btn_nl:
        st.session_state.report_result = None
        st.session_state.comment_result = None
        st.session_state.current_app = "nl_strategy"
        st.rerun()
    if btn_comment:
        st.session_state.report_result = None
        st.session_state.nl_strategy_result = None
        st.session_state.current_app = "comment"
        st.rerun()

    # 渲染对应页面
    if st.session_state.current_app == "report":
        main_report()
    elif st.session_state.current_app == "nl_strategy":
        main_nl_strategy()
    elif st.session_state.current_app == "comment":
        main_stock_comment()


if __name__ == "__main__":
    main()