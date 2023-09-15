import logging
import requests
import time
import threading
import atexit
import enum
import typing


class CircuitBreakerException(BaseException):
    """Exception that arises when remote call is failed"""


class RequestCallException(BaseException):
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

    def open(self) -> None:
        self.state = CircuitBreakerState.OPEN
        self.last_time_of_failure = self.timestamp

    def close(self) -> None:
        self.state = CircuitBreakerState.CLOSED
        self.failure_counts = 0

    def half_open(self) -> None:
        self.state = CircuitBreakerState.HALF_OPEN

    def handle_open_state(self) -> bool:
        return self.failure_counts >= self.threshold

    def handle_reset_state(self) -> typing.Any:
        return self.timestamp - self.last_time_of_failure >= self.timeout

    def make_remote_call(self, func) -> typing.Any:
        if self.state == CircuitBreakerState.OPEN:
            if not self.handle_reset_state():
                return None

        try:
            result_value = func()
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.close()
            return result_value
        except Exception as e:
            self.failure_counts += 1
            if self.handle_open_state():
                self.open()
            raise CircuitBreakerException


# wrapped it as around decorator so it's easily extended
# onto ServiceRegistry() classes
def circuit_breaker(threhsold: int, timeout: int):
    def decorator(func):
        circuit_breaker = CircuitBreaker(threhsold, timeout)

        def wrapper(*args, **kwargs):
            return circuit_breaker.make_remote_call(lambda: func(*args, **kwargs))

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

    def log(self, message: str) -> None:
        logger = logging.getLogger("http_service_registry_logs")
        log_handler = logging.StreamHandler()
        log_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s : %(filename)s : %(funcName)s : %(message)s",
                datefmt="%d-%m-%Y %I:%M:%S",
            ),
        )
        logger.addHandler(log_handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = True
        logger.info(message)

    def register_services(self, service_name: str, service_url: str) -> None:
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

    def get_service(self, service_name: str) -> str:
        if service_name not in self.registered_services:
            raise ValueError(
                "Service name is not registered in the list of service register"
            )
        if not self.registered_services[service_name]["healthy"]:
            raise ValueError("Service name is not healthy")
        return self.registered_services[service_name]["url"]

    @property
    def list_of_all_services(self) -> list:
        return list(self.registered_services.keys())

    def simulate_service_is_unhealthy(self, service_name: str) -> None:
        if service_name not in self.registered_services:
            raise ValueError(
                "Service name is not registered in the list of service register"
            )

        service_availability = self.registered_services[service_name]["availability"]

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

    def _get_service_name_url(self, service_name: str) -> str:
        if service_name in self.registered_services:
            return self.registered_services[service_name]["url"]
        return None

    def get_available_services(self, service_name: str) -> str:
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
            return self._get_service_name_url(available_services)

        return None

    def gracefully_shutdown(self, service_name: str) -> None:
        if service_name in self.registered_services:
            self.registered_services[service_name][
                "availability"
            ] = ServiceRegistryState.DOWN
            self.deregister_service(service_name)

    def _health_check(self) -> None:
        while True:
            for service_name in self.registered_services:
                is_service_healthy = self._simulate_health_check(service_name)
                self.registered_services[service_name]["healthy"] = is_service_healthy
            time.sleep(self.health_check_interval)

    def _make_http_request(self, service_url: str) -> requests.Response:
        session = requests.Session()
        response = session.get(url=service_url)
        response.raise_for_status()
        return response

    @circuit_breaker(threhsold=3, timeout=5)
    def _simulate_health_check(self, service_name: str) -> None:
        while True:
            try:
                service_url = self.registered_services[service_name]["url"]
                response = self._make_http_request(service_url)
                if response.status_code == 200:
                    if self.registered_services[service_name]["healthy"]:
                        self.registered_services[service_name][
                            "availability"
                        ] = ServiceRegistryState.AVAILABLE
                        self.registered_services[service_name]["healthy"] = True
                        self.log("Related service is healthy")
                    else:
                        self.registered_services[service_name][
                            "availability"
                        ] = ServiceRegistryState.DOWN
                        self.registered_services[service_name]["healthy"] = False
                        self.log("Related service is unhealthy")
            except requests.exceptions.RequestException as e:
                self.registered_services[service_name]["healthy"] = False

                # marked all of the exceptions that occurs as failure request
                self.service_tracing["failure_requests"] += 1
                raise Exception(f"Unable to make a request due of error : {e}")

            time.sleep(self.health_check_interval)

    def assign_service(self, service_name: str, assigned_service_name: str) -> None:
        if service_name in self.registered_services:
            if assigned_service_name in self.registered_services:
                if self.registered_services[assigned_service_name]["healthy"]:
                    self.registered_services[service_name]["assigned"] = True
                    self.registered_services[service_name][
                        "assigned_service"
                    ] = assigned_service_name
                    self.log("Success assigned one service to the available service")
                else:
                    self.log("Failed to assigned one service to the available service")

    def deregister_service(self, service_name: str) -> None:
        if service_name not in self.registered_services:
            raise ValueError(
                "Service name is not registered in the list of service register"
            )
        del self.registered_services[service_name]
        self.log(f"Deleted {service_name} service instance")

    def deregister_all_services(self) -> None:
        # i'm not sure why this method would be called
        # after the process is completed
        for service_name in self.list_of_all_services:
            self.deregister_service(service_name)
            self.log("Deleted all registered services name")

    def start_health_check(self) -> None:
        health_check_thread = threading.Thread(target=self._health_check)
        health_check_thread.daemon = True
        health_check_thread.start()

    def get_services_information(self) -> dict:
        services_result = {}
        for service_name, service_data in self.registered_services.items():
            services_result[service_name] = {
                "url": service_data["url"],
                "assigned": service_data["assigned"],
                "assigned_service": service_data["assigned_service"],
                "availability": service_data["availability"].value,
            }
        return services_result

    def trace_service_request(self, service_name: str) -> None:
        start_time = self.timestamp

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
            end_time = self.timestamp
            duration = end_time - start_time

            self.service_tracing["total_requests"] += 1
            if success:
                self.service_tracing["successful_requests"] += 1
            else:
                self.service_tracing["failure_requests"] += 1

            self.service_tracing["duration"] += duration


if __name__ == "__main__":
    registry = ServiceRegistry()

    # register all the related services
    registry.register_services(
        "GetSinglePost", "https://jsonplaceholder.typicode.com/posts/1"
    )
    registry.register_services(
        "GetAllPosts", "https://jsonplaceholder.typicode.com/posts"
    )

    registry.start_health_check()

    check_duration = time.sleep(5)
    while check_duration:
        pass

    result_val = registry.get_services_information()
    print(result_val)

    # tracing between request
    registry.trace_service_request("GetSinglePost")
    print(registry.service_tracing)

    registry.get_service("GetSinglePost")

    # simulate the one of the services are unhealthy
    registry.simulate_service_is_unhealthy("GetSinglePost")

    print(registry.service_tracing)

    # assign the "unhealthy" services to the available service
    registry.assign_service("GetSinglePost", "GetAllPosts")

    get_url = registry.get_available_services("GetSinglePost")
    print(get_url)

    # this will thrown a failure since the service name is unhealthy
    # and all of the process will halted directly
    # registry.get_service("GetSinglePost")

    # de-register all of the services whether it's up or down
    # registry.deregister_all_services()

    # de-register a certain service based on the service name
    # registry.deregister_service("GetAllPosts")

    # gracefully shutdown a single service
    registry.gracefully_shutdown("GetSinglePost")

    # this will return the value as None since we already
    # gracefully shut-in down the GetSinglePost service
    get_url = registry.get_available_services("GetSinglePost")
    print(get_url)
