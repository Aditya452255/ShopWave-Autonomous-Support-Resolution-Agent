from __future__ import annotations

import unittest

from ui_app import _build_table_rows, render_metric_cards, render_ticket_details


class UiHelpersTests(unittest.TestCase):
	def test_render_metric_cards_contains_key_values(self) -> None:
		html = render_metric_cards(
			{
				"total_tickets": 5,
				"resolved": 3,
				"escalated": 2,
				"failed_safe": 1,
				"backend": "deterministic",
				"audit_log": "artifacts/audit_log.json",
			}
		)

		self.assertIn("Total Tickets", html)
		self.assertIn(">5<", html)
		self.assertIn("DETERMINISTIC", html)
		self.assertIn("Available", html)

	def test_build_table_rows_falls_back_to_default_short_reason(self) -> None:
		rows = _build_table_rows(
			[
				{
					"ticket_id": "T-1",
					"case_type": "refund",
					"final_decision": "approve",
					"confidence": {"score": 0.92},
					"short_reason": "",
					"detailed_reason": "",
					"final_reason_summary": "Policy checks passed.",
				}
			]
		)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0][0], "T-1")
		self.assertEqual(rows[0][4], "Approved: policy checks passed")
		self.assertEqual(rows[0][5], "Policy checks passed.")

	def test_render_ticket_details_handles_invalid_state(self) -> None:
		overview, trace, audit, escalation = render_ticket_details("T-1", "{bad json")
		self.assertIn("Select a ticket", overview)
		self.assertIn("Select a ticket", trace)
		self.assertEqual(audit, "{}")
		self.assertIn("No escalation", escalation)


if __name__ == "__main__":
	unittest.main()
