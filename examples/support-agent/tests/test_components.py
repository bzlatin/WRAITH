"""Component tests independent of Wraith; keep these frozen during the trial."""

import unittest
from support_agent.catalog import search, words
from support_agent.orders import lookup
from support_agent.agent import Session


class CatalogTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(words("Can I return?"), ["refund"])

    def test_current_policy(self):
        self.assertEqual(search("refund", "public")[0]["id"], "refund-current")

    def test_audience_filter(self):
        self.assertEqual(search("staff discount", "public"), [])
        self.assertEqual(search("staff discount", "staff")[0]["id"], "discount-staff")

    def test_missing_evidence(self):
        self.assertEqual(search("quantum entanglement", "public"), [])


class OrderTests(unittest.TestCase):
    def test_own_order(self):
        self.assertEqual(lookup("A100", "alice"), {"id": "A100", "status": "shipped"})

    def test_foreign_order(self):
        self.assertIsNone(lookup("B200", "alice"))

    def test_unknown_order(self):
        self.assertIsNone(lookup("missing", "alice"))


class WorkflowTests(unittest.TestCase):
    def test_order_route(self):
        result = Session().ask(
            {"question": "order status", "order_id": "A100", "customer": "alice"}
        )
        self.assertEqual(result["status"], "answered")
        self.assertIn("shipped", result["text"])

    def test_unknown_escalates(self):
        self.assertEqual(
            Session().ask({"question": "quantum entanglement"})["status"], "escalated"
        )


if __name__ == "__main__":
    unittest.main()
