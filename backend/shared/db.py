"""
DynamoDB access helpers for job-app backend.

SINGLE SOURCE OF TRUTH for all DynamoDB interactions.
Reads all table names from environment variables at import time.
Raises clear startup error if any table is missing.

All helpers log operation type, table name, key, and row count affected (never content).

Requirements: 16.1, 16.2, 16.3, 16.4
"""

import os
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

from backend.shared.logging_config import get_contextual_logger

logger = get_contextual_logger(__name__)

# ============================================================================
# TABLE NAME ENVIRONMENT VARIABLES - READ AT IMPORT TIME
# ============================================================================

def _load_table_names() -> Dict[str, str]:
    """
    Load all table names from environment variables at module import.
    
    Raises:
        RuntimeError: If any required table name env var is missing
        
    Returns:
        Dict mapping table logical names to DynamoDB table names
    """
    required_tables = {
        "empresas": "DYNAMODB_TABLE_EMPRESAS",
        "vacantes": "DYNAMODB_TABLE_VACANTES",
        "usuario_vacante": "DYNAMODB_TABLE_USUARIO_VACANTE",
        "entradas": "DYNAMODB_TABLE_ENTRADAS",
        "perfiles": "DYNAMODB_TABLE_PERFILES",
        "suscripciones": "DYNAMODB_TABLE_SUSCRIPCIONES",
        "scan_jobs": "DYNAMODB_TABLE_SCAN_JOBS",
    }
    
    tables = {}
    missing_vars = []
    
    for logical_name, env_var in required_tables.items():
        table_name = os.getenv(env_var)
        if not table_name:
            missing_vars.append(env_var)
        else:
            tables[logical_name] = table_name
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error("startup_error", context={
            "error": "missing_table_env_vars",
            "missing_vars": missing_vars,
        })
        raise RuntimeError(error_msg)
    
    logger.info("dynamodb_tables_loaded", context={
        "loaded_tables": len(tables),
        "table_names": list(tables.values()),
    })
    
    return tables


# Load table names at module import time
TABLES = _load_table_names()


# ============================================================================
# DYNAMODB CLIENT (lazy-initialized to defer boto3 import)
# ============================================================================

_dynamodb_client = None


def _get_dynamodb_client():
    """
    Get or initialize DynamoDB client (lazy initialization).
    
    Returns:
        boto3 DynamoDB resource
    """
    global _dynamodb_client
    if _dynamodb_client is None:
        _dynamodb_client = boto3.resource("dynamodb")
    return _dynamodb_client


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def query_by_pk(
    table_logical_name: str,
    pk_name: str,
    pk_value: str,
    sk_name: Optional[str] = None,
    sk_value: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Query table by primary key (and optional sort key).
    
    Args:
        table_logical_name: Logical table name (e.g., 'perfiles', 'suscripciones')
        pk_name: Primary key attribute name (e.g., 'userId', 'companyId')
        pk_value: Primary key value to query for
        sk_name: Optional sort key attribute name
        sk_value: Optional sort key value (exact match)
        limit: Maximum items to return (default 100)
    
    Returns:
        List of items matching the query
        
    Raises:
        RuntimeError: If table not found or query fails
    """
    if table_logical_name not in TABLES:
        raise RuntimeError(f"Unknown table: {table_logical_name}")
    
    table_name = TABLES[table_logical_name]
    client = _get_dynamodb_client()
    table = client.Table(table_name)
    
    try:
        # Build key expression
        key_expression = f"{pk_name} = :pk_value"
        expression_values = {":pk_value": pk_value}
        
        if sk_name and sk_value:
            key_expression += f" AND {sk_name} = :sk_value"
            expression_values[":sk_value"] = sk_value
        
        # Execute query
        response = table.query(
            KeyConditionExpression=key_expression,
            ExpressionAttributeValues=expression_values,
            Limit=limit,
        )
        
        items = response.get("Items", [])
        logger.info("query_by_pk_success", context={
            "table": table_name,
            "pk_name": pk_name,
            "sk_name": sk_name,
            "row_count": len(items),
        })
        
        return items
    
    except ClientError as e:
        logger.error("query_by_pk_failed", context={
            "table": table_name,
            "pk_name": pk_name,
            "error": str(e),
        })
        raise


def query_by_sk(
    table_logical_name: str,
    index_name: str,
    sk_name: str,
    sk_value: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Query table using a GSI (Global Secondary Index) by sort key.
    
    Args:
        table_logical_name: Logical table name
        index_name: GSI or LSI name to query
        sk_name: Sort key attribute name in the index
        sk_value: Sort key value to query for
        limit: Maximum items to return
        
    Returns:
        List of items matching the query
        
    Raises:
        RuntimeError: If table not found or query fails
    """
    if table_logical_name not in TABLES:
        raise RuntimeError(f"Unknown table: {table_logical_name}")
    
    table_name = TABLES[table_logical_name]
    client = _get_dynamodb_client()
    table = client.Table(table_name)
    
    try:
        response = table.query(
            IndexName=index_name,
            KeyConditionExpression=f"{sk_name} = :sk_value",
            ExpressionAttributeValues={":sk_value": sk_value},
            Limit=limit,
        )
        
        items = response.get("Items", [])
        logger.info("query_by_sk_success", context={
            "table": table_name,
            "index": index_name,
            "sk_name": sk_name,
            "row_count": len(items),
        })
        
        return items
    
    except ClientError as e:
        logger.error("query_by_sk_failed", context={
            "table": table_name,
            "index": index_name,
            "error": str(e),
        })
        raise


def put_item(
    table_logical_name: str,
    item: Dict[str, Any],
) -> None:
    """
    Put an item into a DynamoDB table (create or replace).
    
    Args:
        table_logical_name: Logical table name
        item: Item to put (must include all key attributes)
        
    Raises:
        RuntimeError: If table not found or put operation fails
    """
    if table_logical_name not in TABLES:
        raise RuntimeError(f"Unknown table: {table_logical_name}")
    
    table_name = TABLES[table_logical_name]
    client = _get_dynamodb_client()
    table = client.Table(table_name)
    
    try:
        table.put_item(Item=item)
        
        logger.info("put_item_success", context={
            "table": table_name,
            "row_count": 1,
        })
    
    except ClientError as e:
        logger.error("put_item_failed", context={
            "table": table_name,
            "error": str(e),
        })
        raise


def update_item(
    table_logical_name: str,
    key: Dict[str, Any],
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Update an item in a DynamoDB table.
    
    Args:
        table_logical_name: Logical table name
        key: Key attributes identifying the item (e.g., {"userId": "user-123"})
        updates: Attributes to update (e.g., {"cargosActivos": ["Role1", "Role2"]})
        
    Returns:
        Updated item attributes
        
    Raises:
        RuntimeError: If table not found or update operation fails
    """
    if table_logical_name not in TABLES:
        raise RuntimeError(f"Unknown table: {table_logical_name}")
    
    table_name = TABLES[table_logical_name]
    client = _get_dynamodb_client()
    table = client.Table(table_name)
    
    try:
        # Build update expression
        update_parts = []
        expression_values = {}
        
        for i, (attr_name, attr_value) in enumerate(updates.items()):
            placeholder = f":val_{i}"
            update_parts.append(f"{attr_name} = {placeholder}")
            expression_values[placeholder] = attr_value
        
        update_expression = "SET " + ", ".join(update_parts)
        
        # Execute update
        response = table.update_item(
            Key=key,
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ReturnValues="ALL_NEW",
        )
        
        updated_item = response.get("Attributes", {})
        logger.info("update_item_success", context={
            "table": table_name,
            "row_count": 1,
            "updated_attributes": len(updates),
        })
        
        return updated_item
    
    except ClientError as e:
        logger.error("update_item_failed", context={
            "table": table_name,
            "error": str(e),
        })
        raise


def delete_item(
    table_logical_name: str,
    key: Dict[str, Any],
) -> None:
    """
    Delete an item from a DynamoDB table.
    
    Args:
        table_logical_name: Logical table name
        key: Key attributes identifying the item to delete
        
    Raises:
        RuntimeError: If table not found or delete operation fails
    """
    if table_logical_name not in TABLES:
        raise RuntimeError(f"Unknown table: {table_logical_name}")
    
    table_name = TABLES[table_logical_name]
    client = _get_dynamodb_client()
    table = client.Table(table_name)
    
    try:
        table.delete_item(Key=key)
        
        logger.info("delete_item_success", context={
            "table": table_name,
            "row_count": 1,
        })
    
    except ClientError as e:
        logger.error("delete_item_failed", context={
            "table": table_name,
            "error": str(e),
        })
        raise


# ============================================================================
# SCAN OPERATIONS (utility for special cases)
# ============================================================================

def scan_items(
    table_logical_name: str,
    filter_expression: Optional[str] = None,
    expression_values: Optional[Dict[str, Any]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Scan a table with optional filter (use sparingly, can be expensive).
    
    Args:
        table_logical_name: Logical table name
        filter_expression: Optional FilterExpression for scan
        expression_values: Values for filter expression
        limit: Maximum items to return
        
    Returns:
        List of items matching the filter (or all items if no filter)
        
    Raises:
        RuntimeError: If table not found or scan fails
    """
    if table_logical_name not in TABLES:
        raise RuntimeError(f"Unknown table: {table_logical_name}")
    
    table_name = TABLES[table_logical_name]
    client = _get_dynamodb_client()
    table = client.Table(table_name)
    
    try:
        scan_kwargs = {"Limit": limit}
        if filter_expression:
            scan_kwargs["FilterExpression"] = filter_expression
        if expression_values:
            scan_kwargs["ExpressionAttributeValues"] = expression_values
        
        response = table.scan(**scan_kwargs)
        items = response.get("Items", [])
        
        logger.info("scan_items_success", context={
            "table": table_name,
            "row_count": len(items),
        })
        
        return items
    
    except ClientError as e:
        logger.error("scan_items_failed", context={
            "table": table_name,
            "error": str(e),
        })
        raise
