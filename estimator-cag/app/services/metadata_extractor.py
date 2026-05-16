"""Heuristic metadata extractor that enriches ProjectMetadata across conversation turns.

Design decision — heuristic over LLM extractor
-----------------------------------------------
A second LLM call per turn (the "extractor" path) would be more robust but adds
latency and cost on every request.  Given that the metadata fields are narrow and
well-defined, a regex/keyword approach is accurate enough for MVP:

- ``project_name``:  matched by common title phrases in the user transcript.
- ``mentioned_technologies``:  scanned against a curated allow-list of ~70 tech
  keywords; false-positive rate is acceptably low for estimation context.
- ``assumed_team_size``:  extracted from numeric team-size patterns in the LLM response.
- ``agreed_scope``:  first 300 chars of the transcript, trimmed to a sentence boundary.

The heuristic runs in <1 ms, adds zero cost, and degrades gracefully (fields stay
``None``/empty when no signal is found).  The class can be swapped for an LLM-based
implementation without touching the router by keeping the same ``update()`` interface.
"""

from __future__ import annotations

import re

from app.services.sessions import ProjectMetadata

# ---------------------------------------------------------------------------
# Tech allow-list  (lowercase)
# ---------------------------------------------------------------------------

_TECHNOLOGIES: frozenset[str] = frozenset(
    {
        # Frontend
        "react",
        "vue",
        "angular",
        "svelte",
        "next.js",
        "nuxt",
        "remix",
        "tailwind",
        "bootstrap",
        "vite",
        "webpack",
        # Backend
        "python",
        "fastapi",
        "django",
        "flask",
        "node.js",
        "express",
        "nestjs",
        "spring boot",
        "rails",
        "laravel",
        "go",
        "rust",
        # Mobile
        "ios",
        "android",
        "swift",
        "kotlin",
        "react native",
        "flutter",
        "expo",
        # Databases
        "postgresql",
        "mysql",
        "sqlite",
        "mongodb",
        "redis",
        "elasticsearch",
        "dynamodb",
        "firestore",
        "supabase",
        # Cloud & infra
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "terraform",
        "github actions",
        "gitlab ci",
        "jenkins",
        # Languages
        "typescript",
        "javascript",
        "java",
        "c#",
        ".net",
        "php",
        "ruby",
        # AI / ML
        "openai",
        "anthropic",
        "langchain",
        "llamaindex",
        "hugging face",
        "pytorch",
        "tensorflow",
        # Protocols & messaging
        "graphql",
        "grpc",
        "websocket",
        "kafka",
        "rabbitmq",
        "stripe",
    }
)

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

_PROJECT_NAME_PATTERNS: list[re.Pattern[str]] = [
    # "Project name is ShopCore."
    re.compile(r"(?i:project\s+name\s+is\s+)['\"]?([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)(?=\s|$|['\"]|\.)", re.IGNORECASE),
    # "Project name: ShopCore" or "Project name = ShopCore"
    re.compile(r"(?i:project\s+name\s*[:=]\s*)['\"]?([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)(?=\s|$|['\"]|\.)", re.IGNORECASE),
    # "project called ShopCore" or "app named ShopCore"
    re.compile(
        r"(?i:(?:project|app|application|platform|system|tool|service)\s+"
        r"(?:called|named|titled|known as)\s+)['\"]?([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)(?=\s+(?:for|that|to|in|on|at)\b|['\"]|$|\.)"
    ),
    # "building ShopCore" or "building a ShopCore"
    re.compile(r"(?i:building\s+(?:a\s+)?)['\"]?([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)(?=\s+(?:for|that|to|in|on|at)\b|['\"]|$|\.)['\"]?"),
    # first Markdown heading
    re.compile(r"^#+\s+(.+)$", re.MULTILINE),
    # "project: ShopCore" or "project ShopCore"
    re.compile(
        r"(?i:project\s*[:=]?\s*)['\"]?([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)(?=\s+(?:for|that|to|in|on|at)\b|['\"]|$|\.)"
    ),
]

_TEAM_SIZE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"team\s+of\s+(\d{1,2})", re.IGNORECASE),
    re.compile(
        r"(\d{1,2})\s+(?:developers?|engineers?|people|members?)", re.IGNORECASE
    ),
    re.compile(r"(\d{1,2})-person\s+team", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Public extractor
# ---------------------------------------------------------------------------


class MetadataExtractor:
    """Heuristic extractor — enriches a :class:`~app.services.sessions.ProjectMetadata`
    from a new conversation turn without making additional LLM calls.

    Usage::

        extractor = MetadataExtractor()
        session.metadata = extractor.update(transcript, llm_response, session.metadata)
    """

    def update(
        self,
        transcript: str,
        llm_response: str,
        existing: ProjectMetadata,
    ) -> ProjectMetadata:
        """Return a new :class:`ProjectMetadata` enriched from *transcript* and *llm_response*.

        Existing values are preserved; new values are only filled when a field is
        still ``None``/empty and a confident pattern match is found.

        Args:
            transcript: The user-supplied text (may include extracted attachment text).
            llm_response: The latest assistant response to mine for team-size signals.
            existing: The session's current metadata to extend.

        Returns:
            A fresh :class:`ProjectMetadata` instance with enriched fields.
        """
        combined = f"{transcript}\n{llm_response}"

        project_name = existing.project_name or self._extract_project_name(transcript)
        team_size = existing.assumed_team_size or self._extract_team_size(llm_response)
        technologies = set(existing.mentioned_technologies) | self._extract_technologies(combined)
        scope = existing.agreed_scope or self._extract_scope(transcript)

        return ProjectMetadata(
            project_name=project_name,
            assumed_team_size=team_size,
            mentioned_technologies=sorted(technologies),
            agreed_scope=scope,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_project_name(text: str) -> str | None:
        for pattern in _PROJECT_NAME_PATTERNS:
            match = pattern.search(text)
            if match:
                name = match.group(1).strip()
                if 2 <= len(name) <= 60:
                    return name
        return None

    @staticmethod
    def _extract_technologies(text: str) -> set[str]:
        lower = text.lower()
        return {tech for tech in _TECHNOLOGIES if tech in lower}

    @staticmethod
    def _extract_team_size(text: str) -> int | None:
        for pattern in _TEAM_SIZE_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    size = int(match.group(1))
                    if 1 <= size <= 50:
                        return size
                except ValueError:
                    pass
        return None

    @staticmethod
    def _extract_scope(transcript: str, max_chars: int = 300) -> str | None:
        cleaned = transcript.strip()
        if not cleaned:
            return None
        if len(cleaned) <= max_chars:
            return cleaned
        truncated = cleaned[:max_chars]
        last_period = max(truncated.rfind(". "), truncated.rfind(".\n"))
        if last_period > 50:
            return truncated[: last_period + 1]
        return truncated + "…"
