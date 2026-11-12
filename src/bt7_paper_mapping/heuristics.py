from __future__ import annotations

import re
import difflib
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from tas_copilot_contracts import PaperExperimentLink, ProvenanceRecord


def map_paper_to_experiments(paper: dict[str, Any], experiments: Iterable[dict[str, Any]], threshold: float = 0.2) -> list[PaperExperimentLink]:
    """Return candidate paper-to-experiment links using deterministic metadata overlap."""

    paper_id = str(paper.get("paper_id") or paper.get("id") or "unknown-paper")
    paper_text = _paper_text(paper)
    paper_tokens = _tokens(paper_text)
    paper_year = _year(paper.get("year") or paper_text)
    paper_authors = _paper_authors(paper)
    links: list[PaperExperimentLink] = []

    for experiment in experiments:
        experiment_id = str(experiment.get("experiment_id") or experiment.get("id") or "")
        if not experiment_id:
            continue
        confidence, evidence = _score_experiment(paper_text, paper_tokens, paper_year, paper_authors, experiment)
        if confidence < threshold:
            continue
        links.append(
            PaperExperimentLink(
                paper_id=paper_id,
                experiment_id=experiment_id,
                confidence=round(min(confidence, 0.99), 3),
                evidence=evidence,
                mapping_method="deterministic_bt7_record_linkage_v0",
                notes="Candidate generated from deterministic metadata and text overlap. Human review still required.",
                provenance=[
                    ProvenanceRecord(source_type="paper", source_id=paper_id, method="paper_text_metadata_overlap"),
                    ProvenanceRecord(source_type="experiment", source_id=experiment_id, method="experiment_metadata_overlap"),
                ],
                status="candidate",
            )
        )
    return sorted(links, key=lambda link: link.confidence, reverse=True)


def _score_experiment(
    paper_text: str,
    paper_tokens: set[str],
    paper_year: int | None,
    paper_authors: list[str],
    experiment: dict[str, Any],
) -> tuple[float, list[str]]:
    score = 0.0
    evidence: list[str] = []
    if not _date_compatible(experiment, paper_year):
        return 0.0, ["paper year predates experiment date"]

    experiment_id = str(experiment.get("experiment_id") or experiment.get("id") or "")
    if experiment_id and _contains_identifier(paper_text, experiment_id):
        score += 0.45
        evidence.append(f"paper text mentions experiment id {experiment_id}")

    proposal_id = str(experiment.get("proposal_id") or experiment.get("proposal") or "")
    if proposal_id and _contains_identifier(paper_text, proposal_id):
        score += 0.35
        evidence.append(f"paper text mentions proposal id {proposal_id}")

    for field, weight in [("sample", 0.15), ("material", 0.15), ("compound", 0.15)]:
        value = str(experiment.get(field) or "")
        if value and _token_overlap(value, paper_tokens):
            score += weight
            evidence.append(f"{field} term matches paper text: {value}")

    people = (
        _as_list(experiment.get("participants"))
        + _as_list(experiment.get("principal_investigator"))
        + _as_list(experiment.get("users"))
        + _as_list(experiment.get("authors"))
    )
    name_matches = _name_matches([str(person) for person in people if person], paper_authors)
    if name_matches:
        score += min(0.3, 0.1 * len(name_matches))
        evidence.append("author/participant overlap: " + ", ".join(f"{left}~{right}" for left, right, _ in name_matches[:3]))

    experiment_year = _experiment_year(experiment)
    if paper_year and experiment_year and abs(paper_year - experiment_year) <= 1:
        score += 0.1
        evidence.append(f"paper year {paper_year} is close to experiment year {experiment_year}")

    metadata = experiment.get("metadata") if isinstance(experiment.get("metadata"), dict) else {}
    for key in ["proposal_id", "experiment_id", "run_range", "sample", "material"]:
        value = str(metadata.get(key) or "")
        if value and _contains_identifier(paper_text, value):
            score += 0.05
            evidence.append(f"metadata field {key} matches paper text: {value}")

    exp_text = _experiment_text(experiment)
    similarity = _text_similarity(exp_text, paper_text)
    if similarity > 0.1:
        score += min(0.15, similarity * 0.3)
        evidence.append(f"experiment text similarity {similarity:.2f}")

    return score, evidence


def _paper_text(paper: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ["paper_id", "id", "title", "abstract", "text", "doi", "journal"]:
        value = paper.get(key)
        if value:
            parts.append(str(value))
    for author in _as_list(paper.get("authors")):
        parts.append(str(author))
    for chunk in _as_list(paper.get("chunks")):
        if isinstance(chunk, dict):
            parts.append(str(chunk.get("text") or chunk.get("content") or ""))
        else:
            parts.append(str(chunk))
    metadata = paper.get("metadata") if isinstance(paper.get("metadata"), dict) else {}
    parts.extend(str(value) for value in metadata.values() if value)
    return "\n".join(parts).lower()


def _paper_authors(paper: dict[str, Any]) -> list[str]:
    authors = [str(author) for author in _as_list(paper.get("authors")) if author]
    citation = str(paper.get("citation") or paper.get("bt7_citation_raw") or "")
    authors.extend(_extract_authors_from_citation(citation))
    return _dedupe(authors)


def _extract_authors_from_citation(citation: str) -> list[str]:
    """Extract likely author last names from the legacy BT-7 manifest citation string."""

    parts = re.split(r"\s*,\s*(Phys\.|Nature|Science|J\.|Nat\.|Commun|Appl\.|Rev\.|Mater\.|Lett\.)", citation)
    if not parts:
        return []
    author_part = parts[0]
    names = re.findall(r"([A-Z][A-Za-z]+(?:-[A-Z][A-Za-z]+)?)", author_part)
    skip_words = {"Phys", "Rev", "Nature", "Science", "Nat", "Commun", "Mater", "Lett", "Appl", "The", "And", "With"}
    return [name for name in names if name not in skip_words]


def _experiment_text(experiment: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ["experiment_id", "id", "proposal_id", "proposal", "title", "name", "sample", "material", "compound"]:
        value = experiment.get(key)
        if value:
            parts.append(str(value))
    for key in ["expt_names", "comments", "samples", "lattices"]:
        parts.extend(str(value) for value in _as_list(experiment.get(key)) if value)
    metadata = experiment.get("metadata") if isinstance(experiment.get("metadata"), dict) else {}
    parts.extend(str(value) for value in metadata.values() if value)
    return " ".join(parts).lower()


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9][a-z0-9_+\-.]*", value.lower()) if len(token) > 1}


def _token_overlap(value: str, tokens: set[str]) -> bool:
    value_tokens = _tokens(value)
    return bool(value_tokens and value_tokens <= tokens) or bool(value_tokens.intersection(tokens))


def _text_similarity(left: str, right: str) -> float:
    left_words = _tokens(left) - _stop_words()
    right_words = _tokens(right) - _stop_words()
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)


def _contains_identifier(text: str, identifier: str) -> bool:
    cleaned = identifier.strip().lower()
    if not cleaned:
        return False
    if len(cleaned) <= 2:
        return False
    return cleaned in text


def _normalize_name(name: str) -> str:
    name = re.sub(r"^(dr\.?|prof\.?)\s*", "", name.lower().strip())
    tokens = [token for token in re.split(r"\s+", name) if token]
    if not tokens:
        return ""
    last = tokens[-1].strip(",.;")
    return last if len(last) > 2 else " ".join(tokens[-2:])


def _name_matches(experiment_names: list[str], paper_authors: list[str], threshold: float = 0.8) -> list[tuple[str, str, float]]:
    matches: list[tuple[str, str, float]] = []
    exp_normalized = [(name, _normalize_name(name)) for name in experiment_names]
    paper_normalized = [(name, _normalize_name(name)) for name in paper_authors]
    for exp_original, exp_name in exp_normalized:
        for paper_original, paper_name in paper_normalized:
            if not exp_name or not paper_name:
                continue
            if exp_name == paper_name:
                matches.append((exp_original, paper_original, 1.0))
            elif len(exp_name) > 2 and len(paper_name) > 2:
                ratio = difflib.SequenceMatcher(None, exp_name, paper_name).ratio()
                if ratio >= threshold:
                    matches.append((exp_original, paper_original, ratio))
    return matches


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _year(value: Any) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", str(value))
    return int(match.group(0)) if match else None


def _experiment_year(experiment: dict[str, Any]) -> int | None:
    for key in ["year", "start_date", "end_date", "date"]:
        year = _year(experiment.get(key))
        if year:
            return year
    date_range = experiment.get("date_range")
    if isinstance(date_range, list) and date_range and date_range[0]:
        try:
            return datetime.fromtimestamp(float(date_range[0])).year
        except (TypeError, ValueError, OSError):
            pass
    metadata = experiment.get("metadata") if isinstance(experiment.get("metadata"), dict) else {}
    for key in ["year", "start_date", "end_date", "date"]:
        year = _year(metadata.get(key))
        if year:
            return year
    return None


def _date_compatible(experiment: dict[str, Any], paper_year: int | None) -> bool:
    experiment_year = _experiment_year(experiment)
    if not experiment_year or not paper_year:
        return True
    return paper_year >= experiment_year


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _stop_words() -> set[str]:
    return {
        "the",
        "a",
        "an",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "scan",
        "temperature",
        "field",
        "magnetic",
        "neutron",
        "scattering",
    }
