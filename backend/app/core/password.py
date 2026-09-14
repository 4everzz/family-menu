"""密码的哈希与校验。

为什么不直接存密码明文？
    数据库一旦外流（备份被拷走、被拖库），明文密码等于把用户的账号直接送人。
    更糟的是很多人多个网站复用同一个密码，泄露一个等于泄露一片。
    所以库里只存"哈希"——一个不可逆的指纹，就算泄露也推不回原密码。

为什么用 bcrypt，而不是 SHA-256 这类普通哈希？
    SHA-256 是为"快"设计的：一块显卡一秒能算几十亿次，
    八位随机密码几个小时就能穷举完。快，在这里恰恰是缺点。
    bcrypt 是为"慢"设计的，并且有两个关键特性：
      · 加盐：每个密码配一段随机盐一起算，所以同样的密码算出来的哈希也不一样。
             破解者没法预先算一张"常见密码 → 哈希"的大表来批量比对。
      · 成本因子：算一次固定要花一点时间（几十毫秒），暴力尝试的代价被成倍放大。
    这点"慢"只在登录那一下发生，用户完全感觉不到，
    但对批量破解的人来说，成本翻了几个数量级。

关于 bcrypt 的 72 字节上限：
    bcrypt 只计算密码的前 72 个字节，超出部分被忽略。
    如果不加限制，用户会以为自己设的 100 位密码很安全，其实后面 20 位根本没参与。
    所以这里把长度上限压在 72 以下，让"能输入的"和"真正生效的"保持一致。
"""

import bcrypt

# 密码长度限制。单位是字符数。
# 上限 64 是刻意压的：中文密码一个字占 3 个字节，64 字符最坏情况约 192 字节，
# 所以这里还要在编码后按字节再挡一次（见 hash_password 的说明）。
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64

# bcrypt 实际参与计算的字节上限
_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    """把明文密码转成可直接存库的哈希字符串。

    gensalt() 会自动生成随机盐，并且把盐、成本因子一起编码进返回值里，
    所以数据库不需要单独存盐——校验时从这串哈希里就能把它们取回来。
    """
    encoded = plain.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        # 走到这里说明调用方漏了长度校验；宁可报错也不要静默"只算一部分"，
        # 否则用户会以为自己设了个强密码。
        raise ValueError(f"密码编码后超过 {_BCRYPT_MAX_BYTES} 字节，bcrypt 无法完整参与计算")

    hashed = bcrypt.hashpw(encoded, bcrypt.gensalt())
    # bcrypt 输出的是 ASCII 字节串（salt + hash 的 base64），转成字符串方便存 varchar
    return hashed.decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    """校验明文密码是否与库里的哈希匹配。

    hashed 为空（这个账号还没设过密码）时一律返回 False，而不是抛异常：
    对调用方来说，"没设密码"和"密码不对"是同一件事——这次登录不成立。
    把两种情况合并处理，接口层就不用写两套分支。

    另外故意不区分"用户不存在"和"密码错误"（见 AuthService）：
    如果分开提示，攻击者就能拿一堆用户名来试，从提示语里判断哪些账号真实存在。
    """
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        # 库里的哈希格式不合法（比如被人手工改过、或者从别处导入了脏数据）。
        # 当作"校验不通过"处理，不要让这个异常漏到接口层变成 500。
        return False
