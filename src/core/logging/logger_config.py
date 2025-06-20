# src/core/logging/logger_config.py
import logging
import sys

DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

def setup_logger(name: str, level: int = logging.INFO, log_format: str = DEFAULT_LOG_FORMAT, date_format: str = DEFAULT_DATE_FORMAT):
    """Configures and returns a logger instance."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding multiple handlers if logger already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(log_format, datefmt=date_format)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

if __name__ == '__main__':
    # Example Usage
    logger1 = setup_logger('wolf_chat_system', level=logging.DEBUG)
    logger1.debug("This is a debug message from logger1.")
    logger1.info("This is an info message from logger1.")

    logger2 = setup_logger('another_module', level=logging.WARNING)
    logger2.warning("This is a warning message from logger2.")
    logger2.error("This is an error message from logger2.")

    # Demonstrate that handlers are not duplicated
    logger1_again = setup_logger('wolf_chat_system')
    logger1_again.info("Another info message from logger1, ensuring no duplicate handlers.")
