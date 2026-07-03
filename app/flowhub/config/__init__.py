"""FlowHub - Configuration Core public API.

All consumers (backend, CLI, installer, tests, worker) import from here.
No web framework, database, or external service dependency anywhere in this package.

Typical usage:

    from app.flowhub.config import ConfigurationManager

    manager = ConfigurationManager(env_file=Path(".env"))
    manager.load()
    result = manager.validate()
    if not result:
        print(result.format_errors())
        sys.exit(1)
    config = manager.get()
"""

from .expander import expand_template_variables, find_unexpanded_template_variables
from .loader import ConfigurationError, EnvironmentLoader
from .manager import ConfigurationManager, NotLoadedError, NotValidError
from .migration import ConfigMigration
from .profiles import ConfigProfile
from .schema import FlowHubConfig
from .secrets import EnvSecretProvider, SecretProvider, SECRET_FIELDS
from .validation import (
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    ConfigValidator,
    FieldError,
    ValidationResult,
)

__all__ = [
    # Manager (primary entry point)
    "ConfigurationManager",
    "NotLoadedError",
    "NotValidError",
    # Schema
    "FlowHubConfig",
    # Profiles
    "ConfigProfile",
    # Validation
    "ConfigValidator",
    "ValidationResult",
    "FieldError",
    "REQUIRED_FIELDS",
    "OPTIONAL_FIELDS",
    # Secrets
    "SecretProvider",
    "EnvSecretProvider",
    "SECRET_FIELDS",
    # Loading
    "EnvironmentLoader",
    "ConfigurationError",
    # Expansion
    "expand_template_variables",
    "find_unexpanded_template_variables",
    # Migration
    "ConfigMigration",
]
