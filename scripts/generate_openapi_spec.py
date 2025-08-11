#!/usr/bin/env python3
"""
Script to generate OpenAPI specification from the API Gateway service.

This script imports the FastAPI app and exports its OpenAPI specification
without needing to run the full service with all dependencies.
"""

import json
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def generate_openapi_spec():
    """Generate and save the OpenAPI specification."""
    try:
        # Import the FastAPI app
        from services.api_gateway_service.app.main import create_app
        
        # Create the app instance
        app = create_app()
        
        # Get the OpenAPI schema
        openapi_schema = app.openapi()
        
        # Save to file
        docs_dir = project_root / "docs"
        docs_dir.mkdir(exist_ok=True)
        
        spec_file = docs_dir / "api-gateway-openapi.json"
        with open(spec_file, "w", encoding="utf-8") as f:
            json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
        
        print(f"✅ OpenAPI specification generated successfully!")
        print(f"📄 Saved to: {spec_file}")
        print(f"📊 Contains {len(openapi_schema.get('paths', {}))} endpoints")
        
        # Print summary of endpoints
        paths = openapi_schema.get('paths', {})
        if paths:
            print("\n📋 API Endpoints:")
            for path, methods in paths.items():
                method_list = list(methods.keys())
                print(f"  {path}: {', '.join(method_list).upper()}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure you're running this from the project root with PDM:")
        print("   pdm run python scripts/generate_openapi_spec.py")
        return False
        
    except Exception as e:
        print(f"❌ Error generating OpenAPI spec: {e}")
        return False

if __name__ == "__main__":
    success = generate_openapi_spec()
    sys.exit(0 if success else 1)
