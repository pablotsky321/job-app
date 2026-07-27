#!/usr/bin/env python3
"""
Export OpenAPI specification from FastAPI app to JSON file.

This script:
1. Loads environment from .env file (maps TABLE_* to DYNAMODB_TABLE_*)
2. Imports the fully assembled FastAPI app from backend/main.py
3. Calls app.openapi() to generate OpenAPI spec
4. Writes the result to frontend/openapi/openapi.json (indented JSON)

Usage:
    python scripts/export-openapi.py

Environment Variables:
    - All DynamoDB table names must be set (checked during app startup)
    - CORS_ALLOWED_ORIGINS (optional, defaults to http://localhost:3000)
    - Bedrock region and model IDs (checked during app startup)

Output:
    - frontend/openapi/openapi.json (readable indented JSON)

Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6
"""

import json
import sys
import os
from pathlib import Path

# Load .env file from project root
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    print(f"Loading environment from {env_file}")
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)
    except ImportError:
        # Manual .env parsing if python-dotenv not available
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()

# Map .env table names to expected backend names
env_mapping = {
    "TABLE_EMPRESAS": "DYNAMODB_TABLE_EMPRESAS",
    "TABLE_VACANTES": "DYNAMODB_TABLE_VACANTES",
    "TABLE_USUARIO_VACANTE": "DYNAMODB_TABLE_USUARIO_VACANTE",
    "TABLE_ENTRADAS": "DYNAMODB_TABLE_ENTRADAS",
    "TABLE_PERFILES": "DYNAMODB_TABLE_PERFILES",
    "TABLE_SUSCRIPCIONES": "DYNAMODB_TABLE_SUSCRIPCIONES",
    "TABLE_SCANJOBS": "DYNAMODB_TABLE_SCAN_JOBS",
    "SCAN_QUEUE_URL": "SQS_QUEUE_SCAN_URL",
    "SCAN_DLQ_URL": "SQS_QUEUE_SCAN_DLQ_URL",
    "SCORING_QUEUE_URL": "SQS_QUEUE_SCORING_URL",
    "SCORING_DLQ_URL": "SQS_QUEUE_SCORING_DLQ_URL",
    "BEDROCK_MODEL_ID_SMALL": "BEDROCK_MODEL_SMALL",
    "BEDROCK_MODEL_ID_MEDIUM": "BEDROCK_MODEL_MID",
}

# Apply mappings
for old_key, new_key in env_mapping.items():
    if old_key in os.environ and new_key not in os.environ:
        os.environ[new_key] = os.environ[old_key]

# Set default CORS origins if not set
if "CORS_ALLOWED_ORIGINS" not in os.environ:
    os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"

# Add backend to path so we can import from it
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.main import create_app


def main():
    """
    Generate and export OpenAPI specification.
    
    Raises:
        RuntimeError: If app startup fails (missing env vars, Bedrock unavailable)
        IOError: If output directory doesn't exist or file write fails
    """
    print("[*] Initializing FastAPI app...")
    
    try:
        # Create the FastAPI app (this validates env vars and Bedrock)
        app = create_app()
        print("[OK] FastAPI app initialized successfully")
    except Exception as e:
        print(f"[ERROR] Failed to initialize app: {e}", file=sys.stderr)
        sys.exit(1)
    
    print("[*] Generating OpenAPI specification...")
    
    try:
        # Generate OpenAPI spec
        openapi_spec = app.openapi()
        if not openapi_spec:
            raise RuntimeError("app.openapi() returned None")
        print(f"[OK] OpenAPI spec generated ({len(json.dumps(openapi_spec))} bytes)")
    except Exception as e:
        print(f"[ERROR] Failed to generate OpenAPI spec: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Determine output path
    output_dir = Path(__file__).parent.parent / "frontend" / "openapi"
    output_file = output_dir / "openapi.json"
    
    print(f"[*] Output directory: {output_dir}")
    
    # Ensure output directory exists
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[OK] Output directory ready")
    except Exception as e:
        print(f"[ERROR] Failed to create output directory: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Write OpenAPI spec to file
    print(f"[*] Writing OpenAPI spec to {output_file}...")
    
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(openapi_spec, f, indent=2, ensure_ascii=False)
        
        # Calculate file size
        file_size = output_file.stat().st_size
        print(f"[OK] OpenAPI spec written successfully ({file_size} bytes)")
        print(f"[*] Output file: {output_file}")
    except Exception as e:
        print(f"[ERROR] Failed to write OpenAPI spec: {e}", file=sys.stderr)
        sys.exit(1)
    
    print("\n[SUCCESS] OpenAPI export complete!")
    print(f"   Frontend can now import from: {output_file}")


if __name__ == "__main__":
    main()
