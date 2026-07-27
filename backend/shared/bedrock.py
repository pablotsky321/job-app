"""
Bedrock integration module.

ONLY module that reads BEDROCK_MODEL_* env vars and invokes Amazon Bedrock.
Never hardcodes model IDs. Always uses boto3 with strict timeouts.
Validates all LLM output against Pydantic models (never raw json.loads()).
Retries once on validation failure with error injected into prompt.

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 12.1, 12.2, 12.3, 12.4, 12.5,
              19.1, 19.2, 19.3, 19.4
"""

import os
import json
import logging
import re
from typing import Type, TypeVar, Any, Optional
from datetime import datetime

import boto3
from botocore.config import Config
from pydantic import BaseModel, ValidationError

# Import logging utilities
from backend.shared.logging_config import get_contextual_logger

# Set up logger
logger = get_contextual_logger(__name__)

# Content type constants
JSON_CONTENT_TYPE = "application/json"

T = TypeVar("T", bound=BaseModel)


class BedrockClient:
    """
    Client for invoking Amazon Bedrock models with retry and validation.

    - Reads model IDs from environment variables (never hardcoded)
    - Configures boto3 with strict timeouts: connect_timeout=10, read_timeout=20
    - Validates all responses against Pydantic models
    - Retries once on validation failure with error injected into prompt
    - Logs model ID and region on every invocation
    - Logs attempt count on retries
    """

    def __init__(self):
        """Initialize Bedrock client with environment variables and strict timeouts."""
        self.region = os.getenv("BEDROCK_REGION", "us-east-1")
        self.model_small = os.getenv("BEDROCK_MODEL_SMALL")
        self.model_mid = os.getenv("BEDROCK_MODEL_MID")

        # Validate that all required env vars are set
        if not self.model_small:
            raise RuntimeError("Environment variable BEDROCK_MODEL_SMALL is not set")
        if not self.model_mid:
            raise RuntimeError("Environment variable BEDROCK_MODEL_MID is not set")

        # Configure boto3 with strict timeouts
        config = Config(
            connect_timeout=10,
            read_timeout=20,
        )
        self.client = boto3.client("bedrock-runtime", region_name=self.region, config=config)

    def invoke_with_retry(
        self,
        prompt: str,
        response_model: Type[T],
        model_id: str,
        max_retries: int = 1,
    ) -> T:
        """
        Invoke Bedrock model with Pydantic validation and retry on failure.

        Args:
            prompt: Initial prompt to send to the model
            response_model: Pydantic model to validate response against
            model_id: Bedrock model ID (e.g., from BEDROCK_MODEL_SMALL or BEDROCK_MODEL_MID)
            max_retries: Maximum number of retries on validation failure (default 1)

        Returns:
            Parsed and validated response as response_model instance

        Raises:
            ValidationError: If response validation fails after all retries
            Exception: If Bedrock invocation fails (timeout, service error)
        """
        attempt = 0
        current_prompt = prompt

        while attempt <= max_retries:
            attempt += 1
            try:
                response = self._invoke_bedrock_once(model_id, current_prompt)
                validated = self._parse_and_validate(response, response_model, model_id, attempt)
                return validated
            except ValidationError as ve:
                if not self._handle_validation_error(ve, model_id, attempt, max_retries):
                    raise
                # Update prompt with error for retry
                current_prompt = self._prepare_retry_prompt(prompt, ve, response_model)

        # Should not reach here
        raise RuntimeError("Bedrock invocation exhausted all retries")

    def _invoke_bedrock_once(self, model_id: str, prompt: str) -> str:
        """
        Invoke Bedrock model once and return the response text.

        Args:
            model_id: Bedrock model ID
            prompt: Prompt to send

        Returns:
            Response text from the model

        Raises:
            Exception: On Bedrock API error or timeout
        """
        logger.info(
            "bedrock_invoke_start",
            context={
                "model_id": model_id,
                "region": self.region,
                "attempt": 1,
            },
        )

        response = self.client.invoke_model(
            modelId=model_id,
            body=json.dumps({"prompt": prompt, "max_tokens": 2048}),
            contentType=JSON_CONTENT_TYPE,
            accept=JSON_CONTENT_TYPE,
        )

        response_body = json.loads(response["body"].read().decode("utf-8"))
        response_text = self._extract_text_from_response(response_body)

        if not response_text:
            raise ValueError("No text found in Bedrock response")

        return response_text

    def _extract_text_from_response(self, response_body: Any) -> Optional[str]:
        """
        Extract text from Bedrock response body.

        Handles different response formats (completion, text, output, etc.).

        Args:
            response_body: Parsed JSON response body

        Returns:
            Text content or None if not found
        """
        # Try common response formats
        if isinstance(response_body, dict):
            for key in ["completion", "text", "output"]:
                if key in response_body:
                    return response_body[key]
            # Try to find first string value
            for value in response_body.values():
                if isinstance(value, str):
                    return value
        elif isinstance(response_body, str):
            return response_body

        return None

    def _parse_and_validate(
        self,
        response_text: str,
        response_model: Type[T],
        model_id: str,
        attempt: int,
    ) -> T:
        """
        Parse JSON from response text and validate against Pydantic model.

        Args:
            response_text: Raw text response from model
            response_model: Pydantic model to validate against
            model_id: Model ID (for logging)
            attempt: Attempt number (for logging)

        Returns:
            Validated model instance

        Raises:
            ValidationError: If Pydantic validation fails
            ValueError: If JSON parsing fails
        """
        # Extract JSON from response text
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            json_match = re.search(r"\[.*\]", response_text, re.DOTALL)

        json_str = json_match.group(0) if json_match else response_text

        try:
            response_data = json.loads(json_str)
        except json.JSONDecodeError as je:
            logger.error(
                "bedrock_json_decode_error",
                context={
                    "model_id": model_id,
                    "region": self.region,
                    "attempt": attempt,
                    "error": str(je),
                },
            )
            raise ValueError(f"Failed to decode JSON from Bedrock response: {je}")

        # Validate against Pydantic model
        validated = response_model.model_validate(response_data)

        logger.info(
            "bedrock_invoke_success",
            context={
                "model_id": model_id,
                "region": self.region,
                "attempt": attempt,
                "response_length": len(response_text),
            },
        )

        return validated

    def _handle_validation_error(
        self,
        error: ValidationError,
        model_id: str,
        attempt: int,
        max_retries: int,
    ) -> bool:
        """
        Handle Pydantic validation error.

        Args:
            error: The validation error
            model_id: Model ID (for logging)
            attempt: Current attempt number
            max_retries: Maximum number of retries allowed

        Returns:
            True if we should retry, False if we should give up
        """
        logger.warning(
            "bedrock_validation_failed",
            context={
                "model_id": model_id,
                "region": self.region,
                "attempt": attempt,
                "error": str(error),
            },
        )

        if attempt >= max_retries:
            logger.error(
                "bedrock_validation_failed_final",
                context={
                    "model_id": model_id,
                    "region": self.region,
                    "attempts": attempt,
                    "error": str(error),
                },
            )
            return False

        return True

    def _prepare_retry_prompt(
        self,
        original_prompt: str,
        error: ValidationError,
        response_model: Type[T],
    ) -> str:
        """
        Prepare retry prompt with error injected.

        Args:
            original_prompt: Original prompt
            error: Validation error from first attempt
            response_model: Pydantic model schema

        Returns:
            Updated prompt with error context
        """
        error_summary = str(error)
        schema_str = response_model.model_json_schema()

        retry_prompt = (
            f"Previous response failed validation. Error: {error_summary}\n"
            f"Please try again, ensuring the response is valid JSON matching this schema:\n"
            f"{json.dumps(schema_str, indent=2)}\n\n"
            f"Original request:\n{original_prompt}"
        )
        return retry_prompt


def startup_validation() -> None:
    """
    Validate Bedrock models are accessible at Lambda startup.

    Sends a trivial "Respond with ok" prompt to each configured model
    with a 2-second timeout. Raises a descriptive error if any model
    is not accessible.

    Raises:
        RuntimeError: If any model is not accessible or invocation times out
    """
    logger.info("bedrock_startup_validation_start")

    # Read model IDs from env vars
    region = os.getenv("BEDROCK_REGION", "us-east-1")
    model_small = os.getenv("BEDROCK_MODEL_SMALL")
    model_mid = os.getenv("BEDROCK_MODEL_MID")

    if not model_small:
        raise RuntimeError(
            "Bedrock startup validation failed: BEDROCK_MODEL_SMALL env var not set"
        )
    if not model_mid:
        raise RuntimeError(
            "Bedrock startup validation failed: BEDROCK_MODEL_MID env var not set"
        )

    # Create a client for validation with a 2-second timeout
    validation_config = Config(connect_timeout=2, read_timeout=2)
    validation_client = boto3.client(
        "bedrock-runtime", region_name=region, config=validation_config
    )

    models_to_test = [
        ("BEDROCK_MODEL_SMALL", model_small),
        ("BEDROCK_MODEL_MID", model_mid),
    ]

    for env_var_name, model_id in models_to_test:
        try:
            logger.info(
                "bedrock_startup_test_model",
                context={
                    "model_id": model_id,
                    "region": region,
                },
            )

            # Send trivial prompt to test model
            response = validation_client.invoke_model(
                modelId=model_id,
                body=json.dumps({"prompt": "Respond with ok", "max_tokens": 10}),
                contentType=JSON_CONTENT_TYPE,
                accept=JSON_CONTENT_TYPE,
            )

            # Just check that we got a response
            response_body = response["body"].read()
            if not response_body:
                raise RuntimeError(f"Empty response from {model_id}")

            logger.info(
                "bedrock_startup_test_model_success",
                context={
                    "model_id": model_id,
                    "region": region,
                },
            )

        except Exception as e:
            error_msg = (
                f"Bedrock startup validation failed for {env_var_name}:\n"
                f"  Model ID: {model_id}\n"
                f"  Region: {region}\n"
                f"  Error: {str(e)}\n"
                f"  Type: {type(e).__name__}"
            )
            logger.error(
                "bedrock_startup_validation_failed",
                context={
                    "model_id": model_id,
                    "region": region,
                    "env_var": env_var_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise RuntimeError(error_msg) from e

    logger.info("bedrock_startup_validation_complete")


# Global instance
_bedrock_client: Optional[BedrockClient] = None


def get_bedrock_client() -> BedrockClient:
    """
    Get or create the global Bedrock client instance.

    Lazy initialization on first use to defer cold start cost.
    """
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = BedrockClient()
    return _bedrock_client
