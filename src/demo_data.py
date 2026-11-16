"""Demo account data.

The demo account is a public, low-privilege login (see src/auth.py) whose notes
live in the same table but are flagged `is_demo = True`. They are invisible to
the owner, guests and other visitors, and they are re-seeded once per day so the
demo always looks fresh without keeping anything a visitor typed forever.

Enable it by setting DEMO_PASSWORD in the environment; leaving it empty disables
the demo login entirely.
"""

import os
from datetime import date, datetime, time, timedelta

from src.models.note import Note
from src.models.user import db


def _specs():
    """Notes that make the demo look like a real, slightly used notebook."""
    today = date.today()
    return [
        {
            "title": "下周产品评审会",
            "content": (
                "周二下午三点在会议室 A 和产品、前端一起过下个版本的需求。\n"
                "需要提前准备：原型图、上个版本的用户反馈、性能数据。"
            ),
            "tags": ["会议", "产品", "评审"],
            "event_date": today + timedelta(days=1),
            "event_time": time(15, 0),
            "summary": "周二 15:00 产品评审会，需准备原型图、用户反馈和性能数据。",
            "todos": [
                {"text": "整理上个版本的用户反馈", "done": True},
                {"text": "导出性能数据看板", "done": False},
                {"text": "确认会议室 A 的预约", "done": False},
            ],
        },
        {
            "title": "本周要交付的三件事",
            "content": "1. 支付回调的幂等改造\n2. 订单列表接口补分页\n3. 给测试同学写一份联调说明",
            "tags": ["计划", "开发"],
            "event_date": today + timedelta(days=3),
            "event_time": None,
            "todos": [
                {"text": "支付回调幂等改造", "done": False},
                {"text": "订单列表补分页", "done": False},
                {"text": "写联调说明", "done": False},
            ],
        },
        {
            "title": "读完《重构》第 3 章",
            "content": (
                "这章讲的是「代码的坏味道」，印象最深的是重复代码和过长函数。\n"
                "对照自己的项目，下单逻辑里确实有一段可以抽出来的分支。"
            ),
            "tags": ["阅读", "重构"],
            "event_date": today - timedelta(days=2),
            "event_time": None,
        },
        {
            "title": "周末安排",
            "content": "周六上午去看牙，下午陪爸妈买菜；周日把房间收拾一下，晚上早点睡。",
            "tags": ["生活"],
            "event_date": today + timedelta(days=5),
            "event_time": time(9, 30),
        },
        {
            "title": "关于索引的一点笔记",
            "content": (
                "查询走不走索引，除了看字段有没有索引，还要看区分度。\n"
                "像 status 这种只有几个取值的字段，单独建索引意义不大，"
                "更适合放在联合索引的后面。"
            ),
            "tags": ["数据库", "学习"],
            "event_date": None,
            "event_time": None,
        },
        {
            "title": "和导师讨论论文选题",
            "content": "导师建议把范围收窄到「支付系统的幂等设计」，先做一次文献综述，下周三前发过去。",
            "tags": ["论文", "导师"],
            "event_date": today + timedelta(days=7),
            "event_time": time(14, 0),
            "summary": "论文选题收窄到支付系统幂等设计，下周三前提交文献综述。",
        },
        {
            "title": "一条随手记",
            "content": "早上通勤时想到：如果回调验签失败，除了记日志，还应该留一条可追溯的记录，方便对账。",
            "tags": ["想法"],
            "event_date": None,
            "event_time": None,
        },
    ]


def _seed():
    for index, spec in enumerate(_specs()):
        note = Note(
            title=spec["title"],
            content=spec["content"],
            event_date=spec.get("event_date"),
            event_time=spec.get("event_time"),
            is_public=False,
            is_demo=True,
            author_ip="demo",
            pinned=index == 0,
            summary=spec.get("summary"),
        )
        note.set_tags(spec.get("tags") or [])
        note.set_todos(spec.get("todos") or [])
        db.session.add(note)
    db.session.commit()


def ensure_demo_data(force=False):
    """Seed the demo notes, resetting them once per day.

    Safe to call on every demo login and at startup: it only writes when the
    demo set is missing or older than today.
    """
    if not os.environ.get("DEMO_PASSWORD"):
        return

    try:
        latest = (
            Note.query.filter(Note.is_demo.is_(True))
            .order_by(Note.created_at.desc())
            .first()
        )
        if latest is not None and not force and latest.created_at.date() >= date.today():
            return

        Note.query.filter(Note.is_demo.is_(True)).delete(synchronize_session=False)
        db.session.commit()
        _seed()
    except Exception:  # 演示数据失败不应该影响登录
        db.session.rollback()
        raise
