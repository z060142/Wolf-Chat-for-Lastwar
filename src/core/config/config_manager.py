# src/core/config/config_manager.py

class ConfigManager:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = {}

    def load_config(self):
        # In a real scenario, this would load from a file (e.g., JSON, YAML)
        # For now, we'll use a dummy dictionary
        self.config = {"dummy_setting": "dummy_value"}
        print(f"Configuration loaded from {self.config_path}")

    def get_setting(self, key: str, default=None):
        return self.config.get(key, default)

    def set_setting(self, key: str, value):
        self.config[key] = value

    def save_config(self):
        # In a real scenario, this would save to a file
        print(f"Configuration saved to {self.config_path}")

if __name__ == '__main__':
    # Example Usage
    manager = ConfigManager(config_path="settings.json")
    manager.load_config()
    print(f"Dummy setting: {manager.get_setting('dummy_setting')}")
    manager.set_setting('new_setting', 123)
    print(f"New setting: {manager.get_setting('new_setting')}")
    manager.save_config()
