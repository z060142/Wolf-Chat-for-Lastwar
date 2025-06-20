# tests/unit/core/test_logger_config.py
import unittest
import logging
from src.core.logging.logger_config import setup_logger, DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT
from src.core.logging.formatters import JsonFormatter

class TestLoggerConfig(unittest.TestCase):

    def test_setup_logger_basic(self):
        """Tests basic logger setup with default parameters."""
        logger_name = "test_logger_basic"
        logger = setup_logger(logger_name)

        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, logger_name)
        self.assertEqual(logger.level, logging.INFO) # Default level
        self.assertTrue(len(logger.handlers) > 0)
        if logger.handlers:
            self.assertIsInstance(logger.handlers[0], logging.StreamHandler)
            self.assertIsInstance(logger.handlers[0].formatter, logging.Formatter)
            self.assertEqual(logger.handlers[0].formatter._fmt, DEFAULT_LOG_FORMAT)

    def test_setup_logger_custom_level_format(self):
        """Tests logger setup with custom level and format."""
        logger_name = "test_logger_custom"
        custom_format = "%(levelname)s: %(message)s"
        custom_date_format = "%H:%M:%S"
        logger = setup_logger(logger_name, level=logging.DEBUG, log_format=custom_format, date_format=custom_date_format)

        self.assertEqual(logger.level, logging.DEBUG)
        if logger.handlers:
            self.assertEqual(logger.handlers[0].formatter._fmt, custom_format)
            self.assertEqual(logger.handlers[0].formatter.datefmt, custom_date_format)

    def test_setup_logger_idempotency(self):
        """Tests that calling setup_logger multiple times for the same logger doesn't add handlers."""
        logger_name = "idempotent_logger"
        logger1 = setup_logger(logger_name)
        initial_handler_count = len(logger1.handlers)

        logger2 = setup_logger(logger_name) # Call again
        self.assertEqual(len(logger2.handlers), initial_handler_count)
        self.assertIs(logger1, logger2) # Should return the same logger instance

    def test_json_formatter(self):
        """Tests the JsonFormatter integration."""
        logger_name = "json_test_logger"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)

        # Clear existing handlers for this specific test logger if any
        if logger.hasHandlers():
            logger.handlers.clear()

        json_handler = logging.StreamHandler()
        json_formatter = JsonFormatter()
        json_handler.setFormatter(json_formatter)
        logger.addHandler(json_handler)

        # This test will not check stdout, but ensures the formatter can be assigned and used.
        # A more comprehensive test would capture log output and parse the JSON.
        try:
            logger.info("Test message for JSON formatter.")
        except Exception as e:
            self.fail(f"Logging with JsonFormatter raised an exception: {e}")

        self.assertEqual(len(logger.handlers), 1)
        self.assertIsInstance(logger.handlers[0].formatter, JsonFormatter)


if __name__ == '__main__':
    unittest.main()
