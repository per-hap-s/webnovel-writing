#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Modules - 配置文件

API 配置通过环境变量读取（支持 .env 文件）：
- WEBNOVEL_RAG_BASE_URL, WEBNOVEL_RAG_API_KEY
- WEBNOVEL_RAG_EMBED_MODEL, WEBNOVEL_RAG_RERANK_MODEL
"""

import logging
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Mapping, Optional

from runtime_compat import normalize_windows_path

_logger = logging.getLogger(__name__)
APP_ROOT_ENV_FALLBACK_KEYS = frozenset({"WEBNOVEL_RAG_API_KEY"})
_INITIAL_ENV_KEYS = frozenset(os.environ.keys())
_RUNTIME_ENV_MANAGED_KEYS: set[str] = set()

from .context_weights import TEMPLATE_WEIGHTS_DYNAMIC_DEFAULT


def _get_app_root_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"

def _get_user_claude_root() -> Path:
    raw = os.environ.get("WEBNOVEL_CLAUDE_HOME") or os.environ.get("CLAUDE_HOME")
    if raw:
        try:
            return normalize_windows_path(raw).expanduser().resolve()
        except (OSError, RuntimeError) as e:
            _logger.debug(
                "路径解析失败，使用非解析路径: %s, 错误: %s",
                raw,
                e,
            )
            return normalize_windows_path(raw).expanduser()
    return (Path.home() / ".claude").resolve()


def _parse_dotenv_file(
    env_path: Path,
    *,
    allowed_keys: set[str] | frozenset[str] | None = None,
    protected_keys: set[str] | frozenset[str] | None = None,
) -> dict[str, str]:
    if not env_path.exists():
        return {}
    parsed: dict[str, str] = {}
    try:
        with open(env_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if not key:
                        continue
                    if allowed_keys is not None and key not in allowed_keys:
                        continue
                    if protected_keys is not None and key in protected_keys:
                        continue
                    parsed[key] = value
        return parsed
    except (IOError, OSError, UnicodeDecodeError) as e:
        _logger.debug(
            "加载 .env 文件失败: %s, 错误: %s",
            env_path,
            e,
        )
        return {}


def _apply_runtime_env_values(
    values: Mapping[str, str],
    *,
    explicit_env_keys: set[str] | frozenset[str],
) -> None:
    global _RUNTIME_ENV_MANAGED_KEYS
    explicit_keys = set(explicit_env_keys)
    next_managed_keys = {key for key in values if key not in explicit_keys}

    for key in list(_RUNTIME_ENV_MANAGED_KEYS):
        if key in explicit_keys:
            continue
        if key not in next_managed_keys:
            os.environ.pop(key, None)

    for key, value in values.items():
        if key in explicit_keys:
            continue
        os.environ[key] = value

    _RUNTIME_ENV_MANAGED_KEYS = next_managed_keys


def _collect_runtime_env_values(project_root: Optional[Path] = None) -> dict[str, str]:
    values: dict[str, str] = {}
    for layer in (
        _parse_dotenv_file(_get_user_claude_root() / "webnovel-writer" / ".env"),
        _parse_dotenv_file(
            _get_app_root_env_path(),
            allowed_keys=APP_ROOT_ENV_FALLBACK_KEYS,
        ),
        _parse_dotenv_file(Path.cwd() / ".env"),
    ):
        values.update(layer)

    if project_root is not None:
        values.update(_parse_dotenv_file(project_root / ".env"))

    return values


def _runtime_env_for_project(project_root: Path) -> dict[str, str]:
    values = _collect_runtime_env_values(project_root)
    for key in _INITIAL_ENV_KEYS:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def _get_env_text(env_values: Mapping[str, str], key: str, default: str = "") -> str:
    value = str(env_values.get(key) or "").strip()
    return value if value else default


def _get_env_int(env_values: Mapping[str, str], key: str, default: int) -> int:
    raw = str(env_values.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        _logger.debug("环境变量 %s 不是有效整数: %s", key, raw)
        return default


def _load_dotenv():
    """
    加载 .env 文件（best-effort）。

    约定：
    - 项目级 `.env`（当前工作目录下）优先；
    - 全局 `.env` 作为兜底：`~/.claudewebnovel writer/.env`
    """
    # 1) 当前目录（常见：用户从项目根目录执行）
    _apply_runtime_env_values(_collect_runtime_env_values(None), explicit_env_keys=_INITIAL_ENV_KEYS)

def load_runtime_env(project_root: Optional[str | Path] = None) -> None:
    """
    Best-effort load runtime environment from the current working directory,
    the user-level fallback, and optionally a specific project root.

    Priority:
    - explicitly exported environment variables
    - project_root/.env
    - cwd/.env and user fallback .env
    """
    try:
        root = normalize_windows_path(project_root).expanduser().resolve() if project_root is not None else None
    except (OSError, RuntimeError, TypeError, ValueError) as e:
        _logger.debug(
            "Runtime env path resolve failed: %s, error: %s",
            project_root,
            e,
        )
        _apply_runtime_env_values(_collect_runtime_env_values(None), explicit_env_keys=_INITIAL_ENV_KEYS)
        return

    _apply_runtime_env_values(_collect_runtime_env_values(root), explicit_env_keys=_INITIAL_ENV_KEYS)


_load_dotenv()


def _default_context_template_weights_dynamic() -> dict[str, dict[str, dict[str, float]]]:
    return {
        stage: {
            template: dict(weights)
            for template, weights in templates.items()
        }
        for stage, templates in TEMPLATE_WEIGHTS_DYNAMIC_DEFAULT.items()
    }


@dataclass
class DataModulesConfig:
    """数据模块配置"""

    # ================= 项目路径 =================
    project_root: Path = field(default_factory=lambda: Path.cwd())

    @property
    def webnovel_dir(self) -> Path:
        return self.project_root / ".webnovel"

    @property
    def state_file(self) -> Path:
        return self.webnovel_dir / "state.json"

    @property
    def index_db(self) -> Path:
        return self.webnovel_dir / "index.db"

    # v5.1 引入: alias_index_file 已废弃，别名存储在 index.db aliases 表

    @property
    def chapters_dir(self) -> Path:
        return self.project_root / "正文"

    @property
    def settings_dir(self) -> Path:
        return self.project_root / "设定集"

    @property
    def outline_dir(self) -> Path:
        return self.project_root / "大纲"


    # ================= Embedding API 配置 =================
    embed_api_type: str = "openai"
    embed_base_url: str = field(default_factory=lambda: os.getenv("WEBNOVEL_RAG_BASE_URL", "https://api.siliconflow.cn/v1"))
    embed_model: str = field(default_factory=lambda: os.getenv("WEBNOVEL_RAG_EMBED_MODEL", "BAAI/bge-m3"))
    embed_api_key: str = field(default_factory=lambda: os.getenv("WEBNOVEL_RAG_API_KEY", ""))

    @property
    def embed_url(self) -> str:
        return self.embed_base_url

    # ================= Rerank API 配置 =================
    rerank_api_type: str = "openai"
    rerank_base_url: str = field(default_factory=lambda: os.getenv("WEBNOVEL_RAG_BASE_URL", "https://api.siliconflow.cn/v1"))
    rerank_model: str = field(default_factory=lambda: os.getenv("WEBNOVEL_RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"))
    rerank_api_key: str = field(default_factory=lambda: os.getenv("WEBNOVEL_RAG_API_KEY", ""))

    @property
    def rerank_url(self) -> str:
        return self.rerank_base_url

    # ================= 并发配置 =================
    embed_concurrency: int = 64
    rerank_concurrency: int = 32
    embed_batch_size: int = 64

    # ================= 超时配置 =================
    cold_start_timeout: int = 300
    normal_timeout: int = 180

    # ================= 重试配置 =================
    api_max_retries: int = field(default_factory=lambda: int(os.getenv("WEBNOVEL_RAG_MAX_RETRIES", "6")))
    api_retry_delay: float = field(default_factory=lambda: int(os.getenv("WEBNOVEL_RAG_RETRY_INITIAL_DELAY_MS", "500")) / 1000.0)

    api_retry_max_delay_ms: int = field(default_factory=lambda: int(os.getenv("WEBNOVEL_RAG_RETRY_MAX_DELAY_MS", "8000")))

    # ================= 检索配置 =================
    vector_top_k: int = 30
    bm25_top_k: int = 20
    rerank_top_n: int = 10
    rrf_k: int = 60

    vector_full_scan_max_vectors: int = 500
    vector_prefilter_bm25_candidates: int = 200
    vector_prefilter_recent_candidates: int = 200

    # ================= Graph-RAG 配置 =================
    graph_rag_enabled: bool = False
    graph_rag_expand_hops: int = 1
    graph_rag_max_expanded_entities: int = 30
    graph_rag_candidate_limit: int = 150
    graph_rag_boost_same_entity: float = 0.2
    graph_rag_boost_related_entity: float = 0.1
    graph_rag_boost_recency: float = 0.05

    relationship_graph_from_index_enabled: bool = True

    # ================= 实体提取配置 =================
    extraction_confidence_high: float = 0.8
    extraction_confidence_medium: float = 0.5

    # ================= 列表截断限制 =================
    max_disambiguation_warnings: int = 500
    max_disambiguation_pending: int = 1000
    max_state_changes: int = 2000

    context_recent_summaries_window: int = 3
    context_recent_meta_window: int = 3
    context_alerts_slice: int = 10
    context_max_appearing_characters: int = 10
    context_max_urgent_foreshadowing: int = 5
    context_story_skeleton_interval: int = 20
    context_story_skeleton_max_samples: int = 5
    context_story_skeleton_snippet_chars: int = 400
    context_extra_section_budget: int = 800
    context_ranker_enabled: bool = True
    context_ranker_recency_weight: float = 0.7
    context_ranker_frequency_weight: float = 0.3
    context_ranker_hook_bonus: float = 0.2
    context_ranker_length_bonus_cap: float = 0.2
    context_ranker_alert_critical_keywords: tuple[str, ...] = (
        "冲突",
        "矛盾",
        "critical",
        "break",
        "违规",
        "断裂",
    )
    context_ranker_debug: bool = False
    context_reader_signal_enabled: bool = True
    context_reader_signal_recent_limit: int = 5
    context_reader_signal_window_chapters: int = 20
    context_reader_signal_review_window: int = 5
    context_reader_signal_include_debt: bool = False
    context_genre_profile_enabled: bool = True
    context_genre_profile_max_refs: int = 8
    context_genre_profile_fallback: str = "shuangwen"
    context_compact_text_enabled: bool = True
    context_compact_min_budget: int = 120
    context_compact_head_ratio: float = 0.65
    context_writing_guidance_enabled: bool = True
    context_writing_guidance_max_items: int = 6
    context_writing_guidance_low_score_threshold: float = 75.0
    context_writing_guidance_hook_diversify: bool = True
    context_methodology_enabled: bool = True
    context_methodology_genre_whitelist: tuple[str, ...] = ("*",)
    context_methodology_label: str = "digital-serial-v1"
    context_writing_checklist_enabled: bool = True
    context_writing_checklist_min_items: int = 3
    context_writing_checklist_max_items: int = 6
    context_writing_checklist_default_weight: float = 1.0
    context_writing_score_persist_enabled: bool = True
    context_writing_score_include_reader_trend: bool = True
    context_writing_score_trend_window: int = 10
    context_rag_assist_enabled: bool = True
    context_rag_assist_top_k: int = 4
    context_rag_assist_min_outline_chars: int = 40
    context_rag_assist_max_query_chars: int = 120
    context_dynamic_budget_enabled: bool = True
    context_dynamic_budget_early_chapter: int = 30
    context_dynamic_budget_late_chapter: int = 120
    context_dynamic_budget_early_core_bonus: float = 0.08
    context_dynamic_budget_early_scene_bonus: float = 0.04
    context_dynamic_budget_late_global_bonus: float = 0.08
    context_dynamic_budget_late_scene_penalty: float = 0.06
    context_template_weights_dynamic: dict[str, dict[str, dict[str, float]]] = field(
        default_factory=_default_context_template_weights_dynamic
    )
    context_genre_profile_support_composite: bool = True
    context_genre_profile_max_genres: int = 2
    context_genre_profile_separators: tuple[str, ...] = (
        "+",
        "/",
        "|",
        ",",
        "，",
        "、",
    )

    export_recent_changes_slice: int = 20
    export_disambiguation_slice: int = 20

    # ================= 查询默认限制 =================
    query_recent_chapters_limit: int = 10
    query_scenes_by_location_limit: int = 20
    query_entity_appearances_limit: int = 50
    query_recent_appearances_limit: int = 20

    # ================= 伏笔紧急度 =================
    foreshadowing_urgency_pending_high: int = 100
    foreshadowing_urgency_pending_medium: int = 50
    foreshadowing_urgency_target_proximity: int = 5
    foreshadowing_urgency_score_high: int = 100
    foreshadowing_urgency_score_medium: int = 60
    foreshadowing_urgency_score_target: int = 80
    foreshadowing_urgency_score_low: int = 20
    foreshadowing_urgency_threshold_show: int = 60

    foreshadowing_tier_weight_core: float = 3.0
    foreshadowing_tier_weight_sub: float = 2.0
    foreshadowing_tier_weight_decor: float = 1.0

    # ================= 角色活跃度 =================
    character_absence_warning: int = 30
    character_absence_critical: int = 100
    character_candidates_limit: int = 800

    # ================= Strand Weave 节奏 =================
    strand_quest_max_consecutive: int = 5
    strand_fire_max_gap: int = 10
    strand_constellation_max_gap: int = 15

    strand_quest_ratio_min: int = 55
    strand_quest_ratio_max: int = 65
    strand_fire_ratio_min: int = 20
    strand_fire_ratio_max: int = 30
    strand_constellation_ratio_min: int = 10
    strand_constellation_ratio_max: int = 20

    # ================= 爽点节奏 =================
    pacing_segment_size: int = 100
    pacing_words_per_point_excellent: int = 1000
    pacing_words_per_point_good: int = 1500
    pacing_words_per_point_acceptable: int = 2000

    # ================= RAG 存储 =================
    @property
    def rag_db(self) -> Path:
        return self.webnovel_dir / "rag.db"

    @property
    def vector_db(self) -> Path:
        return self.webnovel_dir / "vectors.db"

    def ensure_dirs(self):
        """
        确保项目数据目录存在。
        
        创建 .webnovel 目录及其父目录（如果不存在）。
        此方法应在任何需要访问数据目录的操作之前调用。
        """
        self.webnovel_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_project_root(cls, project_root: str | Path) -> "DataModulesConfig":
        """
        从项目根目录创建配置实例。
        
        此方法会先加载项目级 .env 文件，然后创建配置实例。
        这确保了 EMBED_*/RERANK_* 等环境变量能够正确生效。
        
        参数:
            project_root: 项目根目录路径，支持字符串或 Path 对象。
            
        返回:
            DataModulesConfig: 配置实例。
        """
        root = normalize_windows_path(project_root).expanduser().resolve()
        runtime_env = _runtime_env_for_project(root)
        return cls(
            project_root=root,
            embed_base_url=_get_env_text(runtime_env, "WEBNOVEL_RAG_BASE_URL", "https://api.siliconflow.cn/v1"),
            embed_model=_get_env_text(runtime_env, "WEBNOVEL_RAG_EMBED_MODEL", "BAAI/bge-m3"),
            embed_api_key=_get_env_text(runtime_env, "WEBNOVEL_RAG_API_KEY", ""),
            rerank_base_url=_get_env_text(runtime_env, "WEBNOVEL_RAG_BASE_URL", "https://api.siliconflow.cn/v1"),
            rerank_model=_get_env_text(runtime_env, "WEBNOVEL_RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
            rerank_api_key=_get_env_text(runtime_env, "WEBNOVEL_RAG_API_KEY", ""),
            api_max_retries=_get_env_int(runtime_env, "WEBNOVEL_RAG_MAX_RETRIES", 6),
            api_retry_delay=_get_env_int(runtime_env, "WEBNOVEL_RAG_RETRY_INITIAL_DELAY_MS", 500) / 1000.0,
            api_retry_max_delay_ms=_get_env_int(runtime_env, "WEBNOVEL_RAG_RETRY_MAX_DELAY_MS", 8000),
        )


_default_config: Optional[DataModulesConfig] = None


def get_config(project_root: Optional[Path] = None) -> DataModulesConfig:
    """
    获取数据模块配置实例。
    
    如果指定了项目根目录，则创建新的配置实例并验证。
    如果未指定，则返回全局默认配置实例（首次调用时自动创建）。
    
    参数:
        project_root: 项目根目录路径。如果为 None，则使用自动检测的项目根目录。
        
    返回:
        DataModulesConfig: 数据模块配置实例。
    """
    global _default_config
    if project_root is not None:
        config = DataModulesConfig.from_project_root(project_root)
        validate_config(config)
        return config
    if _default_config is None:
        from project_locator import resolve_project_root

        root = resolve_project_root()
        _default_config = DataModulesConfig.from_project_root(root)
        validate_config(_default_config)
    return _default_config


def set_project_root(project_root: str | Path):
    """
    设置项目根目录并更新全局配置实例。
    
    此函数会重新创建全局默认配置实例，并加载项目级 .env 文件。
    
    参数:
        project_root: 项目根目录路径，支持字符串或 Path 对象。
    """
    global _default_config
    _default_config = DataModulesConfig.from_project_root(project_root)


def validate_config(config: Optional[DataModulesConfig] = None) -> bool:
    """
    Validate required RAG configuration.
    """
    if config is None:
        config = get_config()

    provider = (os.environ.get("WEBNOVEL_LLM_PROVIDER") or "").strip().lower()
    if provider == "mock":
        validate_config_bounds(config)
        return True

    all_valid = True

    if not config.embed_api_key or not config.embed_api_key.strip():
        _logger.warning(
            "[config] WEBNOVEL_RAG_API_KEY is missing. Set WEBNOVEL_RAG_API_KEY in .env or the environment."
        )
        all_valid = False

    if all_valid:
        _logger.info("[config] RAG configuration validated successfully.")

    validate_config_bounds(config)
    return all_valid

def validate_config_bounds(config: DataModulesConfig) -> bool:
    """
    验证配置值是否在合理范围内。
    
    检查以下配置边界：
    - embed_concurrency: 1-256
    - rerank_concurrency: 1-128
    - embed_batch_size: 1-256
    - cold_start_timeout: >= 10
    - normal_timeout: >= 10
    - api_max_retries: 1-10
    - api_retry_delay: >= 0
    - api_retry_max_delay_ms: >= retry_initial_delay_ms
    
    参数:
        config: 要验证的配置对象
        
    返回:
        bool: 所有配置值是否都在合理范围内
    """
    all_valid = True
    
    # 并发配置验证
    if not (1 <= config.embed_concurrency <= 256):
        _logger.warning(
            "【配置警告】embed_concurrency=%d 超出合理范围 [1, 256]，建议调整。",
            config.embed_concurrency
        )
        all_valid = False
    
    if not (1 <= config.rerank_concurrency <= 128):
        _logger.warning(
            "【配置警告】rerank_concurrency=%d 超出合理范围 [1, 128]，建议调整。",
            config.rerank_concurrency
        )
        all_valid = False
    
    if not (1 <= config.embed_batch_size <= 256):
        _logger.warning(
            "【配置警告】embed_batch_size=%d 超出合理范围 [1, 256]，建议调整。",
            config.embed_batch_size
        )
        all_valid = False
    
    # 超时配置验证
    if config.cold_start_timeout < 10:
        _logger.warning(
            "【配置警告】cold_start_timeout=%d 过小，可能导致频繁超时，建议 >= 10。",
            config.cold_start_timeout
        )
    
    if config.normal_timeout < 10:
        _logger.warning(
            "【配置警告】normal_timeout=%d 过小，可能导致频繁超时，建议 >= 10。",
            config.normal_timeout
        )
    
    # 重试配置验证
    if not (0 <= config.api_max_retries <= 10):
        _logger.warning(
            "【配置警告】api_max_retries=%d 超出合理范围 [0, 10]，建议调整。",
            config.api_max_retries
        )
        all_valid = False
    
    if config.api_retry_delay < 0:
        _logger.warning(
            "【配置警告】api_retry_delay=%.2f 为负数，建议 >= 0。",
            config.api_retry_delay
        )
        all_valid = False
    
    return all_valid


def _alias_module_name() -> None:
    module = sys.modules.get(__name__)
    if module is None:
        return
    if __name__.startswith("scripts.data_modules"):
        alias = __name__.replace("scripts.data_modules", "data_modules", 1)
    elif __name__.startswith("data_modules"):
        alias = __name__.replace("data_modules", "scripts.data_modules", 1)
    else:
        return
    sys.modules.setdefault(alias, module)


_alias_module_name()



