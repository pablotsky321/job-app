"""
Pytest configuration and fixtures for backend tests.

Sets up environment variables and common fixtures for all tests.
"""

import os
import pytest

# Set environment variables BEFORE any imports
os.environ.setdefault("BEDROCK_REGION", "us-east-1")
os.environ.setdefault("BEDROCK_MODEL_SMALL", "anthropic.claude-3-haiku-20250514")
os.environ.setdefault("BEDROCK_MODEL_MID", "anthropic.claude-3-5-sonnet-20241022")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("DYNAMODB_TABLE_EMPRESAS", "test-empresas")
os.environ.setdefault("DYNAMODB_TABLE_VACANTES", "test-vacantes")
os.environ.setdefault("DYNAMODB_TABLE_USUARIO_VACANTE", "test-usuario-vacante")
os.environ.setdefault("DYNAMODB_TABLE_PERFILES", "test-perfiles")
os.environ.setdefault("DYNAMODB_TABLE_SUSCRIPCIONES", "test-suscripciones")
os.environ.setdefault("DYNAMODB_TABLE_SCAN_JOBS", "test-scan-jobs")
os.environ.setdefault("DYNAMODB_TABLE_ENTRADAS", "test-entradas")
os.environ.setdefault("SQS_QUEUE_SCAN_URL", "https://sqs.us-east-1.amazonaws.com/123456789/test-scan")
os.environ.setdefault("SQS_QUEUE_SCAN_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123456789/test-scan-dlq")
os.environ.setdefault("SQS_QUEUE_SCORING_URL", "https://sqs.us-east-1.amazonaws.com/123456789/test-scoring")
os.environ.setdefault("SQS_QUEUE_SCORING_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123456789/test-scoring-dlq")
