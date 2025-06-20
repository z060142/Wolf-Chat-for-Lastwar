# tests/unit/core/test_config_manager.py
import unittest
import os
from src.core.config.config_manager import ConfigManager
from src.core.config.config_validator import ConfigValidator # Added for potential use or future tests

class TestConfigManager(unittest.TestCase):

    def setUp(self):
        self.test_config_path = "test_settings.json"
        # Ensure a clean state by removing the test file if it exists
        if os.path.exists(self.test_config_path):
            os.remove(self.test_config_path)
        self.manager = ConfigManager(config_path=self.test_config_path)

    def tearDown(self):
        # Clean up the created test file
        if os.path.exists(self.test_config_path):
            os.remove(self.test_config_path)

    def test_load_config_dummy(self):
        """Tests loading of the initial dummy configuration."""
        self.manager.load_config() # Uses dummy config
        self.assertEqual(self.manager.get_setting("dummy_setting"), "dummy_value")

    def test_get_setting(self):
        """Tests retrieving settings."""
        self.manager.load_config()
        self.assertEqual(self.manager.get_setting("dummy_setting"), "dummy_value")
        self.assertIsNone(self.manager.get_setting("non_existent_key"))
        self.assertEqual(self.manager.get_setting("non_existent_key", "default"), "default")

    def test_set_setting(self):
        """Tests adding or updating settings."""
        self.manager.load_config()
        self.manager.set_setting("new_key", "new_value")
        self.assertEqual(self.manager.get_setting("new_key"), "new_value")
        self.manager.set_setting("dummy_setting", "updated_value")
        self.assertEqual(self.manager.get_setting("dummy_setting"), "updated_value")

    def test_save_config_dummy(self):
        """
        Tests the save_config method.
        Note: The current ConfigManager.save_config() only prints.
        A real test would involve writing to a file and then reading it back.
        This test primarily ensures the method runs without error.
        Future enhancements would involve mocking file I/O or actually checking file content.
        """
        self.manager.set_setting("test_save", "save_value")
        try:
            self.manager.save_config() # Currently just prints
            # If it were writing to self.test_config_path, we'd verify content here.
        except Exception as e:
            self.fail(f"save_config() raised an exception {e}")

if __name__ == '__main__':
    unittest.main()
