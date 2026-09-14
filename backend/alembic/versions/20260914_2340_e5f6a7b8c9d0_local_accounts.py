"""local accounts: split user identity out of users

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-14 23:40:00.000000+08:00

这次改了什么（一句话）：
    把"登录方式"从 users 表搬进新的 user_identities 表，
    并给 users 加上自建账号需要的 username / password_hash 两列。

⚠️ 这是一份"带数据搬运"的迁移，不是纯改结构：
   现有用户的 openid 是他们唯一的登录凭证，直接删列等于这批人全部登不进来。
   所以顺序必须是 建新表 → 搬数据 → 再删旧列，不能图省事反着来。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# 迁移标识（Alembic 用它串起版本链，不要手改）
revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 被这次改动波及的旧列注释，回滚时原样写回去
OLD_NICKNAME_COMMENT = '昵称'
OLD_AVATAR_COMMENT = '头像地址。注意：微信给的链接是临时地址会过期，不可长期依赖'
OLD_OPENID_COMMENT = '微信 openid，同一小程序内唯一，登录时按它查找或创建用户'
OLD_UNIONID_COMMENT = '微信 unionid，仅在绑定了微信开放平台账号时才有，用于跨应用识别同一用户'


def upgrade() -> None:
    """升级：把微信身份搬出 users，并给 users 加上自建账号所需的两列。"""

    # ---------- 1. 新建登录方式表 ----------
    op.create_table(
        'user_identities',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column(
            'user_id',
            sa.BigInteger(),
            nullable=False,
            comment='所属用户。用户注销时这条绑定跟着删（CASCADE）',
        ),
        sa.Column(
            'provider',
            sa.String(length=16),
            nullable=False,
            comment='登录来源。目前取值：wx_mp=微信小程序',
        ),
        sa.Column(
            'external_id',
            sa.String(length=128),
            nullable=False,
            comment='该平台下识别用户的标识。微信小程序存的是 openid',
        ),
        sa.Column(
            'unionid',
            sa.String(length=64),
            nullable=True,
            comment='微信 unionid，用于跨应用识别同一个人；未绑定微信开放平台时为空',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='创建时间',
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='更新时间',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name='user_identities_user_id_fkey',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'provider',
            'external_id',
            name='uq_user_identities_provider_external_id',
        ),
    )
    op.create_index(
        op.f('ix_user_identities_user_id'), 'user_identities', ['user_id'], unique=False
    )
    op.create_index(
        op.f('ix_user_identities_unionid'), 'user_identities', ['unionid'], unique=False
    )

    # ---------- 2. 把现有 openid 搬进新表 ----------
    # 这一步必须发生在删列之前。每个老用户的微信身份变成一行 provider='wx_mp' 的记录，
    # 搬完之后他们照样能用小程序登录，只是身份换了张表存。
    op.execute(
        """
        INSERT INTO user_identities (user_id, provider, external_id, unionid, created_at, updated_at)
        SELECT id, 'wx_mp', openid, unionid, now(), now()
        FROM users
        """
    )

    # ---------- 3. 数据搬完了，才删旧列 ----------
    op.drop_index(op.f('ix_users_unionid'), table_name='users')
    op.drop_index(op.f('ix_users_openid'), table_name='users')
    op.drop_column('users', 'openid')
    op.drop_column('users', 'unionid')

    # ---------- 4. 加上自建账号需要的两列 ----------
    # 两列都允许为空：存量用户是被搬过来的老账号，本来就没有用户名和密码，
    # 只能走微信小程序登录。若设成 NOT NULL，这份迁移对存量数据会直接失败。
    # PostgreSQL 的 unique 索引允许多个 NULL 并存，所以"老用户没有用户名"不会互相冲突。
    op.add_column(
        'users',
        sa.Column(
            'username',
            sa.String(length=32),
            nullable=True,
            comment=(
                '登录用户名：3-20 位 ASCII 字母/数字/下划线，统一存小写（避免 Tom 和 tom 变成两个账号）。'
                '允许为空是为了兼容改造前那批只有微信 openid 的老用户——他们目前只能走小程序登录'
            ),
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'password_hash',
            sa.String(length=128),
            nullable=True,
            comment='密码哈希（bcrypt）。绝不存明文；为空表示该账号尚未设置密码',
        ),
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # ---------- 5. 同步两处列注释 ----------
    # 微信改成自建账号后，这两列的说明已经不对了：头像不再是"微信临时链接"。
    # 注释不改不会影响功能，但留着错误的说明，下次看表的人会被误导。
    op.alter_column(
        'users',
        'nickname',
        existing_type=sa.String(length=64),
        comment='昵称，用户可自行修改',
    )
    op.alter_column(
        'users',
        'avatar_url',
        existing_type=sa.String(length=512),
        comment='头像地址。为空时前端显示默认占位头像，而不是留一片空白',
    )


def downgrade() -> None:
    """回滚：把微信身份搬回 users，并去掉自建账号的两列。

    ⚠️ 这份回滚是有损的，所以它选择"主动报错"而不是"悄悄删数据"：
       旧结构里 openid 是必填且唯一的一列，而自建账号（只有用户名密码）根本没有 openid，
       放不回旧结构。遇到这种账号时这里会直接抛错，让你先决定怎么处理，
       而不是替你把这个账号连同他的家庭组、菜谱一起删掉。
    """
    bind = op.get_bind()

    # ---------- 0. 先检查能不能安全回滚，不能就立刻停下 ----------
    stranded = bind.execute(
        sa.text(
            """
            SELECT count(*) FROM users
            WHERE id NOT IN (
                SELECT user_id FROM user_identities WHERE provider = 'wx_mp'
            )
            """
        )
    ).scalar()
    if stranded:
        raise RuntimeError(
            f"库里有 {stranded} 个账号没有微信身份（自建账号），旧表结构容纳不了它们。"
            "请先单独处理这些账号（迁移或删除），再执行这次回滚。"
        )

    # ---------- 1. 把微信身份搬回 users ----------
    op.add_column(
        'users',
        sa.Column('openid', sa.String(length=64), nullable=True, comment=OLD_OPENID_COMMENT),
    )
    op.add_column(
        'users',
        sa.Column('unionid', sa.String(length=64), nullable=True, comment=OLD_UNIONID_COMMENT),
    )
    bind.execute(
        sa.text(
            """
            UPDATE users AS u
            SET openid = i.external_id, unionid = i.unionid
            FROM user_identities AS i
            WHERE i.user_id = u.id AND i.provider = 'wx_mp'
            """
        )
    )

    # ---------- 2. 恢复旧约束 ----------
    op.alter_column(
        'users',
        'openid',
        existing_type=sa.String(length=64),
        nullable=False,
        comment=OLD_OPENID_COMMENT,
    )
    op.create_index(op.f('ix_users_openid'), 'users', ['openid'], unique=True)
    op.create_index(op.f('ix_users_unionid'), 'users', ['unionid'], unique=False)

    # ---------- 3. 摘掉自建账号的两列 ----------
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'username')

    # ---------- 4. 把两处列注释改回原来的说法 ----------
    op.alter_column(
        'users',
        'nickname',
        existing_type=sa.String(length=64),
        comment=OLD_NICKNAME_COMMENT,
    )
    op.alter_column(
        'users',
        'avatar_url',
        existing_type=sa.String(length=512),
        comment=OLD_AVATAR_COMMENT,
    )

    # ---------- 5. 删掉登录方式表 ----------
    op.drop_index(op.f('ix_user_identities_unionid'), table_name='user_identities')
    op.drop_index(op.f('ix_user_identities_user_id'), table_name='user_identities')
    op.drop_table('user_identities')
