import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import cloudinary.api

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
        
        self.ensure_table_exists()
    
    def get_connection(self):
        """Crear connexió a PostgreSQL"""
        return psycopg2.connect(self.database_url)
    
    def ensure_table_exists(self):
        """Crear taula restaurant_media si no existeix"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS restaurant_media (
                    id SERIAL PRIMARY KEY,
                    type VARCHAR(50) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    description TEXT,
                    file_url TEXT NOT NULL,
                    thumbnail_url TEXT,
                    file_type VARCHAR(10) NOT NULL,
                    file_size INTEGER,
                    cloudinary_public_id VARCHAR(200),
                    active BOOLEAN DEFAULT TRUE,
                    date DATE,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Crear índexs per millorar rendiment
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_media_type ON restaurant_media(type);
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_media_active ON restaurant_media(active);
            """)
            
            conn.commit()
            cursor.close()
            conn.close()
            print("✅ Taula restaurant_media creada/verificada")
        
        except Exception as e:
            print(f"❌ Error creant taula restaurant_media: {e}")
    
    def upload_media(self, file_path, media_type, title, description=None, date=None):
        """
        Pujar un arxiu (PDF o imatge) a Cloudinary i guardar-lo a la BD
        
        Args:
            file_path: Ruta al arxiu local
            media_type: 'menu_dia', 'carta', 'promocio', 'event'
            title: Títol del document
            description: Descripció opcional
            date: Data associada (per menús del dia)
        
        Returns:
            dict amb info del media carregat
        """
        try:
            # Detectar tipus d'arxiu
            file_extension = file_path.split('.')[-1].lower()
            
            # Determinar resource_type per Cloudinary
            if file_extension == 'pdf':
                resource_type = 'raw'
                file_type = 'pdf'
            elif file_extension in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                resource_type = 'image'
                file_type = file_extension
            else:
                raise ValueError(f"Tipus d'arxiu no suportat: {file_extension}")
            
            print(f"📤 Pujant {file_type} a Cloudinary...")
            
            # Pujar a Cloudinary amb accés públic
            upload_result = cloudinary.uploader.upload(
                file_path,
                folder=f"restaurant/{media_type}",
                resource_type=resource_type,
                use_filename=True,
                unique_filename=True,
                access_mode='public'  # ✅ Fer el PDF públic per poder-lo obrir
            )
            
                        # Per PDFs, afegir paràmetre fl_attachment per forçar visualització al navegador
            if file_type == 'pdf':
                # Transformar URL per obrir al navegador en lloc de descarregar
                file_url = upload_result['secure_url'].replace('/upload/', '/upload/fl_attachment/')
            else:
                file_url = upload_result['secure_url']
                
            public_id = upload_result['public_id']
            file_size = upload_result.get('bytes', 0)
            
            # Generar thumbnail per PDFs
            thumbnail_url = None
            if file_type == 'pdf':
                try:
                    # Cloudinary pot generar preview del PDF
                    thumbnail_url = cloudinary.CloudinaryImage(public_id).image(
                        format="jpg",
                        page=1,
                        width=300,
                        crop="scale"
                    )
                except:
                    thumbnail_url = None
            else:
                # Per imatges, crear thumbnail
                thumbnail_url = cloudinary.CloudinaryImage(public_id).image(
                    width=300,
                    height=300,
                    crop="fill"
                )
            
            # Guardar a la base de dades
            conn = self.get_connection()
            cursor = conn.cursor()
            
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
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ Media pujat correctament: ID {media_id}")
            
            return {
                'id': media_id,
                'url': file_url,
                'thumbnail': thumbnail_url,
                'type': file_type,
                'size': file_size
            }
        
        except Exception as e:
            print(f"❌ Error pujant media: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_active_media(self, media_type=None, date=None):
        """
        Obtenir media actius
        
        Args:
            media_type: Filtrar per tipus (opcional)
            date: Filtrar per data (opcional)
        
        Returns:
            Llista de diccionaris amb info dels media
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
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
            
            cursor.execute(query, params)
            
            media_list = []
            for row in cursor.fetchall():
                media_list.append({
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
                })
            
            cursor.close()
            conn.close()
            
            return media_list
        
        except Exception as e:
            print(f"❌ Error obtenint media: {e}")
            return []
    
    def get_menu(self, menu_type=None, day_name=None):
        """
        Obtenir menú segons tipus i dia (funció intel·ligent)
        
        Args:
            menu_type: 'carta' per menú permanent, 'menu_dia' per menú del dia
            day_name: Nom del dia (dilluns, martes, monday, etc.) per menu_dia
        
        Returns:
            dict amb info del menú o None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if menu_type == 'carta':
                # Buscar carta permanent
                print(f"🔍 Buscant carta permanent...")
                cursor.execute("""
                    SELECT id, title, description, file_url, file_type
                    FROM restaurant_media
                    WHERE type = 'carta' AND active = TRUE
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
            
            elif menu_type == 'menu_dia' and day_name:
                # Buscar menú del dia per nom del dia
                day_name_lower = day_name.lower()
                print(f"🔍 Buscant menú del dia: {day_name}")
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
                # Si no s'especifica res, retornar carta per defecte
                print(f"🔍 Buscant carta (per defecte)...")
                cursor.execute("""
                    SELECT id, title, description, file_url, file_type
                    FROM restaurant_media
                    WHERE type = 'carta' AND active = TRUE
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result:
                print(f"✅ Menú trobat: {result[1]}")
                return {
                    'id': result[0],
                    'title': result[1],
                    'description': result[2],
                    'url': result[3],
                    'type': result[4]
                }
            else:
                print(f"❌ Cap menú trobat per type={menu_type}, day={day_name}")
            
            return None
        
        except Exception as e:
            print(f"❌ Error obtenint menú: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def deactivate_media(self, media_id):
        """Desactivar un media (no l'elimina, només l'amaga)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE restaurant_media
                SET active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (media_id,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        
        except Exception as e:
            print(f"❌ Error desactivant media: {e}")
            return False
    
    def delete_media(self, media_id):
        """Eliminar completament un media (BD + Cloudinary)"""
        try:
            # Obtenir public_id de Cloudinary
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT cloudinary_public_id, file_type
                FROM restaurant_media
                WHERE id = %s
            """, (media_id,))
            
            result = cursor.fetchone()
            
            if not result:
                cursor.close()
                conn.close()
                return False
            
            public_id = result[0]
            file_type = result[1]
            
            # Eliminar de Cloudinary
            resource_type = 'raw' if file_type == 'pdf' else 'image'
            cloudinary.uploader.destroy(public_id, resource_type=resource_type)
            
            # Eliminar de la BD
            cursor.execute("DELETE FROM restaurant_media WHERE id = %s", (media_id,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ Media {media_id} eliminat correctament")
            return True
        
        except Exception as e:
            print(f"❌ Error eliminant media: {e}")
            import traceback
            traceback.print_exc()
            return False
