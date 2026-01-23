import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class ConfigManager:
    """
    Configuration manager that loads environment-specific configurations from separate JSON files.
    The environment is determined by the ENVIRONMENT environment variable.
    Environment variables from .env file are used as keys to look up values in config files.
    """
    
    def __init__(self, base_path: str = "."):
        """
        Initialize the configuration manager.
        
        Args:
            base_path: Base path where config files are located
        """
        self.base_path = Path(base_path)
        self._config: Optional[Dict[str, Any]] = None
        self._environment: Optional[str] = None
        self._env_mappings: Dict[str, str] = {}
        self._config_file_path: Optional[Path] = None
        self._env_file_path: Optional[Path] = None
        self._load_config()

    def _get_environment(self) -> str:
        """Get the environment from the instance where it is deployed.
        
        Checks ENVIRONMENT variable first (for ECS), falls back to 'dev'.
        
        Returns:
            The environment from the environment variable or default 'dev'.
        """
        return os.getenv("ENVIRONMENT", "dev")
    
    def _load_config(self) -> None:
        """Load configuration from environment-specific JSON file and map environment variables to config values."""
        try:
            # Get environment from environment variable
            self._environment = self._get_environment()
            
            # Determine config file path based on environment
            self._config_file_path = self.base_path / f"config_{self._environment}.json"
            self._env_file_path = self.base_path / f".env_{self._environment}"
            
            if not self._config_file_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {self._config_file_path}")
            
            with open(self._config_file_path, 'r') as f:
                self._config = json.load(f)
            
            # Since we now have separate files for each environment, 
            # the config is directly the configuration values (no environment wrapper)
            
            # Load environment variable mappings
            self._load_env_mappings()
                
        except Exception as e:
            raise RuntimeError(f"Failed to load configuration: {str(e)}")
    
    def _load_env_mappings(self) -> None:
        """Load environment variables and map them to config file keys."""
        if not self._env_file_path or not self._env_file_path.exists():
            return
        
        # Read environment-specific .env file and create mappings
        with open(self._env_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    env_var, config_key = line.split('=', 1)
                    self._env_mappings[env_var] = config_key
    
    def _get_config_value(self, env_var_name: str, default: Any = None) -> Any:
        """
        Get configuration value with priority: environment variables → config file → default.
        
        This allows ECS to inject secrets via environment variables while maintaining
        backward compatibility with local development using config files.
        
        Args:
            env_var_name: The environment variable name (e.g., 'POSTGRES_DB')
            default: Default value if not found

        Returns:
            The configuration value from environment variable, config file, or default
        """
        if self._config is None:
            raise RuntimeError("Configuration not loaded")
        
        # PRIORITY 1: Check actual environment variables first (ECS Secrets Manager injects these)
        env_value = os.getenv(env_var_name)
        if env_value is not None:
            return env_value
        
        # PRIORITY 2: Get the config key from environment variable mapping
        config_key = self._env_mappings.get(env_var_name)
        if not config_key:
            return default
        
        # PRIORITY 3: Get the value from the environment-specific config file
        return self._config.get(config_key, default)
    
    @property
    def environment(self) -> str:
        """Get the current environment."""
        return self._environment
    
    @property
    def config(self) -> Dict[str, Any]:
        """Get the current environment's configuration."""
        if self._config is None:
            raise RuntimeError("Configuration not loaded")
        return self._config
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration for the current environment."""
        return {
            "host": self._get_config_value("POSTGRES_HOST", "localhost"),
            "port": self._get_config_value("POSTGRES_PORT", 5432),
            "db": self._get_config_value("POSTGRES_DB", ""),
            "user": self._get_config_value("POSTGRES_USER", ""),
            "password": self._get_config_value("POSTGRES_PASSWORD", "")
        }
    
    def get_application_config(self) -> Dict[str, Any]:
        """Get application configuration for the current environment."""
        return {
            "secret_key": self._get_config_value("SECRET_KEY", ""),
            "debug": self._get_config_value("DEBUG", False),
            "environment": self._environment
        }
    
    def get_jwt_config(self) -> Dict[str, Any]:
        """Get JWT configuration for the current environment."""
        return {
            "algorithm": self._get_config_value("JWT_ALGORITHM", "HS256"),
            "access_token_expire_minutes": self._get_config_value("ACCESS_TOKEN_EXPIRE_MINUTES", 20)
        }
    
    def get_database_url(self) -> str:
        """Get the complete database URL for the current environment."""
        host = self._get_config_value("POSTGRES_HOST", "localhost")
        port = self._get_config_value("POSTGRES_PORT", 5432)
        db = self._get_config_value("POSTGRES_DB", "")
        user = self._get_config_value("POSTGRES_USER", "")
        password = self._get_config_value("POSTGRES_PASSWORD", "")
        
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
    
    def get_secret_key(self) -> str:
        """Get the secret key for the current environment."""
        secret_key = self._get_config_value("SECRET_KEY")
        if not secret_key:
            raise ValueError("SECRET_KEY not found in configuration")
        return secret_key
    
    def is_debug(self) -> bool:
        """Check if debug mode is enabled for the current environment."""
        debug_value = self._get_config_value("DEBUG", False)
        # Handle both string and boolean values
        if isinstance(debug_value, str):
            return debug_value.lower() in ("true", "1", "yes", "on")
        return bool(debug_value)
    
    def get_jwt_algorithm(self) -> str:
        """Get JWT algorithm for the current environment."""
        return self._get_config_value("JWT_ALGORITHM", "HS256")
    
    def get_access_token_expire_minutes(self) -> int:
        """Get access token expiration time in minutes for the current environment."""
        return int(self._get_config_value("ACCESS_TOKEN_EXPIRE_MINUTES", 20))
    
    def get_cors_origins(self) -> list:
        """Get CORS origins for the current environment."""
        if self._config is None:
            raise RuntimeError("Configuration not loaded")
        return self._config.get("cors_origins", ["*"])

    
    def reload_config(self) -> None:
        """Reload configuration from file."""
        self._load_config()
    
    def get_all_configs(self) -> Dict[str, Any]:
        """Get all configurations for the current environment (for debugging purposes)."""
        return self._config


# Global configuration instance
config = ConfigManager()
