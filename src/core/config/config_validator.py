# src/core/config/config_validator.py

class ConfigValidator:
    def __init__(self, schema=None):
        self.schema = schema or {}

    def validate(self, config_data: dict) -> bool:
        # Basic validation: checks if all keys in schema are present in config_data
        # and if their types match.
        # A more robust validator would use a library like Pydantic or jsonschema.
        if not self.schema:
            print("No schema provided, skipping validation.")
            return True

        for key, expected_type in self.schema.items():
            if key not in config_data:
                print(f"Validation Error: Missing key '{key}' in configuration.")
                return False
            if not isinstance(config_data[key], expected_type):
                print(f"Validation Error: Key '{key}' has type {type(config_data[key])}, expected {expected_type}.")
                return False
        print("Configuration validation successful.")
        return True

if __name__ == '__main__':
    # Example Usage
    schema = {
        "api_key": str,
        "timeout": int,
        "feature_enabled": bool
    }
    validator = ConfigValidator(schema)

    valid_config = {
        "api_key": "your_api_key_here",
        "timeout": 30,
        "feature_enabled": True
    }
    print(f"Validating valid_config: {validator.validate(valid_config)}")

    invalid_config_missing_key = {
        "api_key": "your_api_key_here",
        "timeout": 30
        # "feature_enabled" is missing
    }
    print(f"Validating invalid_config_missing_key: {validator.validate(invalid_config_missing_key)}")

    invalid_config_wrong_type = {
        "api_key": "your_api_key_here",
        "timeout": "should_be_int", # Wrong type
        "feature_enabled": True
    }
    print(f"Validating invalid_config_wrong_type: {validator.validate(invalid_config_wrong_type)}")
