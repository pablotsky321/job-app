#!/usr/bin/env python3
"""
Build and package Lambda function .zip files for deployment.

This script creates .zip archives for 5 Lambda functions, installs their dependencies
from backend/pyproject.toml, and uploads them to S3 in the paths expected by
terraform/modules/lambda/main.tf.

Usage:
    python scripts/build_lambda_packages.py [--dry-run] [--bucket BUCKET] [--key-prefix PREFIX]

Environment variables (used if CLI args not provided):
    LAMBDA_CODE_BUCKET: S3 bucket name for Lambda code (required)
    LAMBDA_CODE_KEY_PREFIX: S3 key prefix (default: "lambda-code")

The 5 Lambda functions:
    1. api: FastAPI + Mangum (backend/main.py)
    2. orquestador: Orchestrator (backend/main.py, same code as api)
    3. scan_worker: SQS consumer (backend/workers/scan_worker.py)
    4. scoring_worker: SQS consumer (backend/workers/scoring_worker.py)
    5. notificador: Email notification (backend/workers/notificador.py)

For api/orquestador: builds the .zip once (same content) and uploads to both paths.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional


def get_repo_root() -> Path:
    """Find the repository root directory."""
    current = Path(__file__).parent.parent
    if (current / "backend").exists() and (current / "terraform").exists():
        return current
    raise RuntimeError("Could not find repository root")


def get_backend_dir(repo_root: Path) -> Path:
    """Get backend directory path."""
    return repo_root / "backend"


def get_build_dir() -> Path:
    """Create and return a temporary build directory."""
    return Path(tempfile.mkdtemp(prefix="lambda_build_"))


def copy_backend_structure(build_dir: Path, backend_dir: Path) -> None:
    """Copy backend/ directory preserving package structure."""
    dest_backend = build_dir / "backend"
    if dest_backend.exists():
        shutil.rmtree(dest_backend)
    shutil.copytree(backend_dir, dest_backend, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".mypy_cache", "tests", "*.egg-info", ".hypothesis", "pytest_results.txt", "*.md", "requirements.txt"))


def install_dependencies(build_dir: Path, backend_dir: Path, dry_run: bool = False) -> None:
    if dry_run:
        print(f"[DRY-RUN] Would install dependencies from {backend_dir / 'pyproject.toml'}")
        return

    pyproject_path = backend_dir / "pyproject.toml"
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--platform", "manylinux2014_x86_64",
        "--implementation", "cp",
        "--python-version", "3.12",
        "--only-binary=:all:",
        "--target",
        str(build_dir),
        str(backend_dir),
    ]

    print(f"Installing dependencies to {build_dir}: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: Failed to install dependencies:")
        print(result.stderr)
        raise RuntimeError(f"pip install failed with code {result.returncode}")

    print("Dependencies installed successfully")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"ERROR: Failed to install dependencies:")
        print(result.stderr)
        raise RuntimeError(f"pip install failed with code {result.returncode}")
    
    print("Dependencies installed successfully")


def create_zip(build_dir: Path, function_name: str, dry_run: bool = False) -> Optional[Path]:
    """
    Create a .zip archive from the build directory.
    
    Returns the path to the created .zip file, or None if dry_run is True.
    """
    zip_path = build_dir.parent / f"{function_name}.zip"
    
    if dry_run:
        print(f"[DRY-RUN] Would create {zip_path}")
        # For dry-run, still list the contents to verify structure
        print(f"[DRY-RUN] Contents would include:")
        for item in sorted(build_dir.rglob("*")):
            if item.is_file():
                rel_path = item.relative_to(build_dir)
                print(f"  {rel_path}")
        return None
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(build_dir):
            # Skip __pycache__ and other build artifacts
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".mypy_cache", "*.egg-info")]
            
            for file in files:
                if file.endswith((".pyc", ".pyo")):
                    continue
                file_path = Path(root) / file
                arcname = file_path.relative_to(build_dir)
                zf.write(file_path, arcname)
    
    print(f"Created {zip_path} ({zip_path.stat().st_size} bytes)")
    return zip_path


def list_zip_contents(zip_path: Path) -> None:
    """List and print the contents of a zip file."""
    print(f"Contents of {zip_path.name}:")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in sorted(zf.filelist, key=lambda x: x.filename):
            print(f"  {info.filename} ({info.file_size} bytes)")


def upload_to_s3(zip_path: Path, bucket: str, key: str, dry_run: bool = False) -> None:
    """Upload a .zip file to S3."""
    if dry_run:
        print(f"[DRY-RUN] Would upload {zip_path} to s3://{bucket}/{key}")
        return
    
    try:
        import boto3
    except ImportError:
        raise RuntimeError("boto3 is required for S3 upload. Install with: pip install boto3")
    
    s3_client = boto3.client("s3")
    
    print(f"Uploading {zip_path.name} to s3://{bucket}/{key}")
    try:
        s3_client.upload_file(str(zip_path), bucket, key)
        print(f"Successfully uploaded to s3://{bucket}/{key}")
    except Exception as e:
        print(f"ERROR: Failed to upload to S3: {e}")
        raise


def build_lambda_package(
    function_name: str,
    repo_root: Path,
    bucket: str,
    key_prefix: str,
    dry_run: bool = False,
) -> Optional[Path]:
    """
    Build a single Lambda package.
    
    Returns the path to the created .zip file, or None if dry_run is True.
    """
    backend_dir = get_backend_dir(repo_root)
    build_dir = get_build_dir()
    
    try:
        print(f"\n{'='*80}")
        print(f"Building {function_name}")
        print(f"{'='*80}")
        
        # Step 1: Copy backend structure
        print(f"Copying backend structure to build directory...")
        copy_backend_structure(build_dir, backend_dir)
        
        # Step 2: Install dependencies
        print(f"Installing dependencies...")
        install_dependencies(build_dir, backend_dir, dry_run=dry_run)
        
        # Step 3: Create zip
        zip_path = create_zip(build_dir, function_name, dry_run=dry_run)
        
        if not dry_run and zip_path:
            list_zip_contents(zip_path)
            
            # Step 4: Upload to S3
            s3_key = f"{key_prefix}/{function_name}/code.zip"
            upload_to_s3(zip_path, bucket, s3_key, dry_run=dry_run)
            
            return zip_path
        elif dry_run:
            return None
        
        return zip_path
    
    finally:
        # Cleanup build directory
        if build_dir.exists():
            shutil.rmtree(build_dir)
            print(f"Cleaned up build directory {build_dir}")


def build_shared_package(
    repo_root: Path,
    bucket: str,
    key_prefix: str,
    functions: List[str],
    dry_run: bool = False,
) -> Optional[Path]:
    """
    Build a single shared .zip package (used for api and orquestador).
    
    This builds the package once and returns it for reuse.
    """
    backend_dir = get_backend_dir(repo_root)
    build_dir = get_build_dir()
    
    try:
        print(f"\n{'='*80}")
        print(f"Building shared package for: {', '.join(functions)}")
        print(f"{'='*80}")
        
        # Step 1: Copy backend structure
        print(f"Copying backend structure to build directory...")
        copy_backend_structure(build_dir, backend_dir)
        
        # Step 2: Install dependencies
        print(f"Installing dependencies...")
        install_dependencies(build_dir, backend_dir, dry_run=dry_run)
        
        # Step 3: Create zip with a temporary name
        zip_path = create_zip(build_dir, "shared", dry_run=dry_run)
        
        if not dry_run and zip_path:
            list_zip_contents(zip_path)
        
        return zip_path
    
    finally:
        # Only cleanup if we're not in dry-run (dry-run cleans immediately)
        if dry_run and build_dir.exists():
            shutil.rmtree(build_dir)
            print(f"Cleaned up build directory {build_dir}")


def upload_shared_package(
    zip_path: Optional[Path],
    bucket: str,
    key_prefix: str,
    functions: List[str],
    dry_run: bool = False,
) -> None:
    """Upload a shared package to multiple S3 paths."""
    if zip_path is None:
        return
    
    for function_name in functions:
        s3_key = f"{key_prefix}/{function_name}/code.zip"
        upload_to_s3(zip_path, bucket, s3_key, dry_run=dry_run)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build and package Lambda function .zip files for deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build all Lambdas and upload to S3
  python scripts/build_lambda_packages.py

  # Dry-run: build locally without uploading
  python scripts/build_lambda_packages.py --dry-run

  # Use custom bucket and key prefix
  python scripts/build_lambda_packages.py --bucket my-lambda-bucket --key-prefix my-prefix
        """,
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build locally without uploading to S3",
    )
    
    parser.add_argument(
        "--bucket",
        type=str,
        help="S3 bucket name (default: env LAMBDA_CODE_BUCKET)",
    )
    
    parser.add_argument(
        "--key-prefix",
        type=str,
        help="S3 key prefix (default: env LAMBDA_CODE_KEY_PREFIX or 'lambda-code')",
    )
    
    args = parser.parse_args()
    
    # Get bucket and key prefix
    bucket = args.bucket or os.environ.get("LAMBDA_CODE_BUCKET")
    key_prefix = args.key_prefix or os.environ.get("LAMBDA_CODE_KEY_PREFIX", "lambda-code")
    
    if not bucket and not args.dry_run:
        print("ERROR: LAMBDA_CODE_BUCKET not set and --bucket not provided")
        sys.exit(1)
    
    if args.dry_run:
        bucket = bucket or "dry-run-bucket"
        print(f"[DRY-RUN MODE] bucket={bucket}, key_prefix={key_prefix}")
    else:
        print(f"Configuration: bucket={bucket}, key_prefix={key_prefix}")
    
    repo_root = get_repo_root()
    
    # Define Lambda functions
    # For api and orquestador, we'll build once and upload to both paths
    shared_functions = ["api", "orquestador"]
    individual_functions = ["scan_worker", "scoring_worker", "notificador"]
    
    try:
        # Build shared package for api and orquestador
        shared_zip = build_shared_package(
            repo_root,
            bucket,
            key_prefix,
            shared_functions,
            dry_run=args.dry_run,
        )
        
        # Upload to both paths
        if not args.dry_run:
            upload_shared_package(
                shared_zip,
                bucket,
                key_prefix,
                shared_functions,
                dry_run=args.dry_run,
            )
        else:
            # For dry-run, simulate uploads
            for func_name in shared_functions:
                s3_key = f"{key_prefix}/{func_name}/code.zip"
                print(f"[DRY-RUN] Would upload to s3://{bucket}/{s3_key}")
        
        # Build individual packages
        for function_name in individual_functions:
            build_lambda_package(
                function_name,
                repo_root,
                bucket,
                key_prefix,
                dry_run=args.dry_run,
            )
        
        print(f"\n{'='*80}")
        print("Build complete!")
        print(f"{'='*80}")
        
        if args.dry_run:
            print("Dry-run mode: no files were uploaded to S3")
        else:
            print(f"All packages uploaded to s3://{bucket}/{key_prefix}/")
    
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
