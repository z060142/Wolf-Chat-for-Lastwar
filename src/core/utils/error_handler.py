# src/core/utils/error_handler.py
import functools
import logging
from src.core.exceptions.base_exceptions import BaseWolfException

# It's better to get the logger from logger_config
# from src.core.logging.logger_config import setup_logger
# logger = setup_logger(__name__)
# For now, using a basicConfig for simplicity in this standalone example part
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


def unified_error_handler(func):
    """
    A decorator to handle exceptions in a unified way.
    It logs the exception and can be extended to perform other actions
    like sending notifications or re-raising specific exceptions.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BaseWolfException as bwe:
            logger.error(f"Custom application error caught in {func.__name__}: {bwe}", exc_info=True)
            # Depending on the strategy, you might re-raise, or return a default/error value
            # For now, re-raising to make it visible
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred in {func.__name__}: {e}", exc_info=True)
            # Wrap unexpected errors in a generic BaseWolfException or re-raise
            raise BaseWolfException(f"Unexpected error in {func.__name__}: {str(e)}")
    return wrapper

if __name__ == '__main__':
    # Example Usage:
    from src.core.exceptions.base_exceptions import ConfigError

    @unified_error_handler
    def function_that_might_fail(succeed: bool):
        if succeed:
            print("Function executed successfully.")
            return "Success"
        else:
            raise ValueError("A deliberate value error.")

    @unified_error_handler
    def function_with_custom_exception():
        raise ConfigError("This is a custom configuration error.")

    print("--- Example 1: Function succeeds ---")
    function_that_might_fail(succeed=True)
    print("\n--- Example 2: Function fails with standard exception ---")
    try:
        function_that_might_fail(succeed=False)
    except BaseWolfException as e:
        print(f"Caught expected BaseWolfException: {e}")

    print("\n--- Example 3: Function fails with custom BaseWolfException ---")
    try:
        function_with_custom_exception()
    except ConfigError as e: # More specific handling if needed
        print(f"Caught expected ConfigError: {e}")
    except BaseWolfException as e: # Generic handling
        print(f"Caught expected BaseWolfException: {e}")
