# src/core/container/service_container.py
from typing import Any, Callable, Dict, Optional

class ServiceContainer:
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._singletons: Dict[str, Any] = {} # Stores already instantiated singletons

    def register_service(self, name: str, service: Any, singleton: bool = False):
        """Registers a pre-instantiated service.
        If singleton is True, this instance will always be returned.
        """
        if name in self._services or name in self._factories:
            raise ValueError(f"Service or factory with name '{name}' already registered.")
        if singleton:
            self._singletons[name] = service
        self._services[name] = service
        print(f"Service '{name}' registered {'as singleton' if singleton else ''}.")

    def register_factory(self, name: str, factory: Callable[[], Any], singleton: bool = False):
        """Registers a factory function to create a service.
        If singleton is True, the factory will be called once and the instance reused.
        """
        if name in self._services or name in self._factories:
            raise ValueError(f"Service or factory with name '{name}' already registered.")
        self._factories[name] = factory
        if singleton:
            # Mark as a singleton factory, but don't instantiate yet
            self._singletons[name] = None # Placeholder to indicate it's a singleton
        print(f"Factory for '{name}' registered {'as singleton' if singleton else ''}.")

    def get_service(self, name: str) -> Any:
        """Retrieves a service by its name."""
        # Check singletons first
        if name in self._singletons:
            if self._singletons[name] is None and name in self._factories: # Singleton factory not yet instantiated
                print(f"Instantiating singleton factory for '{name}'...")
                self._singletons[name] = self._factories[name]()
            if self._singletons[name] is not None: # Pre-registered singleton or instantiated factory
                 return self._singletons[name]
            # If it was registered as a singleton service directly
            if name in self._services and self._services[name] is self._singletons.get(name):
                return self._services[name]


        # Check factories for non-singleton instances
        if name in self._factories:
            print(f"Creating new instance of '{name}' from factory.")
            return self._factories[name]()

        # Check pre-instantiated non-singleton services
        if name in self._services:
            return self._services[name]

        raise ValueError(f"Service or factory with name '{name}' not found.")

    def is_registered(self, name: str) -> bool:
        """Checks if a service or factory is registered."""
        return name in self._services or name in self._factories

if __name__ == '__main__':
    # Example Usage
    container = ServiceContainer()

    # Dummy classes for example
    class DatabaseService:
        def __init__(self, connection_string: str):
            self.connection_string = connection_string
            print(f"DatabaseService initialized with {connection_string}")
        def query(self, sql: str):
            return f"Executing query: {sql}"

    class UserService:
        def __init__(self, db_service: DatabaseService):
            self.db_service = db_service
            print("UserService initialized")
        def get_user(self, user_id: int):
            return self.db_service.query(f"SELECT * FROM users WHERE id = {user_id}")

    # 1. Register a factory for DatabaseService (as a singleton)
    container.register_factory("db", lambda: DatabaseService("prod_db_connection"), singleton=True)

    # 2. Register a factory for UserService (transient - new instance each time)
    container.register_factory("user_service", lambda: UserService(container.get_service("db")))

    # 3. Register a pre-instantiated service (e.g. a simple config object)
    app_config = {"version": "1.0", "debug_mode": False}
    container.register_service("app_config", app_config, singleton=True)

    print("\n--- Retrieving services ---")
    db_instance1 = container.get_service("db")
    db_instance2 = container.get_service("db")
    print(f"db_instance1 is db_instance2: {db_instance1 is db_instance2}") # Should be True

    user_service1 = container.get_service("user_service")
    user_service2 = container.get_service("user_service")
    print(f"user_service1 is user_service2: {user_service1 is user_service2}") # Should be False

    retrieved_config = container.get_service("app_config")
    print(f"Retrieved config: {retrieved_config}")
    print(f"retrieved_config is app_config: {retrieved_config is app_config}") # Should be True

    print(f"Is 'db' registered? {container.is_registered('db')}")
    print(f"Is 'non_existent_service' registered? {container.is_registered('non_existent_service')}")

    # Example of trying to register a duplicate
    try:
        container.register_service("db", "another_db_service")
    except ValueError as e:
        print(f"Error registering duplicate: {e}")

    # Example of a singleton service directly registered
    class SingletonService:
        def __init__(self):
            print("SingletonService Initialized (direct registration)")

    s_service = SingletonService()
    container.register_service("s_service", s_service, singleton=True)
    s_service1 = container.get_service("s_service")
    s_service2 = container.get_service("s_service")
    print(f"s_service1 is s_service2: {s_service1 is s_service2}")
