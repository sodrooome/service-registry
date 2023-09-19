import unittest
from service_registry import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerException,
)


def mock_remote_call():
    return "Success"


def mock_failed_remote_call():
    raise Exception("Mock Error")


class TestCircuitBreakerService(unittest.TestCase):
    def setUp(self) -> None:
        self.circuit_breaker = CircuitBreaker(threshold=3, timeout=5)

    def test_initial_state(self):
        self.assertEqual(self.circuit_breaker.state, CircuitBreakerState.CLOSED)
        self.assertEqual(self.circuit_breaker.failure_counts, 0)

    def test_open_state(self):
        self.circuit_breaker.state = CircuitBreakerState.OPEN
        self.assertFalse(self.circuit_breaker.handle_open_state())

    def test_closed_state(self):
        self.circuit_breaker.state = CircuitBreakerState.CLOSED
        self.assertFalse(self.circuit_breaker.handle_open_state())

    def test_reset_state(self):
        self.circuit_breaker.last_time_of_failure = self.circuit_breaker.timestamp - 10
        self.assertTrue(self.circuit_breaker.handle_reset_state())

    def test_remote_call_in_closed_state(self):
        result = self.circuit_breaker.make_remote_call(mock_remote_call)
        self.assertEqual(result, "Success")
        self.assertEqual(self.circuit_breaker.state, CircuitBreakerState.CLOSED)

    def test_failed_remote_call_in_closed_state(self):
        with self.assertRaises(CircuitBreakerException):
            self.circuit_breaker.make_remote_call(mock_failed_remote_call)

        self.assertEqual(self.circuit_breaker.state, CircuitBreakerState.CLOSED)
        self.assertEqual(self.circuit_breaker.failure_counts, 1)


if __name__ == "__main__":
    unittest.main()
