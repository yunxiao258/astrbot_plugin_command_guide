"""astrbot_plugin_command_guide 纯函数单元测试（不依赖 AstrBot 运行时）。

运行：python -m unittest test_command_guide -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astrbot_plugin_command_guide.main import (
    build_pages,
    count_commands,
    filter_descriptors,
    format_command_block,
    group_by_plugin,
    parse_guide_args,
)


def make_desc(**kw):
    """构造 list_commands 风格的指令描述 dict。"""
    base = {
        "handler_full_name": "demo.main",
        "handler_name": "main",
        "plugin": "astrbot_plugin_demo",
        "plugin_display_name": None,
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


class TestParseArgs(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(parse_guide_args(""), (None, 1))
        self.assertEqual(parse_guide_args("   "), (None, 1))

    def test_plain_page(self):
        self.assertEqual(parse_guide_args("2"), (None, 2))
        self.assertEqual(parse_guide_args("10"), (None, 10))

    def test_zero_page_clamped(self):
        self.assertEqual(parse_guide_args("0"), (None, 1))

    def test_keyword(self):
        self.assertEqual(parse_guide_args("打卡"), ("打卡", 1))
        self.assertEqual(parse_guide_args("卧 底"), ("卧 底", 1))

    def test_keyword_with_page(self):
        self.assertEqual(parse_guide_args("打卡 2"), ("打卡", 2))
        self.assertEqual(parse_guide_args("卧底 数据 3"), ("卧底 数据", 3))

    def test_non_numeric_tail(self):
        self.assertEqual(parse_guide_args("2024 数据"), ("2024 数据", 1))
        self.assertEqual(parse_guide_args("a 3 b"), ("a 3 b", 1))


class TestFilter(unittest.TestCase):
    def test_reserved_filter(self):
        cmds = [
            make_desc(plugin="astrbot", effective_command="help", reserved=True),
            make_desc(effective_command="hello"),
        ]
        out = filter_descriptors(cmds, include_reserved=False)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["effective_command"], "hello")

    def test_reserved_subcommand_filter(self):
        cmds = [
            make_desc(
                effective_command="game",
                is_group=True,
                sub_commands=[
                    make_desc(
                        effective_command="game x",
                        parent_signature="game",
                        original_command="x",
                        reserved=True,
                    ),
                    make_desc(
                        effective_command="game y",
                        parent_signature="game",
                        original_command="y",
                    ),
                ],
            )
        ]
        out = filter_descriptors(cmds, include_reserved=False)
        self.assertEqual(len(out[0]["sub_commands"]), 1)
        self.assertEqual(out[0]["sub_commands"][0]["effective_command"], "game y")

    def test_disabled_filter(self):
        cmds = [
            make_desc(effective_command="on"),
            make_desc(effective_command="off", enabled=False),
        ]
        out = filter_descriptors(cmds, show_disabled=False)
        self.assertEqual([d["effective_command"] for d in out], ["on"])

    def test_disabled_subcommand_filter(self):
        cmds = [
            make_desc(
                effective_command="game",
                is_group=True,
                sub_commands=[
                    make_desc(
                        effective_command="game a",
                        parent_signature="game",
                        original_command="a",
                        enabled=False,
                    ),
                    make_desc(
                        effective_command="game b",
                        parent_signature="game",
                        original_command="b",
                    ),
                ],
            )
        ]
        out = filter_descriptors(cmds, show_disabled=False)
        self.assertEqual(len(out[0]["sub_commands"]), 1)
        self.assertEqual(out[0]["sub_commands"][0]["effective_command"], "game b")

    def test_keyword_hit_self_keeps_block(self):
        cmds = [
            make_desc(
                effective_command="game",
                is_group=True,
                description="小游戏合集",
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
                    ),
                ],
            )
        ]
        out = filter_descriptors(cmds, keyword="游戏")
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]["sub_commands"]), 2)

    def test_keyword_hit_subcommand_only(self):
        cmds = [
            make_desc(
                effective_command="game",
                is_group=True,
                description="小游戏合集",
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
            )
        ]
        out = filter_descriptors(cmds, keyword="卧底")
        self.assertEqual(len(out), 1)
        subs = out[0]["sub_commands"]
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["original_command"], "卧底")

    def test_keyword_no_hit(self):
        cmds = [make_desc(effective_command="hello", description="打招呼")]
        self.assertEqual(filter_descriptors(cmds, keyword="不存在的"), [])

    def test_keyword_match_alias(self):
        cmds = [make_desc(effective_command="hello", aliases=["hi", "你好"])]
        out = filter_descriptors(cmds, keyword="hi")
        self.assertEqual(len(out), 1)

    def test_keyword_match_plugin_name(self):
        cmds = [make_desc(plugin="astrbot_plugin_memo", effective_command="备忘")]
        out = filter_descriptors(cmds, keyword="memo")
        self.assertEqual(len(out), 1)

    def test_keyword_match_display_name(self):
        cmds = [
            make_desc(
                plugin="astrbot_plugin_demo",
                plugin_display_name="指令大全",
                effective_command="guide",
            )
        ]
        out = filter_descriptors(cmds, keyword="指令大全")
        self.assertEqual(len(out), 1)

    def test_case_insensitive(self):
        cmds = [make_desc(effective_command="Status", description="状态同步")]
        out = filter_descriptors(cmds, keyword="status")
        self.assertEqual(len(out), 1)


class TestGroup(unittest.TestCase):
    def test_group_and_sort(self):
        cmds = [
            make_desc(plugin="astrbot_plugin_b", effective_command="zebra"),
            make_desc(plugin="astrbot_plugin_a", effective_command="banana"),
            make_desc(plugin="astrbot_plugin_a", effective_command="apple"),
        ]
        groups = group_by_plugin(cmds)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["name"], "astrbot_plugin_a")
        self.assertEqual(
            [i["effective_command"] for i in groups[0]["items"]],
            ["apple", "banana"],
        )

    def test_display_name_priority(self):
        cmds = [
            make_desc(
                plugin="astrbot_plugin_a",
                plugin_display_name="备忘录",
                effective_command="备忘",
            )
        ]
        groups = group_by_plugin(cmds)
        self.assertEqual(groups[0]["display"], "备忘录")

    def test_unknown_plugin(self):
        cmds = [make_desc(plugin="", effective_command="x")]
        groups = group_by_plugin(cmds)
        self.assertEqual(groups[0]["display"], "未知插件")


class TestFormat(unittest.TestCase):
    def test_basic_line(self):
        desc = make_desc(effective_command="hello", description="打招呼")
        lines = format_command_block(desc)
        self.assertEqual(lines, ["/hello · 打招呼"])

    def test_admin_permission(self):
        desc = make_desc(effective_command="status", permission="admin")
        lines = format_command_block(desc)
        self.assertIn("[管理员]", lines[0])

    def test_member_permission(self):
        desc = make_desc(effective_command="sync", permission="member")
        lines = format_command_block(desc)
        self.assertIn("[成员]", lines[0])

    def test_everyone_no_mark(self):
        desc = make_desc(effective_command="hello", permission="everyone")
        self.assertNotIn("所有人", format_command_block(desc)[0])

    def test_disabled_mark(self):
        desc = make_desc(effective_command="old", enabled=False)
        lines = format_command_block(desc)
        self.assertIn("[停用]", lines[0])

    def test_aliases(self):
        desc = make_desc(effective_command="hello", aliases=["hi", "你好"])
        lines = format_command_block(desc)
        self.assertIn("/hi", lines[0])
        self.assertIn("/你好", lines[0])

    def test_subcommand_alias_with_parent(self):
        sub = make_desc(
            effective_command="game 卧底",
            parent_signature="game",
            original_command="卧底",
            aliases=["谁是卧底"],
        )
        lines = format_command_block(sub)
        self.assertIn("/game 谁是卧底", lines[0])

    def test_group_marker(self):
        desc = make_desc(effective_command="game", is_group=True)
        lines = format_command_block(desc)
        self.assertIn("📁", lines[0])

    def test_subcommand_indent(self):
        desc = make_desc(
            effective_command="game",
            is_group=True,
            sub_commands=[
                make_desc(
                    effective_command="game 卧底",
                    parent_signature="game",
                    original_command="卧底",
                    description="谁是卧底",
                )
            ],
        )
        lines = format_command_block(desc)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("  /game 卧底"))

    def test_desc_truncated(self):
        desc = make_desc(effective_command="x", description="长" * 100)
        lines = format_command_block(desc)
        self.assertLessEqual(len(lines[0]), 150)
        self.assertIn("…", lines[0])


class TestPages(unittest.TestCase):
    def test_single_page(self):
        cmds = [make_desc(effective_command="a"), make_desc(effective_command="b")]
        pages = build_pages(group_by_plugin(cmds), 2000)
        self.assertEqual(len(pages), 1)
        self.assertIn("/a", pages[0])
        self.assertIn("/b", pages[0])

    def test_multi_page(self):
        cmds = [make_desc(effective_command=f"cmd{i}") for i in range(10)]
        pages = build_pages(group_by_plugin(cmds), 60)
        self.assertGreater(len(pages), 1)
        # 每页都不超过预算（加上后续行会超）
        for p in pages:
            self.assertLessEqual(len(p), 200)
        # 全部内容都在
        joined = "\n".join(pages)
        for i in range(10):
            self.assertIn(f"/cmd{i}", joined)

    def test_big_group_split(self):
        cmds = [make_desc(effective_command=f"x{i}") for i in range(9)]
        pages = build_pages(group_by_plugin(cmds), 50)
        self.assertGreater(len(pages), 1)
        joined = "\n".join(pages)
        for i in range(9):
            self.assertIn(f"/x{i}", joined)

    def test_header_present(self):
        cmds = [make_desc(effective_command=f"y{i}") for i in range(9)]
        pages = build_pages(group_by_plugin(cmds), 50)
        self.assertGreater(len(pages), 1)
        self.assertIn("📁", pages[0])
        # 同组跨页延续时页头只出现一次
        self.assertEqual(sum(p.count("📁") for p in pages), 1)

    def test_empty_groups(self):
        self.assertEqual(build_pages([], 1000), [])

    def test_min_chars_clamped(self):
        cmds = [make_desc(effective_command="a")]
        pages = build_pages(group_by_plugin(cmds), 1)
        self.assertEqual(len(pages), 1)
        self.assertIn("/a", pages[0])


class TestCount(unittest.TestCase):
    def test_count_with_subcommands(self):
        groups = [
            {
                "name": "a",
                "display": "a",
                "items": [
                    make_desc(
                        effective_command="game",
                        is_group=True,
                        sub_commands=[
                            make_desc(effective_command="game x", original_command="x"),
                            make_desc(effective_command="game y", original_command="y"),
                        ],
                    ),
                    make_desc(effective_command="hello"),
                ],
            }
        ]
        self.assertEqual(count_commands(groups), 4)

    def test_count_empty(self):
        self.assertEqual(count_commands([]), 0)


if __name__ == "__main__":
    unittest.main()
