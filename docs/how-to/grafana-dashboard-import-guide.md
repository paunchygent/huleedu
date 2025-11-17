# Grafana Dashboard Import Guide

This guide walks you through importing and configuring the HuleEdu three-tier dashboard system into your Grafana instance.

## Prerequisites

Before importing the dashboards, ensure you have:

1. **Grafana Running**: Access Grafana at <http://localhost:3000>
   - Default credentials: admin/admin
   - Auto-configured with Prometheus and Loki data sources

   ```bash
   pdm run obs-up  # Start observability stack
   # or
   docker compose -f observability/docker-compose.observability.yml up -d
   ```

2. **Data Sources Auto-Configured**:
   - **Prometheus**: <http://localhost:9091> (external) / `http://prometheus:9090` (internal)
   - **Loki**: <http://localhost:3100> (external) / `http://loki:3100` (internal) ✅ WORKING
   - **Alertmanager**: <http://localhost:9094/> (external) / `http://alertmanager:9093` (internal)
   - **Jaeger**: <http://localhost:16686> (distributed tracing UI)

3. **Services Running**: HuleEdu microservices and infrastructure must be running

   ```bash
   pdm run dc-up  # Start all services and infrastructure
   # or
   docker compose up -d
   ```

   **Quick Status Check**:

   ```bash
   pdm run dc-ps  # Check all container status
   curl http://localhost:9091/api/v1/targets  # Check Prometheus targets
   ```

## Step 1: Verify Data Sources

1. Log into Grafana (default credentials: admin/admin)
2. Navigate to **Configuration** → **Data Sources** (or **Connections** → **Data sources** in newer versions)
3. Verify you have (should be auto-configured):
   - **Prometheus** data source pointing to `http://prometheus:9090` (internal)
   - **Loki** data source pointing to `http://loki:3100` (internal) ✅ CONFIRMED WORKING
   - **External Access**: Prometheus UI at <http://localhost:9091>
   - **External Access**: Loki logs via Grafana Explore

4. **Add AlertManager Data Source (Manual)**:
   - Click **Add data source** → **AlertManager**
   - **Name**: `AlertManager`
   - **URL**: `http://alertmanager:9093` (internal container URL)
   - **Implementation**: `Prometheus` (default)
   - Click **Save & Test**

If these don't exist, add them:

### Adding Prometheus Data Source

1. Click **Add data source**
2. Select **Prometheus**
3. Configure:
   - Name: `Prometheus`
   - URL: `http://prometheus:9090`
4. Click **Save & Test**

### Adding Loki Data Source

1. Click **Add data source**
2. Select **Loki**
3. Configure:
   - Name: `Loki`
   - URL: `http://loki:3100`
4. Click **Save & Test**

## Step 2: Import the Dashboards

Import the dashboards in this specific order to ensure proper navigation links:

### 1. Import System Health Overview (Tier 1)

1. Navigate to **Dashboards** → **Import** (or click the **+** icon → **Import**)
2. Click **Upload JSON file**
3. Select: `grafana/dashboards/HuleEdu_System_Health_Overview.json`
4. In the import dialog:
   - Name: Keep as "HuleEdu System Health Overview"
   - Folder: Select "General" or create a new folder called "HuleEdu"
   - UID: Keep as `huleedu-system-health`
   - Select **Prometheus** for the data source variable
5. Click **Import**

### 2. Import Service Deep Dive (Tier 2)

1. Navigate to **Dashboards** → **Import**
2. Click **Upload JSON file**
3. Select: `grafana/dashboards/HuleEdu_Service_Deep_Dive_Template.json`
4. In the import dialog:
   - Name: Keep as "HuleEdu Service Deep Dive"
   - Folder: Same as Tier 1
   - UID: Keep as `huleedu-service-deep-dive`
   - Select **Prometheus** for the Prometheus data source
   - Select **Loki** for the Loki data source
5. Click **Import**

### 3. Import Troubleshooting Dashboard (Tier 3)

1. Navigate to **Dashboards** → **Import**
2. Click **Upload JSON file**
3. Select: `grafana/dashboards/HuleEdu_Troubleshooting.json`
4. In the import dialog:
   - Name: Keep as "HuleEdu Troubleshooting"
   - Folder: Same as Tier 1 & 2
   - UID: Keep as `huleedu-troubleshooting`
   - Select **Prometheus** for the Prometheus data source
   - Select **Loki** for the Loki data source
5. Click **Import**

## Step 3: Verify Dashboard Functionality

### System Health Overview

1. Open the dashboard
2. Verify you see:
   - Service availability percentage (should show >0% if services are running)
   - Global error rate graph
   - Infrastructure status panels (Kafka, PostgreSQL, Redis)
   - Active alerts (if any are firing)

### Service Deep Dive

1. Open the dashboard
2. Use the **Service** dropdown to select a service (e.g., `batch_orchestrator_service`)
3. Verify you see:
   - Request rate and duration graphs
   - Error rate table by endpoint
   - Business metrics (if applicable to selected service)
   - Live logs from the selected service

### Troubleshooting Dashboard

1. Open the dashboard
2. To test with a correlation ID:
   - First, generate some traffic to create logs
   - Look in the Service Deep Dive logs for a correlation_id
   - Copy a correlation ID from the logs
   - Paste it into the **Correlation ID** field
3. Verify you see:
   - Distributed trace timeline
   - Service involvement map
   - Log level distribution

## Step 4: Configure Dashboard Settings

### Set Default Time Ranges

1. For each dashboard, click the time range selector (top right)
2. Recommended defaults:
   - System Health: Last 6 hours
   - Service Deep Dive: Last 1 hour
   - Troubleshooting: Last 1 hour

### Configure Auto-Refresh

1. Click the refresh icon next to the time range
2. Recommended refresh rates:
   - System Health: 30s
   - Service Deep Dive: 30s
   - Troubleshooting: 5s (when actively troubleshooting)

### Save as Default

1. After configuring time range and refresh
2. Click **Save dashboard** (disk icon)
3. Check **Save current time range as dashboard default**
4. Click **Save**

## Step 5: HuleEdu Service URLs

### **Service Health Endpoints**

| Service | External URL | Health Check | Metrics |
|---------|--------------|--------------|----------|
| API Gateway | <http://localhost:8080> | /healthz | /metrics |
| LLM Provider | <http://localhost:8090> | /healthz | /metrics |
| Content Service | <http://localhost:8001> | /healthz | /metrics |
| File Service | <http://localhost:7001> | /healthz | /metrics |
| Batch Orchestrator | <http://localhost:5001> | /healthz | /metrics |
| Class Management | <http://localhost:5002> | /healthz | /metrics |
| CJ Assessment | <http://localhost:9095> | /healthz | /metrics |
| Spell Checker | <http://localhost:8002> | /healthz | /metrics |
| Result Aggregator | <http://localhost:4003> | /healthz | /metrics |
| Essay Lifecycle API | <http://localhost:6001> | /healthz | /metrics |

### **Loki Log Aggregation System**

**Loki is extensively used** for centralized log aggregation across all HuleEdu services:

#### **Loki Access Points**

- **Loki API**: <http://localhost:3100> (direct API access) ✅ WORKING
- **Grafana Integration**: <http://localhost:3000/explore> (pre-configured data source)
- **Internal Container**: `http://loki:3100` ✅ CONFIRMED WORKING FOR GRAFANA

#### **Active Log Labels**

Loki automatically extracts these labels from all service logs:

- `container` - Docker container name
- `correlation_id` - Request correlation UUID
- `level` - Log level (info, error, warning, debug)
- `logger_name` - Python logger hierarchy
- `service` - Service identifier
- `service_name` - Full service name

#### **Common Loki Queries**

```logql
# All logs from a specific service
{service="llm_provider_service"}

# Error logs across all services
{level="error"}

# Trace a specific request by correlation ID
{correlation_id="550e8400-e29b-41d4-a716-446655440000"}

# Container-specific logs
{container="huleedu_batch_orchestrator_service"}

# JSON field extraction
{service=~".+"} | json | line_format "{{.level}}: {{.event}}"
```

#### **Troubleshooting Dashboard Integration**

The HuleEdu Troubleshooting dashboard uses Loki extensively for:

- **Correlation ID Tracing**: Complete request timeline across services
- **Service Log Filtering**: Real-time log streaming by service
- **Error Context**: Detailed error logs with full context
- **Performance Analysis**: Request duration and service interaction logs

## Step 6: Create Dashboard Bookmarks

For quick access, bookmark these URLs:

### **Dashboard URLs**

- **System Health**: <http://localhost:3000/d/huleedu-system-health/huleedu-system-health-overview>
- **Service Deep Dive**: <http://localhost:3000/d/huleedu-service-deep-dive/huleedu-service-deep-dive>
- **Troubleshooting**: <http://localhost:3000/d/huleedu-troubleshooting/huleedu-troubleshooting>

### **Direct Component Access**

- **Grafana**: <http://localhost:3000> (admin/admin)
- **Prometheus**: <http://localhost:9091> (metrics & queries)
- **Loki**: <http://localhost:3100> (log aggregation API) ✅ WORKING
- **Alertmanager**: <http://localhost:9094/> (alert management - note trailing slash)
- **Jaeger**: <http://localhost:16686> (distributed tracing)

### **Data Source URLs for Grafana Configuration**

**Use these internal URLs when configuring data sources in Grafana:**

- **Prometheus**: `http://prometheus:9090`
- **Loki**: `http://loki:3100` ✅ CONFIRMED WORKING
- **AlertManager**: `http://alertmanager:9093` (no trailing slash for data source)

### **Infrastructure Monitoring**

- **Kafka Metrics**: <http://localhost:9308/metrics>
- **PostgreSQL Metrics**: <http://localhost:9187/metrics>
- **Redis Metrics**: <http://localhost:9121/metrics>
- **Node Metrics**: <http://localhost:9100/metrics>

## Troubleshooting Common Issues

### No Data Showing

1. **Check service status**:

   ```bash
   docker compose ps
   ```

2. **Verify Prometheus is scraping**:
   - Go to <http://localhost:9091/targets> (Note: Port 9091, not 9090)
   - All 14+ targets should show as "UP"
   - Services: 10+ microservices
   - Exporters: kafka_exporter, postgres_exporter, redis_exporter, node_exporter

3. **Check metric names**:
   - Go to <http://localhost:9091> (Prometheus UI)
   - Try these test queries:
     - `up{job=~".*_service"}` (should return 10+ services)
     - `huleedu:service_availability:percent` (should return 100)
     - `huleedu:http_requests:rate5m` (should return current request rate)

### Service Dropdown Empty

1. Ensure services are running and being scraped
2. Wait 1-2 minutes for Prometheus to collect data
3. Refresh the dashboard

### Logs Not Showing

1. Verify Promtail is running:

   ```bash
   docker compose ps promtail
   ```

2. Check Loki for any logs:
   - In Grafana, go to **Explore**
   - Select Loki data source
   - Run query: `{service=~".+"}`

### JSON Parser Errors in Logs

If you see `JSONParserErr` with successful log messages:

1. **This is expected behavior** - The services use structlog which outputs JSON, but not all fields are present in every log
2. **The actual log messages are still captured** - You can see the event details even with the parser error
3. **To reduce these errors**, consider using the improved Promtail configuration (`promtail-config-improved.yml`)
4. **Correlation IDs are still tracked** - They appear in logs that involve event processing

### Correlation ID Search Returns No Results

1. Ensure the correlation ID exists in logs
2. Check the time range includes when the correlation ID was active
3. Verify the correlation_id label is being extracted by Promtail

## Navigation Tips

### Progressive Disclosure Flow

1. **Start at System Health** for overall platform status
2. **Drill down to Service Deep Dive** when you identify a problematic service
3. **Use Troubleshooting** when you need to trace a specific request

### Finding and Using Correlation IDs

Correlation IDs are UUID values that track a request across all services. Here's how to find and use them:

#### Where to Find Correlation IDs

1. **In Service Deep Dive Dashboard**:
   - Navigate to the Live Logs panel
   - Look for `correlation_id` field in JSON logs
   - Example: `"correlation_id": "550e8400-e29b-41d4-a716-446655440000"`

2. **In Application Error Responses**:
   - When an API returns an error, it includes a correlation ID
   - Check HTTP response headers or error body

3. **In Alert Notifications**:
   - Critical errors often include correlation IDs in alert descriptions

#### How to Use Correlation IDs

1. **Copy the Correlation ID**:
   - From logs: Click on a log entry to expand it
   - Find the correlation_id field
   - Copy the UUID value (without quotes)

2. **Navigate to Troubleshooting Dashboard**:
   - Go to the HuleEdu Troubleshooting dashboard
   - Paste the correlation ID into the text field
   - The dashboard will show:
     - Complete request timeline across all services
     - Which services were involved
     - Any errors that occurred
     - Performance metrics during that request

3. **Typical Workflow**:
   ```
   User reports error → Check Service Deep Dive logs → Find correlation_id → 
   Paste in Troubleshooting dashboard → See complete request trace
   ```

### Using Variables

- **Service Selection**: Use the dropdown in Service Deep Dive to switch between services
- **Log Filtering**: Use the log filter text box to search for specific terms
- **Correlation ID**: Copy from logs or error messages for request tracing

### Keyboard Shortcuts

- `d + h`: Go to dashboard home
- `d + s`: Dashboard settings
- `d + v`: Toggle variable values display
- `?`: Show all keyboard shortcuts

## Best Practices

1. **Regular Review**: Check System Health dashboard at least twice daily
2. **Alert Response**: When alerts fire, use the dashboard links in the alert
3. **Performance Baseline**: Familiarize yourself with normal metrics during low and high traffic
4. **Correlation IDs**: Always include correlation IDs in bug reports for easier troubleshooting

## Next Steps

1. Set up alert notification channels in Grafana
2. Create custom dashboard panels for your specific use cases
3. Configure dashboard permissions for team members
4. Export dashboard JSON files periodically as backups

For more information on using these dashboards effectively, see:

- [Grafana Playbook](../OPERATIONS/01-Grafana-Playbook.md)
- [Observability Rules](../../.cursor/rules/071-observability-rules-and-patterns.md)
