import logging
import sys

def setup_logging():
    """
    Sets up a professional and detailed logging configuration.
    """
    # Professional log format with timestamp, log level, file/function/line number, and message
    log_format = "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Create formatter
    formatter = logging.Formatter(log_format, datefmt=date_format)
    
    # Create console handler to print to terminal
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers if any, to avoid duplicate logs
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.addHandler(console_handler)
    
    # Configure specific loggers (like uvicorn and fastapi) to use our format
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logger = logging.getLogger(logger_name)
        logger.handlers = [console_handler]
        logger.propagate = False # Prevent propagating to root logger and printing twice

    # Hook to log unhandled exceptions (System Crashes)
    def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # Ignore KeyboardInterrupt (when you press Ctrl+C)
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        root_logger.error("Unhandled exception / System Crash:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_unhandled_exception
