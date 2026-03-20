"""
Webnovel Dashboard FastAPI application.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import re
import sqlite3
import sys
from subprocess import run
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from scripts.init_project import (
    build_planning_fill_template,
    evaluate_planning_readiness,
    get_planning_profile_field_specs,
    normalize_planning_profile,
    sync_master_outline_with_profile,
)

from .orchestrator import OrchestrationService
from .path_guard import safe_resolve
from .task_models import (
    SupervisorBatchDismissRequest,
    SupervisorChecklistSaveRequest,
    SupervisorTrackingRequest,
    SupervisorBatchUndismissRequest,
    BootstrapProjectRequest,
    CancelTaskRequest,
    ErrorResponse,
    InvalidFactDecisionRequest,
    LLMSettingsRequest,
    PlanningProfileRequest,
    RAGSettingsRequest,
    RetryRequest,
    ReviewDecisionRequest,
    SupervisorDismissRequest,
    TaskRequest,
)
from .watcher import FileWatcher

logger = logging.getLogger(__name__)


class APIError(Exception):
    """
    自定义 API 错误异常类
    
    用于携带错误代码和详细信息，便于异常处理器统一处理。
    
    Attributes:
        status_code: HTTP 状态码
        code: 错误代码
        message: 错误消息
        details: 可选的详细信息
    """
    def __init__(self, status_code: int, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    请求超时中间件
    
    为每个请求设置超时限制，防止长时间运行的请求阻塞服务器资源。
    超时时间可通过环境变量 REQUEST_TIMEOUT_SECONDS 配置，默认 30 秒。
    """
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=REQUEST_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            error_response = ErrorResponse(
                code='REQUEST_TIMEOUT',
                message=f'请求处理超时，超过 {REQUEST_TIMEOUT_SECONDS} 秒',
                details={'timeout_seconds': REQUEST_TIMEOUT_SECONDS}
            )
            return JSONResponse(
                status_code=504,
                content=error_response.model_dump()
            )


_project_root: Path | None = None
_watcher = FileWatcher()
STATIC_DIR = Path(__file__).parent / 'frontend' / 'dist'
FILE_TREE_FOLDERS = ('正文', '大纲', '设定集')
PROJECT_STATE_SECTION = '项目状态'
PROJECT_STATE_SUMMARIES_PATH = '.webnovel/summaries'
PROJECT_STATE_FILE_PATH = '.webnovel/state.json'
RELATIONSHIP_TYPE_LABELS = {
    'family': '家庭',
    'ally': '同盟',
    'enemy': '敌对',
    'mentor': '师友',
    'subordinate': '上下级',
    'colleague': '同事',
    'suspect': '嫌疑',
    'investigating': '调查',
    'conflict': '冲突',
    'owes': '欠债',
    'protects': '保护',
    'watches': '监视',
    'warned_by': '预警来源',
}

REQUEST_TIMEOUT_SECONDS = int(os.environ.get('REQUEST_TIMEOUT_SECONDS', '30'))
DB_BUSY_TIMEOUT_MS = int(os.environ.get('DB_BUSY_TIMEOUT_MS', '5000'))

HTTP_STATUS_MESSAGES = {
    400: '请求无效，请检查输入后重试。',
    401: '当前请求未通过身份校验。',
    403: '当前操作被拒绝。',
    404: '未找到请求的资源。',
    405: '当前请求方法不被允许。',
    409: '当前操作与现有数据冲突，请调整后重试。',
    422: '请求参数校验失败。',
    429: '请求过于频繁，请稍后再试。',
    500: '服务器内部错误，请稍后重试。',
    502: '上游服务暂时不可用，请稍后重试。',
    503: '服务暂时不可用，请稍后重试。',
    504: '请求处理超时，请稍后重试。',
}

HTTP_DETAIL_MESSAGE_MAP = {
    'Project already initialized.': '项目已初始化，不能重复创建。',
    'Project already initialized': '项目已初始化，不能重复创建。',
    'state.json not found.': '未找到 state.json。',
    'Task not found.': '未找到任务。',
    'Project bootstrap failed': '项目初始化失败。',
    'Project bootstrap did not create state.json': '项目初始化未完成，未生成 state.json。',
    'Request validation failed': '请求参数校验失败。',
    'Unknown error': '未知错误。',
}


def _get_cors_origins() -> list[str]:
    """
    从环境变量获取 CORS 允许的来源列表。
    
    环境变量 CORS_ORIGINS 应为逗号分隔的 URL 列表，
    例如: "http://localhost:3000,https://example.com"
    
    Returns:
        list[str]: 允许的来源列表，未配置时返回空列表
    """
    cors_origins_str = os.environ.get('CORS_ORIGINS', '').strip()
    
    if not cors_origins_str:
        logger.warning(
            'CORS_ORIGINS 环境变量未配置，CORS 将拒绝所有跨域请求。'
            '建议设置 CORS_ORIGINS 环境变量，例如: '
            'CORS_ORIGINS=http://localhost:3000,https://your-domain.com'
        )
        return []
    
    origins = [origin.strip() for origin in cors_origins_str.split(',') if origin.strip()]
    
    if not origins:
        logger.warning('CORS_ORIGINS 环境变量为空，CORS 将拒绝所有跨域请求。')
        return []
    
    logger.info(f'CORS 允许的来源: {origins}')
    return origins


def _get_project_root() -> Path:
    if _project_root is None:
        raise HTTPException(status_code=500, detail='未配置项目根目录。')
    return _project_root


def _webnovel_dir(project_root: Path | None = None) -> Path:
    return (project_root or _get_project_root()) / '.webnovel'

def _project_env_path(project_root: Path | None = None) -> Path:
    return (project_root or _get_project_root()) / '.env'


def _state_path(project_root: Path | None = None) -> Path:
    return _webnovel_dir(project_root) / 'state.json'


def create_app(project_root: str | Path | None = None) -> FastAPI:
    global _project_root

    if project_root:
        _project_root = Path(project_root).resolve()

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        app.state.dashboard_loop = asyncio.get_running_loop()
        app.state.orchestrators = {}
        webnovel = _webnovel_dir()
        if webnovel.is_dir():
            _watcher.start(webnovel, app.state.dashboard_loop)
        app.state.orchestrator = _get_orchestrator_for_root(_get_project_root(), refresh=True)
        try:
            yield
        finally:
            _watcher.stop()

    app = FastAPI(title='网文管理面板', version='0.2.0', lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_origins(),
        allow_methods=['GET', 'POST'],
        allow_headers=['*'],
    )
    app.add_middleware(TimeoutMiddleware)

    def _resolve_request_project_root(http_request: Request | None = None, *, explicit_root: Optional[str] = None) -> Path:
        candidate = explicit_root or (http_request.query_params.get('project_root') if http_request else None)
        if candidate:
            return Path(candidate).resolve()
        return _get_project_root()

    def _ensure_project_watch(project_root_value: Path) -> None:
        loop = getattr(app.state, 'dashboard_loop', None)
        webnovel_dir = _webnovel_dir(project_root_value)
        if loop is not None and webnovel_dir.is_dir():
            _watcher.watch(webnovel_dir, loop)

    def _get_orchestrator_for_root(project_root_value: Path, *, refresh: bool = False) -> OrchestrationService:
        registry: dict[str, OrchestrationService] = getattr(app.state, 'orchestrators', {})
        app.state.orchestrators = registry
        root_key = str(project_root_value.resolve())
        orchestrator = registry.get(root_key)
        if refresh or orchestrator is None:
            orchestrator = OrchestrationService(project_root_value)
            registry[root_key] = orchestrator
        _ensure_project_watch(project_root_value)
        if root_key == str(_get_project_root()):
            app.state.orchestrator = orchestrator
        return orchestrator

    def _get_request_orchestrator(http_request: Request | None = None, *, explicit_root: Optional[str] = None, refresh: bool = False) -> OrchestrationService:
        project_root_value = _resolve_request_project_root(http_request, explicit_root=explicit_root)
        return _get_orchestrator_for_root(project_root_value, refresh=refresh)

    def _looks_like_english_message(text: str) -> bool:
        return bool(text) and text.isascii()

    def _build_details(
        details: Optional[Dict[str, Any]] = None,
        *,
        status_code: Optional[int] = None,
        original_message: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        merged: Dict[str, Any] = {}
        if details:
            merged.update(details)
        if status_code is not None:
            merged.setdefault('status_code', status_code)
        if original_message:
            merged.setdefault('original_message', original_message)
        return merged or None

    def _translate_http_message(status_code: int, detail_text: str) -> str:
        if detail_text in HTTP_DETAIL_MESSAGE_MAP:
            return HTTP_DETAIL_MESSAGE_MAP[detail_text]
        if detail_text and not _looks_like_english_message(detail_text):
            return detail_text
        return HTTP_STATUS_MESSAGES.get(status_code, '操作失败，请稍后重试。')

    def _format_validation_details(errors: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "errors": [
                {
                    "field": ".".join(str(loc) for loc in error.get("loc", [])),
                    "message": error.get("msg", "Invalid value"),
                    "type": error.get("type", "validation_error"),
                }
                for error in errors
            ]
        }

    def _error_response(
        status_code: int,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        *,
        original_message: Optional[str] = None,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                code=code,
                message=message,
                details=_build_details(details, status_code=status_code, original_message=original_message),
            ).model_dump(),
        )

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return _error_response(
            exc.status_code,
            exc.code,
            exc.message,
            exc.details,
            original_message=exc.details.get('original_message') if exc.details else None,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code_map = {
            400: 'BAD_REQUEST',
            401: 'UNAUTHORIZED',
            403: 'FORBIDDEN',
            404: 'NOT_FOUND',
            405: 'METHOD_NOT_ALLOWED',
            409: 'CONFLICT',
            422: 'VALIDATION_ERROR',
            429: 'RATE_LIMITED',
            500: 'INTERNAL_ERROR',
            502: 'BAD_GATEWAY',
            503: 'SERVICE_UNAVAILABLE',
        }
        detail_text = str(exc.detail) if exc.detail else ''
        return _error_response(
            exc.status_code,
            code_map.get(exc.status_code, 'UNKNOWN_ERROR'),
            _translate_http_message(exc.status_code, detail_text),
            None,
            original_message=detail_text or None,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            422,
            'VALIDATION_ERROR',
            '请求参数校验失败。',
            _format_validation_details(exc.errors()),
        )

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return _error_response(
            500,
            'INTERNAL_VALIDATION_ERROR',
            '内部数据校验失败。',
            _format_validation_details(exc.errors()),
        )

    @app.exception_handler(sqlite3.Error)
    async def sqlite_exception_handler(request: Request, exc: sqlite3.Error) -> JSONResponse:
        """
        处理 SQLite 数据库异常
        
        将数据库相关错误转换为统一的 ErrorResponse 格式返回。
        包括连接错误、查询错误、完整性约束错误等。
        
        Args:
            request: FastAPI 请求对象
            exc: sqlite3.Error 异常实例
            
        Returns:
            JSONResponse: 包含统一错误格式的响应
        """
        logger.error('数据库错误: %s', exc)
        error_code = 'DATABASE_ERROR'
        status_code = 500
        message = '数据库操作失败。'
        if isinstance(exc, sqlite3.OperationalError):
            if 'database is locked' in str(exc).lower():
                error_code = 'DATABASE_LOCKED'
                status_code = 503
                message = '数据库正忙，请稍后重试。'
            elif 'no such table' in str(exc).lower():
                error_code = 'TABLE_NOT_FOUND'
                status_code = 404
                message = '所需数据表不存在。'
        elif isinstance(exc, sqlite3.IntegrityError):
            error_code = 'INTEGRITY_ERROR'
            status_code = 409
            message = '数据约束校验失败。'
        return _error_response(
            status_code,
            error_code,
            message,
            {'error_type': type(exc).__name__, 'message': str(exc)},
            original_message=str(exc),
        )

    @app.exception_handler(json.JSONDecodeError)
    async def json_decode_exception_handler(request: Request, exc: json.JSONDecodeError) -> JSONResponse:
        """
        处理 JSON 解析异常
        
        将 JSON 解析错误转换为统一的 ErrorResponse 格式返回。
        
        Args:
            request: FastAPI 请求对象
            exc: json.JSONDecodeError 异常实例
            
        Returns:
            JSONResponse: 包含统一错误格式的响应
        """
        logger.error('JSON 解析错误: %s', exc)
        return _error_response(
            400,
            'JSON_PARSE_ERROR',
            'JSON 数据解析失败。',
            {
                'error_type': type(exc).__name__,
                'message': str(exc),
                'position': exc.pos,
                'line': exc.lineno,
                'column': exc.colno,
            },
            original_message=str(exc),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        处理所有未捕获的异常
        
        将未知异常转换为统一的 ErrorResponse 格式返回。
        记录错误日志以便排查问题。
        
        Args:
            request: FastAPI 请求对象
            exc: 异常实例
            
        Returns:
            JSONResponse: 包含统一错误格式的响应
        """
        logger.exception('未处理的异常: %s', exc)
        return _error_response(
            500,
            'INTERNAL_ERROR',
            '服务器内部错误，请稍后重试。',
            {'error_type': type(exc).__name__},
            original_message=str(exc),
        )

    def _get_db(project_root_value: Path | None = None) -> sqlite3.Connection:
        """获取数据库连接
        
        创建并配置 SQLite 数据库连接，启用 WAL 模式以支持并发访问。
        WAL 模式允许同时进行读写操作，提高并发性能。
        
        Returns:
            sqlite3.Connection: 配置好的数据库连接对象
        
        Raises:
            HTTPException: 当数据库文件不存在时抛出 404 错误
        """
        db_path = _webnovel_dir(project_root_value) / 'index.db'
        if not db_path.is_file():
            raise HTTPException(404, '未找到 index.db。')
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _read_env_lines(env_path: Path) -> list[str]:
        if not env_path.exists():
            return []
        try:
            return env_path.read_text(encoding='utf-8-sig').splitlines()
        except UnicodeDecodeError:
            return env_path.read_text(encoding='utf-8', errors='replace').splitlines()

    def _parse_env_values(env_path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in _read_env_lines(env_path):
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                continue
            key, _, value = stripped.partition('=')
            key = key.strip()
            value = value.strip()
            if key:
                values[key] = value
        return values

    def _write_env_updates(env_path: Path, updates: dict[str, str]) -> None:
        lines = _read_env_lines(env_path)
        pending = dict(updates)
        next_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                next_lines.append(line)
                continue
            key, _, _ = stripped.partition('=')
            key = key.strip()
            if key in pending:
                next_lines.append(f'{key}={pending.pop(key)}')
            else:
                next_lines.append(line)

        if next_lines and next_lines[-1].strip():
            next_lines.append('')
        for key, value in pending.items():
            next_lines.append(f'{key}={value}')

        env_path.write_text('\n'.join(next_lines).rstrip() + '\n', encoding='utf-8')

    def _mask_secret(value: str) -> str:
        if not value:
            return ''
        if len(value) <= 8:
            return '*' * len(value)
        return f'{value[:4]}***{value[-4:]}'

    def _project_env_or_os(project_root_value: Path | None = None) -> dict[str, str]:
        values = _parse_env_values(_project_env_path(project_root_value))
        merged = dict(os.environ)
        merged.update(values)
        return merged

    def _read_state_data(project_root_value: Path | None = None) -> dict[str, Any]:
        state_path = _state_path(project_root_value)
        if not state_path.is_file():
            raise HTTPException(404, '未找到 state.json。')
        return json.loads(state_path.read_text(encoding='utf-8'))

    def _write_state_data(state_data: dict[str, Any], project_root_value: Path | None = None) -> None:
        state_path = _state_path(project_root_value)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _planning_profile_payload(state_data: dict[str, Any], project_root_value: Path) -> dict[str, Any]:
        project_info = state_data.get('project_info') or {}
        planning = state_data.setdefault('planning', {})
        profile = normalize_planning_profile(
            planning.get('profile'),
            title=str(project_info.get('title') or '').strip(),
            genre=str(project_info.get('genre') or '').strip(),
        )
        outline_path = project_root_value / '大纲' / '总纲.md'
        outline_text = outline_path.read_text(encoding='utf-8') if outline_path.is_file() else ''
        readiness = evaluate_planning_readiness(profile, outline_text=outline_text)
        planning['profile'] = profile
        planning['readiness'] = readiness
        return {
            'profile': profile,
            'readiness': readiness,
            'last_blocked': planning.get('last_blocked'),
            'field_specs': get_planning_profile_field_specs(),
            'fill_template': build_planning_fill_template(),
            'outline_file': '大纲/总纲.md',
        }

    def _sync_planning_profile(state_data: dict[str, Any], profile_input: dict[str, Any], project_root_value: Path) -> dict[str, Any]:
        project_info = state_data.setdefault('project_info', {})
        title = str(project_info.get('title') or '').strip()
        genre = str(project_info.get('genre') or '').strip()
        target_chapters = int(project_info.get('target_chapters') or 600)
        planning = state_data.setdefault('planning', {})
        profile = normalize_planning_profile(profile_input, title=title, genre=genre)
        outline_path = project_root_value / '大纲' / '总纲.md'
        existing_outline = outline_path.read_text(encoding='utf-8') if outline_path.is_file() else ''
        updated_outline = sync_master_outline_with_profile(
            existing_outline,
            title=title,
            genre=genre,
            target_chapters=target_chapters,
            profile=profile,
        )
        outline_path.parent.mkdir(parents=True, exist_ok=True)
        outline_path.write_text(updated_outline, encoding='utf-8')
        readiness = evaluate_planning_readiness(profile, outline_text=updated_outline)
        planning['profile'] = profile
        planning['readiness'] = readiness
        return {
            'profile': profile,
            'readiness': readiness,
            'last_blocked': planning.get('last_blocked'),
            'field_specs': get_planning_profile_field_specs(),
            'fill_template': build_planning_fill_template(),
            'outline_file': '大纲/总纲.md',
            'saved': True,
        }

    def _llm_settings_payload(project_root_value: Path) -> dict[str, Any]:
        env = _project_env_or_os(project_root_value)
        api_key = (env.get('WEBNOVEL_LLM_API_KEY') or env.get('OPENAI_API_KEY') or '').strip()
        provider = (env.get('WEBNOVEL_LLM_PROVIDER') or 'openai-compatible').strip() or 'openai-compatible'
        return {
            'provider': provider,
            'base_url': (env.get('WEBNOVEL_LLM_BASE_URL') or env.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1').strip(),
            'model': (env.get('WEBNOVEL_LLM_MODEL') or env.get('OPENAI_MODEL') or '').strip(),
            'has_api_key': bool(api_key),
            'api_key_masked': _mask_secret(api_key),
        }

    def _rag_settings_payload(project_root_value: Path) -> dict[str, Any]:
        env = _project_env_or_os(project_root_value)
        api_key = (env.get('WEBNOVEL_RAG_API_KEY') or '').strip()
        return {
            'base_url': (env.get('WEBNOVEL_RAG_BASE_URL') or 'https://api.siliconflow.cn/v1').strip(),
            'embed_model': (env.get('WEBNOVEL_RAG_EMBED_MODEL') or 'BAAI/bge-m3').strip(),
            'rerank_model': (env.get('WEBNOVEL_RAG_RERANK_MODEL') or 'BAAI/bge-reranker-v2-m3').strip(),
            'has_api_key': bool(api_key),
            'api_key_masked': _mask_secret(api_key),
        }

    def _refresh_runtime_settings(project_root_value: Path, updates: dict[str, str]) -> None:
        for key, value in updates.items():
            os.environ[key] = value
        _get_orchestrator_for_root(project_root_value, refresh=True)

    def _fetchall_safe(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
        """
        安全执行数据库查询并返回所有结果
        
        执行 SQL 查询并将结果转换为字典列表。对于表不存在的情况返回空列表，
        其他数据库错误向上抛出由异常处理器统一处理。
        
        Args:
            conn: 数据库连接对象
            query: SQL 查询语句
            params: 查询参数元组
            
        Returns:
            list[dict]: 查询结果字典列表
            
        Raises:
            sqlite3.Error: 数据库操作错误（表不存在除外）
        """
        try:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError as exc:
            if 'no such table' in str(exc).lower():
                logger.warning('数据库表不存在，返回空列表: %s', exc)
                return []
            raise

    def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
        columns: set[str] = set()
        for row in rows:
            if isinstance(row, sqlite3.Row):
                column_name = row['name']
            else:
                column_name = row[1]
            if column_name:
                columns.add(str(column_name))
        return columns

    def _build_narrative_entity_clause(columns: set[str], entity: str) -> tuple[Optional[str], list[Any]]:
        entity_columns = [
            column
            for column in (
                'entity_id',
                'owner_entity',
                'character_id',
                'holder_entity_id',
                'subject_entity_id',
                'observer_entity_id',
                'knower_entity_id',
                'source_entity_id',
                'target_entity_id',
                'related_entity_id',
                'from_entity',
                'to_entity',
            )
            if column in columns
        ]
        like_columns = [column for column in ('participants', 'participants_json') if column in columns]
        if not entity_columns:
            if not like_columns:
                return None, []
            clause = '(' + ' OR '.join(f'{column} LIKE ?' for column in like_columns) + ')'
            return clause, [f'%{entity}%'] * len(like_columns)
        equality_clause = [f'{column} = ?' for column in entity_columns]
        like_clause = [f'{column} LIKE ?' for column in like_columns]
        clause = '(' + ' OR '.join([*equality_clause, *like_clause]) + ')'
        return clause, [entity] * len(entity_columns) + [f'%{entity}%'] * len(like_columns)

    def _build_scalar_chapter_clause(
        columns: set[str],
        chapter: int,
        *,
        exact: tuple[str, ...] = (),
        before_or_equal: tuple[str, ...] = (),
        after_or_equal: tuple[str, ...] = (),
    ) -> tuple[Optional[str], list[Any]]:
        for column in exact:
            if column in columns:
                return f'{column} = ?', [chapter]
        for column in before_or_equal:
            if column in columns:
                return f'{column} <= ?', [chapter]
        for column in after_or_equal:
            if column in columns:
                return f'{column} >= ?', [chapter]
        return None, []

    def _build_foreshadowing_chapter_clause(columns: set[str], chapter: int) -> tuple[Optional[str], list[Any]]:
        if 'introduced_chapter' in columns and 'payoff_chapter' in columns:
            return '(introduced_chapter <= ? AND (payoff_chapter IS NULL OR payoff_chapter >= ?))', [chapter, chapter]
        if 'introduced_chapter' in columns and 'resolved_chapter' in columns:
            return '(introduced_chapter <= ? AND (resolved_chapter IS NULL OR resolved_chapter >= ?))', [chapter, chapter]
        if 'planted_chapter' in columns and 'payoff_chapter' in columns:
            return '(planted_chapter <= ? AND (payoff_chapter IS NULL OR payoff_chapter = 0 OR payoff_chapter >= ?))', [chapter, chapter]
        if 'planted_chapter' in columns and 'resolved_chapter' in columns:
            return '(planted_chapter <= ? AND (resolved_chapter IS NULL OR resolved_chapter = 0 OR resolved_chapter >= ?))', [chapter, chapter]
        return _build_scalar_chapter_clause(
            columns,
            chapter,
            exact=('chapter',),
            before_or_equal=('introduced_chapter', 'planted_chapter', 'start_chapter'),
            after_or_equal=('payoff_chapter', 'resolved_chapter'),
        )

    def _build_timeline_chapter_clause(columns: set[str], chapter: int) -> tuple[Optional[str], list[Any]]:
        return _build_scalar_chapter_clause(
            columns,
            chapter,
            exact=('chapter', 'event_chapter', 'occurred_chapter'),
            before_or_equal=('start_chapter',),
        )

    def _build_character_arc_chapter_clause(columns: set[str], chapter: int) -> tuple[Optional[str], list[Any]]:
        if 'chapter' in columns:
            return 'chapter = ?', [chapter]
        if 'start_chapter' in columns and 'end_chapter' in columns:
            return '(start_chapter <= ? AND (end_chapter IS NULL OR end_chapter >= ?))', [chapter, chapter]
        return _build_scalar_chapter_clause(
            columns,
            chapter,
            before_or_equal=('start_chapter',),
            after_or_equal=('end_chapter',),
        )

    def _build_knowledge_state_chapter_clause(columns: set[str], chapter: int) -> tuple[Optional[str], list[Any]]:
        return _build_scalar_chapter_clause(
            columns,
            chapter,
            exact=('chapter', 'known_chapter', 'discovered_chapter'),
            before_or_equal=('updated_chapter',),
        )

    def _list_narrative_rows(
        conn: sqlite3.Connection,
        *,
        table_name: str,
        chapter: Optional[int],
        entity: Optional[str],
        limit: int,
        chapter_clause_builder: Callable[[set[str], int], tuple[Optional[str], list[Any]]],
        order_columns: tuple[str, ...],
    ) -> list[dict]:
        columns = _table_columns(conn, table_name)
        if not columns:
            return []

        clauses: list[str] = []
        params: list[Any] = []

        if chapter is not None:
            chapter_clause, chapter_params = chapter_clause_builder(columns, chapter)
            if chapter_clause:
                clauses.append(chapter_clause)
                params.extend(chapter_params)

        if entity:
            entity_clause, entity_params = _build_narrative_entity_clause(columns, entity)
            if entity_clause:
                clauses.append(entity_clause)
                params.extend(entity_params)

        query = f'SELECT * FROM {table_name}'
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)

        order_terms = [f'{column} DESC' for column in order_columns if column in columns]
        if 'id' in columns and 'id DESC' not in order_terms:
            order_terms.append('id DESC')
        if order_terms:
            query += ' ORDER BY ' + ', '.join(order_terms)

        query += ' LIMIT ?'
        params.append(limit)
        rows = _fetchall_safe(conn, query, tuple(params))
        normalized: list[dict] = []
        for row in rows:
            item = dict(row)
            for field in ('participants', 'participants_json', 'relationship_state_json'):
                raw = item.get(field)
                if not raw:
                    continue
                try:
                    item[field] = json.loads(raw)
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            if 'objective_fact' in item:
                item['objective_fact'] = bool(item.get('objective_fact'))
            normalized.append(item)
        return normalized

    @app.get('/api/project/info')
    def project_info(request: Request):
        project_root_value = _resolve_request_project_root(request)
        _ensure_project_watch(project_root_value)
        payload = _read_state_data(project_root_value)
        if isinstance(payload, dict):
            project_info_payload = dict(payload.get('project_info') or {})
            dashboard_context = dict(payload.get('dashboard_context') or {})
            dashboard_context.update(
                {
                    'project_root': str(project_root_value),
                    'project_initialized': True,
                    'title': str(project_info_payload.get('title') or payload.get('project_name') or '').strip(),
                    'genre': str(project_info_payload.get('genre') or '').strip(),
                }
            )
            payload = dict(payload)
            payload['dashboard_context'] = dashboard_context
        return payload

    @app.get('/api/project/planning-profile')
    def get_planning_profile(request: Request):
        project_root_value = _resolve_request_project_root(request)
        state_data = _read_state_data(project_root_value)
        return _planning_profile_payload(state_data, project_root_value)

    @app.post('/api/project/planning-profile')
    async def save_planning_profile(http_request: Request, request: PlanningProfileRequest):
        project_root_value = _resolve_request_project_root(http_request)
        state_data = _read_state_data(project_root_value)
        payload = _sync_planning_profile(state_data, request.model_dump(), project_root_value)
        _write_state_data(state_data, project_root_value)
        return payload

    @app.post('/api/project/bootstrap')
    async def bootstrap_project(http_request: Request, request: BootstrapProjectRequest):
        target_root = Path(request.project_root or _get_project_root()).resolve()
        state_path = target_root / '.webnovel' / 'state.json'
        if state_path.is_file():
            raise HTTPException(409, '项目已初始化，不能重复创建。')

        target_root.mkdir(parents=True, exist_ok=True)
        title = (request.title or target_root.name or 'My Novel').strip() or 'My Novel'
        genre = (request.genre or '\u7384\u5e7b').strip() or '\u7384\u5e7b'
        script_path = Path(__file__).resolve().parent.parent / 'scripts' / 'init_project.py'
        completed = await asyncio.to_thread(
            run,
            [sys.executable, str(script_path), str(target_root), title, genre],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False,
        )
        if completed.returncode != 0:
            raise APIError(500, 'PROJECT_BOOTSTRAP_FAILED', '项目初始化失败。', {
                'return_code': completed.returncode,
                'stdout': completed.stdout,
                'stderr': completed.stderr,
                'original_message': 'Project bootstrap failed',
            })
        if not state_path.is_file():
            raise APIError(500, 'PROJECT_BOOTSTRAP_INCOMPLETE', '项目初始化未完成，未生成 state.json。', {
                'stdout': completed.stdout,
                'stderr': completed.stderr,
                'original_message': 'Project bootstrap did not create state.json',
            })
        _ensure_project_watch(target_root)
        current_root = _resolve_request_project_root(http_request)
        return {
            'created': True,
            'project_root': str(target_root),
            'title': title,
            'genre': genre,
            'state_file': str(state_path),
            'project_switch_required': str(target_root) != str(current_root),
            'suggested_dashboard_url': f"/?project_root={quote(str(target_root))}",
        }

    @app.get('/api/llm/status')
    def llm_status(request: Request):
        return _get_request_orchestrator(request).probe_llm()

    @app.get('/api/codex/status')
    def codex_status(request: Request):
        return _get_request_orchestrator(request).probe_llm()

    @app.get('/api/rag/status')
    def rag_status(request: Request):
        return _get_request_orchestrator(request).probe_rag()

    @app.get('/api/settings/llm')
    def llm_settings(request: Request):
        project_root_value = _resolve_request_project_root(request)
        return _llm_settings_payload(project_root_value)

    @app.post('/api/settings/llm')
    async def save_llm_settings(http_request: Request, request: LLMSettingsRequest):
        project_root_value = _resolve_request_project_root(http_request)
        current = _project_env_or_os(project_root_value)
        provider = (request.provider or 'openai-compatible').strip() or 'openai-compatible'
        base_url = (request.base_url or current.get('WEBNOVEL_LLM_BASE_URL') or current.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1').strip()
        model = (request.model or current.get('WEBNOVEL_LLM_MODEL') or current.get('OPENAI_MODEL') or '').strip()
        api_key = (request.api_key or current.get('WEBNOVEL_LLM_API_KEY') or current.get('OPENAI_API_KEY') or '').strip()

        if not model:
            raise HTTPException(400, '\u5199\u4f5c\u6a21\u578b\u4e0d\u80fd\u4e3a\u7a7a\u3002')
        if not api_key:
            raise HTTPException(400, '\u5199\u4f5c\u6a21\u578b API Key \u4e0d\u80fd\u4e3a\u7a7a\u3002')

        updates = {
            'WEBNOVEL_LLM_PROVIDER': provider,
            'WEBNOVEL_LLM_BASE_URL': base_url,
            'WEBNOVEL_LLM_MODEL': model,
            'WEBNOVEL_LLM_API_KEY': api_key,
        }
        _write_env_updates(_project_env_path(project_root_value), updates)
        _refresh_runtime_settings(project_root_value, updates)
        return {
            'saved': True,
            'settings': _llm_settings_payload(project_root_value),
            'status': _get_orchestrator_for_root(project_root_value).probe_llm(),
        }

    @app.get('/api/settings/rag')
    def rag_settings(request: Request):
        project_root_value = _resolve_request_project_root(request)
        return _rag_settings_payload(project_root_value)

    @app.post('/api/settings/rag')
    async def save_rag_settings(http_request: Request, request: RAGSettingsRequest):
        project_root_value = _resolve_request_project_root(http_request)
        current = _project_env_or_os(project_root_value)
        base_url = (request.base_url or current.get('WEBNOVEL_RAG_BASE_URL') or 'https://api.siliconflow.cn/v1').strip()
        embed_model = (request.embed_model or current.get('WEBNOVEL_RAG_EMBED_MODEL') or '').strip()
        rerank_model = (request.rerank_model or current.get('WEBNOVEL_RAG_RERANK_MODEL') or '').strip()
        api_key = (request.api_key or current.get('WEBNOVEL_RAG_API_KEY') or '').strip()

        if not embed_model:
            raise HTTPException(400, 'Embedding \u6a21\u578b\u4e0d\u80fd\u4e3a\u7a7a\u3002')
        if not rerank_model:
            raise HTTPException(400, 'Rerank \u6a21\u578b\u4e0d\u80fd\u4e3a\u7a7a\u3002')
        if not api_key:
            raise HTTPException(400, 'RAG API Key \u4e0d\u80fd\u4e3a\u7a7a\u3002')

        updates = {
            'WEBNOVEL_RAG_BASE_URL': base_url,
            'WEBNOVEL_RAG_EMBED_MODEL': embed_model,
            'WEBNOVEL_RAG_RERANK_MODEL': rerank_model,
            'WEBNOVEL_RAG_API_KEY': api_key,
        }
        _write_env_updates(_project_env_path(project_root_value), updates)
        _refresh_runtime_settings(project_root_value, updates)
        return {
            'saved': True,
            'settings': _rag_settings_payload(project_root_value),
            'status': _get_orchestrator_for_root(project_root_value).probe_rag(),
        }

    @app.get('/api/tasks')
    def list_tasks(request: Request, limit: int = 50):
        return _get_request_orchestrator(request).list_tasks(limit=limit)

    def _create_task(task_type: str, request: TaskRequest, http_request: Request):
        project_root_value = request.project_root or str(_resolve_request_project_root(http_request))
        payload = request.model_dump() if hasattr(request, 'model_dump') else request.dict()
        payload['project_root'] = project_root_value
        return _get_request_orchestrator(explicit_root=project_root_value).create_task(task_type, payload)

    @app.post('/api/tasks/init')
    async def create_init_task(http_request: Request, request: TaskRequest):
        return _create_task('init', request, http_request)

    @app.post('/api/tasks/plan')
    async def create_plan_task(http_request: Request, request: TaskRequest):
        return _create_task('plan', request, http_request)

    @app.post('/api/tasks/write')
    async def create_write_task(http_request: Request, request: TaskRequest):
        return _create_task('write', request, http_request)

    @app.post('/api/tasks/guarded-write')
    async def create_guarded_write_task(http_request: Request, request: TaskRequest):
        return _create_task('guarded-write', request, http_request)

    @app.post('/api/tasks/guarded-batch-write')
    async def create_guarded_batch_write_task(http_request: Request, request: TaskRequest):
        return _create_task('guarded-batch-write', request, http_request)

    @app.post('/api/tasks/review')
    async def create_review_task(http_request: Request, request: TaskRequest):
        return _create_task('review', request, http_request)

    @app.post('/api/tasks/resume')
    async def create_resume_task(http_request: Request, request: TaskRequest):
        return _create_task('resume', request, http_request)

    @app.get('/api/supervisor/recommendations')
    def list_supervisor_recommendations(request: Request, limit: int = 4, include_dismissed: bool = False):
        orchestrator = _get_request_orchestrator(request)
        if include_dismissed:
            return orchestrator.list_supervisor_recommendations(limit=limit, include_dismissed=True)
        return orchestrator.list_supervisor_recommendations(limit=limit)

    @app.post('/api/supervisor/dismiss')
    async def dismiss_supervisor_recommendation(http_request: Request, request: SupervisorDismissRequest):
        return _get_request_orchestrator(http_request).dismiss_supervisor_recommendation(
            request.stable_key,
            request.fingerprint,
            reason=request.reason,
            note=request.note,
        )

    @app.post('/api/supervisor/dismiss-batch')
    async def dismiss_supervisor_recommendations_batch(http_request: Request, request: SupervisorBatchDismissRequest):
        return _get_request_orchestrator(http_request).dismiss_supervisor_recommendations_batch(
            [{"stable_key": item.stable_key, "fingerprint": item.fingerprint} for item in request.items],
            reason=request.reason,
            note=request.note,
        )

    @app.post('/api/supervisor/undismiss')
    async def undismiss_supervisor_recommendation(http_request: Request, request: SupervisorDismissRequest):
        return _get_request_orchestrator(http_request).undismiss_supervisor_recommendation(request.stable_key)

    @app.post('/api/supervisor/undismiss-batch')
    async def undismiss_supervisor_recommendations_batch(http_request: Request, request: SupervisorBatchUndismissRequest):
        return _get_request_orchestrator(http_request).undismiss_supervisor_recommendations_batch(request.stable_keys)

    @app.post('/api/supervisor/tracking')
    async def set_supervisor_tracking(http_request: Request, request: SupervisorTrackingRequest):
        payload = {
            "status": request.status,
            "note": request.note,
        }
        if request.linked_task_id:
            payload["linked_task_id"] = request.linked_task_id
        if request.linked_checklist_path:
            payload["linked_checklist_path"] = request.linked_checklist_path
        return _get_request_orchestrator(http_request).set_supervisor_recommendation_tracking(
            request.stable_key,
            request.fingerprint,
            **payload,
        )

    @app.post('/api/supervisor/tracking/clear')
    async def clear_supervisor_tracking(http_request: Request, request: SupervisorTrackingRequest):
        return _get_request_orchestrator(http_request).clear_supervisor_recommendation_tracking(request.stable_key)

    @app.post('/api/supervisor/checklists')
    async def save_supervisor_checklist(http_request: Request, request: SupervisorChecklistSaveRequest):
        return _get_request_orchestrator(http_request).save_supervisor_checklist(
            request.content,
            chapter=request.chapter,
            selected_keys=request.selected_keys,
            category_filter=request.category_filter,
            sort_mode=request.sort_mode,
            title=request.title,
            note=request.note,
        )

    @app.get('/api/supervisor/checklists')
    def list_supervisor_checklists(request: Request, limit: int = 10):
        return _get_request_orchestrator(request).list_supervisor_checklists(limit=limit)

    @app.get('/api/supervisor/audit-repair-reports')
    def list_supervisor_audit_repair_reports(request: Request, limit: int = 10):
        return _get_request_orchestrator(request).list_supervisor_audit_repair_reports(limit=limit)

    @app.get('/api/supervisor/audit-log')
    def list_supervisor_audit_log(request: Request, limit: int = 200):
        return _get_request_orchestrator(request).list_supervisor_audit_log(limit=limit)

    @app.get('/api/supervisor/audit-health')
    def get_supervisor_audit_health(request: Request, issue_limit: int = 20):
        return _get_request_orchestrator(request).get_supervisor_audit_health(issue_limit=issue_limit)

    @app.get('/api/supervisor/audit-repair-preview')
    def get_supervisor_audit_repair_preview(request: Request, proposal_limit: int = 20):
        return _get_request_orchestrator(request).get_supervisor_audit_repair_preview(proposal_limit=proposal_limit)

    @app.get('/api/tasks/{task_id}')
    def get_task(task_id: str, request: Request):
        task = _get_request_orchestrator(request).get_task(task_id)
        if not task:
            raise HTTPException(404, '未找到任务。')
        return task

    @app.get('/api/tasks/{task_id}/events')
    def get_task_events(task_id: str, request: Request, limit: int = 200):
        return _get_request_orchestrator(request).get_events(task_id, limit=limit)

    @app.post('/api/tasks/{task_id}/retry')
    async def retry_task(task_id: str, http_request: Request, request: RetryRequest | None = None):
        try:
            return _get_request_orchestrator(http_request).retry_task(task_id, resume_from_step=request.resume_from_step if request else None)
        except KeyError as exc:
            raise HTTPException(404, '未找到任务。') from exc

    @app.post('/api/tasks/{task_id}/cancel')
    async def cancel_task(task_id: str, http_request: Request, request: CancelTaskRequest | None = None):
        try:
            return _get_request_orchestrator(http_request).cancel_task(task_id, reason=request.reason if request else '')
        except KeyError as exc:
            raise HTTPException(404, '未找到任务。') from exc

    @app.post('/api/review/approve')
    async def approve_review(http_request: Request, request: ReviewDecisionRequest):
        try:
            return _get_request_orchestrator(http_request).approve_writeback(request.task_id, request.reason)
        except KeyError as exc:
            raise HTTPException(404, '未找到任务。') from exc

    @app.post('/api/review/reject')
    async def reject_review(http_request: Request, request: ReviewDecisionRequest):
        try:
            return _get_request_orchestrator(http_request).reject_writeback(request.task_id, request.reason)
        except KeyError as exc:
            raise HTTPException(404, '未找到任务。') from exc

    @app.post('/api/review/confirm-invalid-facts')
    async def confirm_invalid_facts(http_request: Request, request: InvalidFactDecisionRequest):
        return _get_request_orchestrator(http_request).confirm_invalid_facts(request.ids, request.action)

    @app.get('/api/entities')
    def list_entities(request: Request, entity_type: Optional[str] = Query(None, alias='type'), include_archived: bool = False):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            q = 'SELECT * FROM entities'
            params: list = []
            clauses: list[str] = []
            if entity_type:
                clauses.append('type = ?')
                params.append(entity_type)
            if not include_archived:
                clauses.append('is_archived = 0')
            if clauses:
                q += ' WHERE ' + ' AND '.join(clauses)
            q += ' ORDER BY last_appearance DESC'
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    @app.get('/api/entities/{entity_id}')
    def get_entity(entity_id: str, request: Request):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            row = conn.execute('SELECT * FROM entities WHERE id = ?', (entity_id,)).fetchone()
            if not row:
                raise HTTPException(404, '未找到实体。')
            return dict(row)

    @app.get('/api/relationships')
    def list_relationships(request: Request, entity: Optional[str] = None, limit: int = 200):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            has_alias_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'aliases'"
            ).fetchone() is not None
            alias_join_sql = (
                'LEFT JOIN (SELECT entity_id, MIN(alias) AS alias FROM aliases GROUP BY entity_id) fa ON fa.entity_id = r.from_entity '
                'LEFT JOIN (SELECT entity_id, MIN(alias) AS alias FROM aliases GROUP BY entity_id) ta ON ta.entity_id = r.to_entity'
            ) if has_alias_table else ''
            base_query = (
                'SELECT r.*, '
                'COALESCE(fe.canonical_name, r.from_entity) AS from_entity_name, '
                'COALESCE(te.canonical_name, r.to_entity) AS to_entity_name, '
                f"{'fa.alias AS from_entity_alias, ta.alias AS to_entity_alias ' if has_alias_table else 'NULL AS from_entity_alias, NULL AS to_entity_alias '}"
                'FROM relationships r '
                'LEFT JOIN entities fe ON fe.id = r.from_entity '
                'LEFT JOIN entities te ON te.id = r.to_entity '
                f'{alias_join_sql}'
            )
            if entity:
                rows = conn.execute(
                    f'{base_query} WHERE r.from_entity = ? OR r.to_entity = ? ORDER BY r.chapter DESC LIMIT ?',
                    (entity, entity, limit),
                ).fetchall()
            else:
                rows = conn.execute(f'{base_query} ORDER BY r.chapter DESC LIMIT ?', (limit,)).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item['from_entity_display'] = _resolve_relationship_entity_display(
                    canonical_name=item.get('from_entity_name'),
                    alias=item.get('from_entity_alias'),
                    raw_id=item.get('from_entity'),
                )
                item['to_entity_display'] = _resolve_relationship_entity_display(
                    canonical_name=item.get('to_entity_name'),
                    alias=item.get('to_entity_alias'),
                    raw_id=item.get('to_entity'),
                )
                item['type_label'] = _translate_relationship_type(item.get('type'))
                item['from_entity_label'] = '起始实体'
                item['to_entity_label'] = '目标实体'
                item['type_label_label'] = '关系类型'
                items.append(item)
            return items

    @app.get('/api/relationship-events')
    def list_relationship_events(request: Request, entity: Optional[str] = None, from_chapter: Optional[int] = None, to_chapter: Optional[int] = None, limit: int = 200):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            q = 'SELECT * FROM relationship_events'
            params: list = []
            clauses: list[str] = []
            if entity:
                clauses.append('(from_entity = ? OR to_entity = ?)')
                params.extend([entity, entity])
            if from_chapter is not None:
                clauses.append('chapter >= ?')
                params.append(from_chapter)
            if to_chapter is not None:
                clauses.append('chapter <= ?')
                params.append(to_chapter)
            if clauses:
                q += ' WHERE ' + ' AND '.join(clauses)
            q += ' ORDER BY chapter DESC, id DESC LIMIT ?'
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
            return [dict(r) for r in rows]

    @app.get('/api/chapters')
    def list_chapters(request: Request):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            rows = conn.execute('SELECT * FROM chapters ORDER BY chapter ASC').fetchall()
            return [dict(r) for r in rows]

    @app.get('/api/scenes')
    def list_scenes(request: Request, chapter: Optional[int] = None, limit: int = 500):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            if chapter is not None:
                rows = conn.execute('SELECT * FROM scenes WHERE chapter = ? ORDER BY scene_index ASC', (chapter,)).fetchall()
            else:
                rows = conn.execute('SELECT * FROM scenes ORDER BY chapter ASC, scene_index ASC LIMIT ?', (limit,)).fetchall()
            return [dict(r) for r in rows]

    @app.get('/api/reading-power')
    def list_reading_power(request: Request, limit: int = 50):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            rows = conn.execute('SELECT * FROM chapter_reading_power ORDER BY chapter DESC LIMIT ?', (limit,)).fetchall()
            return [dict(r) for r in rows]

    @app.get('/api/review-metrics')
    def list_review_metrics(request: Request, limit: int = 20):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            rows = conn.execute('SELECT * FROM review_metrics ORDER BY end_chapter DESC LIMIT ?', (limit,)).fetchall()
            return [_with_display_timestamps(dict(r), fields=('created_at',)) for r in rows]

    @app.get('/api/state-changes')
    def list_state_changes(request: Request, entity: Optional[str] = None, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            if entity:
                rows = conn.execute('SELECT * FROM state_changes WHERE entity_id = ? ORDER BY chapter DESC LIMIT ?', (entity, limit)).fetchall()
            else:
                rows = conn.execute('SELECT * FROM state_changes ORDER BY chapter DESC LIMIT ?', (limit,)).fetchall()
            return [dict(r) for r in rows]

    @app.get('/api/aliases')
    def list_aliases(request: Request, entity: Optional[str] = None):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            if entity:
                rows = conn.execute('SELECT * FROM aliases WHERE entity_id = ?', (entity,)).fetchall()
            else:
                rows = conn.execute('SELECT * FROM aliases').fetchall()
            return [dict(r) for r in rows]

    @app.get('/api/overrides')
    def list_overrides(request: Request, status: Optional[str] = None, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            if status:
                return _fetchall_safe(conn, 'SELECT * FROM override_contracts WHERE status = ? ORDER BY chapter DESC LIMIT ?', (status, limit))
            return _fetchall_safe(conn, 'SELECT * FROM override_contracts ORDER BY chapter DESC LIMIT ?', (limit,))

    @app.get('/api/debts')
    def list_debts(request: Request, status: Optional[str] = None, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            if status:
                return _fetchall_safe(conn, 'SELECT * FROM chase_debt WHERE status = ? ORDER BY updated_at DESC LIMIT ?', (status, limit))
            return _fetchall_safe(conn, 'SELECT * FROM chase_debt ORDER BY updated_at DESC LIMIT ?', (limit,))

    @app.get('/api/debt-events')
    def list_debt_events(request: Request, debt_id: Optional[int] = None, limit: int = 200):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            if debt_id is not None:
                return _fetchall_safe(conn, 'SELECT * FROM debt_events WHERE debt_id = ? ORDER BY chapter DESC, id DESC LIMIT ?', (debt_id, limit))
            return _fetchall_safe(conn, 'SELECT * FROM debt_events ORDER BY chapter DESC, id DESC LIMIT ?', (limit,))

    @app.get('/api/invalid-facts')
    def list_invalid_facts(request: Request, status: Optional[str] = None, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            if status:
                return _fetchall_safe(conn, 'SELECT * FROM invalid_facts WHERE status = ? ORDER BY marked_at DESC LIMIT ?', (status, limit))
            return _fetchall_safe(conn, 'SELECT * FROM invalid_facts ORDER BY marked_at DESC LIMIT ?', (limit,))

    @app.get('/api/rag-queries')
    def list_rag_queries(request: Request, query_type: Optional[str] = None, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            if query_type:
                rows = _fetchall_safe(conn, 'SELECT * FROM rag_query_log WHERE query_type = ? ORDER BY created_at DESC LIMIT ?', (query_type, limit))
            else:
                rows = _fetchall_safe(conn, 'SELECT * FROM rag_query_log ORDER BY created_at DESC LIMIT ?', (limit,))
            return [_with_display_timestamps(dict(r), fields=('created_at',)) for r in rows]

    @app.get('/api/tool-stats')
    def list_tool_stats(request: Request, tool_name: Optional[str] = None, limit: int = 200):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            if tool_name:
                rows = _fetchall_safe(conn, 'SELECT * FROM tool_call_stats WHERE tool_name = ? ORDER BY created_at DESC LIMIT ?', (tool_name, limit))
            else:
                rows = _fetchall_safe(conn, 'SELECT * FROM tool_call_stats ORDER BY created_at DESC LIMIT ?', (limit,))
            return [_with_display_timestamps(dict(r), fields=('created_at',)) for r in rows]

    @app.get('/api/checklist-scores')
    def list_checklist_scores(request: Request, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            return _fetchall_safe(conn, 'SELECT * FROM writing_checklist_scores ORDER BY chapter DESC LIMIT ?', (limit,))

    @app.get('/api/story-plans')
    def list_story_plans(request: Request, limit: int = 20):
        project_root_value = _resolve_request_project_root(request)
        return _list_story_plans(project_root_value, limit=limit)

    @app.get('/api/foreshadowing')
    def list_foreshadowing(request: Request, chapter: Optional[int] = None, entity: Optional[str] = None, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            return _list_narrative_rows(
                conn,
                table_name='foreshadowing_items',
                chapter=chapter,
                entity=entity,
                limit=limit,
                chapter_clause_builder=_build_foreshadowing_chapter_clause,
                order_columns=('introduced_chapter', 'planted_chapter', 'chapter', 'updated_at', 'created_at'),
            )

    @app.get('/api/timeline-events')
    def list_timeline_events(request: Request, chapter: Optional[int] = None, entity: Optional[str] = None, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            return _list_narrative_rows(
                conn,
                table_name='timeline_events',
                chapter=chapter,
                entity=entity,
                limit=limit,
                chapter_clause_builder=_build_timeline_chapter_clause,
                order_columns=('chapter', 'event_chapter', 'occurred_chapter', 'updated_at', 'created_at'),
            )

    @app.get('/api/character-arcs')
    def list_character_arcs(request: Request, chapter: Optional[int] = None, entity: Optional[str] = None, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            return _list_narrative_rows(
                conn,
                table_name='character_arcs',
                chapter=chapter,
                entity=entity,
                limit=limit,
                chapter_clause_builder=_build_character_arc_chapter_clause,
                order_columns=('chapter', 'start_chapter', 'updated_at', 'created_at'),
            )

    @app.get('/api/knowledge-states')
    def list_knowledge_states(request: Request, chapter: Optional[int] = None, entity: Optional[str] = None, limit: int = 100):
        with closing(_get_db(_resolve_request_project_root(request))) as conn:
            return _list_narrative_rows(
                conn,
                table_name='knowledge_states',
                chapter=chapter,
                entity=entity,
                limit=limit,
                chapter_clause_builder=_build_knowledge_state_chapter_clause,
                order_columns=('chapter', 'known_chapter', 'discovered_chapter', 'updated_at', 'created_at'),
            )

    @app.get('/api/files/tree')
    def file_tree(request: Request):
        root = _resolve_request_project_root(request)
        _get_request_orchestrator(request)
        result = {}
        for folder_name in FILE_TREE_FOLDERS:
            folder = root / folder_name
            if not folder.is_dir():
                result[folder_name] = []
                continue
            result[folder_name] = _walk_tree(folder, root)
        result[PROJECT_STATE_SECTION] = _build_project_state_tree(root)
        return result

    @app.get('/api/files/read')
    def file_read(request: Request, path: str):
        root = _resolve_request_project_root(request)
        _get_request_orchestrator(request)
        resolved = safe_resolve(root, path)
        allowed_parents = [root / name for name in FILE_TREE_FOLDERS]
        allow_state_file = resolved == (root / PROJECT_STATE_FILE_PATH).resolve()
        allow_summary_file = _is_child(resolved, (root / PROJECT_STATE_SUMMARIES_PATH))
        if not any(_is_child(resolved, parent) for parent in allowed_parents) and not allow_state_file and not allow_summary_file:
            raise HTTPException(403, '只能读取正文、大纲、设定集、项目状态下的文件。')
        if not resolved.is_file():
            raise HTTPException(404, '未找到文件。')
        encoding = 'utf-8'
        is_binary = False
        try:
            content = resolved.read_text(encoding=encoding)
        except UnicodeDecodeError:
            content = ''
            is_binary = True
            encoding = 'binary'
        stat = resolved.stat()
        return {
            'path': path,
            'content': content,
            'exists': True,
            'is_binary': is_binary,
            'encoding': encoding,
            'size': stat.st_size,
            'modified_at': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            'modified_at_display': _format_display_datetime(datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()),
            'display_name': _display_name_for_path(path),
            'file_type': _file_type_for_path(path),
            'is_internal': allow_state_file or allow_summary_file,
            'doc_status': _detect_doc_status(path, content),
            'summary_card': _build_file_summary_card(root, path, content),
            'internal_hint': '内部状态 / 机器可读 / 不建议直接编辑' if (allow_state_file or allow_summary_file) else None,
        }

    @app.get('/api/events')
    async def sse(request: Request):
        _ensure_project_watch(_resolve_request_project_root(request))
        q = _watcher.subscribe()

        async def _gen():
            try:
                while True:
                    msg = await q.get()
                    yield f'data: {msg}\n\n'
            except asyncio.CancelledError:
                pass
            finally:
                _watcher.unsubscribe(q)

        return StreamingResponse(_gen(), media_type='text/event-stream')

    if STATIC_DIR.is_dir():
        assets_dir = STATIC_DIR / 'assets'
        if assets_dir.is_dir():
            app.mount('/assets', StaticFiles(directory=str(assets_dir)), name='assets')

        @app.get('/{full_path:path}')
        def serve_spa(full_path: str):
            index = STATIC_DIR / 'index.html'
            if index.is_file():
                return FileResponse(str(index))
            raise HTTPException(404, '未找到前端构建产物。')

    else:
        @app.get('/')
        def no_frontend():
            return HTMLResponse(
                '<h2>网文管理面板 API 正在运行</h2>'
                '<p>前端资源缺失，请先构建 dashboard/frontend 后重试。</p>'
                '<p>API 文档：<a href="/docs">/docs</a></p>'
            )

    return app


def _walk_tree(folder: Path, root: Path) -> list[dict]:
    items = []
    for child in sorted(folder.iterdir()):
        rel = str(child.relative_to(root)).replace('\\', '/')
        is_internal = rel == PROJECT_STATE_FILE_PATH or rel.startswith(f'{PROJECT_STATE_SUMMARIES_PATH}/')
        if child.is_dir():
            items.append(
                {
                    'name': child.name,
                    'type': 'dir',
                    'path': rel,
                    'display_name': _display_name_for_path(rel),
                    'file_type': _file_type_for_path(rel),
                    'is_internal': is_internal,
                    'doc_status': None,
                    'children': _walk_tree(child, root),
                }
            )
        else:
            content = _read_text_preview(child)
            items.append(
                {
                    'name': child.name,
                    'type': 'file',
                    'path': rel,
                    'size': child.stat().st_size,
                    'display_name': _display_name_for_path(rel),
                    'file_type': _file_type_for_path(rel),
                    'is_internal': is_internal,
                    'doc_status': _detect_doc_status(rel, content),
                }
            )
    return items


def _build_project_state_tree(root: Path) -> list[dict]:
    items: list[dict] = []
    state_file = root / PROJECT_STATE_FILE_PATH
    if state_file.is_file():
        items.append(
            {
                'name': state_file.name,
                'type': 'file',
                'path': PROJECT_STATE_FILE_PATH,
                'size': state_file.stat().st_size,
                'display_name': 'state.json（内部状态）',
                'file_type': '内部状态文件',
                'is_internal': True,
                'doc_status': '内部状态',
            }
        )
    summaries_dir = root / PROJECT_STATE_SUMMARIES_PATH
    if summaries_dir.is_dir():
        items.append(
            {
                'name': '章节摘要',
                'type': 'dir',
                'path': PROJECT_STATE_SUMMARIES_PATH,
                'display_name': '章节摘要',
                'file_type': '摘要目录',
                'is_internal': True,
                'doc_status': None,
                'children': _walk_tree(summaries_dir, root),
            }
        )
    return items


def _read_text_preview(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return ''


def _display_name_for_path(path: str) -> str:
    normalized = str(path or '').replace('\\', '/').strip('/')
    name = normalized.split('/')[-1] if normalized else ''
    chapter_in_volume_match = normalized and re.match(r'^正文/第(\d+)卷/第(\d{4})章\.md$', normalized)
    volume_match = name and re.match(r'^第(\d+)卷$', name)
    if normalized == PROJECT_STATE_FILE_PATH:
        return 'state.json（内部状态）'
    if normalized == PROJECT_STATE_SUMMARIES_PATH:
        return '章节摘要'
    if chapter_in_volume_match:
        return f'第{int(chapter_in_volume_match.group(2))}章'
    if volume_match:
        return f'第{int(volume_match.group(1))}卷'
    plan_match = name and re.match(r'^volume-(\d+)-plan\.md$', name, re.IGNORECASE)
    if plan_match:
        return f'第{int(plan_match.group(1))}卷规划.md'
    chapter_match = name and re.match(r'^第(\d{4})章\.md$', name)
    if chapter_match:
        return f'第{int(chapter_match.group(1))}章'
    summary_match = name and re.match(r'^ch(\d{4})\.md$', name, re.IGNORECASE)
    if summary_match:
        return f'第{int(summary_match.group(1))}章摘要'
    return name or normalized or '未命名文件'


def _format_display_datetime(value: Any) -> Optional[str]:
    text = str(value or '').strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone()
    return local.strftime('%Y-%m-%d %H:%M:%S')


def _with_display_timestamps(item: dict[str, Any], *, fields: tuple[str, ...]) -> dict[str, Any]:
    enriched = dict(item)
    for field in fields:
        if field in enriched and enriched.get(field):
            enriched[f'{field}_display'] = _format_display_datetime(enriched.get(field))
    return enriched


def _list_story_plans(project_root: Path, limit: int = 20) -> list[dict[str, Any]]:
    story_dir = project_root / '.webnovel' / 'story-director'
    if not story_dir.is_dir():
        return []

    items: list[dict[str, Any]] = []
    for path in sorted(story_dir.glob('plan-ch*.json'), reverse=True)[: max(1, int(limit))]:
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        chapters = [item for item in (payload.get('chapters') or []) if isinstance(item, dict)]
        anchor_chapter = int(payload.get('anchor_chapter') or 0)
        current_slot = next((item for item in chapters if int(item.get('chapter') or 0) == anchor_chapter), chapters[0] if chapters else {})
        stat = path.stat()
        updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        items.append(
            _with_display_timestamps(
                {
                    'anchor_chapter': anchor_chapter,
                    'planning_horizon': int(payload.get('planning_horizon') or 0),
                    'priority_threads': payload.get('priority_threads') or [],
                    'payoff_schedule': payload.get('payoff_schedule') or [],
                    'defer_schedule': payload.get('defer_schedule') or [],
                    'risk_flags': payload.get('risk_flags') or [],
                    'transition_notes': payload.get('transition_notes') or [],
                    'chapter_count': len(chapters),
                    'current_role': str((current_slot or {}).get('role') or '').strip(),
                    'current_goal': str((current_slot or {}).get('chapter_goal') or '').strip(),
                    'current_hook': str((current_slot or {}).get('ending_hook_target') or '').strip(),
                    'rationale': str(payload.get('rationale') or '').strip(),
                    'path': f'.webnovel/story-director/{path.name}',
                    'updated_at': updated_at,
                },
                fields=('updated_at',),
            )
        )
    return items


def _file_type_for_path(path: str) -> str:
    normalized = str(path or '').replace('\\', '/').strip('/')
    name = normalized.split('/')[-1] if normalized else ''
    if normalized == PROJECT_STATE_FILE_PATH:
        return '内部状态文件'
    if normalized == PROJECT_STATE_SUMMARIES_PATH:
        return '摘要目录'
    if normalized.startswith(f'{PROJECT_STATE_SUMMARIES_PATH}/'):
        return '摘要'
    if re.match(r'^正文/第\d+卷$', normalized):
        return '卷目录'
    if re.match(r'^正文/第\d+卷/第\d{4}章\.md$', normalized):
        return '正文'
    if re.match(r'^volume-\d+-plan\.md$', name, re.IGNORECASE):
        return '卷规划'
    if re.match(r'^第\d{4}章\.md$', name):
        return '正文'
    if re.match(r'^ch\d{4}\.md$', name, re.IGNORECASE):
        return '摘要'
    if normalized.startswith('设定集/'):
        return '设定文档'
    if normalized.startswith('大纲/'):
        return '大纲文档'
    return '文件'


def _detect_doc_status(path: str, content: str) -> str | None:
    normalized = str(path or '').replace('\\', '/')
    if normalized == PROJECT_STATE_FILE_PATH:
        return '内部状态'
    if '/设定集/' in f'/{normalized}':
        text = str(content or '').strip()
        if not text:
            return '模板'
        if '待补充' in text or '（待填写）' in text or 'TODO' in text:
            return '待补充'
        return '已沉淀'
    return None


def _build_file_summary_card(root: Path, path: str, content: str) -> dict | None:
    normalized = str(path or '').replace('\\', '/')
    if normalized != PROJECT_STATE_FILE_PATH:
        return None
    try:
        payload = json.loads(content or '{}')
    except json.JSONDecodeError:
        return {
            'title': '项目状态摘要',
            'kind': 'internal_state',
            'warning': '内部状态文件无法解析，建议检查最近一次写回。',
            'items': [],
        }
    project = payload.get('project_info') or {}
    progress = payload.get('progress') or {}
    planning = payload.get('planning') or {}
    return {
        'title': '项目状态摘要',
        'kind': 'internal_state',
        'warning': '内部状态 / 机器可读 / 不建议直接编辑',
        'items': [
            {'label': '项目标题', 'value': project.get('title') or '待补充'},
            {'label': '当前章节', 'value': f"第 {int(progress.get('current_chapter') or 0)} 章"},
            {'label': '当前卷', 'value': f"第 {int(progress.get('current_volume') or 1)} 卷"},
            {'label': '总字数', 'value': str(progress.get('total_words') or 0)},
            {'label': '最近更新时间', 'value': progress.get('last_updated') or project.get('updated_at') or payload.get('updated_at') or '-'},
            {'label': '卷规划状态', 'value': '已规划' if (planning.get('volume_plans') or {}) else '未规划'},
        ],
    }


def _resolve_relationship_entity_display(*, canonical_name: Any, alias: Any, raw_id: Any) -> str:
    raw = str(raw_id or '').strip()
    canonical = str(canonical_name or '').strip()
    alias_text = str(alias or '').strip()
    if canonical and canonical != raw:
        return canonical
    if alias_text:
        return alias_text
    if canonical:
        return canonical
    if raw:
        return raw
    return '-'


def _translate_relationship_type(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return '-'
    if text in RELATIONSHIP_TYPE_LABELS:
        return RELATIONSHIP_TYPE_LABELS[text]
    fallback = text.replace('_', ' / ').replace('-', ' / ')
    return f'关系：{fallback}'


def _is_child(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
