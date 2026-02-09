import time
import uuid
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.logger import logger
from app.utils.security import sanitize_log_input
import traceback
import sys


class RequestResponseMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request/response headers and enhanced logging
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID for correlation
        request_id = str(uuid.uuid4())
        correlation_id = request.headers.get("X-Correlation-ID", request_id)
        
        # Add request ID to request state for use in endpoints
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        
        # Log incoming request
        start_time = time.time()
        logger.info(
            f"Request started - "
            f"ID: {sanitize_log_input(request_id)}, "
            f"Correlation-ID: {sanitize_log_input(correlation_id)}, "
            f"Method: {sanitize_log_input(request.method)}, "
            f"URL: {sanitize_log_input(str(request.url))}, "
            f"Client: {sanitize_log_input(request.client.host) if request.client else 'unknown'}, "
            f"User-Agent: {sanitize_log_input(request.headers.get('user-agent', 'unknown'))}"
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Add response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Process-Time"] = f"{process_time:.4f}s"
            response.headers["X-API-Version"] = "1.0"
            response.headers["X-Server"] = "Workflow-Orchestrator-API"
            
            # Add CORS headers if not already present
            if "Access-Control-Allow-Origin" not in response.headers:
                response.headers["Access-Control-Allow-Origin"] = "*"
            if "Access-Control-Allow-Methods" not in response.headers:
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            if "Access-Control-Allow-Headers" not in response.headers:
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Request-ID, X-Correlation-ID"
            
            # Log successful response
            logger.info(
                f"Request completed - "
                f"ID: {sanitize_log_input(request_id)}, "
                f"Correlation-ID: {sanitize_log_input(correlation_id)}, "
                f"Status: {response.status_code}, "
                f"Process-Time: {process_time:.4f}s"
            )
            
            return response
            
        except HTTPException as e:
            # Handle FastAPI HTTP exceptions - preserve status code and details
            process_time = time.time() - start_time
            
            # Log HTTP exception with appropriate level
            log_level = logger.error if e.status_code >= 500 else logger.warning
            log_level(
                f"HTTP Exception - "
                f"ID: {sanitize_log_input(request_id)}, "
                f"Correlation-ID: {sanitize_log_input(correlation_id)}, "
                f"Status: {e.status_code}, "
                f"Detail: {sanitize_log_input(str(e.detail))}, "
                f"Process-Time: {process_time:.4f}s"
            )
            
            # Create error response preserving the original status code
            error_response = JSONResponse(
                status_code=e.status_code,
                content={
                    "detail": e.detail,
                    "request_id": request_id,
                    "correlation_id": correlation_id
                }
            )
            
            # Add headers to error response
            error_response.headers["X-Request-ID"] = request_id
            error_response.headers["X-Correlation-ID"] = correlation_id
            error_response.headers["X-Process-Time"] = f"{process_time:.4f}s"
            error_response.headers["X-API-Version"] = "1.0"
            error_response.headers["X-Server"] = "Content-Authoring-API"
            
            return error_response
            
        except Exception as e:
            # Handle unexpected exceptions - return 500
            process_time = time.time() - start_time
            
            # Get the full stack trace
            exc_type, exc_value, exc_traceback = sys.exc_info()
            stack_trace = traceback.format_exception(exc_type, exc_value, exc_traceback)
            stack_trace_str = ''.join(stack_trace)
            
            # Log unexpected error with full stack trace
            logger.error(
                f"Unexpected error - "
                f"ID: {sanitize_log_input(request_id)}, "
                f"Correlation-ID: {sanitize_log_input(correlation_id)}, "
                f"Error: {sanitize_log_input(str(e))}, "
                f"Type: {sanitize_log_input(type(e).__name__)}, "
                f"Process-Time: {process_time:.4f}s, "
                f"Stack-Trace: {sanitize_log_input(stack_trace_str)}"
            )
            
            # Create error response for unexpected errors
            error_response = JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "message": "An unexpected error occurred"
                }
            )
            
            # Add headers to error response
            error_response.headers["X-Request-ID"] = request_id
            error_response.headers["X-Correlation-ID"] = correlation_id
            error_response.headers["X-Process-Time"] = f"{process_time:.4f}s"
            error_response.headers["X-API-Version"] = "1.0"
            error_response.headers["X-Server"] = "Content-Authoring-API"
            
            return error_response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
