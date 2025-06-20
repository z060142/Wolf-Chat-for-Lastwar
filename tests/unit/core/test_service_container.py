# tests/unit/core/test_service_container.py
import unittest
from src.core.container.service_container import ServiceContainer
from src.core.container.service_registry import ServiceRegistry # For registry tests if needed later

# Dummy classes for testing
class MockService:
    def __init__(self, name="default"):
        self.name = name
        self.initialized_count = 1 # To check if factory re-initializes

    def get_name(self):
        return self.name

class DependentService:
    def __init__(self, mock_service: MockService):
        self.mock_service = mock_service

class AnotherMockService:
    pass

class InitializationTracker:
    instance_count = 0
    def __init__(self):
        InitializationTracker.instance_count += 1

class TestServiceContainer(unittest.TestCase):

    def setUp(self):
        self.container = ServiceContainer()
        InitializationTracker.instance_count = 0 # Reset for singleton factory tests

    def test_register_and_get_service(self):
        """Test registering a pre-instantiated service and retrieving it."""
        mock_instance = MockService("pre_registered")
        self.container.register_service("mock", mock_instance)
        retrieved_service = self.container.get_service("mock")
        self.assertIs(retrieved_service, mock_instance)

    def test_register_and_get_factory_transient(self):
        """Test registering a factory for transient (non-singleton) services."""
        self.container.register_factory("transient_mock", lambda: MockService("transient"))
        service1 = self.container.get_service("transient_mock")
        service2 = self.container.get_service("transient_mock")
        self.assertIsNot(service1, service2)
        self.assertEqual(service1.get_name(), "transient")

    def test_register_and_get_factory_singleton(self):
        """Test registering a factory for singleton services."""
        self.container.register_factory("singleton_factory_mock", lambda: InitializationTracker(), singleton=True)

        self.assertEqual(InitializationTracker.instance_count, 0, "Should not initialize on registration")

        service1 = self.container.get_service("singleton_factory_mock")
        self.assertEqual(InitializationTracker.instance_count, 1, "Should initialize on first get")

        service2 = self.container.get_service("singleton_factory_mock")
        self.assertEqual(InitializationTracker.instance_count, 1, "Should not re-initialize for singleton")
        self.assertIs(service1, service2)

    def test_register_service_as_singleton(self):
        """Test registering a pre-instantiated service as a singleton."""
        singleton_instance = MockService("direct_singleton")
        self.container.register_service("direct_singleton_svc", singleton_instance, singleton=True)
        service1 = self.container.get_service("direct_singleton_svc")
        service2 = self.container.get_service("direct_singleton_svc")
        self.assertIs(service1, singleton_instance)
        self.assertIs(service2, singleton_instance)

    def test_get_unregistered_service(self):
        """Test retrieving a service that has not been registered."""
        with self.assertRaises(ValueError):
            self.container.get_service("non_existent")

    def test_register_duplicate_service_name(self):
        """Test that registering a service with a duplicate name raises an error."""
        self.container.register_service("duplicate", MockService())
        with self.assertRaises(ValueError):
            self.container.register_service("duplicate", AnotherMockService())

    def test_register_duplicate_factory_name(self):
        """Test that registering a factory with a duplicate name raises an error."""
        self.container.register_factory("duplicate_factory", lambda: MockService())
        with self.assertRaises(ValueError):
            self.container.register_factory("duplicate_factory", lambda: AnotherMockService())

    def test_register_service_then_factory_same_name(self):
        """Test registering service then factory with same name fails."""
        self.container.register_service("conflict", MockService())
        with self.assertRaises(ValueError):
            self.container.register_factory("conflict", lambda: AnotherMockService())

    def test_register_factory_then_service_same_name(self):
        """Test registering factory then service with same name fails."""
        self.container.register_factory("conflict_factory", lambda: MockService())
        with self.assertRaises(ValueError):
            self.container.register_service("conflict_factory", AnotherMockService())

    def test_is_registered(self):
        """Test the is_registered method."""
        self.assertFalse(self.container.is_registered("some_service"))
        self.container.register_service("some_service", MockService())
        self.assertTrue(self.container.is_registered("some_service"))

        self.assertFalse(self.container.is_registered("some_factory"))
        self.container.register_factory("some_factory", lambda: MockService())
        self.assertTrue(self.container.is_registered("some_factory"))

    def test_dependency_injection_via_factory(self):
        """Test if a factory can resolve dependencies from the container."""
        db_service = MockService("db")
        self.container.register_service("db_service", db_service, singleton=True)
        self.container.register_factory("dependent_service",
                                       lambda: DependentService(self.container.get_service("db_service")))

        dependent_instance = self.container.get_service("dependent_service")
        self.assertIsInstance(dependent_instance, DependentService)
        self.assertIs(dependent_instance.mock_service, db_service)

if __name__ == '__main__':
    unittest.main()
