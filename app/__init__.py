"""
Flask Application Factory
Creates and configures the Flask application with enhanced logging and error handling
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from flask import Flask, jsonify, request


def configure_logging(app: Flask) -> None:
    """Configure application logging"""
    
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    root_logger.addHandler(console_handler)
    
    # Configure app logger
    app.logger.handlers = []
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    
    # Reduce noise from libraries
    logging.getLogger('azure').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)


def register_error_handlers(app: Flask) -> None:
    """Register global error handlers"""
    
    @app.errorhandler(400)
    def bad_request(error):
        app.logger.warning(f"Bad request: {error}")
        return jsonify({
            'error': 'Bad Request',
            'message': str(error.description) if hasattr(error, 'description') else 'Invalid request',
            'status': 400
        }), 400
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'Not Found',
            'message': 'The requested resource was not found',
            'status': 404
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Internal server error: {error}", exc_info=True)
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An unexpected error occurred. Please try again later.',
            'status': 500
        }), 500
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        app.logger.error(f"Unhandled exception: {error}", exc_info=True)
        return jsonify({
            'error': 'Internal Server Error',
            'message': 'An unexpected error occurred',
            'status': 500
        }), 500


def register_request_hooks(app: Flask) -> None:
    """Register request lifecycle hooks for logging"""
    
    @app.before_request
    def log_request_info():
        """Log incoming request details"""
        request.start_time = datetime.now(timezone.utc)
        if app.debug:
            app.logger.debug(
                f"Request: {request.method} {request.path} "
                f"| Client: {request.remote_addr}"
            )
    
    @app.after_request
    def log_response_info(response):
        """Log response details with timing"""
        if hasattr(request, 'start_time'):
            duration = (datetime.now(timezone.utc) - request.start_time).total_seconds() * 1000
            log_level = logging.WARNING if response.status_code >= 400 else logging.DEBUG
            
            if app.debug or response.status_code >= 400:
                app.logger.log(
                    log_level,
                    f"Response: {request.method} {request.path} "
                    f"| Status: {response.status_code} "
                    f"| Duration: {duration:.2f}ms"
                )
        
        return response


def create_app():
    """Create and configure the Flask application"""
    
    app = Flask(__name__)
    
    # Load configuration
    from config import get_config
    config_class = get_config()
    app.config.from_object(config_class)
    
    # Configure logging first
    configure_logging(app)
    
    app.logger.info("=" * 60)
    app.logger.info("Flask RAG Application Starting")
    app.logger.info("=" * 60)
    
    # Validate configuration
    errors = config_class.validate()
    if errors and not app.config.get('DEBUG'):
        for error in errors:
            app.logger.error(f"Configuration error: {error}")
        raise ValueError(f"Configuration errors: {', '.join(errors)}")
    elif errors:
        for error in errors:
            app.logger.warning(f"Configuration warning: {error}")
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register request hooks
    register_request_hooks(app)
    
    # Initialize services
    with app.app_context():
        # Import and register blueprints
        from app.routes import main_bp, api_bp
        app.register_blueprint(main_bp)
        app.register_blueprint(api_bp, url_prefix='/api')
        
        app.logger.info("Blueprints registered")
        
        # Initialize async services
        from app.services import init_services
        
        # Create event loop for async initialization
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(init_services(app))
            app.logger.info("All services initialized successfully")
        except Exception as e:
            app.logger.error(f"Failed to initialize services: {e}", exc_info=True)
            if not app.config.get('DEBUG'):
                raise
    
    app.logger.info("=" * 60)
    app.logger.info("Flask RAG Application Ready")
    app.logger.info("=" * 60)
    
    return app
