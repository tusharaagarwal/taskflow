"""
Security utilities for sanitizing inputs and preventing vulnerabilities.
"""

def sanitize_log_input(value: str) -> str:
    """
    Sanitize input values before logging to prevent Log Injection.
    Removes newline and carriage return characters.
    
    Args:
        value: The string to sanitize.
        
    Returns:
        The sanitized string.
    """
    if not isinstance(value, str):
        return str(value)
    
    # Remove newline and carriage return characters
    return value.replace('\n', '\\n').replace('\r', '\\r')
