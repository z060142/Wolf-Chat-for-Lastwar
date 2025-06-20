# src/core/container/service_registry.py
from src.core.container.service_container import ServiceContainer
from typing import Optional

class ServiceRegistry:
    _container: Optional[ServiceContainer] = None

    @classmethod
    def get_container(cls) -> ServiceContainer:
        """Returns the global service container instance, creating it if necessary."""
        if cls._container is None:
            cls._container = ServiceContainer()
            print("ServiceRegistry: Created global ServiceContainer instance.")
        return cls._container

    @classmethod
    def set_container(cls, container: ServiceContainer):
        """Allows setting a custom container, e.g., for testing or specific configurations."""
        print("ServiceRegistry: Custom ServiceContainer instance set.")
        cls._container = container

    @classmethod
    def reset_container(cls):
        """Resets the container to None. Useful for testing scenarios."""
        print("ServiceRegistry: Global ServiceContainer instance reset.")
        cls._container = None

if __name__ == '__main__':
    # Example Usage

    # Dummy classes for example
    class LoggingService:
        def log(self, message: str):
            print(f"LOG: {message}")

    class EmailService:
        def send_email(self, to: str, subject: str, body: str):
            print(f"Sending email to {to} with subject '{subject}'")

    # Get the global container
    container1 = ServiceRegistry.get_container()
    container2 = ServiceRegistry.get_container()

    print(f"container1 is container2: {container1 is container2}") # Should be True

    # Register services using the global container
    container1.register_service("logger", LoggingService(), singleton=True)
    container1.register_factory("email_service", EmailService) # Transient

    # Retrieve services using the global container (or another reference to it)
    logger = container2.get_service("logger")
    logger.log("This is a test log message.")

    email_sender1 = container2.get_service("email_service")
    email_sender1.send_email("test@example.com", "Hello", "This is a test email.")

    email_sender2 = ServiceRegistry.get_container().get_service("email_service")
    print(f"email_sender1 is email_sender2: {email_sender1 is email_sender2}") # Should be False

    # Resetting container (e.g., for test isolation)
    ServiceRegistry.reset_container()
    container3 = ServiceRegistry.get_container()
    print(f"container1 is container3 after reset: {container1 is container3}") # Should be False

    try:
        container3.get_service("logger") # Should fail as container was reset
    except ValueError as e:
        print(f"Error after reset: {e}")
