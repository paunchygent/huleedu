#!/usr/bin/env python3
"""
Trace Search Script for HuleEdu Distributed Tracing

This script provides utilities for searching and analyzing traces in Jaeger
by correlation ID, batch ID, or other criteria.

Usage:
    python scripts/trace_search.py --correlation-id <id>
    python scripts/trace_search.py --batch-id <id>
    python scripts/trace_search.py --service <name> --operation <op>
    python scripts/trace_search.py --error-only --last-hour
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp
from rich.console import Console
from rich.table import Table
from rich.tree import Tree


console = Console()


class JaegerTraceSearcher:
    """Search and analyze traces from Jaeger."""

    def __init__(self, jaeger_url: str = "http://localhost:16686"):
        self.jaeger_url = jaeger_url
        self.api_base = f"{jaeger_url}/api"

    async def search_by_correlation_id(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Search traces by correlation ID."""
        tag_query = f"correlation_id={correlation_id}"
        return await self._search_traces(tags=tag_query)

    async def search_by_batch_id(self, batch_id: str) -> List[Dict[str, Any]]:
        """Search traces by batch ID."""
        tag_query = f"batch_id={batch_id}"
        return await self._search_traces(tags=tag_query)

    async def search_by_service_operation(
        self,
        service: Optional[str] = None,
        operation: Optional[str] = None,
        error_only: bool = False,
        lookback_hours: int = 1,
    ) -> List[Dict[str, Any]]:
        """Search traces by service and/or operation."""
        tags = {}
        if error_only:
            tags["error"] = "true"

        return await self._search_traces(
            service=service,
            operation=operation,
            tags=tags,
            lookback_hours=lookback_hours,
        )

    async def _search_traces(
        self,
        service: Optional[str] = None,
        operation: Optional[str] = None,
        tags: Optional[Any] = None,
        lookback_hours: int = 1,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Execute trace search against Jaeger API."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=lookback_hours)

        params = {
            "start": int(start_time.timestamp() * 1_000_000),  # microseconds
            "end": int(end_time.timestamp() * 1_000_000),
            "limit": limit,
        }

        if service:
            params["service"] = service
        if operation:
            params["operation"] = operation
        if tags:
            if isinstance(tags, dict):
                params["tags"] = json.dumps(tags)
            else:
                params["tags"] = tags

        async with aiohttp.ClientSession() as session:
            url = f"{self.api_base}/traces"
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    console.print(
                        f"[red]Error: Failed to search traces. Status: {response.status}[/red]"
                    )
                    return []
                data = await response.json()
                return data.get("data", [])

    async def get_trace_details(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific trace."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_base}/traces/{trace_id}"
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                return data.get("data", [None])[0]

    def format_trace_summary(self, trace: Dict[str, Any]) -> None:
        """Print a formatted summary of a trace."""
        spans = trace.get("spans", [])
        if not spans:
            return

        # Get trace metadata
        trace_id = trace["traceID"]
        root_span = next((s for s in spans if not s.get("references")), spans[0])
        service_name = root_span["process"]["serviceName"]
        operation = root_span["operationName"]
        
        # Calculate duration
        start_time = min(s["startTime"] for s in spans)
        end_time = max(s["startTime"] + s["duration"] for s in spans)
        duration_ms = (end_time - start_time) / 1000  # Convert to milliseconds

        # Count errors
        error_count = sum(1 for s in spans if any(
            t.get("key") == "error" and t.get("value") for t in s.get("tags", [])
        ))

        # Find correlation ID
        correlation_id = None
        for span in spans:
            for tag in span.get("tags", []):
                if tag.get("key") == "correlation_id":
                    correlation_id = tag.get("value")
                    break
            if correlation_id:
                break

        # Create summary table
        table = Table(title=f"Trace Summary: {trace_id[:16]}...")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="yellow")

        table.add_row("Service", service_name)
        table.add_row("Operation", operation)
        table.add_row("Duration", f"{duration_ms:.2f} ms")
        table.add_row("Span Count", str(len(spans)))
        table.add_row("Error Count", str(error_count))
        if correlation_id:
            table.add_row("Correlation ID", correlation_id)

        console.print(table)

        # Create service interaction tree
        self._print_service_tree(spans)

        # Show errors if any
        if error_count > 0:
            self._print_errors(spans)

        # Print Jaeger UI link
        console.print(
            f"\n[blue]View in Jaeger UI:[/blue] {self.jaeger_url}/trace/{trace_id}"
        )

    def _print_service_tree(self, spans: List[Dict[str, Any]]) -> None:
        """Print a tree view of service interactions."""
        tree = Tree("Service Flow")
        
        # Build span hierarchy
        span_map = {s["spanID"]: s for s in spans}
        root_spans = [s for s in spans if not s.get("references")]
        
        def add_span_to_tree(span: Dict[str, Any], parent_node: Tree) -> None:
            service = span["process"]["serviceName"]
            operation = span["operationName"]
            duration_ms = span["duration"] / 1000
            
            # Check for errors
            has_error = any(
                t.get("key") == "error" and t.get("value") 
                for t in span.get("tags", [])
            )
            
            label = f"{service} → {operation} ({duration_ms:.1f}ms)"
            if has_error:
                label = f"[red]{label} ❌[/red]"
            
            node = parent_node.add(label)
            
            # Find child spans
            for s in spans:
                for ref in s.get("references", []):
                    if ref.get("spanID") == span["spanID"]:
                        add_span_to_tree(s, node)
        
        for root_span in root_spans:
            add_span_to_tree(root_span, tree)
        
        console.print(tree)

    def _print_errors(self, spans: List[Dict[str, Any]]) -> None:
        """Print error details from spans."""
        console.print("\n[red]Errors Found:[/red]")
        
        for span in spans:
            tags = {t["key"]: t["value"] for t in span.get("tags", [])}
            if tags.get("error"):
                service = span["process"]["serviceName"]
                operation = span["operationName"]
                
                console.print(f"\n  Service: {service}")
                console.print(f"  Operation: {operation}")
                
                # Look for error message in logs
                for log in span.get("logs", []):
                    for field in log.get("fields", []):
                        if field.get("key") in ["error", "error.message", "message"]:
                            console.print(f"  Error: {field.get('value')}")
                
                # Show error-related tags
                for key, value in tags.items():
                    if "error" in key.lower() or "exception" in key.lower():
                        console.print(f"  {key}: {value}")


async def main():
    """Main entry point for the trace search script."""
    parser = argparse.ArgumentParser(
        description="Search and analyze HuleEdu distributed traces"
    )
    
    # Search criteria
    parser.add_argument(
        "--correlation-id",
        help="Search by correlation ID"
    )
    parser.add_argument(
        "--batch-id",
        help="Search by batch ID"
    )
    parser.add_argument(
        "--service",
        help="Filter by service name"
    )
    parser.add_argument(
        "--operation",
        help="Filter by operation name"
    )
    parser.add_argument(
        "--error-only",
        action="store_true",
        help="Show only traces with errors"
    )
    parser.add_argument(
        "--last-hour",
        action="store_true",
        help="Search only last hour (default)"
    )
    parser.add_argument(
        "--last-day",
        action="store_true",
        help="Search last 24 hours"
    )
    parser.add_argument(
        "--jaeger-url",
        default="http://localhost:16686",
        help="Jaeger URL (default: http://localhost:16686)"
    )
    
    args = parser.parse_args()
    
    # Determine lookback period
    lookback_hours = 1
    if args.last_day:
        lookback_hours = 24
    
    searcher = JaegerTraceSearcher(args.jaeger_url)
    
    # Execute search based on criteria
    traces = []
    
    if args.correlation_id:
        console.print(f"[green]Searching for correlation ID: {args.correlation_id}[/green]")
        traces = await searcher.search_by_correlation_id(args.correlation_id)
    elif args.batch_id:
        console.print(f"[green]Searching for batch ID: {args.batch_id}[/green]")
        traces = await searcher.search_by_batch_id(args.batch_id)
    else:
        console.print(
            f"[green]Searching traces"
            f"{' for service: ' + args.service if args.service else ''}"
            f"{' with operation: ' + args.operation if args.operation else ''}"
            f"{' (errors only)' if args.error_only else ''}[/green]"
        )
        traces = await searcher.search_by_service_operation(
            service=args.service,
            operation=args.operation,
            error_only=args.error_only,
            lookback_hours=lookback_hours,
        )
    
    if not traces:
        console.print("[yellow]No traces found matching criteria[/yellow]")
        return
    
    console.print(f"\n[green]Found {len(traces)} trace(s)[/green]\n")
    
    # Display each trace
    for i, trace in enumerate(traces, 1):
        if i > 1:
            console.print("\n" + "=" * 80 + "\n")
        
        console.print(f"[bold]Trace {i} of {len(traces)}[/bold]")
        searcher.format_trace_summary(trace)
    
    # Print search tips
    if len(traces) == 100:
        console.print(
            "\n[yellow]Note: Result limit reached (100 traces). "
            "Use more specific search criteria to find exact traces.[/yellow]"
        )


if __name__ == "__main__":
    asyncio.run(main())