# src/core/logging/formatters.py
import logging
import json

class JsonFormatter(logging.Formatter):
    """Formats log records as JSON strings."""
    def format(self, record: logging.LogRecord) -> str:
        log_object = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "thread_name": record.threadName,
            "process_id": record.process
        }
        if record.exc_info:
            log_object["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_object)

if __name__ == '__main__':
    # Example Usage
    from src.core.logging.logger_config import setup_logger

    # Configure logger with JsonFormatter
    json_logger = logging.getLogger('json_logger')
    json_logger.setLevel(logging.INFO)

    if not json_logger.handlers:
        json_handler = logging.StreamHandler()
        json_formatter = JsonFormatter()
        json_handler.setFormatter(json_formatter)
        json_logger.addHandler(json_handler)

    json_logger.info("This is an informational message in JSON format.")
    json_logger.warning("This is a warning message, also in JSON.")

    try:
        x = 1 / 0
    except ZeroDivisionError:
        json_logger.error("An error occurred", exc_info=True)

    # Example with a standard logger for comparison
    standard_logger = setup_logger('standard_logger_example')
    standard_logger.info("This is a standard formatted log message.")
