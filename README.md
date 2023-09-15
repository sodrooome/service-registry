## Service Registry

Service Registry is a library designed to simulate the 3rd parties that will invoke our distributed systems by isolating these external parties. It's eventually built upon a service registry pattern by implementing a basic circuit breaker

### Context

This will give you a hint or context regarding what problems will be solved (or can be simulated) with this library

- How do the internal client will know about the available instances?
- How can we self-register one of the services down to a service still available?
- How do we handle the failure services without intersecting with other services?

### Features

Given the context, we can implement several features that might help in the process of overcoming all of those problems such as:

- Circuit breaker
- Service registry (self-assigned services based on the available instance)
- Distributed services tracing (trace all of the failure and success counts)
- Built-in logging mechanism
- Gracefully shutdown a certain service

### Usage

In the code there are several procedures to simulate this library, you can just run it by

```sh
$ python service_registry.py
```

And it will lead you to the logs output like :

```sh
15-09-2023 08:51:04 : service_registry.py : log : Success registered the service name
15-09-2023 08:51:04 : service_registry.py : log : Success registered the service name
15-09-2023 08:51:04 : service_registry.py : log : Success registered the service name
15-09-2023 08:51:04 : service_registry.py : log : Related service is healthy
15-09-2023 08:51:04 : service_registry.py : log : Related service is healthy
15-09-2023 08:51:04 : service_registry.py : log : Related service is healthy
{'GetSinglePost': {'url': 'https://jsonplaceholder.typicode.com/posts/1', 'assigned': False, 'assigned_service': None, 'availability': 'AVAILABLE'}, 'GetAllPosts': {'url': 'https://jsonplaceholder.typicode.com/posts', 'assigned': False, 'assigned_service': None, 'availability': 'STARTING'}}
15-09-2023 08:51:09 : service_registry.py : log : Related service is healthy
15-09-2023 08:51:09 : service_registry.py : log : Related service is healthy
15-09-2023 08:51:09 : service_registry.py : log : Related service is healthy
15-09-2023 08:51:09 : service_registry.py : log : Related service is healthy
{'total_requests': 1, 'successful_requests': 1, 'failure_requests': 0, 'duration': 0.0}
{'total_requests': 1, 'successful_requests': 1, 'failure_requests': 1, 'duration': 0.0}
15-09-2023 08:51:09 : service_registry.py : log : Success assigned one service to the available service
15-09-2023 08:51:09 : service_registry.py : log : Success assigned one service to the available service
15-09-2023 08:51:09 : service_registry.py : log : Success assigned one service to the available service
15-09-2023 08:51:09 : service_registry.py : log : Success assigned one service to the available service
15-09-2023 08:51:09 : service_registry.py : log : Success assigned one service to the available service
https://jsonplaceholder.typicode.com/posts
15-09-2023 08:51:09 : service_registry.py : log : Deleted GetSinglePost service instance
15-09-2023 08:51:09 : service_registry.py : log : Deleted GetSinglePost service instance
15-09-2023 08:51:09 : service_registry.py : log : Deleted GetSinglePost service instance
15-09-2023 08:51:09 : service_registry.py : log : Deleted GetSinglePost service instance
15-09-2023 08:51:09 : service_registry.py : log : Deleted GetSinglePost service instance
15-09-2023 08:51:09 : service_registry.py : log : Deleted GetSinglePost service instance
```

Or, you can adjust the procedure for running it in accordance with what you want to do (you might need to take a look in the built-in APIs directly from the source code to ensure what's the public method that you want to initialize)

### Caveats

Currently, this library doesn't support the asynchronous method so the choice of assigned available service will be based on the first index (this will lead to a problem if the service is also down)

### Acknowledgment

Perpetually, all of those implementations in this library are actually inspired by Hystrix-like from [Netflix](https://github.com/Netflix/Hystrix), and also the whole concept follows the instructions of the microservices pattern (you might read it [here](https://microservices.io/patterns/index.html)).

While it doesn't cover all of the crucial aspects that follow in the Hystrix, to be exact, this library describes what it would be like to simulate a service going down without causing other services to go as well
