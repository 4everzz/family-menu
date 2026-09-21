"""手工验收：跑一轮**真的** Agent —— 真模型 + 真数据 + 真工具。

和 pytest 的分工：
  · pytest（tests/test_agent.py）测的是**我们这边的逻辑**——循环上限、
    协议消息完整性、权限不能被绕过。用假模型，不打真 API，快且免费。
  · 这个脚本测的是**端到端真的能跑通**：真调千问、真的查到 space 1175 的数据、
    真的按 JSON 契约输出。它回答的是"这东西到底能不能用"，
    而那个问题只能靠真跑一次来回答。

⚠️ 会花一点钱：每个用例 1~2 次模型调用，共 5 个用例。
⚠️ 会占用 AI 每日配额（用于验证配额逻辑本身是通的）。
⚠️ 聊天记录**用完即清**——免得这些测试对话出现在用户的 App 对话页里。
⚠️ 退出前会关掉 MCP 子进程（必须在**同一个事件循环**里关，见 main() 末尾注释）。

用法：
    cd E:\\AI\\menu\\backend
    ./.venv/Scripts/python.exe -m tools.check_agent

想验热量查询的话先把 .env 里设成 MCP_ENABLED=true；
不设也能跑通（`lookup_nutrition` 会如实返回"没查到"，这是**正确行为**不是故障）。
"""

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import delete, func, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.event_loop import apply_selector_loop_policy  # noqa: E402
from app.mcp import gateway  # noqa: E402
from app.models.ai_chat import AiChatMessage  # noqa: E402
from app.repositories.ai_chat_repo import AiChatRepository  # noqa: E402
from app.repositories.user_repo import UserRepository  # noqa: E402
from app.schemas.ai_chat import AiChatRequest  # noqa: E402
from app.services.ai_chat_service import AiChatService  # noqa: E402

# 真人测试账号 zjy（id 1602），家庭组 1175。见项目记忆。
ZJY_USER_ID = 1602
ZJY_SPACE_ID = 1175

#: 每个用例都是**用户真的会说的话**，并标注"期望它怎么做"。
#: 期望写成文字而不是断言——这个脚本是给人看的，不是给 CI 跑的；
#: 打印出来一眼就能看出它对不对劲，比一个 assert 失败信息友好得多。
CASES: list[tuple[str, str]] = [
    ("我冰箱里还有白菜吗", "应该调 list_fridge_items"),
    ("有什么快过期了", "应该调 get_expiring_items"),
    ("今天吃什么好", "应该查冰箱 + 查菜谱，然后推荐"),
    ("晚上吃了红烧肉 500g", "应该调 lookup_nutrition 拿基准值"),
    ("今天天气不错", "闲聊，一次工具都不该调"),
]


def _show(index: int, message: str, expectation: str, result) -> None:
    print("-" * 68)
    print(f"[{index}] 用户：{message}")
    print(f"    期望：{expectation}")

    if result.steps:
        for step in result.steps:
            mark = "OK " if step.ok else "ERR"
            print(f"    [{mark}] {step.tool}({_format_args(step.arguments)}) → {step.detail}")
    else:
        print("    （没有调用任何工具）")

    print(f"    intent：{result.intent}")
    print(f"    回复：{result.reply}")

    for action in result.actions:
        estimated = "估算" if action.calories_estimated else "用户提供"
        print(
            f"    草案：{action.food_name} / {action.portion or '未说份量'} / "
            f"{action.calories} kcal（{estimated}）"
            f" | source={action.source}"
            + (f" | 命中食材={action.matched_food}" if action.matched_food else "")
        )


def _format_args(arguments: dict) -> str:
    if not arguments:
        return ""
    return "、".join(f"{key}={value}" for key, value in arguments.items())


async def main() -> None:
    print("=" * 68)
    print("Agent 端到端验收")
    print(f"  模型      : {settings.chat_model}（temperature={settings.chat_temperature}）")
    print(f"  接入点    : {settings.chat_base_url_effective}")
    mcp_state = "已启用" if settings.mcp_enabled else "未启用（查热量会如实返回「没查到」，属正常）"
    print(f"  MCP 热量源: {mcp_state}")
    print(f"  配额开关  : {'开' if settings.ai_quota_enabled else '关'}")
    print("=" * 68)

    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_id(ZJY_USER_ID)
        if user is None:
            print(f"找不到真人测试账号 id={ZJY_USER_ID}，请先确认库里的数据。")
            return

        # ⚠️ 记下当前最大消息 id：脚本跑完要把自己造的对话删掉，
        #    免得这些验收对话混进用户 App 里的真实聊天记录。
        before = await session.execute(select(func.coalesce(func.max(AiChatMessage.id), 0)))
        max_id_before = int(before.scalar() or 0)

        service = AiChatService(AiChatRepository(session), session)

        for index, (message, expectation) in enumerate(CASES, start=1):
            payload = AiChatRequest(message=message, space_id=str(ZJY_SPACE_ID))
            try:
                result = await service.chat(user, payload)
            except Exception as exc:  # noqa: BLE001 —— 一个用例挂了不影响其它的
                print("-" * 68)
                print(f"[{index}] 用户：{message}")
                print(f"    ✗ 这一轮失败了：{type(exc).__name__}: {exc}")
                continue
            _show(index, message, expectation, result)

        await session.commit()

        # 清掉本次产生的对话记录
        await session.execute(delete(AiChatMessage).where(AiChatMessage.id > max_id_before))
        await session.commit()

        # ⚠️ MCP 会话必须在**同一个事件循环**里关掉。
        #    查热量会起 MCP 子进程；如果不在这里关，asyncio.run 收尾时会由
        #    事件循环的 shutdown 逻辑（另一个任务）去退 anyio 的 cancel scope，
        #    stderr 就会被刷一长串
        #    `Attempted to exit cancel scope in a different task than it was entered in`。
        #    ⚠️ 这是**脚本用法问题**，不是服务的问题——uvicorn 那条路径走 lifespan，
        #       同一个循环同一个任务，一直是干净的。
        await gateway.shutdown_all()

    print("-" * 68)
    print("验收跑完（本次产生的对话记录已清理）")


if __name__ == "__main__":
    apply_selector_loop_policy()
    asyncio.run(main())
