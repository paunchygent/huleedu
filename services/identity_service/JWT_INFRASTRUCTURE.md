# Identity Service JWT Infrastructure

## Overview

The HuleEdu Identity Service supports two JWT signing mechanisms:
- **Development**: HS256 symmetric signing with shared secret
- **Production**: RS256 asymmetric signing with RSA key pair

## Current Setup

### Development Mode (HS256)
- **Environment**: `HULEEDU_ENVIRONMENT=development` (default)
- **Secret**: Configured via `IDENTITY_JWT_DEV_SECRET` in `.env`
- **Token Issuer**: `DevTokenIssuer` class
- **Security**: Symmetric key, suitable for development only

### Production Mode (RS256)
- **Environment**: `HULEEDU_ENVIRONMENT=production` or `ENVIRONMENT=production`
- **Private Key**: `./secrets/jwt-private-key.pem` (4096-bit RSA)
- **Public Key**: `./secrets/jwt-public-key.pem` (exposed via JWKS)
- **Key ID**: `huleedu-identity-prod-key-2025-01` (for key rotation)
- **Token Issuer**: `Rs256TokenIssuer` class
- **JWKS Endpoint**: `/jwks` exposes public key for token verification

## Configuration

### Environment Variables
```bash
# Development
IDENTITY_JWT_DEV_SECRET=<secure-random-secret>

# Canonical JWT identity
IDENTITY_JWT_ISSUER=huleedu-identity-service
IDENTITY_JWT_AUDIENCE=huleedu-platform

# Production
IDENTITY_JWT_RS256_PRIVATE_KEY_PATH=./secrets/jwt-private-key.pem
IDENTITY_JWT_RS256_PUBLIC_JWKS_KID=huleedu-identity-prod-key-2025-01
```

### Switching Between Modes
```bash
# Development mode (default)
HULEEDU_ENVIRONMENT=development

# Production mode
HULEEDU_ENVIRONMENT=production
# or
ENVIRONMENT=production
```

## Security Features

### SecretStr Protection
- All JWT secrets use Pydantic's `SecretStr` type
- Secrets are masked in logs: `secrets=***MASKED***`
- Explicit access required: `secret.get_secret_value()`

### File Security
- Private key permissions: `600` (owner read/write only)
- Public key permissions: `644` (readable by all)
- Git ignored: `secrets/` directory and all `*.pem` files

### Token Structure

#### HS256 (Development)
```json
{
  "header": {"alg": "HS256", "typ": "JWT"},
  "payload": {
    "sub": "user_id",
    "org": "org_id",
    "roles": ["teacher", "admin"],
    "exp": 1234567890,
    "iss": "huleedu-identity-service",
    "aud": "huleedu-platform"
  }
}
```

#### RS256 (Production)
```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT",
    "kid": "huleedu-identity-prod-key-2025-01"
  },
  "payload": {
    "sub": "user_id",
    "org": "org_id",
    "roles": ["teacher", "admin"],
    "exp": 1234567890,
    "iss": "huleedu-identity-service",
    "aud": "huleedu-platform"
  }
}
```

#### Refresh Tokens (Dev/Prod)
```json
{
  "header": {"alg": "HS256", "typ": "JWT"},
  "payload": {
    "sub": "user_id",
    "typ": "refresh",
    "jti": "r-<timestamp>",
    "exp": 1234567890,
    "iss": "huleedu-identity-service"
    // Note: no "aud" by design
  }
}
```

## Key Management

### Generating New Keys
```bash
# Generate new RSA key pair
openssl genrsa -out secrets/jwt-private-key.pem 4096
openssl rsa -in secrets/jwt-private-key.pem -pubout -out secrets/jwt-public-key.pem

# Set secure permissions
chmod 600 secrets/jwt-private-key.pem
chmod 644 secrets/jwt-public-key.pem
```

### Key Rotation
1. Generate new key pair with unique filename
2. Update `IDENTITY_JWT_RS256_PUBLIC_JWKS_KID` with new ID
3. Update `IDENTITY_JWT_RS256_PRIVATE_KEY_PATH` with new path
4. Old tokens remain valid until expiration
5. JWKS endpoint exposes multiple keys during transition

## Testing

### Test RS256 in Development
```bash
# Temporarily switch to production mode
ENVIRONMENT=production pdm run pytest services/identity_service/tests/unit/test_token_issuer_unit.py

# Verify token generation
ENVIRONMENT=production pdm run python -c "
from services.identity_service.config import settings
print(f'Will use RS256: {settings.is_production() and bool(settings.JWT_RS256_PRIVATE_KEY_PATH)}')
"
```

### Test JWKS Endpoint
```bash
# Start service in production mode
ENVIRONMENT=production pdm run python services/identity_service/app.py

# Fetch JWKS
curl http://localhost:8000/jwks
```

## Production Deployment

### Prerequisites
1. Generate production RSA key pair
2. Store private key securely (AWS Secrets Manager, Vault, etc.)
3. Set environment variables in production environment
4. Ensure `HULEEDU_ENVIRONMENT=production`

### Security Checklist
- [ ] Private key stored securely
- [ ] Private key never committed to git
- [ ] Unique KID for key rotation
- [ ] JWKS endpoint accessible
- [ ] Token expiration configured appropriately
- [ ] Monitoring for token validation failures

## Troubleshooting

### Common Issues

1. **"JWT_RS256_PRIVATE_KEY_PATH must be set in production"**
   - Ensure path is set in `.env` and file exists
   - Check file permissions

2. **"'SecretStr' object has no attribute 'encode'"**
   - Code is not using `.get_secret_value()` to extract secret
   - Fixed in token issuer implementations

3. **Token verification fails**
   - Ensure public key matches private key
   - Check KID matches between token and JWKS
   - Verify algorithm matches (RS256 vs HS256)
