"""
教学层：把《365天量化金融》课程路径映射为平台内「渐进式、可执行」的引导步骤。

设计原则（对应任务模块 5 + 约束 1「零基础新手无指导完成全链路」）：
  - 每个教学步骤都在平台内「真实可执行」，不是纯文案。
  - 金融术语首次出现附一句白话解释（glossary 字段）。
  - step 类型：
      run     -> 触发一次真实回测（action 含策略与参数）
      tab     -> 跳转到某个功能页
      glossary-> 展示一个术语白话解释
  - 路径示例：第1步看懂指标 → 第4步跑通买入持有 → 第7步双均线 → 第10步修改参数。
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.util.config import get_config

GLOSSARY = {
    "净值": "净值就是「1 块钱起步，现在变成几块钱」。起点净值=1.0；1.5 表示本金涨了 50%。",
    "年化收益率": "把任意时长的收益，折算成「如果按这个速度走满一年」的收益率，方便不同区间互相比较。",
    "夏普比率": "每多承担 1 单位风险，能多赚多少超额收益。越高越「划算」；负数说明风险换不来收益。",
    "最大回撤": "从最高点跌到最低点，最多亏了多少比例。它衡量「最惨能亏多惨」，比平均波动更直观。",
    "前复权": "把历史上的拆股、分红「折算」进价格，让过去和现在的价格可比，直接用来算收益才不会出错。",
    "佣金/印花税/滑点": "佣金是券商手续费；印花税是卖出时交给国家的税；滑点是你下单价和真实成交价之间的微小偏差。三者都会「吃掉」收益。",
    "涨跌停": "A股单日涨跌幅有限制（主板±10%，科创板/创业板±20%）。涨停时买不到，跌停时卖不出。",
    "停牌": "股票临时停止交易（如重大公告）。停牌期间无法买卖，也拿不到当天的价格。",
    "无前瞻偏差": "只用「当时已经知道」的信息做决策。比如用今天收盘信号，只能明天开盘才成交，不能「未卜先知」今天收盘价就成交。",
}


def get_roadmap() -> list:
    cfg = get_config()
    def_sym = cfg["universe"]["default_symbols"]
    bench = cfg["universe"]["benchmark"]
    start = cfg["backtest"]["default_start"]
    end = cfg["backtest"]["default_end"]

    steps = [
        {
            "id": 1, "title": "认识平台与红线：不承诺收益", "tab": "risk",
            "blurb": "先用 30 秒看懂一件事：本平台只用于学习研究，所有回测都是「历史模拟」，不代表未来收益，更不构成投资建议。",
            "glossary_term": "净值",
            "action": {"type": "tab", "target": "risk"},
        },
        {
            "id": 2, "title": "看懂一份回测报告的核心指标", "tab": "config",
            "blurb": "回测跑完会给你一串指标。先认识 4 个最核心的：净值、年化收益率、夏普比率、最大回撤。点下方按钮直接跑一个例子来看。",
            "glossary_term": "夏普比率",
            "action": {"type": "run", "strategy_key": "buy_hold", "params": {},
                       "start": start, "end": end,
                       "caption": "运行：买入持有（默认池）看报告"},
        },
        {
            "id": 3, "title": "三大基础策略范式（课程第29讲）", "tab": "config",
            "blurb": "课程把策略分成三大范式：买入持有、SMA 双均线、月度再平衡。下面三个按钮分别跑一遍，感受它们「动」与「不动」的区别。",
            "glossary_term": "前复权",
            "action": {"type": "run", "strategy_key": "buy_hold", "params": {},
                       "start": start, "end": end,
                       "caption": "① 买入持有"},
            "extra_actions": [
                {"caption": "② SMA双均线(沪深300)", "strategy_key": "sma_dual",
                 "params": {"symbol": bench["symbol"], "asset_type": bench["asset_type"], "fast": 5, "slow": 20}},
                {"caption": "③ 月度再平衡", "strategy_key": "monthly_rebalance", "params": {}},
            ],
        },
        {
            "id": 4, "title": "跑通你的第一个策略：买入持有", "tab": "config",
            "blurb": "这一步的目标：不写任何代码，点一下就跑通完整回测（数据→回测→报告）。这就是「零基础全链路」的第一座里程碑。",
            "glossary_term": "净值",
            "action": {"type": "run", "strategy_key": "buy_hold", "params": {},
                       "start": start, "end": end,
                       "caption": "运行买入持有"},
        },
        {
            "id": 5, "title": "看懂净值曲线与基准对比", "tab": "report",
            "blurb": "报告里的曲线：蓝线是你的策略净值，橙线是基准（沪深300）。曲线一直在 1.0 下方，说明这段时间连「躺着买指数」都在亏——这是 2021–2023 的真实熊市，不是策略的错。",
            "glossary_term": "最大回撤",
            "action": {"type": "run", "strategy_key": "buy_hold", "params": {},
                       "start": start, "end": end,
                       "caption": "运行并查看曲线"},
        },
        {
            "id": 6, "title": "成本如何悄悄吃掉收益", "tab": "report",
            "blurb": "打开报告里的「假设与成本」：佣金万3、印花税万5（仅卖出）、滑点千1。别小看这些，它们会逐笔从你的本金里扣。本平台每一笔成交都扣了这些成本，所以结果是「保守」的。",
            "glossary_term": "佣金/印花税/滑点",
            "action": {"type": "run", "strategy_key": "monthly_rebalance", "params": {},
                       "start": start, "end": end,
                       "caption": "运行月度再平衡看成本"},
        },
        {
            "id": 7, "title": "试试趋势策略：SMA 双均线", "tab": "config",
            "blurb": "金叉买入、死叉卖出。下面用沪深300 跑一遍（快线5日、慢线20日）。注意它买卖更频繁，成本更高，但可能在熊市里少亏一点。",
            "glossary_term": "无前瞻偏差",
            "action": {"type": "run", "strategy_key": "sma_dual",
                       "params": {"symbol": bench["symbol"], "asset_type": bench["asset_type"], "fast": 5, "slow": 20},
                       "start": start, "end": end,
                       "caption": "运行 SMA 双均线(5,20)"},
        },
        {
            "id": 8, "title": "认识市场监管：涨跌停与停牌", "tab": "report",
            "blurb": "A股有涨跌停，停牌时没法交易。本平台在涨停日不允许买入、跌停日不允许卖出，并把这些「没成交」的日子单独列在报告异常区，绝不假装成交。",
            "glossary_term": "涨跌停",
            "action": {"type": "run", "strategy_key": "sma_dual",
                       "params": {"symbol": "600519", "asset_type": "stock", "fast": 5, "slow": 20},
                       "start": start, "end": end,
                       "caption": "运行（看异常区示例）"},
        },
        {
            "id": 9, "title": "纪律性调仓：月度再平衡", "tab": "config",
            "blurb": "每个月第一个交易日，把篮子重新掰回等权重，相当于自动「高抛低吸」一点。跑一遍，对比它和买入持有的交易次数差异。",
            "glossary_term": "停牌",
            "action": {"type": "run", "strategy_key": "monthly_rebalance", "params": {},
                       "start": start, "end": end,
                       "caption": "运行月度再平衡"},
        },
        {
            "id": 10, "title": "亲手改一次参数", "tab": "config",
            "blurb": "进阶第一步：把双均线的快线改成 10、慢线改成 60，再跑一次，看净值和交易次数怎么变。改参数就是你和策略「对话」的方式。",
            "glossary_term": "夏普比率",
            "action": {"type": "run", "strategy_key": "sma_dual",
                       "params": {"symbol": bench["symbol"], "asset_type": bench["asset_type"], "fast": 10, "slow": 60},
                       "start": start, "end": end,
                       "caption": "运行 SMA(10,60) 对比"},
        },
        {
            "id": 11, "title": "数据从哪来？前复权是什么？", "tab": "risk",
            "blurb": "平台行情来自公开免费数据源（新浪/东方财富），使用「前复权」价格。点开「数据与风险」页看数据源、字段与已知限制。",
            "glossary_term": "前复权",
            "action": {"type": "tab", "target": "risk"},
        },
        {
            "id": 12, "title": "下一步学习路径（规划中）", "tab": "risk",
            "blurb": "学会跑通后，你可以继续学：因子研究、模拟交易、蒙特卡洛模拟（课程第17讲）等。这些专业功能在本 MVP 中标记为「规划中」，不影响你已经跑通的核心链路。",
            "glossary_term": "无前瞻偏差",
            "action": {"type": "tab", "target": "risk"},
        },
    ]
    return steps


def get_glossary() -> dict:
    return GLOSSARY
