"""本地开发启动脚本。

为什么要单独一个 run.py，而不是直接敲 uvicorn 命令？
    Windows 上必须把事件循环换成 Selector（原因见 app/core/event_loop.py），
    直接敲 uvicorn 命令很容易忘掉这个参数，然后就报"Psycopg cannot use ProactorEventLoop"。
    把它固化在脚本里，本地开发只需要一条命令：python run.py

用法：
    cd E:\\AI\\menu\\backend
    ./.venv/Scripts/python.exe run.py

启动后可访问 http://127.0.0.1:8000/docs 查看接口文档。
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,  # 改代码后自动重启，开发期方便；线上不用这个脚本
        # 关键：指定自定义事件循环工厂，规避 Windows 上 psycopg 异步不兼容的问题
        loop="app.core.event_loop:selector_loop_factory",
    )
