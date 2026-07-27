"""
Lambda handler entry point for AWS Lambda.

Imports the Mangum ASGI handler from backend.main.
Used by Lambda runtime as the invocation target.

Configuration in Terraform:
  handler = "lambda_handler.handler"
"""

from backend.main import handler

__all__ = ["handler"]
