# Authentication for Admin Endpoints

## AI/Scripts (Development)

```python
from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers

headers = build_admin_headers()  # Auto-generates admin token
# Use headers in HTTP requests to /admin/v1/* endpoints
```

No setup needed. Auto-generates tokens in development.

## Production

```bash
export HULEEDU_SERVICE_ACCOUNT_TOKEN="<token-from-identity-service>"
```

Development auth blocked in production. Requires service account token.

## Verify

```bash
pdm run python -m scripts.cj_experiments_runners.eng5_np.cli verify-auth
```
