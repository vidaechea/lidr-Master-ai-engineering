"""Accumulative summarizer with anchor generation for critical conversation turns.

Anchors are heuristic markers that identify turns containing critical information:
  - ProjectMetadata extraction (project_name, team_size, technologies, scope)
  - Key decisions (approval, rejection, scope changes)
  - Risk identification or mitigations
  - Estimation confidence shifts
  - Contradictions or ambiguities flagged

The summarizer maintains:
  1. A growing summary of accumulated context
  2. A list of anchors keyed by turn number
  3. Keyword patterns to detect critical content
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

import structlog

log = structlog.get_logger(__name__)

AnchorType = Literal[
    "metadata_extraction",
    "scope_change",
    "decision_point",
    "risk_identified",
    "contradiction_flagged",
    "confidence_shift",
    "technology_mentioned",
]


@dataclass
class Anchor:
    """A heuristic marker for a turn containing critical information.

    Args:
        turn_number: Which user turn this anchor was identified in.
        anchor_type: Category of critical information.
        key_information: The extracted or flagged content.
        summary: Brief summary of why this turn is critical.
        message_indices: Indices of messages (in ConversationHistory) that triggered this anchor.
    """

    turn_number: int
    anchor_type: AnchorType
    key_information: str
    summary: str
    message_indices: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "turn_number": self.turn_number,
            "anchor_type": self.anchor_type,
            "key_information": self.key_information,
            "summary": self.summary,
            "message_indices": self.message_indices,
        }


class SummarizerService:
    """Accumulative summarizer that detects critical information and generates anchors.

    Uses heuristic patterns (keywords, regex) to identify critical content in each turn.
    Maintains a growing summary and anchor list without making LLM calls.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # Heuristic patterns for anchor detection
    # ─────────────────────────────────────────────────────────────────────────

    # ProjectMetadata extraction markers
    _PROJECT_NAME_PATTERNS = [
        r"(?:project|app|system|tool|platform|service)\s+(?:name|called|is|named)\s*[:=]?\s*(['\"]?)([A-Za-z0-9\s\-_]+)\1",
        r"(?:we|they|i|the team)\s+(?:are\s+)?(?:building|creating|developing|calling|naming)\s+(['\"]?)([A-Za-z0-9\s\-_]+)\1",
    ]

    _TEAM_SIZE_PATTERNS = [
        r"(?:team\s+)?(?:size|of|has|with)\s+(?:around|about|approximately)?\s*(\d+)\s*(?:people|devs?|engineers?|members?)",
        r"(\d+)\s*(?:people|developers?|engineers?|team\s+members?)",
    ]

    _TECHNOLOGY_PATTERNS = [
        r"(?:using|with|leveraging|built\s+(?:on|with)|requires?|needs?)\s+([A-Za-z0-9\s\-_/.+#]+?)(?:and|,|or|$)",
    ]

    _SCOPE_PATTERNS = [
        r"(?:scope|includes?|features?|requirements?|will\s+(?:build|include))\s*[:=]?\s*([^.!?]{20,150})[.!?]",
        r"(?:it\s+)?(?:should|will|must)\s+(?:include|have|support)\s+([^.!?]{15,100})[.!?]",
    ]

    # Decision and risk patterns
    _DECISION_PATTERNS = [
        r"(?:we\s+)?(?:agree|decided|will\s+(?:use|go|proceed))\s+(?:on|with|to)\s+([^.!?]{10,80})[.!?]",
        r"(?:approved?|rejected?|accepted?)\s+(?:the|this|proposal|estimate)\s+(?:for|of)\s+([^.!?]{10,80})[.!?]",
    ]

    _RISK_PATTERNS = [
        r"(?:risk|concern|issue|problem|challenge|bottleneck|dependency)\s*[:=]?\s*([^.!?]{10,100})[.!?]",
        r"(?:might|could|may)\s+(?:fail|break|cause|result\s+in)\s+([^.!?]{10,80})[.!?]",
    ]

    _CONTRADICTION_PATTERNS = [
        r"(?:but|however|contradicts?|conflicts?|inconsistent|contradictory)\s+(?:with|to)\s+([^.!?]{10,80})[.!?]",
        r"(?:wait|actually|no|not\s+quite)\s*,?\s+([^.!?]{10,100})[.!?]",
    ]

    def __init__(self) -> None:
        self._accumulative_summary: str = ""
        self._anchors: list[Anchor] = []
        self._turn_count: int = 0
        self._last_metadata_turn: int | None = None
        self._last_decision_turn: int | None = None

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def process_turn(
        self,
        turn_number: int,
        user_message: str,
        assistant_response: str | None = None,
    ) -> list[Anchor]:
        """Process a user turn and generate anchors if critical information is detected.

        Args:
            turn_number: The user turn number (1-indexed).
            user_message: The user's message content.
            assistant_response: The assistant's response (optional, may be used for context).

        Returns:
            List of new anchors generated for this turn.
        """
        self._turn_count = turn_number
        new_anchors: list[Anchor] = []
        message_indices = [turn_number * 2 - 1]  # Heuristic: user message at odd index

        full_text = user_message
        if assistant_response:
            full_text += " " + assistant_response
            message_indices.append(turn_number * 2)

        # Run heuristic detectors
        new_anchors.extend(self._detect_metadata_extraction(turn_number, full_text, message_indices))
        new_anchors.extend(self._detect_scope_changes(turn_number, full_text, message_indices))
        new_anchors.extend(self._detect_decision_points(turn_number, full_text, message_indices))
        new_anchors.extend(self._detect_risks(turn_number, full_text, message_indices))
        new_anchors.extend(self._detect_contradictions(turn_number, full_text, message_indices))
        new_anchors.extend(self._detect_technology_mentions(turn_number, full_text, message_indices))

        # Add anchors and update summary
        self._anchors.extend(new_anchors)
        if new_anchors:
            self._update_accumulative_summary(user_message, new_anchors)
            log.info(
                "anchors_generated",
                turn_number=turn_number,
                count=len(new_anchors),
                types=[a.anchor_type for a in new_anchors],
            )

        return new_anchors

    def get_anchors(self) -> list[Anchor]:
        """Return all anchors accumulated so far."""
        return self._anchors.copy()

    def get_anchors_by_type(self, anchor_type: AnchorType) -> list[Anchor]:
        """Return all anchors of a specific type."""
        return [a for a in self._anchors if a.anchor_type == anchor_type]

    def get_accumulative_summary(self) -> str:
        """Return the current accumulative summary of critical information."""
        return self._accumulative_summary

    def anchor_count(self) -> int:
        """Return the total number of anchors generated so far."""
        return len(self._anchors)

    def summary_char_count(self) -> int:
        """Return the character count of the accumulative summary."""
        return len(self._accumulative_summary)

    # ─────────────────────────────────────────────────────────────────────────
    # Heuristic detectors (return list of Anchor if anything detected)
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_metadata_extraction(
        self,
        turn_number: int,
        text: str,
        message_indices: list[int],
    ) -> list[Anchor]:
        """Detect project_name, team_size, technologies, scope mentions."""
        anchors: list[Anchor] = []

        # Project name
        for pattern in self._PROJECT_NAME_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                extracted = match.group(2) if match.lastindex >= 2 else match.group(1)
                if extracted and len(extracted) > 2:
                    anchors.append(
                        Anchor(
                            turn_number=turn_number,
                            anchor_type="metadata_extraction",
                            key_information=f"project_name: {extracted.strip()}",
                            summary=f"Project name identified: '{extracted.strip()}'",
                            message_indices=message_indices,
                        )
                    )

        # Team size
        for pattern in self._TEAM_SIZE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                size = match.group(1)
                anchors.append(
                    Anchor(
                        turn_number=turn_number,
                        anchor_type="metadata_extraction",
                        key_information=f"team_size: {size}",
                        summary=f"Team size identified: {size} members",
                        message_indices=message_indices,
                    )
                )

        # Scope
        for pattern in self._SCOPE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                scope = match.group(1) if match.lastindex >= 1 else ""
                if scope and len(scope) > 10:
                    anchors.append(
                        Anchor(
                            turn_number=turn_number,
                            anchor_type="metadata_extraction",
                            key_information=f"scope: {scope[:100]}",
                            summary="Scope information extracted",
                            message_indices=message_indices,
                        )
                    )

        return anchors

    def _detect_technology_mentions(
        self,
        turn_number: int,
        text: str,
        message_indices: list[int],
    ) -> list[Anchor]:
        """Detect technology/framework mentions."""
        anchors: list[Anchor] = []

        # Common technologies
        tech_keywords = [
            r"\b(?:React|Vue|Angular|Next\.js|Svelte)\b",
            r"\b(?:Django|FastAPI|Flask|Spring|Node\.js|Express)\b",
            r"\b(?:PostgreSQL|MongoDB|MySQL|Redis|Elasticsearch)\b",
            r"\b(?:Docker|Kubernetes|AWS|GCP|Azure)\b",
            r"\b(?:GraphQL|REST|gRPC|WebSocket)\b",
            r"\b(?:Python|JavaScript|TypeScript|Go|Rust)\b",
        ]

        techs_found: set[str] = set()
        for pattern in tech_keywords:
            matches = re.finditer(pattern, text)
            for match in matches:
                techs_found.add(match.group(0))

        if techs_found:
            anchors.append(
                Anchor(
                    turn_number=turn_number,
                    anchor_type="technology_mentioned",
                    key_information=", ".join(sorted(techs_found)),
                    summary=f"Technologies mentioned: {', '.join(sorted(techs_found))}",
                    message_indices=message_indices,
                )
            )

        return anchors

    def _detect_scope_changes(
        self,
        turn_number: int,
        text: str,
        message_indices: list[int],
    ) -> list[Anchor]:
        """Detect scope additions, removals, or clarifications."""
        change_indicators = [
            r"(?:also\s+)?(?:need|need|require|include|add|remove|exclude)\s+([^.!?]{10,80})[.!?]",
            r"(?:scope\s+)?(?:change|update|revised?|clarified?)\s+(?:to|as)\s+([^.!?]{10,80})[.!?]",
        ]

        anchors: list[Anchor] = []
        for pattern in change_indicators:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                change = match.group(1) if match.lastindex >= 1 else ""
                if change and len(change) > 5:
                    anchors.append(
                        Anchor(
                            turn_number=turn_number,
                            anchor_type="scope_change",
                            key_information=change[:100],
                            summary=f"Scope modification: {change[:50]}",
                            message_indices=message_indices,
                        )
                    )

        return anchors

    def _detect_decision_points(
        self,
        turn_number: int,
        text: str,
        message_indices: list[int],
    ) -> list[Anchor]:
        """Detect decisions, approvals, rejections."""
        anchors: list[Anchor] = []

        for pattern in self._DECISION_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                decision = match.group(1) if match.lastindex >= 1 else ""
                if decision and len(decision) > 5:
                    self._last_decision_turn = turn_number
                    anchors.append(
                        Anchor(
                            turn_number=turn_number,
                            anchor_type="decision_point",
                            key_information=decision[:100],
                            summary=f"Key decision made: {decision[:50]}",
                            message_indices=message_indices,
                        )
                    )

        return anchors

    def _detect_risks(
        self,
        turn_number: int,
        text: str,
        message_indices: list[int],
    ) -> list[Anchor]:
        """Detect risk identification or mitigation mentions."""
        anchors: list[Anchor] = []

        for pattern in self._RISK_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                risk = match.group(1) if match.lastindex >= 1 else ""
                if risk and len(risk) > 5:
                    anchors.append(
                        Anchor(
                            turn_number=turn_number,
                            anchor_type="risk_identified",
                            key_information=risk[:100],
                            summary=f"Risk identified: {risk[:50]}",
                            message_indices=message_indices,
                        )
                    )

        return anchors

    def _detect_contradictions(
        self,
        turn_number: int,
        text: str,
        message_indices: list[int],
    ) -> list[Anchor]:
        """Detect contradictions or conflicting information."""
        anchors: list[Anchor] = []

        for pattern in self._CONTRADICTION_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                contradiction = match.group(1) if match.lastindex >= 1 else ""
                if contradiction and len(contradiction) > 5:
                    anchors.append(
                        Anchor(
                            turn_number=turn_number,
                            anchor_type="contradiction_flagged",
                            key_information=contradiction[:100],
                            summary=f"Potential contradiction: {contradiction[:50]}",
                            message_indices=message_indices,
                        )
                    )

        return anchors

    def _update_accumulative_summary(self, user_message: str, anchors: list[Anchor]) -> None:
        """Update the accumulative summary with newly detected information."""
        summary_parts = []

        for anchor in anchors:
            if anchor.anchor_type == "metadata_extraction":
                summary_parts.append(f"[METADATA] {anchor.key_information}")
            elif anchor.anchor_type == "decision_point":
                summary_parts.append(f"[DECISION] {anchor.summary}")
            elif anchor.anchor_type == "risk_identified":
                summary_parts.append(f"[RISK] {anchor.key_information}")
            elif anchor.anchor_type == "scope_change":
                summary_parts.append(f"[SCOPE] {anchor.summary}")
            elif anchor.anchor_type == "technology_mentioned":
                summary_parts.append(f"[TECH] {anchor.key_information}")
            else:
                summary_parts.append(f"[{anchor.anchor_type.upper()}] {anchor.summary}")

        new_summary = " | ".join(summary_parts)
        if self._accumulative_summary:
            self._accumulative_summary += " | " + new_summary
        else:
            self._accumulative_summary = new_summary
