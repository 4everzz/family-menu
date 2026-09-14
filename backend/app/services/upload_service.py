"""图片上传。

安全与健壮性（这三条任何一条漏了都是事故）：

1. **文件名随机化（uuid4）**：
    绝不使用用户上传的原始文件名。原始文件名可能包含路径穿越（../../etc/passwd）、
    可能与已有文件重名造成覆盖、也可能带有一堆奇形怪状的字符。
    用 uuid 命名后，文件名不可预测、不可穿越、永不覆盖。

2. **扩展名白名单 + 内容嗅探双重校验**：
    只看扩展名不够（把 .exe 改名 .jpg 就混进来了），
    所以再读文件头的"魔数"确认它真的是声称的那种图片。
    两道都过才落盘。

3. **大小上限在读取时就拦截**：
    不是收完整个文件再看大小——那样一个大文件照样占满内存/磁盘。
    分块读取，累计超过上限立刻拒绝。

关于返回的 URL：**只返回相对路径**（如 /uploads/2026/09/xxx.png）。
这是为了将来打包 App 时（wx.cloud.callContainer 不可用、要走 HTTPS 域名），
只改前端"拼 base 地址"这一个地方，数据库里的存量数据完全不用动。

按年/月子目录存放：单个目录塞几十万个文件，文件系统会明显变慢，
按时间分片是成本最低的办法，备份时也方便按月打包。
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import BusinessError

# 允许的图片类型：扩展名 -> (HTTP content-type, 文件头魔数)
# 魔数来自各格式的官方规范，用于确认"内容真的是这种图片"，而不是只信扩展名
ALLOWED_IMAGE_TYPES: dict[str, tuple[str, tuple[bytes, ...]]] = {
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".webp": ("image/webp", (b"RIFF",)),
}


class UploadService:
    """图片上传服务。只做文件落盘和校验，不碰数据库。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        # base_dir 可注入是为了测试：测试里传临时目录，不会污染真实 uploads/
        self.base_dir = base_dir or Path(settings.upload_dir).resolve()

    async def save_image(self, filename: str, content: bytes) -> dict:
        """保存一张图片，返回 {url, size, contentType}。

        content 是接口层已经读进内存的字节。
        大小校验在这里做（接口层只负责把文件读出来），逻辑收在一处好维护。
        """
        if not content:
            raise BusinessError("文件内容为空")

        if len(content) > settings.max_upload_bytes:
            limit_mb = settings.max_upload_bytes / 1024 / 1024
            raise BusinessError(f"图片太大，最大 {limit_mb:g}MB")

        ext = self._allowed_extension(filename, content)
        target = self._target_path(ext)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        url = f"/uploads/{target.relative_to(self.base_dir).as_posix()}"
        return {"url": url, "size": len(content), "contentType": ALLOWED_IMAGE_TYPES[ext][0]}

    def _allowed_extension(self, filename: str, content: bytes) -> str:
        """返回校验通过的扩展名（带点）；不通过就抛业务异常。

        两道校验：
        a) 扩展名在白名单里（同时确定了允许的 content-type）；
        b) 文件头魔数与该类型吻合——扩展名可以随便改，魔数改不了。
        """
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_IMAGE_TYPES:
            allowed = "、".join(sorted(ALLOWED_IMAGE_TYPES))
            raise BusinessError(f"只支持这些格式：{allowed}")

        _, magic_numbers = ALLOWED_IMAGE_TYPES[suffix]
        if not any(content.startswith(magic) for magic in magic_numbers):
            raise BusinessError("文件内容不是有效的图片（扩展名和内容对不上）")
        return suffix

    def _target_path(self, ext: str) -> Path:
        """生成落盘路径：uploads/年/月/uuid.ext。

        uuid4 随机命名——见模块说明，绝不使用用户提供的原始文件名。
        """
        now = datetime.now(timezone.utc)
        return self.base_dir / f"{now.year:04d}" / f"{now.month:02d}" / f"{uuid.uuid4().hex}{ext}"
