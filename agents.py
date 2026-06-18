import re
import numpy as np
from langchain_deepseek import ChatDeepSeek
from config import DEEPSEEK_APIKEY
from utils import get_latest_news

# Agent Prompt模板
DEBATE_PROMPTS = {
    "mood": """你是【市场情绪分析师Agent】，基于以下最新信息对 {symbol} 打分（1–10）。
最新市场信息：{latest_news}
当前辩论轮数：{round}。
历史观点：{history}
输出格式（严格）：
分数：X
理由：（1–2句话，基于最新信息分析）
反驳：（针对其他Agent观点，没有就写“无”）""",

    "news": """你是【热点资讯分析师Agent】，基于以下最新信息对 {symbol} 打分（1–10）。
最新市场信息：{latest_news}
当前辩论轮数：{round}。
历史观点：{history}
输出格式（严格）：
分数：X
理由：（1–2句话，基于最新信息分析）
反驳：（针对其他Agent观点，没有就写“无”）""",

    "risk": """你是【风险分析师Agent】，基于以下最新信息对 {symbol} 打分（1–10，越高风险越小）。
最新市场信息：{latest_news}
当前辩论轮数：{round}。
历史观点：{history}
输出格式（严格）：
分数：X
理由：（1–2句话，基于最新信息分析）
反驳：（针对其他Agent观点，没有就写“无”）""",

    "trend": """你是【趋势技术分析师Agent】，对 {symbol} 打分（1–10）。
当前辩论轮数：{round}。
历史观点：{history}
输出格式（严格）：
分数：X
理由：（1–2句话，基于技术面分析）
反驳：（针对其他Agent观点，没有就写“无”）""",

    "value": """你是【价值基本面分析师Agent】，对 {symbol} 打分（1–10）。
当前辩论轮数：{round}。
历史观点：{history}
输出格式（严格）：
分数：X
理由：（1–2句话，基于基本面分析）
反驳：（针对其他Agent观点，没有就写“无”）"""
}

JUDGE_PROMPT = """你是主裁判Agent，汇总5个Agent对 {symbol} 的辩论与评分。
历史辩论记录：{full_history}
任务：
1. 计算平均分、最高分、最低分
2. 给出最终综合评分（1–10）
3. 给出明确投资结论（强烈看多/看多/中性/看空/强烈看空）
4. 给出简短的综合分析理由
5. 提炼3条核心投资要点
"""

STOCK_COMMENT_PROMPT = """
请你作为一名专业的股票分析师Agent，为{symbol}生成一份专业、客观的股评报告。
请严格按照以下结构输出，不要添加任何多余的内容：

# {symbol} 专业股评报告

## 一、基本信息与最新行情
- 最新价格：{latest_price:.2f}元
- 当日涨跌幅：{change:.2f}%
- 5日均线：{ma5:.2f}元
- 20日均线：{ma20:.2f}元

## 二、最新市场动态与新闻
{latest_news}

## 三、技术面分析
基于最近3个月的K线走势和均线系统，分析当前技术形态、趋势方向、支撑位和压力位。

## 四、基本面分析
结合公司所处行业、近期经营情况和市场预期，分析公司的基本面状况。

## 五、风险提示
列出当前投资该股票可能面临的主要风险，包括市场风险、行业风险、公司风险等。

## 六、综合投资建议
给出客观的投资建议，包括短期和中长期的操作思路。
注意：仅作为投资参考，不构成任何投资建议。

要求：
1. 语言专业、简洁、客观，避免情绪化表达
2. 数据准确，基于提供的行情和新闻信息
3. 分析要有理有据，逻辑清晰
4. 不要预测具体股价，只分析趋势和可能性
"""


# ✅ 已修复：进度条数值越界bug
def committee(symbol: str, debate_rounds: int = 2, progress_bar=None, status_text=None) -> dict:
    try:
        if status_text:
            status_text.text("🔍 获取最新市场信息...")
        if progress_bar:
            progress_bar.progress(5)
        latest_news = get_latest_news(symbol)
        if progress_bar:
            progress_bar.progress(10)

        if status_text:
            status_text.text("🔍 初始化Agent模型...")
        judge_agent = ChatDeepSeek(
            model="deepseek-v4-pro",
            api_key=DEEPSEEK_APIKEY,
            base_url="https://api.deepseek.com/v1",
            temperature=0.1,
            max_tokens=2048,
            timeout=60
        )

        worker_cfg = {
            "model": "deepseek-v4-flash",
            "api_key": DEEPSEEK_APIKEY,
            "base_url": "https://api.deepseek.com/v1",
            "temperature": 0.4,
            "max_tokens": 1024,
            "timeout": 30
        }
        agents = {k: ChatDeepSeek(**worker_cfg) for k in DEBATE_PROMPTS.keys()}
        if progress_bar:
            progress_bar.progress(20)

        # 多轮Agent辩论（✅ 修复进度条计算逻辑）
        debate_history = []
        all_scores = {}
        progress_per_round = int(70 / debate_rounds)  # 辩论阶段总共占70%进度

        for r in range(1, debate_rounds + 1):
            if status_text:
                status_text.text(f"🔍 第 {r} 轮辩论中...")
            round_data = {"round": r, "opinions": {}, "scores": {}}
            for name, agent in agents.items():
                prompt = DEBATE_PROMPTS[name].format(
                    symbol=symbol, round=r, history=debate_history, latest_news=latest_news
                )
                resp = agent.invoke(prompt).content

                # 提取分数
                score_match = re.search(r"分数[:：]\s*(\d+)", resp)
                score = int(score_match.group(1)) if score_match else 5
                round_data["scores"][name] = score
                round_data["opinions"][name] = resp

                if name not in all_scores:
                    all_scores[name] = []
                all_scores[name].append(score)

            debate_history.append(round_data)
            if progress_bar:
                # 每轮辩论结束更新进度
                current_progress = 20 + r * progress_per_round
                progress_bar.progress(min(current_progress, 90))  # 不超过90%

        # 主裁判汇总结论
        if status_text:
            status_text.text("🔍 主裁判Agent汇总结论中...")
        full_history = "\n".join([f"轮{r['round']}：{r['opinions']}" for r in debate_history])
        judge_resp = judge_agent.invoke(JUDGE_PROMPT.format(symbol=symbol, full_history=full_history)).content

        if progress_bar:
            progress_bar.progress(100)
        if status_text:
            status_text.text("✅ 辩论投研完成！")

        # 计算平均分数
        avg_scores = {k: round(np.mean(v), 1) for k, v in all_scores.items()}
        final_avg = round(np.mean(list(avg_scores.values())), 1)

        return {
            "success": True,
            "symbol": symbol,
            "debate_history": debate_history,
            "judge_conclusion": judge_resp,
            "avg_scores": avg_scores,
            "final_score": final_avg
        }
    except Exception as e:
        error_msg = f"❌ 辩论投研流程失败: {str(e)}"
        if status_text:
            status_text.text(error_msg)
        return {"success": False, "msg": str(e)}


# 生成股评函数
def generate_stock_comment(symbol: str) -> str:
    from utils import get_tushare_data
    import time

    df = get_tushare_data(symbol, start_date='20260101', end_date=time.strftime('%Y%m%d'))
    latest_price = df.iloc[-1]['close']
    change = (df.iloc[-1]['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close'] * 100
    ma5 = df['close'].rolling(5).mean().iloc[-1]
    ma20 = df['close'].rolling(20).mean().iloc[-1]

    latest_news = get_latest_news(symbol)

    llm = ChatDeepSeek(
        model="deepseek-v4-pro",
        api_key=DEEPSEEK_APIKEY,
        base_url="https://api.deepseek.com/v1",
        temperature=0.3,
        max_tokens=4096
    )

    prompt = STOCK_COMMENT_PROMPT.format(
        symbol=symbol,
        latest_price=latest_price,
        change=change,
        ma5=ma5,
        ma20=ma20,
        latest_news=latest_news
    )

    return llm.invoke(prompt).content