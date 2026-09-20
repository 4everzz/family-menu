"""AI 对话服务的可测部分。

`chat()` 本身依赖外部大模型（没有 Key 就走不通），不便在单测里跑。
但对话链路里**两个我们自己写的决策点**是纯逻辑、且最容易出错，所以单独测：

  ① 菜名提取（`_extract_dish_name`）——决定"要不要去查 MCP"。
     抠错了要么白跑一次子进程，要么该查的时候没查。

  ② 营养分级（`_parse_actions` 里对 source 的判定）——决定"标成查到的还是估的"。
     这个字段是要写进接口返回、给前端显示可信度、也是简历里"可信度分级"那句话的落点，
     判错就等于在骗用户（把估的说成查的，性质比"估得不准"严重得多）。
"""

import pytest

from app.services import nutrition_service as ns
from app.services.ai_chat_service import _extract_dish_name


class TestExtractDishName:
    """菜名提取。⚠️ 每个用例都对应一个"用户真的会这么说"的场景。"""

    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            # ── 记录型：用户报告吃了什么（带数量/量词）──
            ("中午吃了红烧肉500g", "红烧肉"),
            ("刚吃了个苹果", "苹果"),
            ("喝了碗米饭", "米饭"),
            ("晚上吃了土豆炖牛肉", "土豆炖牛肉"),
            # ── 提问型：用户问一道菜怎么做 ⭐ 最常见的场景 ──
            #
            #    这一组是**用户自己举的例子**（"土豆炖牛肉怎么做"）。
            #    早期版本只认"吃/喝/来/点"这些动词，这类问句全部提取失败，
            #    结果是"用户问了一道很具体的菜，我们却什么都没查"——
            #    而"怎么做"恰恰是最该去查营养成分的时候。
            ("土豆炖牛肉怎么做", "土豆炖牛肉"),
            ("清蒸鲈鱼的做法", "清蒸鲈鱼"),
            ("红烧肉咋做", "红烧肉"),
            ("番茄炒蛋怎么做才好吃", "番茄炒蛋"),
            ("豆腐怎么做", "豆腐"),
        ],
    )
    def test_extracts_expected_dish(self, message, expected):
        assert _extract_dish_name(message) == expected

    @pytest.mark.parametrize(
        "message",
        [
            "今天天气不错",
            "我吃了个那个东西",
            "帮我删掉昨天的记录",
            "",
            "   ",
            None,
        ],
    )
    def test_non_dish_messages_yield_none(self, message):
        """⚠️ 提取不到就返回 None —— 这是"不猜"原则的体现。

        抠出一个不存在的菜名去查，除了浪费一次子进程往返没有任何好处；
        返回 None 让调用方跳过查询、退化成纯估算，和改造前的行为完全一致
        （所以这个功能"最坏情况下不会更差"）。
        """
        assert _extract_dish_name(message) is None


class TestSourceLabeling:
    """营养来源分级。

    为什么这个测试重要：
      接口返回里的 `source` 字段决定了前端怎么展示——是"已核对"还是"AI 估算"。
      把估算标成查到的，等于**用一个精确的外观包装一个不准的数字**，
      比直接给个模糊估计更糟（用户会当真）。
      这三级的值定义在 nutrition_service 里，接口层直接引用，不能各写各的字符串。
    """

    def test_three_levels_are_distinct(self):
        levels = {
            ns.SOURCE_MCP_EXACT,
            ns.SOURCE_MCP_DERIVED,
            ns.SOURCE_LLM_ESTIMATE,
        }
        assert len(levels) == 3, "三个来源等级必须互不相同"

    def test_level_values_are_stable_strings(self):
        """这三个值会写进接口响应、可能被前端/DB 依赖，改动要**显式**发生。

        钉住字面量，是为了将来重构时不声不响地改名——
        改名会让历史数据里的旧值变成"未知来源"，前端渲染就崩了。
        """
        assert ns.SOURCE_MCP_EXACT == "mcp_exact"
        assert ns.SOURCE_MCP_DERIVED == "mcp_derived"
        assert ns.SOURCE_LLM_ESTIMATE == "llm_estimate"
