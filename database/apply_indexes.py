#!/usr/bin/env python3
"""
Script per aplicar índexs a la base de dades PostgreSQL
Pot executar-se des de Railway o localment
"""

import os
import psycopg2
from pathlib import Path

def apply_indexes():
    """Aplica els índexs definits a create_indexes.sql"""

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ ERROR: DATABASE_URL no trobada a les variables d'entorn")
        return False

    # Llegir el fitxer SQL
    sql_file = Path(__file__).parent / 'create_indexes.sql'

    if not sql_file.exists():
        print(f"❌ ERROR: No s'ha trobat {sql_file}")
        return False

    print(f"📄 Llegint {sql_file}...")
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    # Connectar i executar
    try:
        print("🔌 Connectant a PostgreSQL...")
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("⚡ Aplicant índexs...")
        cursor.execute(sql_content)

        conn.commit()

        # Verificar índexs creats
        cursor.execute("""
            SELECT indexname, tablename
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%'
            ORDER BY tablename, indexname
        """)

        indexes = cursor.fetchall()

        print("\n✅ Índexs aplicats correctament!")
        print(f"📊 Total d'índexs personalitzats: {len(indexes)}\n")

        print("📋 Llista d'índexs:")
        current_table = None
        for idx_name, table_name in indexes:
            if table_name != current_table:
                print(f"\n  📁 {table_name}:")
                current_table = table_name
            print(f"    ✓ {idx_name}")

        cursor.close()
        conn.close()

        print("\n🎉 Procés completat amb èxit!")
        return True

    except psycopg2.Error as e:
        print(f"❌ Error de PostgreSQL: {e}")
        return False
    except Exception as e:
        print(f"❌ Error inesperat: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 APLICANT ÍNDEXS DE RENDIMENT A POSTGRESQL")
    print("=" * 60)

    success = apply_indexes()

    exit(0 if success else 1)
