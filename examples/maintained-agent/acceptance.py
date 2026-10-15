"""New targeted unit tests, kept separate from unchanged upstream tests."""

import functools
import sys
import unittest
from unittest.mock import Mock

from smolagents import ToolCallingAgent
from smolagents.models import Model
from smolagents.utils import AgentError


class ValidationTests(unittest.TestCase):
    def test_false_callable_is_a_validation_error(self):
        class Checker:
            def __call__(self, answer, memory, agent):
                return False

        def reject(answer, memory, agent):
            return False

        for checker in (Checker(), functools.partial(reject)):
            with self.subTest(checker=type(checker).__name__):
                agent = ToolCallingAgent(
                    tools=[],
                    model=Mock(spec=Model),
                    final_answer_checks=[checker],
                    verbosity_level=-1,
                )
                with self.assertRaises(AgentError):
                    agent._validate_final_answer("rejected")


if __name__ == "__main__":
    # Existing upstream tests are the independent acceptance checks for the other
    # fixes (including optimized execution and strict generator warnings).
    suite = unittest.TestSuite()
    if sys.argv[1] in ("callable-diagnostics", "combined"):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ValidationTests)
    sys.exit(
        0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    )
