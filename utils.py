import requests
from time import time
from config import DEFAULT_HEADERS


def check_downstream_health(
    services_dict: dict, headers: dict = None
) -> dict[str, any]:
    """
    Utility function to check the health of downstream services,
    it will return the status of each service and the overall status of all services
    """
    services = []
    # falback to default headers if no custom headers provided
    if headers is None:
        headers = DEFAULT_HEADERS

    all_healthy = True
    any_healthy = False

    for name, url in services_dict.items():
        try:
            response = requests.get(url, headers=headers, timeout=10)
            status_code = response.status_code
            healthy = status_code == 200
            try:
                body = response.json()
            except ValueError:
                body = response.text
        except requests.RequestException as e:
            status_code = 0
            healthy = False
            body = str(e)

        if healthy:
            any_healthy = True
        else:
            all_healthy = False

        services.append(
            {
                "name": name,
                "url": url,
                "status_code": status_code,
                "healthy": healthy,
                "response": body,
            }
        )

    if all_healthy:
        status = "healthy"
    elif any_healthy:
        status = "degraded"
    else:
        status = "unhealthy"

    return {
        "status": status,
        "timestamp": int(time() * 1000),
        "services": services,
    }
