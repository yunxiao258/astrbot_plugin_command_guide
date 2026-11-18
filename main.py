"""AstrBot 指令大全插件：一键查询所有已加载插件的指令、别名、权限与说明

数据来源为 AstrBot 核心的 list_commands()（自动包含指令组与子命令结构）。
"""

from __future__ import annotations

import re
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.all import MessageEventResult
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.star.command_management import list_commands

# 插件元数据
PLUGIN_NAME = "astrbot_plugin_command_guide"
PLUGIN_AUTHOR = "云晓"
PLUGIN_DESC = "指令大全：一键查询所有插件的指令、别名、权限与说明"
PLUGIN_VERSION = "1.0.1"

_CMD_NAME = "指令"
DEFAULT_PAGE_CHARS = 2000  # 每页最大字符数（QQ 等平台单条消息长度安全值）
MAX_DESC_CHARS = 80  # 单条指令描述最长展示长度，超出截断
PERMISSION_LABELS = {"everyone": "所有人", "member": "成员", "admin": "管理员"}


def parse_guide_args(text: str) -> tuple[str | None, int]:
    """解析 /指令 命令参数，返回 (关键字, 页码)。

    规则：
    - 无参数 -> (None, 1)
    - 单个纯数字 -> (None, N)，视为翻页
    - 末段为纯数字且参数 >= 2 -> 前段为关键字，末段为页码
    - 其他 -> 全部内容作为关键字，页码 1
    """
    parts = [p for p in re.split(r"\s+", text.strip()) if p]
    if not parts:
        return None, 1
    if len(parts) >= 2 and parts[-1].isdigit():
        keyword = " ".join(parts[:-1]).strip() or None
        return keyword, max(1, int(parts[-1]))
    if len(parts) == 1 and parts[0].isdigit():
        return None, max(1, int(parts[0]))
    return " ".join(parts).strip() or None, 1


def _match_keyword(desc: dict[str, Any], keyword: str) -> bool:
    """指令是否命中关键字（插件名/显示名/指令名/原始名/父级签名/别名/描述）。"""
    kw = keyword.lower()
    fields = [
        str(desc.get("plugin", "")),
        str(desc.get("plugin_display_name", "") or ""),
        str(desc.get("effective_command", "") or ""),
        str(desc.get("original_command", "") or ""),
        str(desc.get("parent_signature", "") or ""),
        str(desc.get("description", "") or ""),
    ]
    fields.extend(str(a) for a in (desc.get("aliases") or []))
    return any(f and kw in f.lower() for f in fields)


def filter_descriptors(
    descriptors: list[dict[str, Any]],
    keyword: str | None = None,
    include_reserved: bool = True,
    show_disabled: bool = True,
) -> list[dict[str, Any]]:
    """按配置与关键字过滤指令列表。

    - include_reserved=False：剔除 AstrBot 内置（reserved）指令及其子命令
    - show_disabled=False：剔除已停用指令（顶层与子命令）
    - keyword 命中顶层指令时保留整块（含子命令）；仅子命令命中时只保留命中的子命令
    """
    kw = (keyword or "").strip().lower()
    result: list[dict[str, Any]] = []
    for desc in descriptors:
        subs = list(desc.get("sub_commands") or [])
        if not include_reserved:
            if desc.get("reserved"):
                continue
            subs = [s for s in subs if not s.get("reserved")]
        if not show_disabled:
            if not desc.get("enabled", True):
                continue
            subs = [s for s in subs if s.get("enabled", True)]
        if kw:
            hit_self = _match_keyword(desc, kw)
            hit_subs = [s for s in subs if _match_keyword(s, kw)]
            if not hit_self and not hit_subs:
                continue
            if not hit_self:
                desc = {**desc, "sub_commands": hit_subs}
                subs = hit_subs
        if subs != (desc.get("sub_commands") or []):
            desc = {**desc, "sub_commands": subs}
        result.append(desc)
    return result


def group_by_plugin(descriptors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按插件分组：组内按 effective_command 字典序，组间按显示名排序。"""
    groups: dict[str, dict[str, Any]] = {}
    for desc in descriptors:
        plugin = str(desc.get("plugin") or "未知插件")
        g = groups.get(plugin)
        if g is None:
            g = groups[plugin] = {
                "name": plugin,
                "display": str(desc.get("plugin_display_name") or plugin),
                "items": [],
            }
        g["items"].append(desc)
    result = list(groups.values())
    for g in result:
        g["items"].sort(key=lambda d: (str(d.get("effective_command") or "")).lower())
    result.sort(key=lambda g: g["display"].lower())
    return result


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _perm_label(desc: dict[str, Any]) -> str:
    return PERMISSION_LABELS.get(desc.get("permission"), "所有人")


def _alias_text(desc: dict[str, Any]) -> str:
    """别名展示文本；子命令别名自动带上父级签名（如 /game 卧底）。"""
    parent = (str(desc.get("parent_signature") or "")).strip()
    names = []
    for a in sorted(desc.get("aliases") or []):
        full = f"{parent} {a}".strip()
        names.append("/" + full)
    return "、".join(names)


def _format_line(desc: dict[str, Any]) -> str:
    """渲染单条指令行：/指令 - 描述 [权限/停用] 别名: ..."""
    name = (str(desc.get("effective_command") or "")).strip()
    parts = [f"/{name} 📁" if desc.get("is_group") else f"/{name}"]
    desc_text = _truncate((str(desc.get("description") or "")).strip(), MAX_DESC_CHARS)
    if desc_text:
        parts.append(desc_text)
    marks = []
    if not desc.get("enabled", True):
        marks.append("停用")
    perm = _perm_label(desc)
    if perm != "所有人":
        marks.append(perm)
    if marks:
        parts.append("[" + "/".join(marks) + "]")
    aliases = _alias_text(desc)
    if aliases:
        parts.append("别名: " + aliases)
    return " · ".join(parts)


def format_command_block(desc: dict[str, Any]) -> list[str]:
    """渲染指令块：指令行 + 缩进子命令行。"""
    lines = [_format_line(desc)]
    for sub in desc.get("sub_commands") or []:
        lines.append("  " + _format_line(sub))
    return lines


def build_pages(groups: list[dict[str, Any]], max_chars: int) -> list[str]:
    """按字符预算把分组结果打包为页文本列表（逐行填充，超限自动换页）。"""
    max_chars = max(50, int(max_chars))
    pages: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for g in groups:
        header = f"📁 {g['display']}"
        if g["name"] and g["name"] != g["display"]:
            header += f"（{g['name']}）"
        block = [header]
        for item in g["items"]:
            block.extend(format_command_block(item))
        for line in block:
            if buf and buf_len + len(line) + 1 > max_chars:
                pages.append("\n".join(buf))
                buf = []
                buf_len = 0
            buf.append(line)
            buf_len += len(line) + 1
    if buf:
        pages.append("\n".join(buf))
    return pages


def count_commands(groups: list[dict[str, Any]]) -> int:
    """指令总数（顶层指令 + 子命令）。"""
    total = 0
    for g in groups:
        for item in g["items"]:
            total += 1 + len(item.get("sub_commands") or [])
    return total


@register(PLUGIN_NAME, PLUGIN_AUTHOR, PLUGIN_DESC, PLUGIN_VERSION)
class CommandGuidePlugin(Star):
    """指令大全：查询所有已加载插件的指令、别名、权限与说明"""

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}

    # ========== 配置读取 ==========

    def _page_chars(self) -> int:
        try:
            return max(200, int(self.config.get("page_chars", DEFAULT_PAGE_CHARS)))
        except (TypeError, ValueError):
            return DEFAULT_PAGE_CHARS

    def _cfg_bool(self, key: str, default: bool) -> bool:
        val = self.config.get(key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            s = val.strip().lower()
            if s in ("1", "true", "yes", "on", "是"):
                return True
            if s in ("0", "false", "no", "off", "否", ""):
                return False
            return default
        if isinstance(val, (int, float)):
            return bool(val)
        return default

    def _include_reserved(self) -> bool:
        return self._cfg_bool("include_reserved", True)

    def _show_disabled(self) -> bool:
        return self._cfg_bool("show_disabled", True)

    def _admin_only(self) -> bool:
        return self._cfg_bool("admin_only", False)

    def _admin_umos(self) -> list[str]:
        v = self.config.get("admin_umos", "")
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return list(v or [])

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        """是否管理员会话（admin_umos 白名单）"""
        umos = self._admin_umos()
        return str(event.session) in umos if umos else False

    def _deny(self) -> str:
        umos = self._admin_umos()
        if not umos:
            return (
                "本插件开启了仅管理员可查询（admin_only），但未配置管理员白名单 admin_umos。\n"
                "请在插件配置中填写 admin_umos（如 default:GroupMessage:1234567890）后重启 AstrBot。"
            )
        return "你没有执行此命令的权限（不在 admin_umos 白名单内）"

    @staticmethod
    def _reply(event: AstrMessageEvent, text: str) -> MessageEventResult:
        """构造命令回复结果（MessageEventResult，框架要求）"""
        return event.chain_result([Plain(text)])

    # ========== 数据获取 ==========

    async def _fetch_commands(self) -> list[dict[str, Any]]:
        """获取所有已加载插件的指令描述；核心 API 异常时返回空列表。"""
        try:
            return await list_commands()
        except Exception as e:  # noqa: BLE001
            logger.error(f"【{PLUGIN_NAME}】获取指令列表失败: {e}")
            return []

    # ========== 指令处理 ==========

    @filter.command(_CMD_NAME, priority=200)
    async def show_guide(self, event: AstrMessageEvent) -> MessageEventResult | None:
        """指令大全：/指令 [页码 | 关键字 [页码]]"""
        if self._admin_only() and not self._is_admin(event):
            return self._reply(event, self._deny())

        raw_text = re.sub(r"^[\\/／]+", "", event.message_str.strip())
        rest = raw_text[len(_CMD_NAME):].strip()
        if rest in ("--help", "-h"):
            return self._reply(
                event,
                f"📖 指令大全 v{PLUGIN_VERSION} 用法：\n"
                "- /指令：查看全部已加载插件指令（自动分页）\n"
                "- /指令 <页码>：跳转到指定页码\n"
                "- /指令 <关键词> [页码]：按插件名/指令名/别名/描述检索\n"
                "- /指令 --help：查看本用法提示",
            )
        keyword, page = parse_guide_args(rest)

        raw = await self._fetch_commands()
        if not raw:
            return self._reply(
                event, "📖 未查询到任何已加载的指令（可能插件尚未加载完成，请稍后再试）"
            )

        filtered = filter_descriptors(
            raw,
            keyword=keyword,
            include_reserved=self._include_reserved(),
            show_disabled=self._show_disabled(),
        )
        if not filtered:
            return self._reply(event, f"📖 未找到与「{keyword}」匹配的指令")

        groups = group_by_plugin(filtered)
        pages = build_pages(groups, self._page_chars())
        total_plugins = len(groups)
        total_cmds = count_commands(groups)
        page = min(max(1, page), len(pages))
        text = self._compose(
            pages[page - 1],
            page,
            len(pages),
            total_plugins,
            total_cmds,
            keyword,
        )
        return self._reply(event, text)

    @staticmethod
    def _compose(
        body: str,
        page: int,
        total_pages: int,
        total_plugins: int,
        total_cmds: int,
        keyword: str | None,
    ) -> str:
        """组装页文本：页头 + 统计 + 正文 + 用法提示。"""
        head = "📖 指令大全"
        if keyword:
            head += f"（搜索: {keyword}）"
        head += f" · 第 {page}/{total_pages} 页"
        tips = "输入 /指令 <页码> 翻页 · /指令 <关键词> 搜索"
        return "\n".join(
            [
                head,
                "━━━━━━━━━━━━━━━━",
                body,
                "━━━━━━━━━━━━━━━━",
                f"共 {total_plugins} 个插件 · {total_cmds} 条指令",
                tips,
            ]
        )
