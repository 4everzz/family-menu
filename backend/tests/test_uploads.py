"""图片上传接口测试。

分层验证：
    - Service 层用**注入的临时目录**做单元测试，不污染真实的 uploads/；
    - 接口层用 monkeypatch 把 settings.upload_dir 指到临时目录；
      静态文件能不能被 GET 到，则放到真实 HTTP 实测里验证
      （因为静态挂载发生在应用创建时，测试里重定向不了）。

测试用的"图片"只需要文件头魔数正确即可——
本服务的校验就是按魔数来的，塞一个最小合法头就足以覆盖所有分支。
"""

from pathlib import Path

from httpx import AsyncClient

from app.core.config import settings
from app.services.upload_service import UploadService

# 最小 PNG：8 字节文件头 + 一点内容。校验只看魔数，不需要真能被解码
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_BYTES = PNG_MAGIC + b"fake-png-body-for-test"


def _auth(token: str) -> dict[str, str]:
    """构造带令牌的请求头。"""
    return {"Authorization": f"Bearer {token}"}


async def _login(client: AsyncClient, login_as, prefix: str) -> str:
    """造一个临时用户，返回令牌。"""
    token, _ = await login_as(prefix)
    return token


# ==================== 接口层 ====================


async def test_upload_png_returns_relative_url(
    client: AsyncClient, login_as, tmp_path: Path, monkeypatch
) -> None:
    """上传成功要返回 /uploads/ 开头的相对路径，文件真实落盘。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    token = await _login(client, login_as, "up-ok")

    response = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("菜品照片.png", PNG_BYTES, "image/png")},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["url"].startswith("/uploads/")
    assert data["url"].endswith(".png")
    assert data["contentType"] == "image/png"

    # 文件确实写到了配置的目录里（按年/月分片）
    relative = data["url"].removeprefix("/uploads/")
    saved = tmp_path / relative
    assert saved.is_file()
    assert saved.read_bytes() == PNG_BYTES


async def test_upload_rejects_disallowed_extension(
    client: AsyncClient, login_as, tmp_path: Path, monkeypatch
) -> None:
    """白名单之外的扩展名直接拒绝（哪怕内容是合法图片）。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    token = await _login(client, login_as, "up-ext")

    response = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("说明.txt", PNG_BYTES, "text/plain")},
        headers=_auth(token),
    )
    assert response.status_code == 400, response.text
    assert "只支持" in response.json()["message"]


async def test_upload_rejects_content_mismatch(
    client: AsyncClient, login_as, tmp_path: Path, monkeypatch
) -> None:
    """扩展名叫 .png、内容却不是图片——靠魔数校验拦下来。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    token = await _login(client, login_as, "up-magic")

    response = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("假图片.png", b"this is definitely not a png", "image/png")},
        headers=_auth(token),
    )
    assert response.status_code == 400, response.text
    assert "不是有效的图片" in response.json()["message"]


async def test_upload_rejects_oversized_file(
    client: AsyncClient, login_as, tmp_path: Path, monkeypatch
) -> None:
    """超过大小上限要被拒绝，且上限来自配置（可调）。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "max_upload_bytes", 8)  # 故意调到很小
    token = await _login(client, login_as, "up-size")

    response = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("big.png", PNG_BYTES, "image/png")},
        headers=_auth(token),
    )
    assert response.status_code == 400, response.text
    assert "太大" in response.json()["message"]


async def test_upload_requires_login(client: AsyncClient) -> None:
    """没登录不能上传——上传会产生文件，必须留得住来源。"""
    response = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 401, response.text


async def test_upload_empty_file_rejected(
    client: AsyncClient, login_as, tmp_path: Path, monkeypatch
) -> None:
    """空文件直接拒绝。"""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    token = await _login(client, login_as, "up-empty")

    response = await client.post(
        "/api/v1/uploads/image",
        files={"file": ("empty.png", b"", "image/png")},
        headers=_auth(token),
    )
    assert response.status_code == 400, response.text
    assert "为空" in response.json()["message"]


# ==================== Service 层 ====================


def test_service_generates_unique_random_names(tmp_path: Path) -> None:
    """两次上传得到两个不同的随机文件名；原始文件名绝不落盘。

    这是安全底线：用户提供的文件名可能带路径穿越或恶意字符，
    一旦落盘就是事故。
    """
    service = UploadService(base_dir=tmp_path)

    import asyncio

    first = asyncio.run(service.save_image("任意的名字.png", PNG_BYTES))
    second = asyncio.run(service.save_image("另一个名字.png", PNG_BYTES))

    assert first["url"] != second["url"]
    # 原始文件名不能出现在 URL 里
    assert "任意的名字" not in first["url"]

    # 目录结构是 年/月 两级
    parts = Path(first["url"].removeprefix("/uploads/")).parts
    assert len(parts) == 3  # 年 / 月 / 文件名


def test_service_rejects_empty_content(tmp_path: Path) -> None:
    """空内容在 Service 层也拦一道（接口层之外的最后防线）。"""
    service = UploadService(base_dir=tmp_path)
    import asyncio

    try:
        asyncio.run(service.save_image("a.png", b""))
    except Exception as error:  # noqa: BLE001 - 只断言"抛了业务异常"
        assert "为空" in str(error)
    else:
        raise AssertionError("空内容应该被拒绝")
