#!/usr/bin/env python3
"""
Validation script for Prometheus configuration and PromQL queries.

This script validates:
1. Prometheus configuration syntax
2. Recording rules syntax
3. Alert rules syntax
4. PromQL queries in dashboards

Usage:
    python scripts/validate_prometheus_config.py
"""

import json
import sys
from pathlib import Path

import yaml


def validate_prometheus_config() -> bool:
    """Validate Prometheus configuration file."""
    config_path = Path("observability/prometheus/prometheus.yml")

    if not config_path.exists():
        print(f"❌ Prometheus config not found: {config_path}")
        return False

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Check required sections
        required_sections = ["global", "scrape_configs", "rule_files"]
        for section in required_sections:
            if section not in config:
                print(f"❌ Missing required section '{section}' in prometheus.yml")
                return False

        # Validate scrape configs
        scrape_configs = config.get("scrape_configs", [])
        if not scrape_configs:
            print("❌ No scrape configs defined")
            return False

        # Check for infrastructure exporters
        jobs = [job.get("job_name") for job in scrape_configs]
        required_exporters = ["kafka_exporter", "postgres_exporter", "redis_exporter"]

        for exporter in required_exporters:
            if exporter not in jobs:
                print(f"❌ Missing infrastructure exporter: {exporter}")
                return False

        print("✅ Prometheus configuration is valid")
        return True

    except yaml.YAMLError as e:
        print(f"❌ Invalid YAML in prometheus.yml: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating prometheus.yml: {e}")
        return False


def validate_recording_rules() -> bool:
    """Validate recording rules syntax."""
    rules_path = Path("observability/prometheus/rules/recording_rules.yml")

    if not rules_path.exists():
        print(f"❌ Recording rules not found: {rules_path}")
        return False

    try:
        with open(rules_path) as f:
            rules = yaml.safe_load(f)

        if "groups" not in rules:
            print("❌ Missing 'groups' section in recording rules")
            return False

        groups = rules["groups"]
        if not groups:
            print("❌ No rule groups defined")
            return False

        for group in groups:
            if "name" not in group:
                print("❌ Rule group missing 'name'")
                return False

            if "rules" not in group:
                print(f"❌ Rule group '{group['name']}' missing 'rules'")
                return False

            for rule in group["rules"]:
                if "record" not in rule:
                    print(f"❌ Recording rule missing 'record' in group '{group['name']}'")
                    return False

                if "expr" not in rule:
                    print(f"❌ Recording rule '{rule['record']}' missing 'expr'")
                    return False

        print("✅ Recording rules are valid")
        return True

    except yaml.YAMLError as e:
        print(f"❌ Invalid YAML in recording_rules.yml: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating recording_rules.yml: {e}")
        return False


def validate_alert_rules() -> bool:
    """Validate alert rules syntax."""
    rules_path = Path("observability/prometheus/rules/service_alerts.yml")

    if not rules_path.exists():
        print(f"❌ Alert rules not found: {rules_path}")
        return False

    try:
        with open(rules_path) as f:
            rules = yaml.safe_load(f)

        if "groups" not in rules:
            print("❌ Missing 'groups' section in alert rules")
            return False

        groups = rules["groups"]
        if not groups:
            print("❌ No alert groups defined")
            return False

        for group in groups:
            if "name" not in group:
                print("❌ Alert group missing 'name'")
                return False

            if "rules" not in group:
                print(f"❌ Alert group '{group['name']}' missing 'rules'")
                return False

            for rule in group["rules"]:
                if "alert" not in rule:
                    print(f"❌ Alert rule missing 'alert' in group '{group['name']}'")
                    return False

                if "expr" not in rule:
                    print(f"❌ Alert rule '{rule['alert']}' missing 'expr'")
                    return False

                if "annotations" not in rule:
                    print(f"❌ Alert rule '{rule['alert']}' missing 'annotations'")
                    return False

        print("✅ Alert rules are valid")
        return True

    except yaml.YAMLError as e:
        print(f"❌ Invalid YAML in service_alerts.yml: {e}")
        return False
    except Exception as e:
        print(f"❌ Error validating service_alerts.yml: {e}")
        return False


def validate_dashboard_queries() -> bool:
    """Validate PromQL queries in dashboard files."""
    dashboard_dir = Path("observability/grafana/dashboards")

    if not dashboard_dir.exists():
        print(f"❌ Dashboard directory not found: {dashboard_dir}")
        return False

    dashboard_files = list(dashboard_dir.glob("*.json"))
    if not dashboard_files:
        print("❌ No dashboard files found")
        return False

    invalid_patterns = [
        "__name__=~",  # Regex patterns that should be replaced
        ".*_http_requests_total",  # Specific regex we optimized
        ".*_http_request_duration",  # Specific regex we optimized
    ]

    issues_found = False

    for dashboard_file in dashboard_files:
        try:
            with open(dashboard_file) as f:
                dashboard = json.load(f)

            # Extract queries from panels
            panels = dashboard.get("panels", [])

            for panel in panels:
                targets = panel.get("targets", [])

                for target in targets:
                    expr = target.get("expr", "")
                    if expr:
                        # Check for inefficient patterns
                        for pattern in invalid_patterns:
                            if pattern in expr:
                                print(
                                    f"❌ Dashboard {dashboard_file.name} contains "
                                    f"inefficient query pattern: {pattern}"
                                )
                                print(f"   Query: {expr}")
                                issues_found = True

        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in {dashboard_file.name}: {e}")
            issues_found = True
        except Exception as e:
            print(f"❌ Error validating {dashboard_file.name}: {e}")
            issues_found = True

    if not issues_found:
        print("✅ Dashboard queries are optimized")
        return True
    else:
        return False


def main():
    """Run all validation checks."""
    print("🔍 Validating Prometheus observability configuration...\n")

    checks = [
        ("Prometheus Configuration", validate_prometheus_config),
        ("Recording Rules", validate_recording_rules),
        ("Alert Rules", validate_alert_rules),
        ("Dashboard Queries", validate_dashboard_queries),
    ]

    all_passed = True

    for check_name, check_func in checks:
        print(f"📋 {check_name}:")
        passed = check_func()
        if not passed:
            all_passed = False
        print()

    if all_passed:
        print("🎉 All validation checks passed!")
        print("✅ Observability configuration is optimized and ready for deployment")
        sys.exit(0)
    else:
        print("❌ Some validation checks failed")
        print("🔧 Please fix the issues before deploying")
        sys.exit(1)


if __name__ == "__main__":
    main()
