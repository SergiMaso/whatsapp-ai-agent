import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
import logging

load_dotenv()

class MediaManager:
    """
    Gestor de media (PDFs, imatges) per al restaurant
    
    Funcionalitats:
    - Pujar menús, cartes, promocions
    - Emmagatzemar a Cloudinary
    - Guardar URLs a PostgreSQL
    - Recuperar media actius
    """
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        
        # Configurar Cloudinary
        cloudinary.config(
            cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
            api_key=os.getenv('CLOUDINARY_API_KEY'),
            api_secret=os.getenv('CLOUDINARY_API_SECRET')
        )

        # Configurar logger
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        self.ensure_table_exists()
    
    def get_connection(self):
        """Crear connexió a PostgreSQL amb timezone correcte"""
        conn = psycopg2.connect(self.database_url)
        cursor = conn.cursor()
        cursor.execute("SET timezone TO 'Europe/Madrid'")
        cursor.close()
        return conn
    
    def ensure_table_exists(self):
        """Crear taula restaurant_media si no existeix"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS restaurant_media (
                            id SERIAL PRIMARY KEY,
                            type VARCHAR(50) NOT NULL,
                            title VARCHAR(200) NOT NULL,
                            description TEXT,
                            file_url TEXT NOT NULL,
                            thumbnail_url TEXT,
                            file_type VARCHAR(20) NOT NULL,
                            file_size INTEGER,
                            cloudinary_public_id VARCHAR(200),
                            active BOOLEAN DEFAULT TRUE,
                            date DATE,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_media_type ON restaurant_media(type);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_media_active ON restaurant_media(active);
                    """)
                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_media_created_at ON restaurant_media(created_at DESC);
                    """)
            
            self.logger.info("✅ Taula restaurant_media creada/verificada")
        
        except Exception as e:
            self.logger.error(f"❌ Error creant taula restaurant_media: {e}")
    
    def upload_media(self, file_path, media_type, title, description=None, date=None):
        """
        Pujar un arxiu (PDF o imatge) a Cloudinary i guardar-lo a la BD
        """
        try:
            # Validar arxiu local
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Fitxer no trobat: {file_path}")

            # Detectar tipus d'arxiu
            file_extension = file_path.split('.')[-1].lower()
            
            if file_extension == 'pdf':
                resource_type = 'raw'
                file_type = 'pdf'
            elif file_extension in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                resource_type = 'image'
                file_type = file_extension
            else:
                raise ValueError(f"Tipus d'arxiu no suportat: {file_extension}")
            
            self.logger.info(f"📤 Pujant {file_type} a Cloudinary...")

            upload_result = cloudinary.uploader.upload(
                file_path,
                folder=f"restaurant/{media_type}",
                resource_type=resource_type,
                use_filename=True,
                unique_filename=True,
                access_mode='public',
                type='upload'
            )
            


            # # Fer que el PDF sigui visualitzable (no descarregable)
            # if file_type == 'pdf':
            #     file_url = upload_result['secure_url'].replace('/upload/', '/upload/fl_attachment:false/')
            # else:
            #     file_url = upload_result['secure_url']

            file_url = upload_result["secure_url"]
            public_id = upload_result['public_id']
            file_size = upload_result.get('bytes', 0)
            
            # Generar thumbnail
            thumbnail_url = None
            if file_type == 'pdf':
                thumbnail_url, _ = cloudinary_url(
                    public_id,
                    format="jpg",
                    page=1,
                    width=300,
                    crop="scale"
                )
            else:
                thumbnail_url, _ = cloudinary_url(
                    public_id,
                    width=300,
                    height=300,
                    crop="fill"
                )
            
            # Guardar a la BD
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO restaurant_media 
                        (type, title, description, file_url, thumbnail_url, file_type, 
                         file_size, cloudinary_public_id, date, active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                        RETURNING id
                    """, (
                        media_type,
                        title,
                        description,
                        file_url,
                        thumbnail_url,
                        file_type,
                        file_size,
                        public_id,
                        date
                    ))
                    media_id = cursor.fetchone()[0]
            
            self.logger.info(f"✅ Media pujat correctament: ID {media_id}")
            
            return {
                'id': media_id,
                'url': file_url,
                'thumbnail': thumbnail_url,
                'type': file_type,
                'size': file_size
            }
        
        except Exception as e:
            self.logger.error(f"❌ Error pujant media: {e}", exc_info=True)
            return None
    
    def get_active_media(self, media_type=None, date=None):
        """Obtenir media actius"""
        try:
            query = """
                SELECT id, type, title, description, file_url, thumbnail_url, 
                       file_type, file_size, date, created_at
                FROM restaurant_media
                WHERE active = TRUE
            """
            params = []
            
            if media_type:
                query += " AND type = %s"
                params.append(media_type)
            
            if date:
                query += " AND date = %s"
                params.append(date)
            
            query += " ORDER BY created_at DESC"
            
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    results = cursor.fetchall()
            
            return [
                {
                    'id': row[0],
                    'type': row[1],
                    'title': row[2],
                    'description': row[3],
                    'file_url': row[4],
                    'thumbnail_url': row[5],
                    'file_type': row[6],
                    'file_size': row[7],
                    'date': row[8].isoformat() if row[8] else None,
                    'created_at': row[9].isoformat() if row[9] else None
                }
                for row in results
            ]
        
        except Exception as e:
            self.logger.error(f"❌ Error obtenint media: {e}", exc_info=True)
            return []
    
    def get_menu(self, menu_type=None, day_name=None):
        """Obtenir menú segons tipus i dia"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    if menu_type == 'carta':
                        self.logger.info(f"🔍 Buscant carta permanent...")
                        cursor.execute("""
                            SELECT id, title, description, file_url, file_type
                            FROM restaurant_media
                            WHERE type = 'carta' AND active = TRUE
                            ORDER BY created_at DESC
                            LIMIT 1
                        """)
                    
                    elif menu_type == 'menu_dia' and day_name:
                        day_name_lower = day_name.lower()
                        self.logger.info(f"🔍 Buscant menú del dia: {day_name}")
                        cursor.execute("""
                            SELECT id, title, description, file_url, file_type
                            FROM restaurant_media
                            WHERE type = 'menu_dia' 
                            AND active = TRUE
                            AND LOWER(title) LIKE %s
                            ORDER BY created_at DESC
                            LIMIT 1
                        """, (f'%{day_name_lower}%',))
                    
                    else:
                        self.logger.info(f"🔍 Buscant carta (per defecte)...")
                        cursor.execute("""
                            SELECT id, title, description, file_url, file_type
                            FROM restaurant_media
                            WHERE type = 'carta' AND active = TRUE
                            ORDER BY created_at DESC
                            LIMIT 1
                        """)
                    
                    result = cursor.fetchone()
            
            if result:
                self.logger.info(f"✅ Menú trobat: {result[1]}")
                return {
                    'id': result[0],
                    'title': result[1],
                    'description': result[2],
                    'url': result[3],
                    'type': result[4]
                }
            else:
                self.logger.warning(f"❌ Cap menú trobat per type={menu_type}, day={day_name}")
                return None
        
        except Exception as e:
            self.logger.error(f"❌ Error obtenint menú: {e}", exc_info=True)
            return None
    
    def deactivate_media(self, media_id):
        """Desactivar un media (no l'elimina, només l'amaga)"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE restaurant_media
                        SET active = FALSE, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (media_id,))
            self.logger.info(f"✅ Media {media_id} desactivat")
            return True
        
        except Exception as e:
            self.logger.error(f"❌ Error desactivant media: {e}", exc_info=True)
            return False
    
    def delete_media(self, media_id):
        """Eliminar completament un media (BD + Cloudinary)"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT cloudinary_public_id, file_type
                        FROM restaurant_media
                        WHERE id = %s
                    """, (media_id,))
                    result = cursor.fetchone()
                    
                    if not result:
                        self.logger.warning(f"❌ Media {media_id} no trobat")
                        return False
                    
                    public_id, file_type = result
                    resource_type = 'raw' if file_type == 'pdf' else 'image'
                    
                    cloudinary.uploader.destroy(public_id, resource_type=resource_type)
                    
                    cursor.execute("DELETE FROM restaurant_media WHERE id = %s", (media_id,))
            
            self.logger.info(f"✅ Media {media_id} eliminat correctament")
            return True
        
        except Exception as e:
            self.logger.error(f"❌ Error eliminant media: {e}", exc_info=True)
            return False
