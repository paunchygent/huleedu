"""CORS utilities for environment-specific origin management.

Optimized for Svelte 5 + Vite development workflows with proper environment isolation.
"""


def get_cors_origins_for_environment(
    env_type: str, custom_origins: list[str] | None = None
) -> list[str]:
    """Get CORS origins based on environment type - optimized for Svelte 5 + Vite.
    
    Args:
        env_type: Environment type (development, staging, production)
        custom_origins: Additional origins to include
        
    Returns:
        List of allowed CORS origins for the specified environment
        
    Example:
        >>> get_cors_origins_for_environment("development")
        ['http://localhost:5173', 'http://localhost:4173', 'http://localhost:3000', 'http://localhost:8080']
        
        >>> get_cors_origins_for_environment("production", ["https://custom.domain.com"])
        ['https://app.huledu.com', 'https://huledu.com', 'https://custom.domain.com']
    """
    base_origins = {
        "development": [
            "http://localhost:5173",  # Vite dev server (primary)
            "http://localhost:4173",  # Vite preview server
            "http://localhost:3000",  # Backup/alternative port
            "http://localhost:8080",  # Custom dev port
        ],
        "staging": [
            "https://staging.huledu.com",
            "https://staging-app.huledu.com",
        ],
        "production": [
            "https://app.huledu.com",
            "https://huledu.com",
        ],
    }

    # Default to development if environment not recognized
    origins = base_origins.get(env_type.lower(), base_origins["development"])

    # Add custom origins if provided
    if custom_origins:
        origins.extend(custom_origins)

    # Remove duplicates while preserving order
    return list(dict.fromkeys(origins))


def is_development_environment(env_type: str) -> bool:
    """Check if running in development environment.
    
    Args:
        env_type: Environment type from settings
        
    Returns:
        True if environment is development-related, False otherwise
        
    Example:
        >>> is_development_environment("development")
        True
        >>> is_development_environment("dev")
        True  
        >>> is_development_environment("production")
        False
    """
    return env_type.lower() in ["development", "dev", "local"]


def get_development_cors_headers(cors_origins: list[str]) -> dict[str, str]:
    """Get development-specific CORS debug headers.
    
    Args:
        cors_origins: List of CORS origins
        
    Returns:
        Dictionary of headers for development debugging
    """
    return {
        "X-HuleEdu-Environment": "development",
        "X-HuleEdu-Dev-Mode": "enabled", 
        "X-HuleEdu-CORS-Origins": ",".join(cors_origins),
    }