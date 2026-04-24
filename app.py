from flask import Flask, request, jsonify
from service_registry import ServiceRegistryManagement

app = Flask(__name__)


registry = ServiceRegistryManagement()
registry.start_health_check()


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "OK"}), 200


# register the relevant/particular downstream services here so it can be exposed through Flask APIs
@app.route("/api/services", methods=["POST"])
def register_service():
    data = request.get_json()

    service_name = data.get("service_name")
    service_url = data.get("service_url")

    if not service_name or not service_url:
        return jsonify({"error": "missing service name or service URL"}), 400

    try:
        registry.register_services(service_name=service_name, service_url=service_url)
        return jsonify({"message": "service registered"}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# list down all the registered services
@app.route("/api/services", methods=["GET"])
def list_of_services():
    return jsonify(registry.get_services_information()), 200


# get particular service URL based on service name
@app.route("/api/service/<service_name>", methods=["GET"])
def get_service(service_name):
    try:
        url = registry.get_available_services(service_name=service_name)
        if not url:
            return jsonify({"error": "There's no available service"}), 404

        return jsonify({"service_name": service_name, "url": url}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# assigne particular service
@app.route("/api/services/assign", methods=["GET"])
def assign_service():
    data = request.get_json()

    service_name = data.get("service_name")
    assigned_service = data.get("assigned_service")

    if not service_name or not assigned_service:
        return jsonify({"error": "missing parameter"}), 400

    registry.assign_service(
        service_name=service_name, assigned_service_name=assign_service
    )
    return jsonify({"message": "Successfully assigned particular service"}), 200


# simulate all the failures or chaos
@app.route("/api/services/<service_name>/fail", methods=["POST"])
def simulate_fail_service(service_name):
    try:
        registry.simulate_service_is_unhealthy(service_name=service_name)
        return jsonify({"message": "marked this service is unhealthy"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# trace the metrics log between each registered services
@app.route("/api/metrics", methods=["GET"])
def metrics():
    return jsonify(registry.service_tracing), 200


# delete particular service
@app.route("/api/services/<service_name>", methods=["DELETE"])
def delete_service(service_name):
    try:
        registry.deregister_service(service_name=service_name)
        return jsonify({"message": "service deregistered"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# check for readiness of the service registry
@app.route("/api/services/<service_name>/ready", methods=["GET"])
def check_readiness(service_name):
    is_ready = registry.is_service_ready(service_name=service_name)
    if is_ready:
        return jsonify({"message": "Service is ready"}), 200
    else:
        return jsonify({"message": "Service is not ready"}), 503


# simulate request
@app.route("/api/services/<service_name>/call", methods=["POST"])
def simulate_call_request(service_name):
    try:
        registry.trace_service_request(service_name=service_name)
        return jsonify({"message": "Request traced successfully"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# dependencies for the service registry
@app.route("/api/dependencies", methods=["POST"])
def add_dependency():
    data = request.get_json()

    service_name = data.get("service_name")
    depends_on = data.get("depends_on")

    if not service_name or not depends_on:
        return jsonify({"error": "Missing parameters"}), 400

    registry.register_dependency(service_name=service_name, depends_on=depends_on)
    return jsonify({"message": "Dependency registered successfully"}), 201


if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
