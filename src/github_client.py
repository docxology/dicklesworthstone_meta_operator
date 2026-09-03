"""GitHub repository enumeration via the ``gh`` CLI (subprocess boundary).

The only network-touching module of the meta-operator, and only indirectly:
everything goes through the ``gh`` CLI (``gh api --paginate --slurp``), so the
operator itself never opens sockets. Tests exercise the default runner through
a PATH-stubbed fake ``gh`` script — real subprocess, zero mocks, zero network.

Pagination robustness: modern ``gh`` supports ``--slurp`` (all pages collected
into one JSON array). ``gh api <url> --paginate --slurp`` yields a single value
shaped like ``[[page1_repos], [page2_repos], ...]``.
Older ``gh`` builds without ``--slurp`` emit the per-page ``--jq`` results
back-to-back, i.e. several concatenated JSON arrays. :func:`enumerate_repos`
accepts every historical shape: a flat list of repo dicts, a list of lists
(one per page), or concatenated top-level arrays (recovered via repeated
:func:`json.JSONDecoder.raw_decode` when the whole blob fails ``json.loads``).
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from typing import Any

from src.models import RepoMeta

logger = logging.getLogger(__name__)

#: Callable seam over the subprocess boundary: takes the full argv, returns stdout.
Runner = Callable[[list[str]], str]

GH_INSTALL_HINT = "gh CLI not found — install https://cli.github.com"


def repos_api_url(user: str) -> str:
    """REST endpoint listing ``user``'s public repositories, 100 per page."""
    return f"https://api.github.com/users/{user}/repos?per_page=100"


def parse_repos(payload: list[dict]) -> list[RepoMeta]:
    """Map raw GitHub repo JSON objects to :class:`RepoMeta`, sorted by name.

    Pure. Tolerates the field shapes GitHub actually emits: ``language`` and
    ``description`` may be ``null`` (become ``""``), ``topics`` may be absent
    (becomes ``[]``), ``default_branch`` may be ``null`` for empty repos.
    Raises ``ValueError`` if ``payload`` is not a list.
    """
    if not isinstance(payload, list):
        raise ValueError(f"parse_repos expects a list of repo objects, got {type(payload).__name__}")
    metas: list[RepoMeta] = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise ValueError(
                f"parse_repos expected repo objects, found {type(entry).__name__} at index {index}"
            )
        metas.append(
            RepoMeta(
                name=str(entry.get("name") or ""),
                html_url=str(entry.get("html_url") or ""),
                clone_url=str(entry.get("clone_url") or ""),
                default_branch=str(entry.get("default_branch") or ""),
                language=str(entry.get("language") or ""),
                description=str(entry.get("description") or ""),
                size_kb=int(entry.get("size") or 0),
                pushed_at=str(entry.get("pushed_at") or ""),
                fork=bool(entry.get("fork") or False),
                archived=bool(entry.get("archived") or False),
                topics=[str(topic) for topic in (entry.get("topics") or [])],
            )
        )
    metas.sort(key=lambda meta: meta.name)
    return metas


def _default_runner(argv: list[str]) -> str:
    """Run ``gh api`` via subprocess; convert every failure to ``RuntimeError``."""
    logger.debug("running gh: %s", argv)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(GH_INSTALL_HINT) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise RuntimeError(f"gh api failed (exit {exc.returncode}): {detail}") from exc
    return proc.stdout


def _top_level_json_values(text: str) -> list[Any]:
    """Decode ``text`` as one JSON value, or as concatenated JSON values.

    Handles the historical ``gh`` shape where ``--paginate`` concatenates the
    per-page results of ``--jq`` into several back-to-back JSON arrays.
    """
    try:
        return [json.loads(text)]
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        value, end = decoder.raw_decode(text, index)
        values.append(value)
        index = end
    if not values:
        raise ValueError("gh api produced no JSON output")
    return values


def _flatten_repo_objects(values: list[Any]) -> list[dict]:
    """Normalize every accepted payload shape to a flat list of repo dicts."""
    flat: list[dict] = []
    for value in values:
        if not isinstance(value, list):
            flat.append(value)
            continue
        for item in value:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)
    return flat


def enumerate_repos(
    user: str, *, include_forks: bool = True, runner: Runner | None = None
) -> list[RepoMeta]:
    """List ``user``'s repositories via ``gh api --paginate --slurp``.

    ``runner`` defaults to a real ``gh`` subprocess call
    (``["gh", "api", <url>, "--paginate", "--slurp"]``); inject a
    callable to run fully offline. Fork repos are filtered out after parsing
    when ``include_forks`` is ``False``. Raises ``RuntimeError`` with an
    actionable message when ``gh`` is missing or fails.
    """
    runner = runner if runner is not None else _default_runner
    argv = ["gh", "api", repos_api_url(user), "--paginate", "--slurp"]
    stdout = runner(argv)
    metas = parse_repos(_flatten_repo_objects(_top_level_json_values(stdout)))
    if include_forks:
        return metas
    return [meta for meta in metas if not meta.fork]