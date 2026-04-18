from __future__ import annotations

import re
from dataclasses import dataclass

from config.settings import AppSettings, settings


@dataclass(slots=True)
class PolicySection:
	title: str
	content: str


class KnowledgeTools:
	def __init__(self, app_settings: AppSettings | None = None) -> None:
		self.settings = app_settings or settings

	def load_policies_text(self) -> str:
		policies_file = self.settings.policies_file
		if not policies_file.exists():
			return ""
		return policies_file.read_text(encoding="utf-8").strip()

	def load_policy_sections(self) -> list[PolicySection]:
		text = self.load_policies_text()
		if not text:
			return []

		sections: list[PolicySection] = []
		current_title = "General"
		current_lines: list[str] = []

		for raw_line in text.splitlines():
			line = raw_line.strip()
			if self._is_section_heading(line):
				if current_lines:
					sections.append(
						PolicySection(title=current_title, content="\n".join(current_lines).strip())
					)
					current_lines = []
				current_title = self._normalize_heading(line)
			elif line:
				current_lines.append(line)

		if current_lines:
			sections.append(PolicySection(title=current_title, content="\n".join(current_lines).strip()))

		return [section for section in sections if section.content]

	def find_relevant_policy_sections(
		self,
		keywords: list[str],
		*,
		max_sections: int = 5,
	) -> dict[str, object]:
		sections = self.load_policy_sections()
		normalized_keywords = [keyword.strip().lower() for keyword in keywords if keyword.strip()]

		if not sections:
			return {
				"success": True,
				"keywords": normalized_keywords,
				"matches": [],
				"reason": "No policy sections were found.",
			}

		if not normalized_keywords:
			selected = sections[:max_sections]
			return {
				"success": True,
				"keywords": [],
				"matches": [
					{"title": section.title, "content": section.content, "score": 0}
					for section in selected
				],
				"reason": "No keywords provided, returning leading sections.",
			}

		scored: list[tuple[int, PolicySection]] = []
		for section in sections:
			text = f"{section.title} {section.content}".lower()
			score = sum(text.count(keyword) for keyword in normalized_keywords)
			if score > 0:
				scored.append((score, section))

		scored.sort(key=lambda item: item[0], reverse=True)
		selected_scored = scored[:max_sections]

		return {
			"success": True,
			"keywords": normalized_keywords,
			"matches": [
				{"title": section.title, "content": section.content, "score": score}
				for score, section in selected_scored
			],
			"reason": "Matched by keyword frequency.",
		}

	def search_knowledge_base(self, query: str, *, max_sections: int = 5) -> dict[str, object]:
		keywords = self._extract_keywords(query)
		result = self.find_relevant_policy_sections(keywords, max_sections=max_sections)
		result["query"] = query
		return result

	@staticmethod
	def _is_section_heading(line: str) -> bool:
		return line.startswith("## ") or (
			line.endswith(":") and len(line) <= 90 and not line.startswith("-")
		)

	@staticmethod
	def _normalize_heading(line: str) -> str:
		if line.startswith("## "):
			return line[3:].strip()
		return line[:-1].strip() if line.endswith(":") else line.strip()

	@staticmethod
	def _extract_keywords(query: str) -> list[str]:
		tokens = re.findall(r"[a-zA-Z0-9_]+", query.lower())
		stop_words = {
			"the",
			"a",
			"an",
			"is",
			"are",
			"to",
			"for",
			"of",
			"and",
			"or",
			"on",
			"in",
			"with",
			"can",
			"i",
			"we",
		}
		return [token for token in tokens if len(token) > 2 and token not in stop_words]

