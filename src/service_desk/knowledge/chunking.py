"""Structure-aware, deterministic chunking for Harborlight knowledge documents.

This module deliberately has no embedding, retrieval, network, or database
dependencies. It turns the version-controlled Markdown source into typed,
stable chunk records for a later ingestion layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import ceil
from pathlib import Path
import re
from typing import Iterable


CORPUS_VERSION = "kb-v1"
CHUNKING_VERSION = "v1"
FROZEN_SOURCE_COMMIT = "8715e4ecc7b3d22efad8340c517e2a254a58fd7c"

PREFERRED_MIN_WORDS = 250
PREFERRED_MAX_WORDS = 450
SOFT_MAX_WORDS = 500
HARD_MAX_WORDS = 600
MAX_OVERLAP_WORDS = 40

_REQUIRED_FRONT_MATTER = ("document_id", "title", "domain", "product")
_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE_PATTERN = re.compile(r"^[ \t]*(`{3,}|~{3,})")


class KnowledgeDocumentError(ValueError):
    """Raised when a knowledge document cannot be parsed safely."""


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """A chunk ready for a future embedding and ingestion layer."""

    chunk_id: str
    chunking_version: str
    corpus_version: str
    document_id: str
    document_title: str
    domain: str
    product: str
    heading_path: tuple[str, ...]
    included_heading_paths: tuple[tuple[str, ...], ...]
    chunk_index: int
    source_path: str
    content: str
    word_count: int
    content_sha256: str
    source_commit: str

    def metadata(self) -> dict[str, object]:
        """Return serializable metadata without duplicating chunk content."""

        return {
            "chunk_id": self.chunk_id,
            "chunking_version": self.chunking_version,
            "corpus_version": self.corpus_version,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "domain": self.domain,
            "product": self.product,
            "heading_path": list(self.heading_path),
            "included_heading_paths": [list(path) for path in self.included_heading_paths],
            "chunk_index": self.chunk_index,
            "source_path": self.source_path,
            "word_count": self.word_count,
            "content_sha256": self.content_sha256,
            "source_commit": self.source_commit,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Validated Markdown source and its structural semantic units."""

    document_id: str
    title: str
    domain: str
    product: str
    source_path: str
    root_heading: str
    root_heading_line: str
    units: tuple["_SemanticUnit", ...]


@dataclass(frozen=True, slots=True)
class _SemanticUnit:
    """One H2 section, including any nested H3 content."""

    lines: tuple[str, ...]
    heading_path: tuple[str, ...]
    included_heading_paths: tuple[tuple[str, ...], ...]


class KnowledgeBaseChunker:
    """Load and chunk Markdown knowledge documents without external services."""

    def __init__(
        self,
        *,
        source_commit: str = FROZEN_SOURCE_COMMIT,
        corpus_version: str = CORPUS_VERSION,
        chunking_version: str = CHUNKING_VERSION,
    ) -> None:
        self._source_commit = source_commit
        self._corpus_version = corpus_version
        self._chunking_version = chunking_version

    def load_documents(
        self, knowledge_directory: Path, *, repository_root: Path | None = None
    ) -> tuple[KnowledgeDocument, ...]:
        """Load all Markdown files beneath a knowledge directory in path order."""

        directory = knowledge_directory.resolve()
        if not directory.is_dir():
            raise KnowledgeDocumentError(f"knowledge directory does not exist: {knowledge_directory}")
        root = (repository_root or directory.parent).resolve()
        documents = [
            self.load_file(path, repository_root=root)
            for path in sorted(directory.rglob("*.md"), key=lambda item: item.as_posix())
        ]
        document_ids = [document.document_id for document in documents]
        if len(document_ids) != len(set(document_ids)):
            raise KnowledgeDocumentError("knowledge directory contains duplicate document_id values")
        return tuple(sorted(documents, key=lambda document: (document.document_id, document.source_path)))

    def load_file(self, source_file: Path, *, repository_root: Path) -> KnowledgeDocument:
        """Parse one Markdown file and validate its required front matter."""

        resolved_file = source_file.resolve()
        try:
            source_path = resolved_file.relative_to(repository_root.resolve()).as_posix()
        except ValueError as error:
            raise KnowledgeDocumentError(
                f"source file must be inside repository root: {source_file}"
            ) from error
        text = _normalise_newlines(resolved_file.read_text(encoding="utf-8"))
        metadata, body_lines = _parse_front_matter(text, source_path)
        root_heading, root_heading_line, units = _build_semantic_units(body_lines, source_path)
        return KnowledgeDocument(
            document_id=metadata["document_id"],
            title=metadata["title"],
            domain=metadata["domain"],
            product=metadata["product"],
            source_path=source_path,
            root_heading=root_heading,
            root_heading_line=root_heading_line,
            units=units,
        )

    def chunk_directory(
        self, knowledge_directory: Path, *, repository_root: Path | None = None
    ) -> tuple[KnowledgeChunk, ...]:
        """Return deterministic chunks for every Markdown file in a directory."""

        documents = self.load_documents(knowledge_directory, repository_root=repository_root)
        return tuple(chunk for document in documents for chunk in self.chunk_document(document))

    def chunk_document(self, document: KnowledgeDocument) -> tuple[KnowledgeChunk, ...]:
        """Chunk one document at H2 boundaries, splitting paragraphs only if needed."""

        units = _expand_oversized_units(document.units, document.root_heading_line)
        groups = _partition_units(units, document.root_heading_line)
        chunks: list[KnowledgeChunk] = []
        for index, group in enumerate(groups, start=1):
            content = _materialise_content(document.root_heading_line, group)
            heading_path = _shared_heading_path(unit.heading_path for unit in group)
            included_paths = _unique_paths(
                path for unit in group for path in unit.included_heading_paths
            )
            chunks.append(
                KnowledgeChunk(
                    chunk_id=(
                        f"{document.document_id}--chunk-{self._chunking_version}--{index:03d}"
                    ),
                    chunking_version=self._chunking_version,
                    corpus_version=self._corpus_version,
                    document_id=document.document_id,
                    document_title=document.title,
                    domain=document.domain,
                    product=document.product,
                    heading_path=heading_path,
                    included_heading_paths=included_paths,
                    chunk_index=index,
                    source_path=document.source_path,
                    content=content,
                    word_count=_word_count(content),
                    content_sha256=sha256(content.encode("utf-8")).hexdigest(),
                    source_commit=self._source_commit,
                )
            )
        return tuple(chunks)


def _normalise_newlines(text: str) -> str:
    return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def _parse_front_matter(text: str, source_path: str) -> tuple[dict[str, str], list[str]]:
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        raise KnowledgeDocumentError(f"{source_path}: front matter must start with '---'")

    try:
        closing_index = next(index for index, line in enumerate(lines[1:], start=1) if line == "---")
    except StopIteration as error:
        raise KnowledgeDocumentError(f"{source_path}: front matter is not closed") from error

    metadata: dict[str, str] = {}
    for line in lines[1:closing_index]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise KnowledgeDocumentError(f"{source_path}: invalid front matter line: {line!r}")
        normalized_key = key.strip()
        if normalized_key in metadata:
            raise KnowledgeDocumentError(f"{source_path}: duplicate front matter key: {normalized_key}")
        metadata[normalized_key] = value.strip()

    missing = [key for key in _REQUIRED_FRONT_MATTER if not metadata.get(key)]
    if missing:
        raise KnowledgeDocumentError(
            f"{source_path}: missing required front matter: {', '.join(missing)}"
        )
    return metadata, lines[closing_index + 1 :]


def _build_semantic_units(
    body_lines: list[str], source_path: str
) -> tuple[str, str, tuple[_SemanticUnit, ...]]:
    headings = _headings_outside_fences(body_lines)
    h1 = next((heading for heading in headings if heading[1] == 1), None)
    if h1 is None:
        raise KnowledgeDocumentError(f"{source_path}: expected one H1 document heading")
    h1_index, _, root_heading = h1
    root_heading_line = body_lines[h1_index]
    h2_indexes = [index for index, level, _ in headings if level == 2 and index > h1_index]

    intro_lines = _trim_blank_lines(body_lines[h1_index + 1 : h2_indexes[0] if h2_indexes else None])
    if not h2_indexes:
        content_lines = _trim_blank_lines([*intro_lines])
        if not content_lines:
            raise KnowledgeDocumentError(f"{source_path}: document has no content after its H1 heading")
        return root_heading, root_heading_line, (
            _SemanticUnit(
                lines=tuple(content_lines),
                heading_path=(root_heading,),
                included_heading_paths=((root_heading,),),
            ),
        )

    units: list[_SemanticUnit] = []
    for position, h2_index in enumerate(h2_indexes):
        end_index = h2_indexes[position + 1] if position + 1 < len(h2_indexes) else len(body_lines)
        section_lines = _trim_blank_lines(body_lines[h2_index:end_index])
        if position == 0:
            section_lines = _trim_blank_lines([*intro_lines, *section_lines])
        h2_heading = _heading_text(body_lines[h2_index], source_path)
        heading_path = (root_heading, h2_heading)
        included_paths = [heading_path]
        for index, level, heading_text in headings:
            if h2_index < index < end_index and level == 3:
                included_paths.append((root_heading, h2_heading, heading_text))
        units.append(
            _SemanticUnit(
                lines=tuple(section_lines),
                heading_path=heading_path,
                included_heading_paths=tuple(included_paths),
            )
        )
    return root_heading, root_heading_line, tuple(units)


def _headings_outside_fences(lines: list[str]) -> list[tuple[int, int, str]]:
    headings: list[tuple[int, int, str]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        fence_match = _FENCE_PATTERN.match(line)
        if fence is not None:
            if fence_match and fence_match.group(1)[0] == fence[0] and len(fence_match.group(1)) >= len(fence):
                fence = None
            continue
        if fence_match:
            fence = fence_match.group(1)
            continue
        heading_match = _HEADING_PATTERN.match(line)
        if heading_match:
            headings.append((index, len(heading_match.group(1)), heading_match.group(2).strip()))
    return headings


def _heading_text(line: str, source_path: str) -> str:
    heading_match = _HEADING_PATTERN.match(line)
    if heading_match is None:
        raise KnowledgeDocumentError(f"{source_path}: invalid heading: {line!r}")
    return heading_match.group(2).strip()


def _expand_oversized_units(
    units: tuple[_SemanticUnit, ...], root_heading_line: str
) -> tuple[_SemanticUnit, ...]:
    expanded: list[_SemanticUnit] = []
    for unit in units:
        if _word_count(_join_lines(root_heading_line, unit.lines)) <= HARD_MAX_WORDS:
            expanded.append(unit)
            continue
        expanded.extend(_split_oversized_unit(unit, root_heading_line))
    return tuple(expanded)


def _split_oversized_unit(unit: _SemanticUnit, root_heading_line: str) -> tuple[_SemanticUnit, ...]:
    """Split a large H2 unit at block boundaries with bounded paragraph overlap."""

    section_heading = next((line for line in unit.lines if line.startswith("## ")), None)
    if section_heading is None:
        return (unit,)
    blocks = _markdown_blocks(unit.lines)
    heading_block_index = next(
        (index for index, block in enumerate(blocks) if section_heading in block), None
    )
    if heading_block_index is None:
        return (unit,)

    leading_blocks = blocks[:heading_block_index]
    prefix = tuple(blocks[heading_block_index])
    content_blocks = blocks[heading_block_index + 1 :]
    fragments: list[tuple[str, ...]] = []
    leading_lines = [line for block in leading_blocks for line in (*block, "")]
    current: list[str] = _trim_blank_lines([*leading_lines, *prefix])
    previous_paragraph: tuple[str, ...] | None = None

    for block in content_blocks:
        candidate = _trim_blank_lines([*current, "", *block])
        if _word_count(_join_lines(root_heading_line, candidate)) <= SOFT_MAX_WORDS:
            current = candidate
        else:
            if len(current) > len(prefix):
                fragments.append(tuple(current))
                overlap = _overlap_block(previous_paragraph)
                current = list(prefix)
                if overlap:
                    current = _trim_blank_lines([*current, "", *overlap])
                current = _trim_blank_lines([*current, "", *block])
            else:
                current = candidate
        if _is_plain_paragraph(block):
            previous_paragraph = tuple(block)

    if current:
        fragments.append(tuple(current))

    return tuple(
        _SemanticUnit(
            lines=fragment,
            heading_path=unit.heading_path,
            included_heading_paths=unit.included_heading_paths,
        )
        for fragment in fragments
    )


def _markdown_blocks(lines: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Keep paragraphs, lists, tables, and fenced code blocks intact as blocks."""

    blocks: list[tuple[str, ...]] = []
    current: list[str] = []
    fence: str | None = None
    for line in lines:
        fence_match = _FENCE_PATTERN.match(line)
        if fence is not None:
            current.append(line)
            if fence_match and fence_match.group(1)[0] == fence[0] and len(fence_match.group(1)) >= len(fence):
                fence = None
            continue
        if fence_match:
            current.append(line)
            fence = fence_match.group(1)
            continue
        if not line.strip():
            if current:
                blocks.append(tuple(_trim_blank_lines(current)))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(tuple(_trim_blank_lines(current)))
    return blocks


def _is_plain_paragraph(block: tuple[str, ...]) -> bool:
    first_line = block[0] if block else ""
    return not (
        first_line.startswith("#")
        or first_line.startswith(("- ", "* ", "+ ", "|"))
        or re.match(r"^\d+\. ", first_line)
        or _FENCE_PATTERN.match(first_line)
    )


def _overlap_block(previous_paragraph: tuple[str, ...] | None) -> tuple[str, ...]:
    if previous_paragraph is None or _word_count("\n".join(previous_paragraph)) > MAX_OVERLAP_WORDS:
        return ()
    return previous_paragraph


def _partition_units(
    units: tuple[_SemanticUnit, ...], root_heading_line: str
) -> tuple[tuple[_SemanticUnit, ...], ...]:
    if not units:
        raise KnowledgeDocumentError("document contains no chunkable content")
    whole_content = _materialise_content(root_heading_line, units)
    whole_words = _word_count(whole_content)
    if whole_words <= SOFT_MAX_WORDS or (len(units) == 1 and whole_words <= HARD_MAX_WORDS):
        return (units,)

    target_count = ceil(whole_words / SOFT_MAX_WORDS)
    while True:
        partition = _best_partition(units, root_heading_line, target_count)
        if partition is not None:
            return partition
        target_count += 1
        if target_count > len(units):
            raise KnowledgeDocumentError(
                "document cannot be partitioned within the hard word limit without "
                "breaking an indivisible Markdown block"
            )


def _best_partition(
    units: tuple[_SemanticUnit, ...], root_heading_line: str, count: int
) -> tuple[tuple[_SemanticUnit, ...], ...] | None:
    """Choose the most balanced valid contiguous H2 partition deterministically."""

    total_words = _word_count(_materialise_content(root_heading_line, units))
    target_words = total_words / count
    memo: dict[tuple[int, int], tuple[float, tuple[tuple[_SemanticUnit, ...], ...]] | None] = {}

    def solve(start: int, remaining: int) -> tuple[float, tuple[tuple[_SemanticUnit, ...], ...]] | None:
        key = (start, remaining)
        if key in memo:
            return memo[key]
        if len(units) - start < remaining:
            memo[key] = None
            return None
        if remaining == 1:
            group = units[start:]
            words = _word_count(_materialise_content(root_heading_line, group))
            result = (float((words - target_words) ** 2), (group,)) if words <= HARD_MAX_WORDS else None
            memo[key] = result
            return result

        best: tuple[float, tuple[tuple[_SemanticUnit, ...], ...]] | None = None
        for end in range(start + 1, len(units) - remaining + 2):
            group = units[start:end]
            words = _word_count(_materialise_content(root_heading_line, group))
            if words > HARD_MAX_WORDS:
                break
            tail = solve(end, remaining - 1)
            if tail is None:
                continue
            candidate = (
                float((words - target_words) ** 2) + tail[0],
                (group, *tail[1]),
            )
            if best is None or candidate[0] < best[0]:
                best = candidate
        memo[key] = best
        return best

    result = solve(0, count)
    return result[1] if result is not None else None


def _materialise_content(root_heading_line: str, units: Iterable[_SemanticUnit]) -> str:
    lines: list[str] = [root_heading_line]
    for unit in units:
        lines.extend(("", *unit.lines))
    return _join_lines(*lines)


def _shared_heading_path(paths: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
    path_list = list(paths)
    if not path_list:
        return ()
    shared: list[str] = []
    for values in zip(*path_list):
        if len(set(values)) != 1:
            break
        shared.append(values[0])
    return tuple(shared)


def _unique_paths(paths: Iterable[tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    seen: set[tuple[str, ...]] = set()
    return tuple(path for path in paths if not (path in seen or seen.add(path)))


def _trim_blank_lines(lines: Iterable[str]) -> list[str]:
    result = list(lines)
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()
    return result


def _join_lines(*parts: Iterable[str] | str) -> str:
    lines: list[str] = []
    for part in parts:
        if isinstance(part, str):
            lines.append(part)
        else:
            lines.extend(part)
    return "\n".join(_trim_blank_lines(lines)) + "\n"


def _word_count(content: str | Iterable[str]) -> int:
    text = content if isinstance(content, str) else "\n".join(content)
    return len(text.split())
