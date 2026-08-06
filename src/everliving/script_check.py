"""Notice when the model answers in Simplified Chinese.

The offline prompt has demanded Traditional Chinese since the beginning — see the
rule in `offline.py` that spells out "所有文字一律用繁體中文,包括 state_changes 的鍵名".
Nothing ever verified it. Groq happened to comply, so the rule looked satisfied for
months; the first local Ollama run produced 「從没见过」 and no part of the system
noticed, because no part of the system was looking.

**Conservative on purpose.** `SIMPLIFIED_ONLY` holds characters that exist only as
simplifications. Every form that is also correct Traditional Chinese is deliberately
absent — 里 (公里), 后 (皇后), 面 (面對), 只 (只有), 干 (干擾), 云, 系, 台, 制, 表, 松, 谷,
表 — even though each of them simplifies something else. Missing a slip costs one
unflagged sentence. Flagging correct prose costs the check itself: a warning that
fires on good output is a warning everyone learns to scroll past.

This reports. It does not repair, and it does not reject: regenerating means another
model call, which on a local model is five minutes of a player staring at nothing.
What to do about a slip is a product decision, and it belongs to the human.
"""

from __future__ import annotations

#: Simplified forms with no legitimate Traditional reading. Grouped roughly by radical
#: so gaps are easy to spot when someone adds to it.
SIMPLIFIED_ONLY = frozenset(
    # 你您他她它那哪 belong to no one — they are identical in both scripts. They were in
    # this set for one commit and the first test on real prose caught them.
    "们个么这"
    "没见过来时会说话语读写记认识让讲论设访证评诊词译试诚详误请课谁调谈谋谢谱"
    "训讯许议计负贝财责败货质贫购贵贸费资赛赞赶趋"
    "东车轨转轮软轻载输辑边达迁运还进远连迟适选递遗邮"
    "国图团园圆场坏块声处备头实宁宝审层岁岛币帮归当录忆怀总恋战"
    "拟择报担拥挥换据损挂摄敌数断无旧显术机权条极构枪样标树档检楼"
    "欢汉汤沟泽洁济测渐满滤滨灭灯灵炉点热爱犹状独猪现环电疗监盘众矿码确礼种积称稳穷竞笔简类粮"
    "紧纯纷绕绍经绩继综编缘纪级纸细终组绝绿缩网罗义习书买卖号员"
    "罚罢联肃肤胜脑脏舰艺节苏药荣获营蓝虑虽蚀补装"
    "观规视觉贯贮贩贤贞"
    "钟钢钥铁铜银铺链销锁锅键镜长门闪闭问闻阅阳阴队阶陆险随隐难雾静"
    "页顶项顺预领频颗题颜风飞饭饮馆马驱验骑鱼鲜鸟鸡鸣齐齿龙龟"
    "华丽举义乐乡书争亚产亲侠俭"
    "变发对开关间"
)


def find_simplified(text: str) -> list[str]:
    """Return the simplified-only characters in `text`, deduplicated, first use first.

    Order matters for the log line: the first offender is usually enough to find the
    sentence it came from.
    """
    seen: dict[str, None] = {}
    for char in text:
        if char in SIMPLIFIED_ONLY:
            seen.setdefault(char, None)
    return list(seen)
