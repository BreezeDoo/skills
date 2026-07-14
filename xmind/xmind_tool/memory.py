"""
xmind_tool.memory: 会话记忆（断点续传）。

记忆文件存放在源 .xmind 文件所在目录的 .xmind-cache/<session>/ 下，
源目录不可写时回退到 cwd/.xmind-cache/<session>/。

设计为对抗长对话上下文压缩：parse 一次后把 markdown 缓存到磁盘，
后续 update 命令可不必重新解析、也不必依赖对话历史。
"""
import os
import re
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

_CACHE_DIR = ".xmind-cache"

# 合法 session id：字母数字 + - _ . ，且不以 . 开头/结尾，无路径分隔符
_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]$|^[A-Za-z0-9]$")


def validate_session_id(session_id: str) -> str:
    """校验 session id 合法性，返回原值。拒绝空串/含路径分隔符/.. 穿越。

    防止 ``<session>`` 拼到路径后越界到缓存目录之外（如 ``../etc`` 或 ``a/b``）。
    """
    if not session_id or not _SESSION_RE.match(session_id):
        raise ValueError(
            f"非法 session id: {session_id!r}。"
            "仅允许字母、数字、- _ .，且不以 . 开头/结尾、不含路径分隔符。"
        )
    return session_id


def _cache_name_for(xmind_path: PathLike) -> str:
    """源文件对应的缓存文件名（.xmind → .md，保留原 stem）。"""
    stem = Path(xmind_path).stem or "xmind"
    return f"{stem}.md"


def _source_cache_dir(xmind_path: PathLike) -> Path:
    """源文件所在目录的 .xmind-cache 路径。"""
    return Path(xmind_path).resolve().parent / _CACHE_DIR


def _cwd_cache_dir() -> Path:
    """回退用的 cwd/.xmind-cache 路径。"""
    return Path.cwd() / _CACHE_DIR


def cache_path(xmind_path: PathLike, session_id: str) -> Path:
    """计算缓存文件路径：首选源目录旁的 .xmind-cache/<session>/，
    源目录不可写时回退到 cwd/.xmind-cache/<session>/。

    返回路径不保证存在——由 save() 实际创建。
    """
    validate_session_id(session_id)
    name = _cache_name_for(xmind_path)
    src_dir = _source_cache_dir(xmind_path)
    if os.access(src_dir.parent, os.W_OK):
        return src_dir / session_id / name
    return _cwd_cache_dir() / session_id / name


def save(xmind_path: PathLike, session_id: str, text: str) -> str:
    """把 text 写入缓存文件，返回实际写入的绝对路径。

    先尝试源目录旁；写失败（权限/只读）则回退到 cwd/.xmind-cache/。
    """
    validate_session_id(session_id)
    name = _cache_name_for(xmind_path)
    candidates = [_source_cache_dir(xmind_path) / session_id, _cwd_cache_dir() / session_id]
    last_err = None
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            out = d / name
            out.write_text(text, encoding="utf-8")
            return str(out.resolve())
        except OSError as e:
            last_err = e
            continue
    raise OSError(f"无法写入缓存目录（源目录与 cwd 均失败）: {last_err}")


def load(xmind_path: PathLike, session_id: str) -> str | None:
    """读取缓存文件内容，无缓存返回 None。"""
    validate_session_id(session_id)
    p = cache_path(xmind_path, session_id)
    if not p.exists():
        # 也可能在回退目录（源目录后来变可写，或当时不可写）
        return None
    return p.read_text(encoding="utf-8")
