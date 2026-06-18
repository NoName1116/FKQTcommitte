import time
import re
import requests
import json
import numpy as np
import pandas as pd
import tushare as ts
from tavily import TavilyClient
from config import TUSHARE_TOKEN, TAVILY_API_KEY, WECOM_WEBHOOK

# 初始化Tushare
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# 初始化Tavily搜索引擎
tavily_client = None
if TAVILY_API_KEY:
    try:
        tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
    except Exception as e:
        print(f"Tavily连接失败: {e}")


# 1. 获取Tushare行情数据
def get_tushare_data(symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    try:
        if not end_date:
            end_date = time.strftime('%Y%m%d')
        if not start_date:
            start_date = (pd.Timestamp.now() - pd.Timedelta(days=90)).strftime('%Y%m%d')

        df = pro.daily(ts_code=symbol, start_date=start_date, end_date=end_date)
        if df.empty:
            raise ValueError("未获取到行情数据，请检查标的代码是否正确")
        df = df.sort_values("trade_date").reset_index(drop=True)
        df["date"] = pd.to_datetime(df["trade_date"])
        df["close"] = df["close"].astype(float)
        df["return"] = df["close"].pct_change()
        df["avg_loss"] = 0.0
        return df
    except Exception as e:
        raise ValueError(f"数据获取失败: {str(e)}")


# 2. 获取最新新闻
def get_latest_news(symbol: str) -> str:
    if not tavily_client:
        return "暂无最新新闻信息"

    try:
        query = f"{symbol} 股票 最新新闻 公告 重大事件"
        result = tavily_client.search(
            query=query,
            max_results=3,
            time_range="day",
            include_answer=False,
            include_raw_content=False,
            search_depth="basic"
        )

        news_content = ""
        for r in result["results"]:
            if len(r["content"]) < 50:
                continue
            news_content += f"{r['title']}: {r['content'][:150]}\n"

        return news_content if news_content else "暂无有效最新新闻信息"
    except Exception as e:
        return f"获取新闻失败: {str(e)}"


# 3. 企业微信消息推送
def send_wecom_message(content: str) -> bool:
    if not WECOM_WEBHOOK:
        return False

    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
        response = requests.post(
            WECOM_WEBHOOK,
            data=json.dumps(payload, ensure_ascii=False),
            headers=headers,
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        print(f"消息推送失败: {str(e)}")
        return False


# 4. 通用回测框架
def run_backtest(df: pd.DataFrame) -> dict:
    data = df.copy()
    data["strategy_return"] = data["position"].shift(1) * data["return"]
    data["strategy_return"] = data["strategy_return"].fillna(0)
    data["标的收益(%)"] = (data["close"] / data["close"].iloc[0]) * 100
    data["策略收益(%)"] = (1 + data["strategy_return"]).cumprod() * 100

    total_return = (1 + data["strategy_return"]).prod() - 1
    days = len(data)
    annual_return = total_return * (365 / days) if days > 0 else 0
    ret_std = data["strategy_return"].std()
    sharpe = np.sqrt(365) * data["strategy_return"].mean() / ret_std if ret_std != 0 else 0
    close_max = data["close"].cummax()
    max_drawdown = (data["close"] / close_max - 1).min() if not data["close"].empty else 0
    trade_days = data[data["strategy_return"] != 0]
    win_rate = (trade_days["strategy_return"] > 0).sum() / len(trade_days) if len(trade_days) > 0 else 0.0

    buy_signals = data["buy_signal"].sum()
    sell_signals = data["sell_signal"].sum()
    actual_trades = len(trade_days)

    return {
        "annual_return": round(annual_return * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "win_rate": round(win_rate * 100, 2),
        "buy_signals": int(buy_signals),
        "sell_signals": int(sell_signals),
        "actual_trades": int(actual_trades),
        "df": data
    }


# 5. 策略解析引擎（✅ 图表已删除所有文字，彻底解决乱码）
def parse_strategy_to_signal(df: pd.DataFrame, strategy_text: str, symbol: str) -> tuple[pd.DataFrame, str, str]:
    data = df.copy()
    msg = "策略解析成功"

    data["buy_signal"] = 0
    data["sell_signal"] = 0
    data["position"] = 0
    data["buy_price"] = np.nan

    buy_text = ""
    sell_text = ""
    stop_loss_text = ""
    take_profit_text = ""

    buy_match = re.search(r"(?:买入条件[:：]|)(.*?)(?:买入|(?=卖出|$))", strategy_text, re.S)
    sell_match = re.search(r"(?:卖出条件[:：]|)(.*?)(?:卖出|(?=止损|止盈|$))", strategy_text, re.S)
    sl_match = re.search(r"(?:止损[:：]|亏损)(.*?)(?:止损|(?=止盈|$))", strategy_text, re.S)
    tp_match = re.search(r"(?:止盈[:：]|盈利)(.*?)(?:止盈|$)", strategy_text, re.S)

    if buy_match:
        buy_text = buy_match.group(1).strip()
    if sell_match:
        sell_text = sell_match.group(1).strip()
    if sl_match:
        stop_loss_text = sl_match.group(1).strip()
    if tp_match:
        take_profit_text = tp_match.group(1).strip()

    if not buy_text or not sell_text:
        msg = "⚠️ 策略缺少必要的买入/卖出条件"

    # 计算均线指标
    ma_nums = re.findall(r"(\d+)日?均线", strategy_text)
    for num in ma_nums:
        n = int(num)
        data[f"ma{n}"] = data["close"].rolling(n).mean()

    # 生成买入信号
    buy_cond = pd.Series([False] * len(data))

    # 处理均线金叉
    cross_up = re.findall(r"(\d+)日均线上穿(\d+)日均线", buy_text)
    for fast, slow in cross_up:
        f, s = int(fast), int(slow)
        if f"ma{f}" in data.columns and f"ma{s}" in data.columns:
            cond = (data[f"ma{f}"] > data[f"ma{s}"]) & (data[f"ma{f}"].shift(1) <= data[f"ma{s}"].shift(1))
            buy_cond = buy_cond | cond

    # 处理价格站上均线
    stand_on_ma = re.findall(r"价格.*?站上(\d+)日均线", buy_text)
    if stand_on_ma:
        use_and = re.search(r"(和|同时|且)", buy_text) is not None

        if use_and:
            temp_cond = pd.Series([True] * len(data))
            for n in stand_on_ma:
                num = int(n)
                if f"ma{num}" in data.columns:
                    temp_cond = temp_cond & (data["close"] > data[f"ma{num}"])
            buy_cond = buy_cond | temp_cond
        else:
            for n in stand_on_ma:
                num = int(n)
                if f"ma{num}" in data.columns:
                    cond = data["close"] > data[f"ma{num}"]
                    buy_cond = buy_cond | cond

    data.loc[buy_cond, "buy_signal"] = 1

    # 生成卖出信号
    sell_cond = pd.Series([False] * len(data))

    # 处理均线死叉
    cross_down = re.findall(r"(\d+)日均线下穿(\d+)日均线", sell_text)
    for fast, slow in cross_down:
        f, s = int(fast), int(slow)
        if f"ma{f}" in data.columns and f"ma{s}" in data.columns:
            cond = (data[f"ma{f}"] < data[f"ma{s}"]) & (data[f"ma{f}"].shift(1) >= data[f"ma{s}"].shift(1))
            sell_cond = sell_cond | cond

    # 处理价格跌破均线
    drop_below_ma = re.findall(r"价格.*?跌破(\d+)日均线", sell_text)
    if drop_below_ma:
        use_and = re.search(r"(和|同时|且)", sell_text) is not None

        if use_and:
            temp_cond = pd.Series([True] * len(data))
            for n in drop_below_ma:
                num = int(n)
                if f"ma{num}" in data.columns:
                    temp_cond = temp_cond & (data["close"] < data[f"ma{num}"])
            sell_cond = sell_cond | temp_cond
        else:
            for n in drop_below_ma:
                num = int(n)
                if f"ma{num}" in data.columns:
                    cond = data["close"] < data[f"ma{num}"]
                    sell_cond = sell_cond | cond

    data.loc[sell_cond, "sell_signal"] = 1

    # 仓位逻辑 + 止盈止损
    sl_rate = None
    tp_rate = None
    sl_percent = re.findall(r"(\d+)%?", stop_loss_text)
    if sl_percent:
        sl_rate = -float(sl_percent[0]) / 100
    tp_percent = re.findall(r"(\d+)%?", take_profit_text)
    if tp_percent:
        tp_rate = float(tp_percent[0]) / 100

    for i in range(1, len(data)):
        pre_pos = data["position"].iloc[i - 1]
        curr_close = data["close"].iloc[i]

        if pre_pos == 1:
            buy_p = data["buy_price"].iloc[i - 1]
            if sl_rate is not None and curr_close <= buy_p * (1 + sl_rate):
                data.loc[i, "position"] = 0
                continue
            if tp_rate is not None and curr_close >= buy_p * (1 + tp_rate):
                data.loc[i, "position"] = 0
                continue
            if data["sell_signal"].iloc[i] == 1:
                data.loc[i, "position"] = 0
                continue
            data.loc[i, "position"] = 1
            data.loc[i, "buy_price"] = buy_p
        else:
            if data["buy_signal"].iloc[i] == 1:
                data.loc[i, "position"] = 1
                data.loc[i, "buy_price"] = curr_close
            else:
                data.loc[i, "position"] = 0

    # ✅ 生成可直接运行的量化代码（图表已删除所有文字）
    quant_code = f"""# Auto-generated Quant Trading Strategy Code
# Strategy: {strategy_text}
# Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}

import tushare as ts
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Configure Tushare
ts.set_token("{TUSHARE_TOKEN if TUSHARE_TOKEN else 'YOUR_TUSHARE_TOKEN'}")
pro = ts.pro_api()

# Get data
symbol = "{symbol}"
df = pro.daily(ts_code=symbol, start_date='{data['trade_date'].iloc[0]}', end_date='{data['trade_date'].iloc[-1]}')
df = df.sort_values("trade_date").reset_index(drop=True)
df["date"] = pd.to_datetime(df["trade_date"])
df["close"] = df["close"].astype(float)
df["return"] = df["close"].pct_change()

# Calculate moving averages
"""
    for num in ma_nums:
        quant_code += f'df["ma{num}"] = df["close"].rolling({num}).mean()\n'

    quant_code += f"""
# Generate signals
df["buy_signal"] = 0
df["sell_signal"] = 0
df["position"] = 0
df["buy_price"] = np.nan

# Buy conditions
"""
    if cross_up:
        for fast, slow in cross_up:
            quant_code += f'# {fast} MA crosses above {slow} MA\n'
            quant_code += f'buy_cond = (df["ma{fast}"] > df["ma{slow}"]) & (df["ma{fast}"].shift(1) <= df["ma{slow}"].shift(1))\n'
            quant_code += 'df.loc[buy_cond, "buy_signal"] = 1\n\n'

    if stand_on_ma:
        if use_and:
            quant_code += '# Price stands above all MAs\n'
            cond_str = ' & '.join([f'(df["close"] > df["ma{n}"])' for n in stand_on_ma])
            quant_code += f'buy_cond = {cond_str}\n'
        else:
            quant_code += '# Price stands above any MA\n'
            cond_str = ' | '.join([f'(df["close"] > df["ma{n}"])' for n in stand_on_ma])
            quant_code += f'buy_cond = {cond_str}\n'
        quant_code += 'df.loc[buy_cond, "buy_signal"] = 1\n\n'

    quant_code += f"""# Sell conditions
"""
    if cross_down:
        for fast, slow in cross_down:
            quant_code += f'# {fast} MA crosses below {slow} MA\n'
            quant_code += f'sell_cond = (df["ma{fast}"] < df["ma{slow}"]) & (df["ma{fast}"].shift(1) >= df["ma{slow}"].shift(1))\n'
            quant_code += 'df.loc[sell_cond, "sell_signal"] = 1\n\n'

    if drop_below_ma:
        if use_and:
            quant_code += '# Price drops below all MAs\n'
            cond_str = ' & '.join([f'(df["close"] < df["ma{n}"])' for n in drop_below_ma])
            quant_code += f'sell_cond = {cond_str}\n'
        else:
            quant_code += '# Price drops below any MA\n'
            cond_str = ' | '.join([f'(df["close"] < df["ma{n}"])' for n in drop_below_ma])
            quant_code += f'sell_cond = {cond_str}\n'
        quant_code += 'df.loc[sell_cond, "sell_signal"] = 1\n\n'

    quant_code += f"""# Position logic + Stop loss / Take profit
sl_rate = {sl_rate if sl_rate else None}  # Stop loss ratio
tp_rate = {tp_rate if tp_rate else None}  # Take profit ratio

for i in range(1, len(df)):
    pre_pos = df["position"].iloc[i-1]
    curr_close = df["close"].iloc[i]

    if pre_pos == 1:
        buy_p = df["buy_price"].iloc[i-1]
        if sl_rate is not None and curr_close <= buy_p * (1 + sl_rate):
            df.loc[i, "position"] = 0
            continue
        if tp_rate is not None and curr_close >= buy_p * (1 + tp_rate):
            df.loc[i, "position"] = 0
            continue
        if df["sell_signal"].iloc[i] == 1:
            df.loc[i, "position"] = 0
            continue
        df.loc[i, "position"] = 1
        df.loc[i, "buy_price"] = buy_p
    else:
        if df["buy_signal"].iloc[i] == 1:
            df.loc[i, "position"] = 1
            df.loc[i, "buy_price"] = curr_close
        else:
            df.loc[i, "position"] = 0

# Calculate returns
df["strategy_return"] = df["position"].shift(1) * df["return"]
df["strategy_return"] = df["strategy_return"].fillna(0)
df["Benchmark Return (%)"] = (df["close"] / df["close"].iloc[0]) * 100
df["Strategy Return (%)"] = (1 + df["strategy_return"]).cumprod() * 100

# ✅ 极简图表（无任何文字，彻底解决乱码）
plt.rcParams['axes.unicode_minus'] = False

fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(df["date"], df["Benchmark Return (%)"], color="#2196F3", linewidth=2)
ax.plot(df["date"], df["Strategy Return (%)"], color="#F44336", linewidth=2)

# Mark buy/sell points
buy_points = df[df["buy_signal"] == 1]
sell_points = df[df["sell_signal"] == 1]
ax.scatter(buy_points["date"], buy_points["Benchmark Return (%)"], color="green", marker="^", s=100)
ax.scatter(sell_points["date"], sell_points["Benchmark Return (%)"], color="red", marker="v", s=100)

ax.grid(True, alpha=0.3)
plt.xticks(rotation=45)
plt.show()
"""

    return data, msg, quant_code