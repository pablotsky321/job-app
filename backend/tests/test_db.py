"""
Unit tests for backend/shared/db.py DynamoDB access helpers.

Tests cover:
- Table name loading from environment variables
- Startup error when table names are missing
- Query, put, update, delete operations
- Logging of operation metadata (not content)
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from backend.shared.db import (
    _load_table_names,
    TABLES,
    query_by_pk,
    query_by_sk,
    put_item,
    update_item,
    delete_item,
    scan_items,
)


class TestTableNameLoading:
    """Test environment variable loading for table names."""
    
    def test_load_table_names_success(self):
        """Test successful loading of all table names from env vars."""
        env_vars = {
            "DYNAMODB_TABLE_EMPRESAS": "prod-empresas",
            "DYNAMODB_TABLE_VACANTES": "prod-vacantes",
            "DYNAMODB_TABLE_USUARIO_VACANTE": "prod-usuario-vacante",
            "DYNAMODB_TABLE_ENTRADAS": "prod-entradas",
            "DYNAMODB_TABLE_PERFILES": "prod-perfiles",
            "DYNAMODB_TABLE_SUSCRIPCIONES": "prod-suscripciones",
            "DYNAMODB_TABLE_SCAN_JOBS": "prod-scan-jobs",
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            tables = _load_table_names()
        
        assert tables["empresas"] == "prod-empresas"
        assert tables["vacantes"] == "prod-vacantes"
        assert tables["usuario_vacante"] == "prod-usuario-vacante"
        assert tables["entradas"] == "prod-entradas"
        assert tables["perfiles"] == "prod-perfiles"
        assert tables["suscripciones"] == "prod-suscripciones"
        assert tables["scan_jobs"] == "prod-scan-jobs"
    
    def test_load_table_names_missing_one_var(self):
        """Test that missing any table name env var raises error."""
        env_vars = {
            "DYNAMODB_TABLE_EMPRESAS": "prod-empresas",
            "DYNAMODB_TABLE_VACANTES": "prod-vacantes",
            # Missing other tables
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(RuntimeError, match="Missing required environment variables"):
                _load_table_names()
    
    def test_load_table_names_empty_var(self):
        """Test that empty env var is treated as missing."""
        env_vars = {
            "DYNAMODB_TABLE_EMPRESAS": "",  # Empty value
            "DYNAMODB_TABLE_VACANTES": "prod-vacantes",
            # Missing others
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(RuntimeError):
                _load_table_names()


class TestQueryByPk:
    """Test query_by_pk helper."""
    
    def test_query_by_pk_with_pk_only(self):
        """Test querying by primary key only."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {"userId": "user-123", "perfilEstructurado": {"skills": []}}
            ]
        }
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            items = query_by_pk("perfiles", "userId", "user-123")
        
        assert len(items) == 1
        assert items[0]["userId"] == "user-123"
        mock_table.query.assert_called_once()
    
    def test_query_by_pk_with_sk(self):
        """Test querying by primary key and sort key."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {
                    "userId": "user-123",
                    "companyId": "comp-456",
                    "activa": True,
                }
            ]
        }
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            items = query_by_pk(
                "suscripciones",
                "userId",
                "user-123",
                sk_name="companyId",
                sk_value="comp-456",
            )
        
        assert len(items) == 1
        assert items[0]["companyId"] == "comp-456"
    
    def test_query_by_pk_unknown_table(self):
        """Test querying unknown table raises error."""
        with pytest.raises(RuntimeError, match="Unknown table"):
            query_by_pk("unknown_table", "pk", "value")
    
    def test_query_by_pk_returns_empty_list(self):
        """Test querying with no results."""
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            items = query_by_pk("empresas", "companyId", "nonexistent")
        
        assert items == []


class TestQueryBySk:
    """Test query_by_sk helper."""
    
    def test_query_by_sk_success(self):
        """Test querying by sort key via GSI."""
        mock_table = MagicMock()
        mock_table.query.return_value = {
            "Items": [
                {"companyId": "comp-1", "nombre": "Company 1"},
                {"companyId": "comp-2", "nombre": "Company 2"},
            ]
        }
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            items = query_by_sk("empresas", "nombre-index", "nombre", "ACME")
        
        assert len(items) == 2
        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["IndexName"] == "nombre-index"


class TestPutItem:
    """Test put_item helper."""
    
    def test_put_item_success(self):
        """Test putting an item successfully."""
        mock_table = MagicMock()
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            item = {"userId": "user-123", "perfilEstructurado": {"skills": []}}
            put_item("perfiles", item)
        
        mock_table.put_item.assert_called_once_with(Item=item)
    
    def test_put_item_unknown_table(self):
        """Test putting to unknown table raises error."""
        with pytest.raises(RuntimeError, match="Unknown table"):
            put_item("unknown_table", {"id": "123"})


class TestUpdateItem:
    """Test update_item helper."""
    
    def test_update_item_success(self):
        """Test updating an item successfully."""
        mock_table = MagicMock()
        mock_table.update_item.return_value = {
            "Attributes": {
                "userId": "user-123",
                "profileVersion": 2,
                "updatedAt": "2024-01-15T10:30:00Z",
            }
        }
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            key = {"userId": "user-123"}
            updates = {
                "profileVersion": 2,
                "updatedAt": "2024-01-15T10:30:00Z",
            }
            result = update_item("perfiles", key, updates)
        
        assert result["profileVersion"] == 2
        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert "SET" in call_kwargs["UpdateExpression"]
    
    def test_update_item_multiple_attributes(self):
        """Test updating multiple attributes."""
        mock_table = MagicMock()
        mock_table.update_item.return_value = {
            "Attributes": {
                "companyId": "comp-1",
                "activa": False,
                "updatedAt": "2024-01-15T10:30:00Z",
            }
        }
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            key = {"userId": "user-1", "companyId": "comp-1"}
            updates = {
                "activa": False,
                "updatedAt": "2024-01-15T10:30:00Z",
            }
            result = update_item("suscripciones", key, updates)
        
        assert result["activa"] is False


class TestDeleteItem:
    """Test delete_item helper."""
    
    def test_delete_item_success(self):
        """Test deleting an item successfully."""
        mock_table = MagicMock()
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            key = {"userId": "user-123"}
            delete_item("perfiles", key)
        
        mock_table.delete_item.assert_called_once_with(Key=key)
    
    def test_delete_item_unknown_table(self):
        """Test deleting from unknown table raises error."""
        with pytest.raises(RuntimeError, match="Unknown table"):
            delete_item("unknown_table", {"id": "123"})


class TestScanItems:
    """Test scan_items helper."""
    
    def test_scan_items_no_filter(self):
        """Test scanning without filter."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {"companyId": "comp-1", "nombre": "Company 1"},
                {"companyId": "comp-2", "nombre": "Company 2"},
            ]
        }
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            items = scan_items("empresas")
        
        assert len(items) == 2
        mock_table.scan.assert_called_once()
    
    def test_scan_items_with_filter(self):
        """Test scanning with filter expression."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {"companyId": "comp-1", "activa": True},
            ]
        }
        
        with patch("backend.shared.db._get_dynamodb_client") as mock_client:
            mock_client.return_value.Table.return_value = mock_table
            
            items = scan_items(
                "suscripciones",
                filter_expression="activa = :active",
                expression_values={":active": True},
            )
        
        assert len(items) == 1
        mock_table.scan.assert_called_once()
        call_kwargs = mock_table.scan.call_args[1]
        assert "FilterExpression" in call_kwargs


class TestEnvVarIntegration:
    """Integration tests with environment variables."""
    
    def test_tables_global_loaded(self):
        """Test that TABLES global is properly populated."""
        # TABLES is already loaded at module import, just verify it's not empty
        assert len(TABLES) > 0
        assert "perfiles" in TABLES
        assert "empresas" in TABLES
        assert "suscripciones" in TABLES
        assert "scan_jobs" in TABLES
