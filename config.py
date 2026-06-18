import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# 加载环境变量
load_dotenv()

# API密钥
DEEPSEEK_APIKEY = os.getenv("DEEPSEEK_API_KEY")
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK")

# 热门标的快速选择
HOT_SYMBOLS = [
    "600519.SH", "000001.SZ", "300750.SZ", "601318.SH",
    "000858.SZ", "601398.SH", "600036.SH", "002594.SZ"
]

# 内置策略库
PRESET_STRATEGIES = {
    "5/10均线金叉死叉策略（默认）": """
    买入条件：5日均线上穿10日均线
    卖出条件：5日均线下穿10日均线
    止盈止损：亏损3%止损，盈利7%止盈
    """,
    "5/20均线趋势策略": """
    买入条件：价格同时站上5日和20日均线
    卖出条件：价格跌破20日均线
    止盈止损：亏损3%止损，盈利8%止盈
    """,
    "20日均线单均线策略": """
    买入条件：价格站上20日均线
    卖出条件：价格跌破20日均线
    止盈止损：亏损4%止损，盈利10%止盈
    """
}

# 全局样式
GLOBAL_STYLE = """
<style>
.stApp {
    background-color: #0E1117;
}
div[data-testid="stFullScreenFrame"] {
    background-color: transparent !important;
}
div[data-testid="stAppViewContainer"] {
    background-color: #0E1117;
}
button[kind="primary"] {
    opacity: 1 !important;
    pointer-events: auto !important;
}
.agent-score-card {
    background-color: #1E2127;
    border-radius: 10px;
    padding: 15px;
    margin: 10px 0;
    border-left: 4px solid #4CAF50;
}
.score-high {
    color: #4CAF50;
    font-size: 24px;
    font-weight: bold;
}
.score-medium {
    color: #FF9800;
    font-size: 24px;
    font-weight: bold;
}
.score-low {
    color: #F44336;
    font-size: 24px;
    font-weight: bold;
}
</style>
"""