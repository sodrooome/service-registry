import logging
import requests
import time
import threading
import enum
import typing
from config import DEFAULT_HEADERS
from metrics import record_event


class CircuitBreakerException(Exception):
    """Exception that arises when remote call is failed"""


class RequestCallException(Exception):
    """Exception that arises when request is failed"""


class CircuitBreakerState(enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF"


class ServiceRegistryState(enum.Enum):
    STARTING = "STARTING"
    AVAILABLE = "AVAILABLE"
    DOWN = "DOWN"


class CircuitBreaker:
    def __init__(self, threshold: int, timeout: int) -> None:
        self.threshold = threshold
        self.timeout = timeout
        self.failure_counts = 0  # initial of failures
        self.state = CircuitBreakerState.CLOSED
        self.last_time_of_failure = None
        self.timestamp = time.time()

        # lock to guard all shared state against concurrent access
        self._lock = threading.Lock()

    def open(self) -> None:
        self.state = CircuitBreakerState.OPEN
        self.last_time_of_failure = time.time()

    def close(self) -> None:
        self.state = CircuitBreakerState.CLOSED
        self.failure_counts = 0

    def half_open(self) -> None:
        self.state = CircuitBreakerState.HALF_OPEN

    def handle_open_state(self) -> bool:
        return self.failure_counts >= self.threshold

    def handle_reset_state(self) -> typing.Any:
        return time.time() - self.last_time_of_failure >= self.timeout

    def make_remote_call(self, func) -> typing.Any:
        # acquire lock for the full state between check and transition
        with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if not self.handle_reset_state():
                    raise CircuitBreakerException(
                        "Circuit is still OPEN, call rejected until timeout exhausted"
                    )
                self.half_open()

        try:
            result_value = func()
            with self._lock:
                if self.state == CircuitBreakerState.HALF_OPEN:
                    self.close()
            return result_value
        except Exception as e:
            with self._lock:
                self.failure_counts += 1
                if self.handle_open_state():
                    self.open()
            raise CircuitBreakerException(f"Remote call failed: {e}") from e


# wrapped it as around decorator so it's easily extended
# onto ServiceRegistry() classes
def circuit_breaker(threhsold: int, timeout: int):
    def decorator(func):
        def wrapper(self, service_name, *args, **kwargs):
            # one breaker per service so when a failing one
            # won't be tripping the breaker for health checks
            breaker = self._circuit_breakers.setdefault(
                service_name, CircuitBreaker(threhsold, timeout)
            )
            return breaker.make_remote_call(
                lambda: func(self, service_name, *args, **kwargs)
            )

        return wrapper

    return decorator


class ServiceRegistry:
    def __init__(self) -> None:
        self.registered_services = {}
        self.health_check_interval = 5  # in seconds
        # atexit.register(self.deregister_all_services)
        self.service_tracing = {
            "total_requests": 0,
            "successful_requests": 0,
            "failure_requests": 0,
            "duration": 0,
        }
        self.timestamp = time.time()
        self._lock = threading.Lock()
        self._setup_logger()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def _setup_logger(self) -> None:
        self.logger = logging.getLogger(f"service_registry_{id(self)}")
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s : %(filename)s : %(funcName)s : %(message)s",
                    datefmt="%d-%m-%Y %I:%M:%S",
                ),
            )
            self.logger.addHandler(handler)
        self.logger.propagate = False

    def log(self, message: str) -> None:
        self.logger.info(message)

    def register_services(self, service_name: str, service_url: str) -> None:
        with self._lock:
            if service_name in self.registered_services:
                raise ValueError(
                    "Service already registered, please use another service name"
                )
            self.registered_services[service_name] = {
                "url": service_url,
                "service_name": service_name,
                "assigned": False,
                "assigned_service": None,
                "healthy": True,
                "availability": ServiceRegistryState.STARTING,
            }
        self.log("Success registered the service name")
        record_event(service_name, "service_registered", service_url)

    def get_service(self, service_name: str) -> str:
        with self._lock:
            if service_name not in self.registered_services:
                raise ValueError(
                    "Service name is not registered in the list of service register"
                )
            if not self.registered_services[service_name]["healthy"]:
                raise ValueError("Service name is not healthy")
            return self.registered_services[service_name]["url"]

    @property
    def list_of_all_services(self) -> list:
        with self._lock:
            return list(self.registered_services.keys())

    def simulate_service_is_unhealthy(self, service_name: str) -> None:
        changed = False
        with self._lock:
            if service_name not in self.registered_services:
                raise ValueError(
                    "Service name is not registered in the list of service register"
                )

            service_availability = self.registered_services[service_name][
                "availability"
            ]

            if self.registered_services[service_name]["healthy"]:
                if service_availability == ServiceRegistryState.AVAILABLE:
                    # simulate when the service is healthy, change the
                    # availability, healthy status to down and also
                    # increase the numbers of failure count
                    self.registered_services[service_name][
                        "availability"
                    ] = ServiceRegistryState.DOWN
                    self.registered_services[service_name]["healthy"] = False
                    self.service_tracing["failure_requests"] += 1
                    changed = True
        if changed:
            record_event(service_name, "service_failure", "simulated failure")

    def _get_service_name_url(self, service_name: str) -> str:
        if service_name in self.registered_services:
            return self.registered_services[service_name]["url"]
        return None

    def get_available_services(self, service_name: str) -> str:
        with self._lock:
            if service_name in self.registered_services:
                if self.registered_services[service_name]["assigned"]:
                    assigned_service = self.registered_services[service_name][
                        "assigned_service"
                    ]
                    return self._get_service_name_url(assigned_service)

            if service_name in self.registered_services:
                if self.registered_services[service_name]["healthy"]:
                    return self._get_service_name_url(service_name)

            available_services = [
                name
                for name, data in self.registered_services.items()
                if data["availability"] == ServiceRegistryState.AVAILABLE
            ]

            # currently, this function would be picked
            # the available service based on the first index
            if available_services:
                return self._get_service_name_url(available_services[0])

        return None

    def gracefully_shutdown(self, service_name: str) -> None:
        with self._lock:
            if service_name in self.registered_services:
                self.registered_services[service_name][
                    "availability"
                ] = ServiceRegistryState.DOWN
        self.deregister_service(service_name)

    def _health_check(self) -> None:
        while True:
            try:
                # snapshot the lock before iterating avoiding race condition
                with self._lock:
                    service_names = list(self.registered_services.keys())

                for service_name in service_names:
                    try:
                        self._simulate_health_check(service_name=service_name)
                    except CircuitBreakerException as e:
                        self.log(f"Health check skipped for {service_name}")
            except Exception as e:
                self.log(f"Health check error: {e}")
            time.sleep(self.health_check_interval)

    def _make_http_request(self, service_url: str) -> requests.Response:
        response = requests.get(url=service_url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
        return response

    @circuit_breaker(threhsold=3, timeout=5)
    def _simulate_health_check(self, service_name: str) -> bool:
        try:
            with self._lock:
                if service_name not in self.registered_services:
                    return None
                service_url = self.registered_services[service_name]["url"]
                previous_availability = self.registered_services[service_name][
                    "availability"
                ]

            response = self._make_http_request(service_url)

            if response.status_code == 200:
                with self._lock:
                    self.registered_services[service_name][
                        "availability"
                    ] = ServiceRegistryState.AVAILABLE
                    self.registered_services[service_name]["healthy"] = True
                    self.service_tracing["successful_requests"] += 1
                self.log("Related service is healthy")
                if previous_availability != ServiceRegistryState.AVAILABLE:
                    record_event(
                        service_name,
                        "health_check_healthy",
                        "state changed to AVAILABLE",
                    )
                return True
        except requests.exceptions.RequestException as e:
            previous_availability = None
            with self._lock:
                if service_name in self.registered_services:
                    previous_availability = self.registered_services[service_name][
                        "availability"
                    ]
                    self.registered_services[service_name][
                        "availability"
                    ] = ServiceRegistryState.DOWN
                    self.registered_services[service_name]["healthy"] = False
                    self.service_tracing["failure_requests"] += 1
            self.log(f"Related service is unhealthy due to error: {e}")
            if (
                previous_availability is not None
                and previous_availability != ServiceRegistryState.DOWN
            ):
                record_event(
                    service_name, "health_check_unhealthy", "state changed to DOWN"
                )
            raise
        return False

    def assign_service(self, service_name: str, assigned_service_name: str) -> None:
        assigned = False
        with self._lock:
            if service_name in self.registered_services:
                if assigned_service_name in self.registered_services:
                    if self.registered_services[assigned_service_name]["healthy"]:
                        self.registered_services[service_name]["assigned"] = True
                        self.registered_services[service_name][
                            "assigned_service"
                        ] = assigned_service_name
                        self.log(
                            "Success assigned one service to the available service"
                        )
                        assigned = True
                    else:
                        self.log(
                            "Failed to assigned one service to the available service"
                        )
        if assigned:
            record_event(
                service_name,
                "service_assigned",
                f"{service_name} assigned to {assigned_service_name}",
            )

    def deregister_service(self, service_name: str) -> None:
        with self._lock:
            if service_name not in self.registered_services:
                raise ValueError(
                    "Service name is not registered in the list of service register"
                )
            del self.registered_services[service_name]
            # drop any circuit breaker for this service
            self._circuit_breakers.pop(service_name, None)
        self.log(f"Deleted {service_name} service instance")
        record_event(service_name, "service_deregistered", service_name)

    def deregister_all_services(self) -> None:
        # i'm not sure why this method would be called
        # after the process is completed
        for service_name in self.list_of_all_services:
            try:
                self.deregister_service(service_name)
            except ValueError:
                pass  # already removed during concurrent process
        self.log("Deleted all registered services name")

    def start_health_check(self) -> None:
        health_check_thread = threading.Thread(target=self._health_check)
        health_check_thread.daemon = True
        health_check_thread.start()

    def get_services_information(self) -> dict:
        services_result = {}
        with self._lock:
            for service_name, service_data in self.registered_services.items():
                services_result[service_name] = {
                    "url": service_data["url"],
                    "assigned": service_data["assigned"],
                    "assigned_service": service_data["assigned_service"],
                    "availability": service_data["availability"].value,
                }
        return services_result

    def trace_service_request(self, service_name: str) -> None:
        start_time = time.time()

        with self._lock:
            if service_name not in self.registered_services:
                raise ValueError(
                    "Service name is not registered in the list of service register"
                )

        try:
            # simulate a request to the certain service
            time.sleep(0.5)
            success = True
        except Exception as e:
            success = False
            raise RequestCallException
        finally:
            end_time = time.time()
            duration = end_time - start_time

            with self._lock:
                self.service_tracing["total_requests"] += 1
                if success:
                    self.service_tracing["successful_requests"] += 1
                else:
                    self.service_tracing["failure_requests"] += 1

                self.service_tracing["duration"] += duration

        record_event(service_name, "request_traced", service_name)


class ServiceRegistryManagement(ServiceRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.dependency_map = {}

    def register_dependency(self, service_name: str, depends_on: str) -> None:
        if service_name not in self.dependency_map:
            self.dependency_map[service_name] = []
        self.dependency_map[service_name].append(depends_on)
        self.log(
            f"Successful register the dependencies between {service_name} that depends on {depends_on} services"
        )
        record_event(
            service_name,
            "dependency_registered",
            f"{service_name} depends on {depends_on}",
        )

    def get_dependencies(self, service_name: str) -> typing.Any:
        return self.dependency_map.get(service_name, [])

    def is_service_ready(self, service_name: str) -> bool:
        dependencies = self.get_dependencies(service_name)
        return all(self.get_available_services(dep) for dep in dependencies)

    def wait_for_dependencies(self, service_name: str, timeout: int = 30) -> bool:
        start_time = time.time()
        while not self.is_service_ready(service_name):
            if time.time() - start_time > timeout:
                return False
            # for now just align the sleep interval with the health check
            time.sleep(self.health_check_interval)
        return True
