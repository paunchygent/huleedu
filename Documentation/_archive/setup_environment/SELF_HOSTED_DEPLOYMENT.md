# HuleEdu Self-Hosted Deployment Guide

## Deployment Architecture

### Current Setup

- **Version Control**: GitHub repository
- **Deployment Target**: Private server (pre-launch)
- **Container Orchestration**: Docker Compose
- **CI/CD**: GitHub Actions (optional)

## Secrets Management for Self-Hosted Deployment

### Phase 1: Immediate Security (GitHub + Server)

#### 1. GitHub Repository Security

```bash
# Ensure .env files are never committed
echo ".env*" >> .gitignore
echo "!.env.example" >> .gitignore

# Remove any accidentally committed secrets
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch docker-compose.yml' \
  --prune-empty --tag-name-filter cat -- --all
```

#### 2. Server-Side Environment Management

```bash
# On your server: Create secure environment directory
sudo mkdir -p /opt/huledu/config
sudo chmod 750 /opt/huledu/config

# Create production environment file
sudo nano /opt/huledu/config/.env.production
```

#### 3. Deployment Script Pattern

```bash
#!/bin/bash
# deploy.sh - Run on your server

# Set secure environment
export ENV_FILE="/opt/huledu/config/.env.production"
export COMPOSE_FILE="/opt/huledu/docker-compose.yml"

# Deploy with environment file
docker compose --env-file $ENV_FILE -f $COMPOSE_FILE up -d
```

### Phase 2: GitHub Actions Integration

#### GitHub Secrets Setup

1. Go to your GitHub repo → Settings → Secrets and variables → Actions
2. Add secrets:
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `GOOGLE_API_KEY`
   - `OPENROUTER_API_KEY`
   - `DEPLOY_HOST` (your server IP)
   - `DEPLOY_USER` (deployment user)
   - `DEPLOY_SSH_KEY` (private key for deployment)

#### Deployment Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy to Server

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Setup SSH
      uses: webfactory/ssh-agent@v0.7.0
      with:
        ssh-private-key: ${{ secrets.DEPLOY_SSH_KEY }}
    
    - name: Deploy to server
      run: |
        # Copy code to server
        rsync -avz --delete \
          --exclude='.env*' \
          --exclude='.git' \
          ./ ${{ secrets.DEPLOY_USER }}@${{ secrets.DEPLOY_HOST }}:/opt/huledu/
        
        # Create environment file on server
        ssh ${{ secrets.DEPLOY_USER }}@${{ secrets.DEPLOY_HOST }} '
          cat > /opt/huledu/.env << EOF
          OPENAI_API_KEY=${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}
          GOOGLE_API_KEY=${{ secrets.GOOGLE_API_KEY }}
          OPENROUTER_API_KEY=${{ secrets.OPENROUTER_API_KEY }}
          ENVIRONMENT=production
          LOG_LEVEL=INFO
          EOF
          
          # Secure the environment file
          chmod 600 /opt/huledu/.env
          
          # Deploy containers
          cd /opt/huledu
          docker compose down --remove-orphans
          docker compose up -d --build
        '
```

### Phase 3: Server Security Hardening

#### System Security

```bash
# Create dedicated user for HuleEdu
sudo useradd -r -s /bin/false huledu
sudo usermod -aG docker huledu

# Secure directories
sudo chown -R huledu:huledu /opt/huledu
sudo chmod -R 750 /opt/huledu
sudo chmod 600 /opt/huledu/.env*
```

#### Docker Security

```bash
# Use Docker secrets for sensitive data
echo "your-openai-key" | docker secret create openai_api_key -

# Update docker-compose.yml to use secrets
services:
  cj_assessment_service:
    secrets:
      - openai_api_key
    environment:
      - OPENAI_API_KEY_FILE=/run/secrets/openai_api_key

secrets:
  openai_api_key:
    external: true
```

#### Firewall Configuration

```bash
# Basic firewall setup
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable

# If you need to access services directly (development only)
sudo ufw allow 5001/tcp  # BOS
sudo ufw allow 6001/tcp  # ELS
sudo ufw allow 7001/tcp  # File Service
```

## Deployment Workflows

### Development Workflow

```bash
# Local development
cp env.example .env
# Edit .env with development keys
docker compose up -d

# Test changes
git add .
git commit -m "feat: new feature"
git push origin feature-branch
```

### Production Deployment

```bash
# Merge to main branch
git checkout main
git merge feature-branch
git push origin main

# GitHub Actions automatically deploys
# Or manual deployment:
ssh user@yourserver.com
cd /opt/huledu
git pull origin main
docker compose down --remove-orphans
docker compose up -d --build
```

## Monitoring & Maintenance

### Log Management

```bash
# Set up log rotation
sudo nano /etc/logrotate.d/huledu
```

```text
/opt/huledu/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 huledu huledu
}
```

### Health Monitoring

```bash
# Simple health check script
#!/bin/bash
# /opt/huledu/scripts/health-check.sh

services=("content_service" "batch_orchestrator_service" "essay_lifecycle_api")

for service in "${services[@]}"; do
    if ! docker compose ps $service | grep -q "Up"; then
        echo "ALERT: $service is down"
        # Send notification (email, Slack, etc.)
    fi
done
```

### Backup Strategy

```bash
# Automated backup script
#!/bin/bash
# /opt/huledu/scripts/backup.sh

# Backup databases
docker exec huleedu_batch_orchestrator_db pg_dump -U huleedu_user batch_orchestrator > /opt/backups/batch_orchestrator_$(date +%Y%m%d).sql

# Backup environment config
cp /opt/huledu/.env /opt/backups/env_$(date +%Y%m%d).backup

# Backup to remote location
rsync -avz /opt/backups/ user@backup-server:/backups/huledu/
```

## Cost-Effective Solutions

### Free/Low-Cost Tools

- **Monitoring**: Grafana + Prometheus (free)
- **Logs**: ELK Stack or Loki (free)
- **Secrets**: File-based with proper permissions (free)
- **Backups**: rsync to another server (free)
- **SSL**: Let's Encrypt (free)

### Recommended Server Specs

```text
Minimum (Development):
- 4 CPU cores
- 8GB RAM
- 100GB SSD
- 1Gbps network

Recommended (Production):
- 8 CPU cores
- 16GB RAM
- 200GB SSD
- 1Gbps network
```

## Pre-Launch Checklist

### Security

- [ ] All secrets removed from git history
- [ ] Environment files secured (600 permissions)
- [ ] Firewall configured
- [ ] SSL certificates installed
- [ ] Regular security updates scheduled

### Deployment

- [ ] Automated deployment pipeline
- [ ] Health monitoring
- [ ] Log aggregation
- [ ] Backup automation
- [ ] Rollback procedures documented

### Monitoring

- [ ] Service health checks
- [ ] Resource usage monitoring
- [ ] Error rate tracking
- [ ] API cost monitoring
- [ ] Disk space alerts

## Transition to Cloud (Future)

When ready for cloud deployment:

1. **Migrate secrets** to cloud secrets manager
2. **Container orchestration** to Kubernetes/ECS
3. **Databases** to managed services
4. **Monitoring** to cloud-native solutions
5. **Scaling** to auto-scaling groups

---

**This setup provides enterprise-grade security with self-hosted simplicity and cost control.**
