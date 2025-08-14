#!/bin/bash
# Validate production database configuration

set -e

if [ "$HULEEDU_ENVIRONMENT" != "production" ]; then
    echo "❌ HULEEDU_ENVIRONMENT must be set to 'production'"
    exit 1
fi

# Check required production variables
required_vars=(
    "HULEEDU_PROD_DB_HOST" 
    "HULEEDU_PROD_DB_PASSWORD"
    "HULEEDU_DB_USER"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    echo "❌ Missing required production environment variables:"
    printf '   - %s\n' "${missing_vars[@]}"
    exit 1
fi

echo "✅ Production configuration validated"
echo "🔗 Database host: $HULEEDU_PROD_DB_HOST"
echo "👤 Database user: $HULEEDU_DB_USER"