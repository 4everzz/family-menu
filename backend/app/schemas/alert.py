"""提醒（异常状态聚合）接口的契约。

这一层只定义"前后端之间传什么"，不写任何规则：
   - 提醒是**实时算出来的**，不是一张表——后端把冰箱里"该注意的状态"聚合成列表返给前端。
   - 所以这里只有一个响应结构 AlertResponse，没有创建/修改的请求体。

为什么用 stable id（如 "fridge_expiring:123"）而不是数据库自增 ID？
   提醒本身不落库（v1 不持久化"已忽略"），没有自己的主键。
   但前端列表渲染、以及将来要做"忽略这条"时，都需要一个稳定且唯一的标识，
   用 "类型:食材ID" 拼出来既稳定又能反查到具体食材，够用了。
"""

from pydantic import BaseModel


class AlertResponse(BaseModel):
    """一条提醒。

    字段说明：
    - id：稳定唯一标识（"类型:关联ID"），用于列表 key 与（将来的）忽略状态。
    - type：提醒类型，目前只有 fridge_expiring / fridge_out 两类。
    - level：紧急程度，danger（已过期/缺货）比 warning（临期）更紧急。
    - title：一句话标题，如「鸡蛋 已过期」「鸡蛋 3 天后过期」「鸡蛋 缺货」。
    - detail：补充说明，如「保质期 2026-09-18」「库存 0 个」。
    - related_id：关联的食材 ID（可空），方便前端跳到对应食材编辑页。
    - action：点击这条提醒要跳转的前端路由，如 /pages/fridge/edit?id=123。
    """

    id: str
    type: str
    level: str
    title: str
    detail: str
    related_id: int | None = None
    action: str
