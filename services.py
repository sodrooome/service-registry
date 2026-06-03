from service_registry import ServiceRegistryManagement
from config import DOWNSTREAM_SERVICES

registry = ServiceRegistryManagement()

for name, url in DOWNSTREAM_SERVICES.items():
    registry.register_services(service_name=name, service_url=url)

# assign the services based on the dependency
registry.assign_service(
    service_name="FE-Chat-Health-Apache-Proxy",
    assigned_service_name="FE-Chat-Health-Node-Proxy",
)
registry.assign_service(
    service_name="FE-Chat-Health-Node-Proxy",
    assigned_service_name="BE-Chat-Health",
)

# register the dependencies between the services
# create a topology of the services based on the deps
registry.register_dependency(
    service_name="FE-Chat-Health-Node-Proxy",
    depends_on="BE-Chat-Health",
)
registry.register_dependency(
    service_name="FE-Chat-Health-Apache-Proxy",
    depends_on="FE-Chat-Health-Node-Proxy",
)
registry.register_dependency(
    service_name="Maukerja-Server",
    depends_on="V3-API-BE",
)
registry.register_dependency(
    service_name="Maukerja-Server",
    depends_on="BE-Chat-Health",
)

# start the health check for the downstream services
registry.start_health_check()
