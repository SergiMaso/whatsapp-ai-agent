"""
Restaurant Configuration Manager
Gestiona la configuració del restaurant amb cache en memòria i recàrrega automàtica.
"""

import os
import psycopg2
from psycopg2 import pool
from typing import Any, Optional, Dict
import json
import logging

logger = logging.getLogger(__name__)


class RestaurantConfig:
    """Singleton per gestionar la configuració del restaurant."""

    _instance = None
    _config_cache: Dict[str, Any] = {}
    _connection_pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RestaurantConfig, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Inicialitza la connexió a la BD i carrega la configuració."""
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL no està definida a les variables d'entorn")

        # Crear connection pool si no existeix
        if RestaurantConfig._connection_pool is None:
            RestaurantConfig._connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=5,
                dsn=database_url
            )

        # Carregar configuració inicial
        self.reload()

    def _get_connection(self):
        """Obtenir una connexió del pool."""
        return RestaurantConfig._connection_pool.getconn()

    def _return_connection(self, conn):
        """Retornar una connexió al pool."""
        RestaurantConfig._connection_pool.putconn(conn)

    def reload(self) -> None:
        """Recarrega tota la configuració des de la BD."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT key, value, value_type
                FROM restaurant_config
            """)

            rows = cursor.fetchall()
            new_cache = {}

            for key, value, value_type in rows:
                # Convertir el valor al tipus correcte
                new_cache[key] = self._cast_value(value, value_type)

            RestaurantConfig._config_cache = new_cache
            logger.info(f"Configuració recarregada: {len(new_cache)} claus")

            cursor.close()
        except Exception as e:
            logger.error(f"Error recarregant configuració: {e}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def _cast_value(self, value: str, value_type: str) -> Any:
        """Converteix un valor de string al tipus correcte."""
        try:
            if value_type == 'int':
                return int(value)
            elif value_type == 'float':
                return float(value)
            elif value_type == 'bool':
                return value.lower() in ('true', '1', 'yes')
            elif value_type == 'json':
                return json.loads(value)
            else:  # string
                return value
        except Exception as e:
            logger.error(f"Error convertint valor '{value}' a tipus '{value_type}': {e}")
            return value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Obtenir un valor de configuració.

        Args:
            key: Clau de configuració
            default: Valor per defecte si la clau no existeix

        Returns:
            El valor de configuració o el valor per defecte
        """
        return RestaurantConfig._config_cache.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """Obtenir un valor enter."""
        value = self.get(key, default)
        return int(value) if value is not None else default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Obtenir un valor decimal."""
        value = self.get(key, default)
        return float(value) if value is not None else default

    def get_str(self, key: str, default: str = "") -> str:
        """Obtenir un valor string."""
        value = self.get(key, default)
        return str(value) if value is not None else default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Obtenir un valor booleà."""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() in ('true', '1', 'yes') if value is not None else default

    def get_list(self, key: str, default: list = None, separator: str = ',') -> list:
        """Obtenir una llista des d'un string separat per comes."""
        if default is None:
            default = []
        value = self.get(key)
        if value is None:
            return default
        if isinstance(value, list):
            return value
        return [item.strip() for item in str(value).split(separator) if item.strip()]

    def set(self, key: str, value: Any) -> None:
        """
        Actualitzar un valor de configuració a la BD i actualitzar el cache.

        Args:
            key: Clau de configuració
            value: Nou valor
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Convertir el valor a string per guardar-lo
            if isinstance(value, (list, dict)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            cursor.execute("""
                UPDATE restaurant_config
                SET value = %s
                WHERE key = %s
            """, (value_str, key))

            conn.commit()

            # Actualitzar cache
            self.reload()

            logger.info(f"Configuració actualitzada: {key} = {value}")

            cursor.close()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error actualitzant configuració {key}: {e}")
            raise
        finally:
            if conn:
                self._return_connection(conn)

    def get_all(self) -> Dict[str, Any]:
        """Obtenir tota la configuració."""
        return RestaurantConfig._config_cache.copy()

    def get_all_with_metadata(self) -> list:
        """Obtenir tota la configuració amb metadades."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT key, value, value_type, category, description, updated_at
                FROM restaurant_config
                ORDER BY category, key
            """)

            rows = cursor.fetchall()
            result = []

            for key, value, value_type, category, description, updated_at in rows:
                result.append({
                    'key': key,
                    'value': value,
                    'value_type': value_type,
                    'category': category,
                    'description': description,
                    'updated_at': updated_at.isoformat() if updated_at else None
                })

            cursor.close()
            return result
        except Exception as e:
            logger.error(f"Error obtenint configuració amb metadades: {e}")
            raise
        finally:
            if conn:
                self._return_connection(conn)


# Crear instància global
config = RestaurantConfig()
