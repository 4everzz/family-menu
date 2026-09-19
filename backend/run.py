"""本地开发启动脚本（带热重载）。

为什么要单独一个 run.py，而不是直接敲 uvicorn 命令？
    Windows 上必须把事件循环换成 Selector（原因见 app/core/event_loop.py），
    直接敲 uvicorn 命令很容易忘掉这个参数，然后就报"Psycopg cannot use ProactorEventLoop"。
    把它固化在脚本里，本地开发只需要一条命令：python run.py

⚠️ 端口/绑定地址必须和 启动后端.bat 保持一致（8300 + 0.0.0.0），否则：
    · 端口不一样 → 前端 http.ts 里的 BASE_URL 只认一个端口，换脚本就联不上；
    · 绑 127.0.0.1 → 手机真机调试连不上。
    （8300 而不是 8000：HBuilderX 跑真机调试时会占用 8000/8001，详见 启动后端.bat 的注释。）

用法：
    cd E:\\AI\\menu\\backend
    ./.venv/Scripts/python.exe run.py

启动后可访问：
    本机    http://127.0.0.1:8300/docs
    局域网  http://本机局域网IP:8300/docs   （手机真机调试）
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8300,
        reload=True,  # 改代码后自动重启，开发期方便；线上不用这个脚本
        # 关键：指定自定义事件循环工厂，规避 Windows 上 psycopg 异步不兼容的问题
        loop="app.core.event_loop:selector_loop_factory",
    )
