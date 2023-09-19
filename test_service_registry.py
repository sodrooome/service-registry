import unittest
import time
from service_registry import ServiceRegistry, ServiceRegistryState


class TestServiceRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.service_registry = ServiceRegistry()
        self.service_registry.register_services(
            "GetSinglePost", "https://jsonplaceholder.typicode.com/posts/1"
        )
        self.service_registry.register_services(
            "GetSecondPost", "https://jsonplaceholder.typicode.com/posts/2"
        )

        self.service_registry.start_health_check()

        check_duration = time.sleep(5)
        while check_duration:
            pass

    def test_check_the_services_is_healthy(self):
        self.assertTrue(
            self.service_registry.registered_services["GetSinglePost"]["healthy"]
        )
        self.assertEqual(
            self.service_registry.registered_services["GetSecondPost"]["availability"],
            ServiceRegistryState.STARTING,
        )

    def test_simulate_services_is_unhealthy(self):
        self.service_registry.simulate_service_is_unhealthy("GetSinglePost")
        self.service_registry.log("(Simulated) service marked as a unhealthy")

        self.assertFalse(
            self.service_registry.registered_services["GetSinglePost"]["healthy"]
        )
        self.assertEqual(self.service_registry.service_tracing["failure_requests"], 1)

    def test_get_available_services(self):
        self.assertEquals(
            self.service_registry.get_available_services("GetSinglePost"),
            "https://jsonplaceholder.typicode.com/posts/1",
        )

    def test_failed_service_url(self):
        with self.assertRaises(ValueError):
            self.service_registry.register_services(
                "GetThirdPost", "http://jsonplaceholder.typicode.com/posts/1"
            )

        # self.assertEqual(
        #     self.service_registry.registered_services["GetThirdPost"],
        #     ServiceRegistryState.DOWN,
        # )

    def test_get_unregistered_services(self):
        with self.assertRaises(ValueError):
            self.service_registry.get_service("GetThirdPost")

    def test_gracefully_shutdown_single_service(self):
        self.assertIsNone(self.service_registry.gracefully_shutdown("GetSecondPost"))

    def test_deregister_all_services(self):
        self.assertIsNone(self.service_registry.deregister_all_services())

    def test_get_services_information(self):
        self.assertEqual(
            self.service_registry.get_service("GetSecondPost"),
            "https://jsonplaceholder.typicode.com/posts/2",
        )

        expected_result = {
            "GetSinglePost": {
                "url": "https://jsonplaceholder.typicode.com/posts/1",
                "assigned": False,
                "assigned_service": None,
                "availability": "AVAILABLE",
            },
            "GetSecondPost": {
                "url": "https://jsonplaceholder.typicode.com/posts/2",
                "assigned": False,
                "assigned_service": None,
                "availability": "STARTING",
            },
        }
        self.assertEqual(
            self.service_registry.get_services_information(), expected_result
        )


if __name__ == "__main__":
    unittest.main()
