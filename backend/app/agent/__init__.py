"""App 内置的 AI Agent：让对话能「自己动手查」，而不是只能干聊。

⭐ 和 `app/mcp/` 的区别（三个东西，方向各不相同，别搞混）：

  · `app/mcp/client`（gateway + servers）：我们的服务去调**别人的** MCP Server，
    用来查食物成分表。
  · `app/mcp/server/`：把**我们的**数据暴露给外面的 AI 客户端（Claude Desktop 等）。
  · `app/agent/`（就是这里）：**App 自己的对话**怎么变成一个会用工具的 Agent。

⭐ 为什么 Agent 的工具**不走 MCP**？
    因为 MCP 那套协议是为**跨进程**而存在的——要起子进程、走 JSON-RPC、
    收一个 token 字符串来做鉴权。App 内的 Agent 和 service 层在**同一个进程**里，
    绕 MCP 一圈等于凭空多一个进程、多一层序列化、多一处故障点
    （stdio 编码、握手超时、stdout 不能 print 这些坑一个都跑不掉），
    而且换不来任何东西。

    所以这里**直接调 service**：
      · 复用 service 层的**权限校验**（`ensure_member`）—— 权限闸门只能有一套；
      · 复用 `MenuQueryService` 的**数据口径**；
      · 不复用 MCP 的协议包装。
"""
