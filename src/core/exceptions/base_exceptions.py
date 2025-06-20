# src/core/exceptions/base_exceptions.py

class BaseWolfException(Exception):
    """Base class for custom exceptions in the Wolf Chat application."""
    def __init__(self, message: str, error_code: int = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message

    def __str__(self):
        if self.error_code:
            return f"[Error Code: {self.error_code}] {self.message}"
        return self.message

class ConfigError(BaseWolfException):
    """Exception raised for errors in the configuration process."""
    def __init__(self, message: str, error_code: int = 1001):
        super().__init__(message, error_code)

class LLMError(BaseWolfException):
    """Exception raised for errors related to LLM interactions."""
    def __init__(self, message: str, error_code: int = 2001):
        super().__init__(message, error_code)

class UIInteractionError(BaseWolfException):
    """Exception raised for errors during UI interaction or detection."""
    def __init__(self, message: str, error_code: int = 3001):
        super().__init__(message, error_code)

if __name__ == '__main__':
    try:
        raise ConfigError("Failed to load configuration file.")
    except BaseWolfException as e:
        print(e)

    try:
        raise LLMError("LLM API returned an error.", error_code=2002)
    except BaseWolfException as e:
        print(e)
