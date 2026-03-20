#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网文项目初始化脚本

目标：
- 生成可运行的项目结构（webnovel-project）
- 创建/更新 .webnovel/state.json（运行时真相）
- 生成基础设定集与大纲模板文件（供 webnovel plan 与 webnovel write 使用）

说明：
- 该脚本是命令 webnovel init 的“唯一允许的文件生成入口”（与命令文档保持一致）。
- 生成的内容以“模板骨架”为主，便于 AI/作者后续补全；但保证所有关键文件存在。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio
from typing import Any, Dict, List
import re

# 安全修复：导入安全工具函数
from security_utils import sanitize_commit_message, atomic_write_json, is_git_available
from project_locator import write_current_project_pointer


# Windows 编码兼容性修复
if sys.platform == "win32":
    enable_windows_utf8_stdio()


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_text_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    path.write_text(content, encoding="utf-8")


def _split_genre_keys(genre: str) -> list[str]:
    raw = (genre or "").strip()
    if not raw:
        return []
    # 支持复合题材：A+B / A+B / A、B / A与B
    raw = re.sub(r"[＋/、]", "+", raw)
    raw = raw.replace("与", "+")
    parts = [p.strip() for p in raw.split("+") if p.strip()]
    return parts or [raw]


def _normalize_genre_key(key: str) -> str:
    aliases = {
        "修仙/玄幻": "修仙",
        "玄幻修仙": "修仙",
        "玄幻": "修仙",
        "修真": "修仙",
        "都市修真": "都市异能",
        "都市高武": "高武",
        "都市奇闻": "都市脑洞",
        "古言脑洞": "古言",
        "游戏电竞": "电竞",
        "电竞文": "电竞",
        "直播": "直播文",
        "直播带货": "直播文",
        "主播": "直播文",
        "克系": "克苏鲁",
        "克系悬疑": "克苏鲁",
    }
    return aliases.get(key, key)


def _apply_label_replacements(text: str, replacements: Dict[str, str]) -> str:
    if not text or not replacements:
        return text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        for label, value in replacements.items():
            if not value:
                continue
            prefix = f"- {label}："
            if stripped.startswith(prefix):
                leading = line[: len(line) - len(stripped)]
                lines[i] = f"{leading}{prefix}{value}"
    return "\n".join(lines)


def _parse_tier_map(raw: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not raw:
        return result
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key, val = part.split(":", 1)
            result[key.strip()] = val.strip()
    return result


def _render_team_rows(names: List[str], roles: List[str]) -> List[str]:
    rows = []
    for idx, name in enumerate(names):
        role = roles[idx] if idx < len(roles) else ""
        rows.append(f"| {name} | {role or '主线/副线'} | | | |")
    return rows


def _ensure_state_schema(state: Dict[str, Any]) -> Dict[str, Any]:
    """确保 state.json 具备 v5.1 架构所需的字段集合（v5.4 沿用）。

    v5.1 变更:
    - entities_v3 和 alias_index 已迁移到 index.db，不再存储在 state.json
    - structured_relationships 已迁移到 index.db relationships 表
    - state.json 保持精简 (< 5KB)
    """
    state.setdefault("project_info", {})
    state.setdefault("progress", {})
    state.setdefault("protagonist_state", {})
    state.setdefault("relationships", {})  # update_state.py 需要此字段
    state.setdefault("disambiguation_warnings", [])
    state.setdefault("disambiguation_pending", [])
    state.setdefault("world_settings", {"power_system": [], "factions": [], "locations": []})
    state.setdefault("plot_threads", {"active_threads": [], "foreshadowing": []})
    state.setdefault("review_checkpoints", [])
    state.setdefault("chapter_meta", {})
    state.setdefault(
        "strand_tracker",
        {
            "last_quest_chapter": 0,
            "last_fire_chapter": 0,
            "last_constellation_chapter": 0,
            "current_dominant": "quest",
            "chapters_since_switch": 0,
            "history": [],
        },
    )
    # v5.1: entities_v3, alias_index, structured_relationships 已迁移到 index.db
    # 不再在 state.json 中初始化这些字段

    # progress schema evolution
    state["progress"].setdefault("current_chapter", 0)
    state["progress"].setdefault("total_words", 0)
    state["progress"].setdefault("last_updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    state["progress"].setdefault("volumes_completed", [])
    state["progress"].setdefault("current_volume", 1)
    state["progress"].setdefault("volumes_planned", [])

    # protagonist schema evolution
    ps = state["protagonist_state"]
    ps.setdefault("name", "")
    ps.setdefault("power", {"realm": "", "layer": 1, "bottleneck": ""})
    ps.setdefault("location", {"current": "", "last_chapter": 0})
    ps.setdefault("golden_finger", {"name": "", "level": 1, "cooldown": 0, "skills": []})
    ps.setdefault("attributes", {})
    planning = state.setdefault("planning", {})
    planning.setdefault("profile", {})
    planning.setdefault("project_info", {})
    planning.setdefault("readiness", {})
    planning.setdefault("last_blocked", None)
    planning.setdefault("volume_plans", {})

    return state


PLANNING_PROFILE_FIELD_SPECS: List[Dict[str, Any]] = [
    {"name": "story_logline", "label": "故事一句话", "multiline": False, "required": True},
    {"name": "protagonist_name", "label": "主角姓名", "multiline": False, "required": True},
    {"name": "protagonist_identity", "label": "主角身份", "multiline": False, "required": True},
    {"name": "protagonist_initial_state", "label": "主角初始状态", "multiline": True, "required": True},
    {"name": "protagonist_desire", "label": "主角欲望", "multiline": False, "required": True},
    {"name": "protagonist_flaw", "label": "主角缺陷", "multiline": False, "required": True},
    {"name": "core_setting", "label": "核心设定", "multiline": True, "required": True},
    {"name": "ability_cost", "label": "能力代价", "multiline": True, "required": True},
    {"name": "volume_1_title", "label": "第 1 卷标题", "multiline": False, "required": True},
    {"name": "volume_1_conflict", "label": "第 1 卷核心冲突", "multiline": True, "required": True},
    {"name": "volume_1_climax", "label": "第 1 卷高潮", "multiline": True, "required": True},
    {
        "name": "major_characters_text",
        "label": "主要角色",
        "multiline": True,
        "required": True,
        "format_hint": "每行：姓名 | 定位 | 与主角关系 | 卷1作用",
    },
    {
        "name": "factions_text",
        "label": "势力",
        "multiline": True,
        "required": True,
        "format_hint": "每行：势力 | 立场 | 与主角关系",
    },
    {"name": "rules_outline", "label": "规则梗概", "multiline": True, "required": True},
    {
        "name": "foreshadowing_text",
        "label": "伏笔与回收",
        "multiline": True,
        "required": True,
        "format_hint": "每行：伏笔内容 | 埋设章 | 回收章 | 层级",
    },
]

PLANNING_PROFILE_FIELD_MAP = {item["name"]: item for item in PLANNING_PROFILE_FIELD_SPECS}
PLANNING_PROFILE_FILE = ".webnovel/planning-profile.json"
PLANNING_PLACEHOLDER_MARKERS = (
    "（待填写）",
    "(待填写)",
    "待填写",
    "待补充",
    "TODO",
    "TBD",
    "示例",
    "占位",
    "请先",
    "请给",
    "请明确",
    "可在首轮卷规划中确定",
    "立场待定",
)


def get_planning_profile_field_specs() -> List[Dict[str, Any]]:
    return [dict(item) for item in PLANNING_PROFILE_FIELD_SPECS]


def _is_placeholder_text(value: str) -> bool:
    stripped = (value or "").strip()
    if not stripped:
        return True
    return any(marker in stripped for marker in PLANNING_PLACEHOLDER_MARKERS)


def normalize_planning_profile(raw: Dict[str, Any] | None, *, title: str = "", genre: str = "") -> Dict[str, str]:
    source = raw or {}
    profile: Dict[str, str] = {}
    for spec in PLANNING_PROFILE_FIELD_SPECS:
        key = spec["name"]
        profile[key] = str(source.get(key) or "").strip()
    return profile


def planning_profile_path(project_root: Path) -> Path:
    return project_root / PLANNING_PROFILE_FILE


def load_planning_profile(project_root: Path, *, title: str = "", genre: str = "") -> Dict[str, str]:
    path = planning_profile_path(project_root)
    if not path.is_file():
        return normalize_planning_profile({}, title=title, genre=genre)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return normalize_planning_profile(raw, title=title, genre=genre)


def save_planning_profile(project_root: Path, profile: Dict[str, Any] | None, *, title: str = "", genre: str = "") -> Dict[str, str]:
    normalized = normalize_planning_profile(profile, title=title, genre=genre)
    path = planning_profile_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, normalized, use_lock=False, backup=False)
    return normalized


def _contains_keyword(text: str, keywords: List[str]) -> bool:
    haystack = (text or "").strip().lower()
    return any(keyword.lower() in haystack for keyword in keywords if keyword)


def build_initial_planning_profile(
    *,
    title: str,
    genre: str,
    protagonist_name: str = "",
    golden_finger_name: str = "",
    core_selling_points: str = "",
    protagonist_desire: str = "",
    protagonist_flaw: str = "",
    protagonist_archetype: str = "",
    protagonist_structure: str = "",
    factions: str = "",
    power_system_type: str = "",
    gf_irreversible_cost: str = "",
) -> Dict[str, str]:
    safe_title = title.strip() or "当前项目"
    safe_genre = genre.strip() or "长篇网文"
    title_and_genre = f"{safe_title} {safe_genre}"
    is_rewind_story = _contains_keyword(title_and_genre, ["回档", "回溯", "回环", "rewind", "loop"])
    is_urban_story = _contains_keyword(title_and_genre, ["都市", "urban", "city", "异能", "supernatural", "悬疑"])
    is_cultivation_story = _contains_keyword(title_and_genre, ["修仙", "修真", "玄幻", "cultivation", "xianxia"])
    default_name = protagonist_name.strip()
    if not default_name:
        if is_rewind_story:
            default_name = "沈砚"
        elif is_cultivation_story:
            default_name = "陆玄"
        elif is_urban_story:
            default_name = "林夜"
        else:
            default_name = "林砚"

    if is_rewind_story:
        default_identity = "雨夜城里值夜班的民间档案修复员"
        default_initial_state = "他刚被卷入一次只能由自己察觉的异常事件，手里没有稳定资源，还要先保住工作与落脚点。"
        default_desire = "先用回档能力保命并锁定第一条可验证线索，再查清异常为什么盯上自己。"
        default_flaw = "习惯独自扛事，越到高压时越不愿把真相告诉他人，导致判断容易失真。"
        default_core_setting = f"《{safe_title}》的核心设定是主角能在高压时刻短暂回档同一事件窗口，但每次回档都会损伤近期记忆，并让异常势力更快锁定他。"
        default_ability_cost = "回档可以换一次重新行动的机会，但会永久失去部分近期记忆、扰乱时间感，并抬高下一次异常反噬强度。"
        default_conflict = "第一卷里，主角必须在记忆代价越来越重之前，查清回档能力与城市异常的来源，同时躲开追索这份能力的制度性力量。"
        default_climax = "卷末，主角用一次高代价回档换到关键证据和立足筹码，却也因此正式暴露在更大的异常网络面前。"
        default_characters = "\n".join(
            [
                f"{default_name} | 主视角角色 | 自身 | 用回档能力换生机并进入主线",
                "顾迟 | 现实侧同伴 | 互相试探 | 提供落地行动支点与风险提醒",
                "调查局巡查官 | 制度性压力 | 潜在敌友 | 代表官方规则与追索",
            ]
        )
        default_factions = "\n".join(
            [
                "异常调查局 | 官方监管 | 既可能保护主角，也可能先行控制主角",
                "雨夜城灰市情报网 | 地下势力 | 提供线索与交易，同时放大代价",
            ]
        )
        default_rules = "\n".join(
            [
                "异常只会在高压节点或极端情绪场景中显形，普通人通常看不见全貌。",
                "主角每次回档只能重来同一事件窗口，且无法跳过已经支付的记忆代价。",
                "一旦异常被制度力量确认，主角必须在隐匿、合作与利用之间做出选择。",
            ]
        )
        default_foreshadowing = "\n".join(
            [
                "第一次异常预警的来源 | 1 | 5 | A",
                "回档代价为何只落在主角身上 | 1 | 12 | A",
            ]
        )
    elif is_cultivation_story:
        default_identity = "边缘宗门里天赋普通却不甘沉底的外门弟子"
        default_initial_state = "他身处资源分配极不公平的修炼环境，稍有失手就会失去继续修行的资格。"
        default_desire = "先抢到第一份能改变命运的修炼资源，再查清宗门与外界真正的力量格局。"
        default_flaw = "过于执拗，不愿在看不顺眼的规则前低头，容易把局势推到必须硬扛的地步。"
        default_core_setting = f"《{safe_title}》围绕一套层级清晰却暗藏代价的修炼体系展开，主角每次突破都必须拿真实代价交换更高层级的机会。"
        default_ability_cost = "每次越级获益都会透支身体、信誉或人情债，主角不能无限制白拿成长。"
        default_conflict = "第一卷聚焦主角如何在宗门压制、资源争夺和外部威胁夹击下，抢到第一块真正属于自己的立足之地。"
        default_climax = "卷末，主角以险胜换来晋升资格，却因此被更高层的势力正式盯上。"
        default_characters = "\n".join(
            [
                f"{default_name} | 主视角角色 | 自身 | 在第一卷完成立足与破局",
                "执事长老 | 宗门管理者 | 压制主角 | 代表旧秩序压力",
                "同门盟友 | 可争取伙伴 | 竞争与合作并存 | 帮主角撬开资源入口",
            ]
        )
        default_factions = "\n".join(
            [
                "所属宗门 | 资源垄断方 | 给予修炼机会也设置层层门槛",
                "外部敌对势力 | 竞争者 | 在卷一推动第一次生死压力",
            ]
        )
        default_rules = "\n".join(
            [
                "境界提升需要资源、功法与实战验证三者同时成立。",
                "越级胜利必须付出可持续追踪的代价，不能无限透支。",
                "宗门层级、资源配额和身份规则会持续影响主角选择。",
            ]
        )
        default_foreshadowing = "\n".join(
            [
                "主角体质或机缘的真正来源 | 1 | 10 | A",
                "宗门内部更大的权力裂缝 | 2 | 15 | B",
            ]
        )
    else:
        default_identity = "被卷入核心事件的普通人，拥有最接近主线真相的切入口"
        default_initial_state = "开篇时资源有限、信息残缺，只能一边保全自己一边追查异常源头。"
        default_desire = "先解决眼前危机并保住立足点，再把零散线索串成能够推动主线的突破口。"
        default_flaw = "习惯先自己消化风险，不到极限不会求助，导致合作效率偏低。"
        default_core_setting = f"《{safe_title}》围绕一个会持续放大冲突的核心异常规则展开，主角既是受益者也是首批付代价的人。"
        default_ability_cost = "主角每次获得额外能力、信息或资源，都必须同步承担不可忽视的副作用或现实后果。"
        default_conflict = "第一卷需要让主角在个人生存、真相追查和外部压力三条线之间被迫同时行动。"
        default_climax = "卷末，主角第一次用真实代价换到关键收益，并据此确认更大主线已经展开。"
        default_characters = "\n".join(
            [
                f"{default_name} | 主视角角色 | 自身 | 在第一卷完成开局立柱与冲突进入",
                "现实侧同伴 | 支点角色 | 逐步建立信任 | 提供行动协助",
                "阶段敌手 | 第一卷阻力 | 对抗与逼迫并存 | 把主角推向主线",
            ]
        )
        default_factions = "\n".join(
            [
                "核心势力 | 与主线直接相关 | 会在第一卷建立与主角的利益关系",
                "外围势力 | 现实层阻力 | 放大主角在信息与资源上的短板",
            ]
        )
        default_rules = "\n".join(
            [
                "世界规则必须可验证，不能只在需要时临时出现。",
                "主角获得收益时必须同步承受代价或留下后患。",
                "制度、资源和信息差会持续决定角色站位与风险等级。",
            ]
        )
        default_foreshadowing = "\n".join(
            [
                "主线核心异常的第一次显形 | 1 | 8 | A",
                "阶段敌手背后的真实诉求 | 2 | 10 | B",
            ]
        )
    initial = {
        "story_logline": core_selling_points.strip() or f"《{safe_title}》讲述{default_name}在{safe_genre}主线里，为了{default_desire}而被迫卷入更大异常与对抗的故事。",
        "protagonist_name": default_name,
        "protagonist_identity": protagonist_archetype.strip() or default_identity,
        "protagonist_initial_state": protagonist_structure.strip() or default_initial_state,
        "protagonist_desire": protagonist_desire.strip() or default_desire,
        "protagonist_flaw": protagonist_flaw.strip() or default_flaw,
        "core_setting": golden_finger_name.strip() or default_core_setting,
        "ability_cost": gf_irreversible_cost.strip() or default_ability_cost,
        "volume_1_title": f"{safe_title}·卷一：立足与破局",
        "volume_1_conflict": default_conflict,
        "volume_1_climax": default_climax,
        "major_characters_text": default_characters,
        "factions_text": factions.strip() or default_factions,
        "rules_outline": power_system_type.strip() or default_rules,
        "foreshadowing_text": default_foreshadowing,
    }
    return normalize_planning_profile(initial, title=title, genre=genre)


def build_planning_fill_template() -> Dict[str, Any]:
    template = {spec["name"]: "" for spec in PLANNING_PROFILE_FIELD_SPECS}
    template["major_characters_text"] = "姓名 | 定位 | 与主角关系 | 卷1作用"
    template["factions_text"] = "势力 | 立场 | 与主角关系"
    template["foreshadowing_text"] = "伏笔内容 | 埋设章 | 回收章 | 层级"
    return {
        "profile": template,
        "required_fields": [spec["name"] for spec in PLANNING_PROFILE_FIELD_SPECS if spec.get("required")],
        "field_specs": get_planning_profile_field_specs(),
    }


def evaluate_planning_readiness(profile: Dict[str, Any] | None, *, outline_text: str = "") -> Dict[str, Any]:
    normalized = normalize_planning_profile(profile)
    missing_items: List[Dict[str, Any]] = []
    for spec in PLANNING_PROFILE_FIELD_SPECS:
        if not spec.get("required"):
            continue
        value = normalized.get(spec["name"], "")
        if _is_placeholder_text(value):
            missing_items.append(
                {
                    "field": spec["name"],
                    "label": spec["label"],
                    "format_hint": spec.get("format_hint", ""),
                }
            )

    outline_sections = [
        "## 故事前提",
        "## 主线推进",
        "## 主要角色",
        "## 势力",
        "## 规则梗概",
        "## 伏笔与回收",
        "## 卷结构",
    ]
    outline_present = [section for section in outline_sections if section in (outline_text or "")]
    outline_missing = [section for section in outline_sections if section not in outline_present]
    outline_missing_items = [
        {
            "field": f"outline_section::{section}",
            "label": section.replace("## ", "").strip(),
            "format_hint": "请确认总纲骨架中存在该章节。",
        }
        for section in outline_missing
    ]
    blocking_items = [*missing_items, *outline_missing_items]
    ok = not blocking_items
    return {
        "ok": ok,
        "status": "ready" if ok else "needs_info",
        "message": "planning profile ready" if ok else "planning input is missing required information",
        "missing_items": missing_items,
        "blocking_items": blocking_items,
        "missing_fields": [item["field"] for item in missing_items],
        "missing_count": len(blocking_items),
        "completed_fields": len(PLANNING_PROFILE_FIELD_SPECS) - len(missing_items),
        "total_required_fields": len(PLANNING_PROFILE_FIELD_SPECS),
        "outline_sections_present": outline_present,
        "outline_sections_missing": outline_missing,
    }


def _render_profile_block(title: str, lines: List[str]) -> List[str]:
    return [title, *lines, ""]


def _render_multiline_rows(value: str, fallback: str) -> List[str]:
    rows = [line.strip() for line in (value or "").splitlines() if line.strip()]
    if rows:
        return [f"- {row}" for row in rows]
    return [f"- {fallback}"]


def _replace_markdown_section(text: str, heading: str, lines: List[str]) -> str:
    normalized_lines = [heading, *lines]
    block = "\n".join(normalized_lines).strip() + "\n"
    if not text.strip():
        return "# 总纲\n\n" + block

    pattern = re.compile(rf"(?ms)^({re.escape(heading)}\n)(.*?)(?=^## |\Z)")
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    base = text.rstrip()
    if not base.endswith("\n"):
        base += "\n"
    return f"{base}\n{block}"


def _replace_volume_block(text: str, heading: str, lines: List[str]) -> str:
    block = "\n".join([heading, *lines]).strip() + "\n"
    pattern = re.compile(rf"(?ms)^({re.escape(heading)}\n)(.*?)(?=^### |\Z)")
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    base = text.rstrip()
    if not base.endswith("\n"):
        base += "\n"
    return f"{base}\n{block}"


def sync_master_outline_with_profile(
    outline_text: str,
    *,
    title: str,
    genre: str,
    target_chapters: int,
    profile: Dict[str, Any] | None,
) -> str:
    normalized = normalize_planning_profile(profile, title=title, genre=genre)
    base_text = (outline_text or "").strip()
    if not base_text:
        base_text = _build_master_outline(target_chapters, title=title, genre=genre)
    if "# 总纲" not in base_text:
        base_text = "# 总纲\n\n" + base_text
    if "## 卷结构" not in base_text:
        base_text = _build_master_outline(target_chapters, title=title, genre=genre).strip()

    story_premise = [
        f"- 书名：{title or '（待填写）'}",
        f"- 题材：{genre or '（待填写）'}",
        f"- 一句话梗概：{normalized['story_logline'] or '（待填写）'}",
        f"- 主角：{normalized['protagonist_name'] or '（待填写）'}",
        f"- 主角身份：{normalized['protagonist_identity'] or '（待填写）'}",
        f"- 主角初始状态：{normalized['protagonist_initial_state'] or '（待填写）'}",
        f"- 核心设定：{normalized['core_setting'] or '（待填写）'}",
        f"- 能力代价：{normalized['ability_cost'] or '（待填写）'}",
    ]
    mainline = [
        f"- 主角当前欲望：{normalized['protagonist_desire'] or '（待填写）'}",
        f"- 主角核心缺陷：{normalized['protagonist_flaw'] or '（待填写）'}",
        f"- 第1卷标题：{normalized['volume_1_title'] or '（待填写）'}",
        f"- 第1卷核心冲突：{normalized['volume_1_conflict'] or '（待填写）'}",
        f"- 第1卷高潮：{normalized['volume_1_climax'] or '（待填写）'}",
    ]
    major_characters = _render_multiline_rows(normalized["major_characters_text"], "姓名 | 定位 | 与主角关系 | 卷1作用")
    factions = _render_multiline_rows(normalized["factions_text"], "势力 | 立场 | 与主角关系")
    rules = _render_multiline_rows(normalized["rules_outline"], "请补充世界规则、能力限制与制度约束")
    foreshadowing = _render_multiline_rows(normalized["foreshadowing_text"], "伏笔内容 | 埋设章 | 回收章 | 层级")

    updated = base_text
    updated = _replace_markdown_section(updated, "## 故事前提", story_premise)
    updated = _replace_markdown_section(updated, "## 主线推进", mainline)
    updated = _replace_markdown_section(updated, "## 主要角色", major_characters)
    updated = _replace_markdown_section(updated, "## 势力", factions)
    updated = _replace_markdown_section(updated, "## 规则梗概", rules)
    updated = _replace_markdown_section(updated, "## 伏笔与回收", foreshadowing)
    if "## 卷结构" not in updated:
        volume_block = _build_master_outline(target_chapters, title=title, genre=genre)
        volume_part = volume_block.split("## 卷结构", 1)[1]
        updated = updated.rstrip() + "\n\n## 卷结构" + volume_part
    first_volume_heading = next((line.strip() for line in updated.splitlines() if line.startswith("### 第1卷（")), "")
    if first_volume_heading:
        key_character = next((line.strip() for line in normalized["major_characters_text"].splitlines() if line.strip()), "")
        key_faction = next((line.strip() for line in normalized["factions_text"].splitlines() if line.strip()), "")
        key_foreshadow = next((line.strip() for line in normalized["foreshadowing_text"].splitlines() if line.strip()), "")
        first_volume_lines = [
            f"- 卷目标：{normalized['protagonist_desire'] or '在第一卷建立立足点并拿到第一条关键线索'}",
            f"- 核心冲突：{normalized['volume_1_conflict'] or '主角必须在压力中主动进入主线冲突'}",
            f"- 升级与代价：{normalized['ability_cost'] or '每次获益都伴随明确代价与后果'}",
            f"- 关键爽点：{normalized['story_logline'] or '主角在高压环境中第一次完成有效破局'}",
            f"- 阶段敌手/阻力：{key_faction or '第一卷的制度压力、资源短缺与阶段敌手同步施压'}",
            f"- 卷末高潮：{normalized['volume_1_climax'] or '卷末用真实代价换到关键收益'}",
            f"- 主要登场角色：{key_character or '主角与第一批关键角色进入棋局'}",
            f"- 关键伏笔（埋/收）：{key_foreshadow or '第1章埋主线伏笔，第10章附近开始第一次回收'}",
            "- 前5章拆解：1-2章建立危机与规则；第3章给首次收益；第4章显影代价；第5章把主角正式推进卷级对抗。",
        ]
        updated = _replace_volume_block(updated, first_volume_heading, first_volume_lines)
    return updated.rstrip() + "\n"


def _build_master_outline(
    target_chapters: int,
    *,
    chapters_per_volume: int = 50,
    title: str = "",
    genre: str = "",
    protagonist_name: str = "",
    golden_finger_name: str = "",
    core_selling_points: str = "",
    protagonist_desire: str = "",
    protagonist_flaw: str = "",
    factions: str = "",
    power_system_type: str = "",
    gf_irreversible_cost: str = "",
) -> str:
    volumes = (target_chapters - 1) // chapters_per_volume + 1 if target_chapters > 0 else 1
    lines: list[str] = [
        "# 总纲",
        "",
        "> 本文件为“总纲骨架”，用于 webnovel plan 细化为卷大纲与章纲。",
        "",
        "## 故事前提",
        f"- 书名：{title or '（待填写）'}",
        f"- 题材：{genre or '（待填写）'}",
        f"- 主角：{protagonist_name or '（待填写）'}",
        f"- 核心设定：{golden_finger_name or '（待填写）'}",
        f"- 能力代价：{gf_irreversible_cost or '（待填写，明确能力收益与不可逆代价）'}",
        "",
        "## 主线推进",
        f"- 主角当前欲望：{protagonist_desire or '（待填写）'}",
        f"- 主角核心缺陷：{protagonist_flaw or '（待填写）'}",
        f"- 核心冲突：{core_selling_points or '（待填写，至少写出主打矛盾与爽点来源）'}",
        f"- 势力格局：{factions or '（待填写）'}",
        f"- 规则/体系：{power_system_type or '（待填写）'}",
        "- 关键伏笔：至少填写 2 条，注明埋点与预期回收位置。",
        "- 节奏要求：前 3 章给出钩子、首次收益、代价显影；前 10 章形成阶段对抗。",
        "",
        "## 卷结构",
        "",
    ]

    for v in range(1, volumes + 1):
        start = (v - 1) * chapters_per_volume + 1
        end = min(v * chapters_per_volume, target_chapters)
        lines.extend(
            [
                f"### 第{v}卷（第{start}-{end}章）",
                "- 卷目标：",
                "- 核心冲突：",
                "- 升级与代价：",
                "- 关键爽点：",
                "- 阶段敌手/阻力：",
                "- 卷末高潮：",
                "- 主要登场角色：",
                "- 关键伏笔（埋/收）：",
                "- 前5章拆解：",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _ensure_plan_ready_outline(
    outline_text: str,
    *,
    title: str,
    genre: str,
    protagonist_name: str,
    golden_finger_name: str,
    core_selling_points: str,
    protagonist_desire: str,
    protagonist_flaw: str,
    factions: str,
    power_system_type: str,
    gf_irreversible_cost: str,
) -> str:
    text = (outline_text or "").rstrip()
    required_sections = {
        "## 故事前提": [
            f"- 书名：{title or '（待填写）'}",
            f"- 题材：{genre or '（待填写）'}",
            f"- 主角：{protagonist_name or '（待填写）'}",
            f"- 核心设定：{golden_finger_name or '（待填写）'}",
            f"- 能力代价：{gf_irreversible_cost or '（待填写，明确能力收益与不可逆代价）'}",
        ],
        "## 主线推进": [
            f"- 主角当前欲望：{protagonist_desire or '（待填写）'}",
            f"- 主角核心缺陷：{protagonist_flaw or '（待填写）'}",
            f"- 核心冲突：{core_selling_points or '（待填写，至少写出主打矛盾与爽点来源）'}",
            f"- 势力格局：{factions or '（待填写）'}",
            f"- 规则/体系：{power_system_type or '（待填写）'}",
            "- 关键伏笔：至少填写 2 条，注明埋点与预期回收位置。",
            "- 节奏要求：前 3 章给出钩子、首次收益、代价显影；前 10 章形成阶段对抗。",
        ],
    }
    append_blocks: list[str] = []
    for heading, lines in required_sections.items():
        if heading in text:
            continue
        append_blocks.extend(["", heading, *lines])
    if not append_blocks:
        return text.rstrip() + "\n"
    return (text + "\n" + "\n".join(append_blocks).strip() + "\n").replace("\n\n\n", "\n\n")


def _inject_volume_rows(template_text: str, target_chapters: int, *, chapters_per_volume: int = 50) -> str:
    """在总纲模板的卷表中注入卷行（若存在表头）。"""
    lines = template_text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("| 卷号"):
            header_idx = i
            break
    if header_idx is None:
        return template_text

    insert_idx = header_idx + 2 if header_idx + 1 < len(lines) else len(lines)
    volumes = (target_chapters - 1) // chapters_per_volume + 1 if target_chapters > 0 else 1
    rows = []
    for v in range(1, volumes + 1):
        start = (v - 1) * chapters_per_volume + 1
        end = min(v * chapters_per_volume, target_chapters)
        rows.append(f"| {v} | | 第{start}-{end}章 | | |")

    # 避免重复插入（若模板已有数据行）
    existing = {line.strip() for line in lines}
    rows = [r for r in rows if r.strip() not in existing]
    return "\n".join(lines[:insert_idx] + rows + lines[insert_idx:])


def init_project(
    project_dir: str,
    title: str,
    genre: str,
    *,
    protagonist_name: str = "",
    target_words: int = 2_000_000,
    target_chapters: int = 600,
    golden_finger_name: str = "",
    golden_finger_type: str = "",
    golden_finger_style: str = "",
    core_selling_points: str = "",
    protagonist_structure: str = "",
    heroine_config: str = "",
    heroine_names: str = "",
    heroine_role: str = "",
    co_protagonists: str = "",
    co_protagonist_roles: str = "",
    antagonist_tiers: str = "",
    world_scale: str = "",
    factions: str = "",
    power_system_type: str = "",
    social_class: str = "",
    resource_distribution: str = "",
    gf_visibility: str = "",
    gf_irreversible_cost: str = "",
    protagonist_desire: str = "",
    protagonist_flaw: str = "",
    protagonist_archetype: str = "",
    antagonist_level: str = "",
    target_reader: str = "",
    platform: str = "",
    currency_system: str = "",
    currency_exchange: str = "",
    sect_hierarchy: str = "",
    cultivation_chain: str = "",
    cultivation_subtiers: str = "",
) -> None:
    project_path = Path(project_dir).expanduser().resolve()
    if ".claude" in project_path.parts:
        raise SystemExit("Refusing to initialize a project inside .claude. Choose a different directory.")
    project_path.mkdir(parents=True, exist_ok=True)

    # 目录结构（同时兼容“卷目录”与后续扩展）
    directories = [
        ".webnovel/backups",
        ".webnovel/archive",
        ".webnovel/summaries",
        "设定集/角色库/主要角色",
        "设定集/角色库/次要角色",
        "设定集/角色库/反派角色",
        "设定集/物品库",
        "设定集/其他设定",
        "大纲",
        "正文/第1卷",
        "审查报告",
    ]
    for dir_path in directories:
        (project_path / dir_path).mkdir(parents=True, exist_ok=True)

    # state.json（创建或增量补齐）
    state_path = project_path / ".webnovel" / "state.json"
    if state_path.exists():
        try:
            state: Dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    else:
        state = {}

    state = _ensure_state_schema(state)
    created_at = state.get("project_info", {}).get("created_at") or datetime.now().strftime("%Y-%m-%d")

    state["project_info"].update(
        {
            "title": title,
            "genre": genre,
            "created_at": created_at,
            "target_words": int(target_words),
            "target_chapters": int(target_chapters),
            # 下面字段属于“初始化元信息”，不影响运行时脚本
            "golden_finger_name": golden_finger_name,
            "golden_finger_type": golden_finger_type,
            "golden_finger_style": golden_finger_style,
            "core_selling_points": core_selling_points,
            "protagonist_structure": protagonist_structure,
            "heroine_config": heroine_config,
            "heroine_names": heroine_names,
            "heroine_role": heroine_role,
            "co_protagonists": co_protagonists,
            "co_protagonist_roles": co_protagonist_roles,
            "antagonist_tiers": antagonist_tiers,
            "world_scale": world_scale,
            "factions": factions,
            "power_system_type": power_system_type,
            "social_class": social_class,
            "resource_distribution": resource_distribution,
            "gf_visibility": gf_visibility,
            "gf_irreversible_cost": gf_irreversible_cost,
            "target_reader": target_reader,
            "platform": platform,
            "currency_system": currency_system,
            "currency_exchange": currency_exchange,
            "sect_hierarchy": sect_hierarchy,
            "cultivation_chain": cultivation_chain,
            "cultivation_subtiers": cultivation_subtiers,
        }
    )

    if protagonist_name:
        state["protagonist_state"]["name"] = protagonist_name

    gf_type_norm = (golden_finger_type or "").strip()
    if gf_type_norm in {"无", "无金手指", "none"}:
        state["protagonist_state"]["golden_finger"]["name"] = "无金手指"
        state["protagonist_state"]["golden_finger"]["level"] = 0
        state["protagonist_state"]["golden_finger"]["cooldown"] = 0
    elif golden_finger_name:
        state["protagonist_state"]["golden_finger"]["name"] = golden_finger_name

    # 确保 golden_finger 字段存在且可编辑
    if not state["protagonist_state"]["golden_finger"].get("name"):
        state["protagonist_state"]["golden_finger"]["name"] = "未命名金手指"

    planning_profile = build_initial_planning_profile(
        title=title,
        genre=genre,
        protagonist_name=protagonist_name,
        golden_finger_name=golden_finger_name,
        core_selling_points=core_selling_points,
        protagonist_desire=protagonist_desire,
        protagonist_flaw=protagonist_flaw,
        protagonist_archetype=protagonist_archetype,
        protagonist_structure=protagonist_structure,
        factions=factions,
        power_system_type=power_system_type,
        gf_irreversible_cost=gf_irreversible_cost,
    )
    state["planning"]["profile"] = planning_profile
    state["planning"]["project_info"] = {
        "title": title,
        "genre": genre,
        "target_chapters": int(target_chapters),
        "outline_file": "大纲/总纲.md",
        "source": "bootstrap",
    }

    state["progress"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    # 使用原子化写入（初始化不需要备份旧文件）
    atomic_write_json(state_path, state, use_lock=True, backup=False)

    # 读取内置模板（可选）
    script_dir = Path(__file__).resolve().parent
    templates_dir = script_dir.parent / "templates"
    output_templates_dir = templates_dir / "output"
    genre_key = (genre or "").strip()
    genre_keys = [_normalize_genre_key(k) for k in _split_genre_keys(genre_key)]
    genre_templates = []
    seen = set()
    for key in genre_keys:
        if not key or key in seen:
            continue
        seen.add(key)
        template_text = _read_text_if_exists(templates_dir / "genres" / f"{key}.md")
        if template_text:
            genre_templates.append(template_text.strip())
    genre_template = "\n\n---\n\n".join(genre_templates)
    golden_finger_templates = _read_text_if_exists(templates_dir / "golden-finger-templates.md")
    output_worldview = _read_text_if_exists(output_templates_dir / "设定集-世界观.md")
    output_power = _read_text_if_exists(output_templates_dir / "设定集-力量体系.md")
    output_protagonist = _read_text_if_exists(output_templates_dir / "设定集-主角卡.md")
    output_heroine = _read_text_if_exists(output_templates_dir / "设定集-女主卡.md")
    output_team = _read_text_if_exists(output_templates_dir / "设定集-主角组.md")
    output_golden_finger = _read_text_if_exists(output_templates_dir / "设定集-金手指.md")
    output_outline = _read_text_if_exists(output_templates_dir / "大纲-总纲.md")
    output_fusion = _read_text_if_exists(output_templates_dir / "复合题材-融合逻辑.md")
    output_antagonist = _read_text_if_exists(output_templates_dir / "设定集-反派设计.md")

    # 基础文件（只在缺失时生成，避免覆盖已有内容）
    now = datetime.now().strftime("%Y-%m-%d")

    worldview_content = output_worldview.strip() if output_worldview else ""
    if not worldview_content:
        worldview_content = "\n".join(
            [
                "# 世界观",
                "",
                f"> 项目：{title}｜题材：{genre}｜创建：{now}",
                "",
                "## 一句话世界观",
                "- （用一句话说明世界的核心规则与卖点）",
                "",
                "## 核心规则（设定即物理）",
                "- 规则1：",
                "- 规则2：",
                "- 规则3：",
                "",
                "## 势力与地理（简版）",
                "- 主要势力：",
                "- 关键地点：",
                "",
                "## 参考题材模板（可删/可改）",
                "",
                (genre_template.strip() + "\n") if genre_template else "（未找到对应题材模板，可自行补充）\n",
            ]
        ).rstrip() + "\n"
    else:
        worldview_content = _apply_label_replacements(
            worldview_content,
            {
                "大陆/位面数量": world_scale,
                "核心势力": factions,
                "社会阶层": social_class,
                "资源分配规则": resource_distribution,
                "宗门/组织层级": sect_hierarchy,
                "货币体系": currency_system,
                "兑换规则": currency_exchange,
            },
        )
    _write_text_if_missing(
        project_path / "设定集" / "世界观.md",
        worldview_content,
    )

    power_content = output_power.strip() if output_power else ""
    if not power_content:
        power_content = "\n".join(
            [
                "# 力量体系",
                "",
                f"> 项目：{title}｜题材：{genre}｜创建：{now}",
                "",
                "## 等级/境界划分",
                "- （列出从弱到强的等级，含突破条件与代价）",
                "",
                "## 技能/招式规则",
                "- 获得方式：",
                "- 成本与副作用：",
                "- 进阶与组合：",
                "",
                "## 禁止事项（防崩坏）",
                "- 未达等级不得使用高阶能力（设定即物理）",
                "- 新增能力必须申报并入库（发明需申报）",
                "",
            ]
        ).rstrip() + "\n"
    else:
        power_content = _apply_label_replacements(
            power_content,
            {
                "体系类型": power_system_type,
                "典型境界链（可选）": cultivation_chain,
                "小境界划分": cultivation_subtiers,
            },
        )
    _write_text_if_missing(
        project_path / "设定集" / "力量体系.md",
        power_content,
    )

    protagonist_content = output_protagonist.strip() if output_protagonist else ""
    if not protagonist_content:
        protagonist_content = "\n".join(
            [
                "# 主角卡",
                "",
                f"> 主角：{protagonist_name or '（待填写）'}｜项目：{title}｜创建：{now}",
                "",
                "## 三要素",
                f"- 欲望：{protagonist_desire or '（待填写）'}",
                f"- 弱点：{protagonist_flaw or '（待填写）'}",
                f"- 人设类型：{protagonist_archetype or '（待填写）'}",
                "",
                "## 初始状态（开局）",
                "- 身份：",
                "- 资源：",
                "- 约束：",
                "",
                "## 金手指概览",
                f"- 称呼：{golden_finger_name or '（待填写）'}",
                f"- 类型：{golden_finger_type or '（待填写）'}",
                f"- 风格：{golden_finger_style or '（待填写）'}",
                "- 成长曲线：",
                "",
            ]
        ).rstrip() + "\n"
    else:
        protagonist_content = _apply_label_replacements(
            protagonist_content,
            {
                "姓名": protagonist_name,
                "真正渴望（可能不自知）": protagonist_desire,
                "性格缺陷": protagonist_flaw,
            },
        )
    _write_text_if_missing(
        project_path / "设定集" / "主角卡.md",
        protagonist_content,
    )

    heroine_content = output_heroine.strip() if output_heroine else ""
    if heroine_content:
        heroine_content = _apply_label_replacements(
            heroine_content,
            {
                "姓名": heroine_names,
                "与主角关系定位（对手/盟友/共谋/牵制）": heroine_role,
            },
        )
        _write_text_if_missing(project_path / "设定集" / "女主卡.md", heroine_content)

    team_content = output_team.strip() if output_team else ""
    if team_content:
        names = [n.strip() for n in co_protagonists.split(",") if n.strip()] if co_protagonists else []
        roles = [r.strip() for r in co_protagonist_roles.split(",") if r.strip()] if co_protagonist_roles else []
        if names:
            lines = team_content.splitlines()
            new_rows = _render_team_rows(names, roles)
            replaced = False
            out_lines: List[str] = []
            for line in lines:
                if line.strip().startswith("| 主角A"):
                    out_lines.extend(new_rows)
                    replaced = True
                    continue
                if replaced and line.strip().startswith("| 主角"):
                    continue
                out_lines.append(line)
            team_content = "\n".join(out_lines)
        _write_text_if_missing(
            project_path / "设定集" / "主角组.md",
            team_content,
        )

    golden_finger_content = output_golden_finger.strip() if output_golden_finger else ""
    if not golden_finger_content:
        golden_finger_content = "\n".join(
            [
                "# 金手指设计",
                "",
                f"> 项目：{title}｜题材：{genre}｜创建：{now}",
                "",
                "## 选型",
                f"- 称呼：{golden_finger_name or '（待填写）'}",
                f"- 类型：{golden_finger_type or '（待填写）'}",
                f"- 风格：{golden_finger_style or '（待填写）'}",
                "",
                "## 规则（必须写清）",
                "- 触发条件：",
                "- 冷却/代价：",
                "- 上限：",
                "- 反噬/风险：",
                "",
                "## 成长曲线（章节规划）",
                "- Lv1：",
                "- Lv2：",
                "- Lv3：",
                "",
                "## 模板参考（可删/可改）",
                "",
                (golden_finger_templates.strip() + "\n") if golden_finger_templates else "（未找到金手指模板库）\n",
            ]
        ).rstrip() + "\n"
    else:
        golden_finger_content = _apply_label_replacements(
            golden_finger_content,
            {
                "类型": golden_finger_type,
                "读者可见度": gf_visibility,
                "不可逆代价": gf_irreversible_cost,
            },
        )
    _write_text_if_missing(
        project_path / "设定集" / "金手指设计.md",
        golden_finger_content,
    )

    fusion_content = output_fusion.strip() if output_fusion else ""
    if fusion_content:
        _write_text_if_missing(
            project_path / "设定集" / "复合题材-融合逻辑.md",
            fusion_content,
        )

    antagonist_content = output_antagonist.strip() if output_antagonist else ""
    if not antagonist_content:
        antagonist_content = "\n".join(
            [
                "# 反派设计",
                "",
                f"> 项目：{title}｜创建：{now}",
                "",
                f"- 反派等级：{antagonist_level or '（待填写）'}",
                "- 动机：",
                "- 资源/势力：",
                "- 与主角的镜像关系：",
                "- 终局：",
                "",
            ]
        ).rstrip() + "\n"
    else:
        tier_map = _parse_tier_map(antagonist_tiers)
        if tier_map:
            lines = antagonist_content.splitlines()
            out_lines = []
            for line in lines:
                if line.strip().startswith("| 小反派"):
                    name = tier_map.get("小反派", "")
                    out_lines.append(f"| 小反派 | {name} | 前期 | | |")
                    continue
                if line.strip().startswith("| 中反派"):
                    name = tier_map.get("中反派", "")
                    out_lines.append(f"| 中反派 | {name} | 中期 | | |")
                    continue
                if line.strip().startswith("| 大反派"):
                    name = tier_map.get("大反派", "")
                    out_lines.append(f"| 大反派 | {name} | 后期 | | |")
                    continue
                out_lines.append(line)
            antagonist_content = "\n".join(out_lines)
    _write_text_if_missing(project_path / "设定集" / "反派设计.md", antagonist_content)

    outline_content = output_outline.strip() if output_outline else ""
    if outline_content:
        outline_content = _inject_volume_rows(outline_content, int(target_chapters)).rstrip() + "\n"
    else:
        outline_content = _build_master_outline(
            int(target_chapters),
            title=title,
            genre=genre,
            protagonist_name=protagonist_name,
            golden_finger_name=golden_finger_name,
            core_selling_points=core_selling_points,
            protagonist_desire=protagonist_desire,
            protagonist_flaw=protagonist_flaw,
            factions=factions,
            power_system_type=power_system_type,
            gf_irreversible_cost=gf_irreversible_cost,
        )
    outline_content = _ensure_plan_ready_outline(
        outline_content,
        title=title,
        genre=genre,
        protagonist_name=protagonist_name,
        golden_finger_name=golden_finger_name,
        core_selling_points=core_selling_points,
        protagonist_desire=protagonist_desire,
        protagonist_flaw=protagonist_flaw,
        factions=factions,
        power_system_type=power_system_type,
        gf_irreversible_cost=gf_irreversible_cost,
    )
    outline_path = project_path / "大纲" / "总纲.md"
    existing_outline = _read_text_if_exists(outline_path)
    if existing_outline:
        outline_content = existing_outline
    outline_content = sync_master_outline_with_profile(
        outline_content,
        title=title,
        genre=genre,
        target_chapters=int(target_chapters),
        profile=planning_profile,
    )
    outline_path.parent.mkdir(parents=True, exist_ok=True)
    outline_path.write_text(outline_content, encoding="utf-8")
    state["planning"]["readiness"] = evaluate_planning_readiness(planning_profile, outline_text=outline_content)
    save_planning_profile(project_path, planning_profile, title=title, genre=genre)
    atomic_write_json(state_path, state, use_lock=True, backup=False)

    _write_text_if_missing(
        project_path / "大纲" / "爽点规划.md",
        "\n".join(
            [
                "# 爽点规划",
                "",
                f"> 项目：{title}｜题材：{genre}｜创建：{now}",
                "",
                "## 核心卖点（来自初始化输入）",
                f"- {core_selling_points or '（待填写，建议 1-3 条，用逗号分隔）'}",
                "",
                "## 密度目标（建议）",
                "- 每章至少 1 个小爽点",
                "- 每 5 章至少 1 个大爽点",
                "",
                "## 分布表（示例，可改）",
                "",
                "| 章节范围 | 主导爽点类型 | 备注 |",
                "|---|---|---|",
                "| 1-5 | 金手指/打脸/反转 | 开篇钩子 + 立人设 |",
                "| 6-10 | 升级/收获 | 进入主线节奏 |",
                "",
            ]
        ),
    )

    # 生成环境变量模板（不写入真实密钥）
    _write_text_if_missing(
        project_path / ".env.example",
        "\n".join(
            [
                "# Webnovel Writer 配置示例（复制为 .env 后填写）",
                "# 注意：请勿将包含真实 API_KEY 的 .env 提交到版本库。",
                "",
                "# Embedding",
                "EMBED_BASE_URL=https://api-inference.modelscope.cn/v1",
                "EMBED_MODEL=Qwen/Qwen3-Embedding-8B",
                "EMBED_API_KEY=",
                "",
                "# Rerank",
                "RERANK_BASE_URL=https://api.jina.ai/v1",
                "RERANK_MODEL=jina-reranker-v3",
                "RERANK_API_KEY=",
                "",
            ]
        )
        + "\n",
    )

    # Git 初始化（仅当项目目录内尚无 .git 且 Git 可用）
    git_dir = project_path / ".git"
    if not git_dir.exists():
        if not is_git_available():
            print("\n⚠️  Git 不可用，跳过版本控制初始化")
            print("💡 如需启用 Git 版本控制，请安装 Git: https://git-scm.com/")
        else:
            print("\nInitializing Git repository...")
            try:
                subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True, text=True)

                gitignore_file = project_path / ".gitignore"
                if not gitignore_file.exists():
                    gitignore_file.write_text(
                        """# Python
__pycache__/
*.py[cod]
*.so

# Env (keep .env.example)
.env
.env.*
!.env.example

# Temporary files
*.tmp
*.bak
.DS_Store

# IDE
.vscode/
.idea/

# Don't ignore .webnovel (we need to track state.json)
# But ignore cache files
.webnovel/context_cache.json
.webnovel/*.lock
.webnovel/*.bak
""",
                        encoding="utf-8",
                    )

                subprocess.run(["git", "add", "."], cwd=project_path, check=True, capture_output=True)
                # 安全修复：清理 title 防止命令注入
                safe_title = sanitize_commit_message(title)
                subprocess.run(
                    ["git", "commit", "-m", f"初始化网文项目：{safe_title}"],
                    cwd=project_path,
                    check=True,
                    capture_output=True,
                )
                print("Git initialized.")
            except subprocess.CalledProcessError as e:
                print(f"Git init failed (non-fatal): {e}")

    # 记录工作区默认项目指针（非阻断）
    try:
        pointer_file = write_current_project_pointer(project_path)
        if pointer_file is not None:
            print(f"Default project pointer updated: {pointer_file}")
    except Exception as e:
        print(f"Default project pointer update failed (non-fatal): {e}")

    print(f"\nProject initialized at: {project_path}")
    print("Key files:")
    print(" - .webnovel/state.json")
    print(" - 设定集/世界观.md")
    print(" - 设定集/力量体系.md")
    print(" - 设定集/主角卡.md")
    print(" - 设定集/金手指设计.md")
    print(" - 大纲/总纲.md")
    print(" - 大纲/爽点规划.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="网文项目初始化脚本（生成项目结构 + state.json + 基础模板）")
    parser.add_argument("project_dir", help="项目目录（建议 ./novel-project）")
    parser.add_argument("title", help="小说标题")
    parser.add_argument(
        "genre",
        help="题材类型（可用“+”组合，如：都市脑洞+规则怪谈；示例：修仙/系统流/都市异能/古言/现实题材）",
    )

    parser.add_argument("--protagonist-name", default="", help="主角姓名")
    parser.add_argument("--target-words", type=int, default=2_000_000, help="目标总字数（默认 2000000）")
    parser.add_argument("--target-chapters", type=int, default=600, help="目标总章节数（默认 600）")

    parser.add_argument("--golden-finger-name", default="", help="金手指称呼/系统名（建议读者可见的代号）")
    parser.add_argument("--golden-finger-type", default="", help="金手指类型（如 系统流/鉴定流/签到流）")
    parser.add_argument("--golden-finger-style", default="", help="金手指风格（如 冷漠工具型/毒舌吐槽型）")
    parser.add_argument("--core-selling-points", default="", help="核心卖点（逗号分隔）")
    parser.add_argument("--protagonist-structure", default="", help="主角结构（单主角/多主角）")
    parser.add_argument("--heroine-config", default="", help="女主配置（无女主/单女主/多女主）")
    parser.add_argument("--heroine-names", default="", help="女主姓名（多个用逗号分隔）")
    parser.add_argument("--heroine-role", default="", help="女主定位（事业线/情感线/对抗线）")
    parser.add_argument("--co-protagonists", default="", help="多主角姓名（逗号分隔）")
    parser.add_argument("--co-protagonist-roles", default="", help="多主角定位（逗号分隔）")
    parser.add_argument("--antagonist-tiers", default="", help="反派分层（如 小反派:张三;中反派:李四;大反派:王五）")
    parser.add_argument("--world-scale", default="", help="世界规模")
    parser.add_argument("--factions", default="", help="势力格局/核心势力")
    parser.add_argument("--power-system-type", default="", help="力量体系类型")
    parser.add_argument("--social-class", default="", help="社会阶层")
    parser.add_argument("--resource-distribution", default="", help="资源分配")
    parser.add_argument("--gf-visibility", default="", help="金手指可见度（明牌/半明牌/暗牌）")
    parser.add_argument("--gf-irreversible-cost", default="", help="金手指不可逆代价")
    parser.add_argument("--currency-system", default="", help="货币体系")
    parser.add_argument("--currency-exchange", default="", help="货币兑换/面值规则")
    parser.add_argument("--sect-hierarchy", default="", help="宗门/组织层级")
    parser.add_argument("--cultivation-chain", default="", help="典型境界链")
    parser.add_argument("--cultivation-subtiers", default="", help="小境界划分（初/中/后/巅 等）")

    # 深度模式可选参数（用于预填模板）
    parser.add_argument("--protagonist-desire", default="", help="主角核心欲望（深度模式）")
    parser.add_argument("--protagonist-flaw", default="", help="主角性格弱点（深度模式）")
    parser.add_argument("--protagonist-archetype", default="", help="主角人设类型（深度模式）")
    parser.add_argument("--antagonist-level", default="", help="反派等级（深度模式）")
    parser.add_argument("--target-reader", default="", help="目标读者（深度模式）")
    parser.add_argument("--platform", default="", help="发布平台（深度模式）")

    args = parser.parse_args()

    init_project(
        args.project_dir,
        args.title,
        args.genre,
        protagonist_name=args.protagonist_name,
        target_words=args.target_words,
        target_chapters=args.target_chapters,
        golden_finger_name=args.golden_finger_name,
        golden_finger_type=args.golden_finger_type,
        golden_finger_style=args.golden_finger_style,
        core_selling_points=args.core_selling_points,
        protagonist_structure=args.protagonist_structure,
        heroine_config=args.heroine_config,
        heroine_names=args.heroine_names,
        heroine_role=args.heroine_role,
        co_protagonists=args.co_protagonists,
        co_protagonist_roles=args.co_protagonist_roles,
        antagonist_tiers=args.antagonist_tiers,
        world_scale=args.world_scale,
        factions=args.factions,
        power_system_type=args.power_system_type,
        social_class=args.social_class,
        resource_distribution=args.resource_distribution,
        gf_visibility=args.gf_visibility,
        gf_irreversible_cost=args.gf_irreversible_cost,
        protagonist_desire=args.protagonist_desire,
        protagonist_flaw=args.protagonist_flaw,
        protagonist_archetype=args.protagonist_archetype,
        antagonist_level=args.antagonist_level,
        target_reader=args.target_reader,
        platform=args.platform,
        currency_system=args.currency_system,
        currency_exchange=args.currency_exchange,
        sect_hierarchy=args.sect_hierarchy,
        cultivation_chain=args.cultivation_chain,
        cultivation_subtiers=args.cultivation_subtiers,
    )


if __name__ == "__main__":
    main()


