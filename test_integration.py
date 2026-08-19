"""astrbot_plugin_command_guide 集成测试：命令分发、分页、搜索、权限、配置开关。

运行：python test_integration.py
需要 venv 中的 astrbot 包（@register 装饰器依赖）。
"""

import asyncio
import os
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astrbot_plugin_command_guide.main import (
    CommandGuidePlugin,
    PLUGIN_NAME,
)

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}")


class FakeCfg:
    def __init__(self, **kw):
        self.kw = kw

    def get(self, key, default=None):
        return self.kw.get(key, default)


class FakeContext:
    def __init__(self):
        pass


class FakeEvent:
    def __init__(self, message_str, session="default:GroupMessage:1234567890"):
        self.message_str = message_str
        self._session = session
        self.result = None

    @property
    def session(self):
        class _S:
            def __init__(self, v):
                self.v = v

            def __str__(self):
                return self.v

        return _S(self._session)

    def chain_result(self, chain):
        self.result = chain
        return self.result

    def get_plain(self):
        if self.result is None:
            return ""
        return "".join(c.text for c in self.result if hasattr(c, "text"))

def make_plugin(cfg_extra=None):
    cfg = FakeCfg(**{
        "page_chars": 2000,
        "include_reserved": True,
        "show_disabled": True,
        "admin_only": False,
        "admin_umos": "",
        **(cfg_extra or {}),
    })
    return CommandGuidePlugin(FakeContext(), cfg)


def make_desc(**kw):
    base = {
        "handler_full_name": "demo.main",
        "handler_name": "main",
        "plugin": "astrbot_plugin_demo",
        "plugin_display_name": "演示插件",
        "module_path": "astrbot_plugin_demo.main",
        "description": "",
        "type": "command",
        "parent_signature": "",
        "parent_group_handler": "",
        "original_command": "hello",
        "current_fragment": "hello",
        "effective_command": "hello",
        "aliases": [],
        "permission": "everyone",
        "enabled": True,
        "is_group": False,
        "has_conflict": False,
        "reserved": False,
        "sub_commands": [],
    }
    base.update(kw)
    return base


def sample_data():
    """模拟多插件指令数据：含指令组/子命令/停用/内置/别名/权限。"""
    return [
        make_desc(
            plugin="astrbot_plugin_memo",
            plugin_display_name="群聊备忘录",
            effective_command="备忘",
            original_command="备忘",
            description="记录与查看备忘",
            aliases=["memo"],
        ),
        make_desc(
            plugin="astrbot_plugin_memo",
            plugin_display_name="群聊备忘录",
            effective_command="提醒",
            original_command="提醒",
            description="定时提醒",
            permission="admin",
            enabled=False,
        ),
        make_desc(
            plugin="astrbot_plugin_group_games",
            plugin_display_name="群聊小游戏",
            effective_command="game",
            original_command="game",
            description="群聊小游戏合集",
            is_group=True,
            sub_commands=[
                make_desc(
                    effective_command="game 卧底",
                    parent_signature="game",
                    original_command="卧底",
                    description="谁是卧底",
                ),
                make_desc(
                    effective_command="game 24点",
                    parent_signature="game",
                    original_command="24点",
                    description="24点挑战",
                ),
            ],
        ),
        make_desc(
            plugin="astrbot",
            plugin_display_name="AstrBot 系统",
            effective_command="help",
            original_command="help",
            description="内置帮助",
            reserved=True,
        ),
        make_desc(
            plugin="astrbot",
            plugin_display_name="AstrBot 系统",
            effective_command="plugin",
            original_command="plugin",
            description="插件管理",
            reserved=True,
            permission="admin",
        ),
        make_desc(
            plugin="astrbot_plugin_status_sync",
            plugin_display_name="机器状态同步",
            effective_command="机器状态",
            original_command="机器状态",
            description="机器状态概览",
            aliases=["sync", "状态"],
        ),
    ]


def run_cmd(plugin, msg, session="default:GroupMessage:1234567890"):
    async def _run():
        ev = FakeEvent(msg, session)
        await plugin.show_guide(ev)
        return ev.get_plain()

    return asyncio.run(_run())


def test_paging_and_content():
    print("[分页与内容]")
    data = sample_data()
    with patch("astrbot_plugin_command_guide.main.list_commands", new=lambda: coro_of(data)):
        plugin = make_plugin({"page_chars": 2000})
        t = run_cmd(plugin, "指令")
        check("默认展示第 1/1 页", "第 1/1 页" in t)
        check("统计插件与指令数", "共 4 个插件" in t and "8 条指令" in t)
        check("按插件分组显示", "群聊备忘录" in t and "群聊小游戏" in t)
        check("指令行", "/备忘" in t and "/机器状态" in t)
        check("子命令缩进", "/game 卧底" in t)
        check("别名展示", "/memo" in t and "/sync" in t)
        check("停用标记", "[停用/管理员]" in t)
        check("权限标记", "[管理员]" in t)
        check("内置指令也显示", "/plugin" in t)


def coro_of(value):
    """把值包装为协程，模拟 async list_commands。"""
    async def _inner():
        return value

    return _inner()


def test_paging_small_budget():
    print("[小预算分页]")
    data = sample_data()
    with patch("astrbot_plugin_command_guide.main.list_commands", new=lambda: coro_of(data)):
        plugin = make_plugin({"page_chars": 120})
        t1 = run_cmd(plugin, "指令")
        check("小预算自动多页", "第 1/" in t1 and "/" in t1)
        t2 = run_cmd(plugin, "指令 2")
        check("页码翻页", "第 2/" in t2)
        # 翻到超出页数时回退最后一页
        t3 = run_cmd(plugin, "指令 999")
        m3 = re.search(r"第 (\d+)/(\d+) 页", t3)
        check("越界页码回退末页", m3 is not None and m3.group(1) == m3.group(2))
        # 全部指令均出现在各页
        joined = t1 + t2 + t3
        check("跨页内容完整", "/备忘" in joined and "/game 卧底" in joined and "/plugin" in joined)


def test_search():
    print("[关键字搜索]")
    data = sample_data()
    with patch("astrbot_plugin_command_guide.main.list_commands", new=lambda: coro_of(data)):
        plugin = make_plugin()
        t = run_cmd(plugin, "指令 卧底")
        check("子命令搜索命中", "卧底" in t and "/game 卧底" in t)
        check("搜索不显示无关插件", "群聊备忘录" not in t)
        check("搜索页头标记", "搜索: 卧底" in t)
        t2 = run_cmd(plugin, "指令 memo")
        check("别名搜索", "/备忘" in t2)
        t3 = run_cmd(plugin, "指令 状态")
        check("插件描述搜索", "/机器状态" in t3)
        t4 = run_cmd(plugin, "指令 不存在的词")
        check("无结果提示", "未找到" in t4)
        t5 = run_cmd(plugin, "指令 备忘录 2")
        check("关键字+页码解析", "备忘录" in t5)


def test_empty_and_error():
    print("[空数据与异常]")
    plugin = make_plugin()
    with patch("astrbot_plugin_command_guide.main.list_commands", new=lambda: coro_of([])):
        t = run_cmd(plugin, "指令")
        check("空列表提示", "未查询到任何已加载的指令" in t)
    with patch(
        "astrbot_plugin_command_guide.main.list_commands",
        new=lambda: raise_(RuntimeError("db down")),
    ):
        t = run_cmd(plugin, "指令")
        check("核心 API 异常不崩溃", "未查询到任何已加载的指令" in t)


def raise_(exc):
    async def _inner():
        raise exc

    return _inner()


def test_permission():
    print("[权限]")
    data = sample_data()
    with patch("astrbot_plugin_command_guide.main.list_commands", new=lambda: coro_of(data)):
        plugin = make_plugin({"admin_only": True, "admin_umos": "default:GroupMessage:999"})
        t = run_cmd(plugin, "指令")
        check("非管理员被拒绝", "权限" in t and "admin_umos" in t)
        t2 = run_cmd(plugin, "指令", session="default:GroupMessage:999")
        check("白名单管理员可用", "第 1/1 页" in t2)
        plugin2 = make_plugin({"admin_only": True, "admin_umos": ""})
        t3 = run_cmd(plugin2, "指令")
        check("未配置白名单提示", "未配置管理员白名单" in t3)


def test_config_switches():
    print("[配置开关]")
    data = sample_data()
    with patch("astrbot_plugin_command_guide.main.list_commands", new=lambda: coro_of(data)):
        plugin = make_plugin({"show_disabled": False})
        t = run_cmd(plugin, "指令")
        check("关闭停用展示", "[停用]" not in t and "定时提醒" not in t)
        plugin2 = make_plugin({"include_reserved": False})
        t2 = run_cmd(plugin2, "指令")
        check("关闭内置指令", "/plugin" not in t2 and "/help" not in t2)
        check("第三方仍展示", "/备忘" in t2)


def test_plugin_metadata():
    print("[插件元数据]")
    from astrbot_plugin_command_guide import main as m
    check("插件注册名", m.PLUGIN_NAME == PLUGIN_NAME)
    check("版本号", m.PLUGIN_VERSION == "1.0.0")


if __name__ == "__main__":
    test_plugin_metadata()
    test_paging_and_content()
    test_paging_small_budget()
    test_search()
    test_empty_and_error()
    test_permission()
    test_config_switches()
    print(f"\n===== 结果: {PASS} PASS / {FAIL} FAIL =====")
    sys.exit(1 if FAIL else 0)
