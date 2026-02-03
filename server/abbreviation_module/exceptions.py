"""
Custom exceptions for the Abbreviation Module.
"""


class AbbreviationModuleError(Exception):
    """Base exception for all abbreviation module errors."""
    pass


class AbbreviationNotFoundError(AbbreviationModuleError):
    """Raised when a document type abbreviation is not found in the database."""
    
    def __init__(self, document_type: str, message: str = None):
        self.document_type = document_type
        self.message = message or f"Abbreviation not found for document type: '{document_type}'"
        super().__init__(self.message)


class AbbreviationCacheError(AbbreviationModuleError):
    """Raised when a cache operation fails."""
    
    def __init__(self, operation: str, message: str = None):
        self.operation = operation
        self.message = message or f"Cache operation failed: {operation}"
        super().__init__(self.message)


class AbbreviationConfigError(AbbreviationModuleError):
    """Raised when configuration validation fails."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class AbbreviationDatabaseError(AbbreviationModuleError):
    """Raised when a database operation fails."""
    
    def __init__(self, operation: str, message: str = None):
        self.operation = operation
        self.message = message or f"Database operation failed: {operation}"
        super().__init__(self.message)
