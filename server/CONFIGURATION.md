# Configuration System

This application uses a JSON-based configuration system that allows you to manage different environment configurations in a single file while using environment variables to select the appropriate configuration.

## How It Works

1. **Environment Variable**: The `ENVIRONMENT` environment variable determines which configuration section to use from `config.json`
2. **JSON Configuration**: All environment-specific settings are stored in a flat structure in `config.json`
3. **Environment Variable Mapping**: Environment variables from `.env` file are used as keys to look up values in `config.json`
4. **Config Manager**: The `ConfigManager` class handles loading and accessing the appropriate configuration

## Setup

### 1. Copy Configuration Files

```bash
# Copy the example configuration file
cp config.example.json config.json

# Copy the appropriate environment file
cp env.dev.example .env  # For development
# OR
cp env.pre_prod.example .env  # For pre-production
# OR
cp env.prod.example .env  # For production
```

### 2. Update Configuration

Edit `config.json` to match your environment settings. The configuration uses a flat structure:

```json
{
  "dev": {
    "database_host": "localhost",
    "database_port": 5432,
    "database_name": "content_designer_dev",
    "database_user": "content_designer_user",
    "database_password": "your-dev-password",
    "secret_key": "your-dev-secret-key",
    "debug": true,
    "jwt_algorithm": "HS256",
    "expire_minutes": 20
  }
}
```

### 3. Set Environment Variables

The `.env` file should contain environment variable mappings to config.json keys:

```env
# Environment Configuration
ENVIRONMENT=dev

# Database Configuration
POSTGRES_HOST=database_host
POSTGRES_PORT=database_port
POSTGRES_DB=database_name
POSTGRES_USER=database_user
POSTGRES_PASSWORD=database_password

# Application Configuration
SECRET_KEY=secret_key
DEBUG=debug

# JWT Configuration
JWT_ALGORITHM=jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES=expire_minutes
```

## Configuration Structure

The configuration uses a flat structure where all settings are at the same level within each environment section.

### Available Configuration Keys

#### Database Configuration
- `database_host`: Database host (default: localhost)
- `database_port`: Database port (default: 5432)
- `database_name`: Database name
- `database_user`: Database username
- `database_password`: Database password

#### Application Configuration
- `secret_key`: JWT secret key
- `debug`: Enable/disable debug mode (true/false)
- `environment`: Environment name (automatically set)

#### JWT Configuration
- `jwt_algorithm`: JWT algorithm (default: HS256)
- `expire_minutes`: Token expiration time in minutes (default: 20)

## How the Mapping Works

The system works by using environment variable values as keys to look up values in `config.json`:

1. **Environment Variable**: `POSTGRES_DB=database_name`
2. **Config Lookup**: Uses `database_name` as a key in `config.json`
3. **Result**: Returns the value for `database_name` from `config.json`

**Example Flow:**
- `.env` file: `POSTGRES_DB=database_name`
- `config.json`: `"database_name": "content_designer_dev"`
- **Result**: `config.get_database_config()['db']` returns `"content_designer_dev"`

## Using the Configuration

### In Your Code

```python
from config_loader import config

# Get database configuration
db_config = config.get_database_config()
database_url = config.get_database_url()

# Get application configuration
secret_key = config.get_secret_key()
is_debug = config.is_debug()

# Get JWT configuration
algorithm = config.get_jwt_algorithm()
expire_minutes = config.get_access_token_expire_minutes()

```

### Available Methods

- `config.get_database_config()`: Get database configuration dict
- `config.get_database_url()`: Get complete database URL
- `config.get_application_config()`: Get application configuration dict
- `config.get_jwt_config()`: Get JWT configuration dict
- `config.get_secret_key()`: Get secret key
- `config.is_debug()`: Check if debug mode is enabled
- `config.get_jwt_algorithm()`: Get JWT algorithm
- `config.get_access_token_expire_minutes()`: Get token expiration time

## Environment Switching

To switch between environments, simply change the `ENVIRONMENT` variable in your `.env` file:

```env
# For development
ENVIRONMENT=dev

# For pre-production
ENVIRONMENT=pre_prod

# For production
ENVIRONMENT=prod
```

## Security Notes

1. **Never commit `config.json`** with real credentials to version control
2. **Use `config.example.json`** as a template
3. **Generate strong secret keys** for production environments
4. **Use environment-specific passwords** for each environment
5. **Consider using secrets management** for production deployments

## Docker Integration

For Docker deployments, you can override the environment variable:

```bash
docker run -e ENVIRONMENT=prod your-app
```

Or in docker-compose.yml:

```yaml
services:
  app:
    environment:
      - ENVIRONMENT=prod
```

## Troubleshooting

### Configuration Not Found
If you get an error about environment not found in configuration:
1. Check that `ENVIRONMENT` variable is set correctly
2. Verify the environment name exists in `config.json`
3. Ensure `config.json` is in the correct location

### File Not Found
If you get a file not found error:
1. Ensure `config.json` exists in the server directory
2. Check file permissions
3. Verify the working directory when running the application

### Invalid Configuration
If you get configuration errors:
1. Validate your `config.json` syntax using a JSON validator
2. Check that all required fields are present
3. Ensure data types match expected values (e.g., port should be a number)
