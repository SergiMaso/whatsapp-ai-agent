"""
Sistema d'autenticació per a la gestió del restaurant

Rols:
- owner: Control total (tu)
- admin: Gestionar reserves, clients, taules (propietari del restaurant)
- staff: Només lectura (veure reserves i clients)

Flux:
1. Setup inicial: Crear primer Owner amb SETUP_KEY
2. Owner envia invitacions amb token únic
3. Nou usuari es registra amb el token
4. Login amb email + password
"""

from flask import Blueprint, request, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import secrets
import os
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv()

# Blueprint per les rutes d'autenticació
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Inicialitzar Flask-Login
login_manager = LoginManager()

class User(UserMixin):
    """Model d'usuari per Flask-Login"""
    
    def __init__(self, user_id, email, full_name, role, is_active=True):
        self.id = user_id
        self.email = email
        self.full_name = full_name
        self.role = role
        self._is_active = is_active  # ← Guardem en variable privada
    
    @property
    def is_active(self):
        """Getter per is_active"""
        return self._is_active
    
    @is_active.setter
    def is_active(self, value):
        """Setter per is_active"""
        self._is_active = value
    
    def __repr__(self):
        return f'<User {self.email} ({self.role})>'

class AuthManager:
    """Gestió d'autenticació i usuaris"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.ensure_auth_tables_exist()
    
    def get_connection(self):
        """Connexió a PostgreSQL"""
        return psycopg2.connect(self.database_url)
    
    def ensure_auth_tables_exist(self):
        """Crear taules d'autenticació si no existeixen"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Taula d'usuaris
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'admin', 'staff')),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            
            # Taula d'invitacions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invitations (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    token VARCHAR(255) UNIQUE NOT NULL,
                    role VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'admin', 'staff')),
                    invited_by INTEGER REFERENCES users(id),
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Taula de tokens de recuperació de password
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    token VARCHAR(255) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print("✅ Taules d'autenticació creades/verificades")
        
        except Exception as e:
            print(f"❌ Error creant taules d'autenticació: {e}")
            raise
    
    def get_user_by_id(self, user_id):
        """Obtenir usuari per ID (per Flask-Login)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, email, full_name, role, is_active
                FROM users
                WHERE id = %s
            """, (user_id,))
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                return User(row[0], row[1], row[2], row[3], row[4])
            return None
        
        except Exception as e:
            print(f"❌ Error obtenint usuari: {e}")
            return None
    
    def get_user_by_email(self, email):
        """Obtenir usuari per email"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, email, password_hash, full_name, role, is_active
                FROM users
                WHERE email = %s
            """, (email,))
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                user_dict = {
                    'id': row[0],
                    'email': row[1],
                    'password_hash': row[2],
                    'full_name': row[3],
                    'role': row[4],
                    'is_active': row[5]
                }
                return user_dict
            return None
        
        except Exception as e:
            print(f"❌ Error obtenint usuari per email: {e}")
            return None
    
    def count_users(self):
        """Comptar usuaris a la BD"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM users")
            count = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            return count
        
        except Exception as e:
            print(f"❌ Error comptant usuaris: {e}")
            return 0
    
    def create_user(self, email, password, full_name, role='admin'):
        """Crear nou usuari"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Verificar que no existeix
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return None
            
            # Hash de la contrasenya
            password_hash = generate_password_hash(password)
            
            # Inserir usuari
            cursor.execute("""
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (email, password_hash, full_name, role))
            
            user_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ Usuari creat: {email} ({role})")
            return user_id
        
        except Exception as e:
            print(f"❌ Error creant usuari: {e}")
            return None
    
    def create_invitation(self, email, role, invited_by_id):
        """Crear invitació amb token únic"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Generar token únic
            token = secrets.token_urlsafe(32)
            
            # Expiració en 7 dies
            expires_at = datetime.now() + timedelta(days=7)
            
            # Inserir invitació
            cursor.execute("""
                INSERT INTO invitations (email, token, role, invited_by, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, token
            """, (email, token, role, invited_by_id, expires_at))
            
            invitation_id, token = cursor.fetchone()
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ Invitació creada per {email} ({role})")
            return {
                'id': invitation_id,
                'token': token,
                'email': email,
                'role': role,
                'expires_at': expires_at.isoformat()
            }
        
        except Exception as e:
            print(f"❌ Error creant invitació: {e}")
            return None
    
    def get_invitation_by_token(self, token):
        """Obtenir invitació per token"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, email, role, expires_at, used
                FROM invitations
                WHERE token = %s
            """, (token,))
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                return {
                    'id': row[0],
                    'email': row[1],
                    'role': row[2],
                    'expires_at': row[3],
                    'used': row[4]
                }
            return None
        
        except Exception as e:
            print(f"❌ Error obtenint invitació: {e}")
            return None
    
    def mark_invitation_used(self, token):
        """Marcar invitació com utilitzada"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE invitations
                SET used = TRUE, used_at = CURRENT_TIMESTAMP
                WHERE token = %s
            """, (token,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        
        except Exception as e:
            print(f"❌ Error marcant invitació com usada: {e}")
            return False
    
    def update_last_login(self, user_id):
        """Actualitzar última connexió"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (user_id,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        
        except Exception as e:
            print(f"❌ Error actualitzant last_login: {e}")
            return False
    
    def create_password_reset_token(self, email):
        """Crear token de recuperació de password"""
        try:
            # Obtenir user_id per email
            user = self.get_user_by_email(email)
            if not user:
                return None
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Generar token únic
            token = secrets.token_urlsafe(32)
            
            # Expiració en 1 hora
            expires_at = datetime.now() + timedelta(hours=1)
            
            # Inserir token
            cursor.execute("""
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES (%s, %s, %s)
                RETURNING id, token
            """, (user['id'], token, expires_at))
            
            reset_id, token = cursor.fetchone()
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ Token de recuperació creat per {email}")
            return {
                'id': reset_id,
                'token': token,
                'expires_at': expires_at.isoformat()
            }
        
        except Exception as e:
            print(f"❌ Error creant token de recuperació: {e}")
            return None
    
    def get_password_reset_token(self, token):
        """Obtenir token de recuperació"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT prt.id, prt.user_id, prt.expires_at, prt.used, u.email
                FROM password_reset_tokens prt
                JOIN users u ON prt.user_id = u.id
                WHERE prt.token = %s
            """, (token,))
            
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'expires_at': row[2],
                    'used': row[3],
                    'email': row[4]
                }
            return None
        
        except Exception as e:
            print(f"❌ Error obtenint token de recuperació: {e}")
            return None
    
    def reset_password(self, token, new_password):
        """Resetear password amb token"""
        try:
            # Validar token
            reset_data = self.get_password_reset_token(token)
            
            if not reset_data:
                return False
            
            # Verificar expiració
            if reset_data['expires_at'] < datetime.now():
                return False
            
            # Verificar que no s'ha usat
            if reset_data['used']:
                return False
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Actualitzar password
            password_hash = generate_password_hash(new_password)
            cursor.execute("""
                UPDATE users
                SET password_hash = %s
                WHERE id = %s
            """, (password_hash, reset_data['user_id']))
            
            # Marcar token com usat
            cursor.execute("""
                UPDATE password_reset_tokens
                SET used = TRUE
                WHERE token = %s
            """, (token,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ Password resetejat per {reset_data['email']}")
            return True
        
        except Exception as e:
            print(f"❌ Error resetejant password: {e}")
            return False
    
    def change_password(self, user_id, old_password, new_password):
        """Canviar password (requereix l'antiga)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Obtenir password actual
            cursor.execute("""
                SELECT password_hash, email
                FROM users
                WHERE id = %s
            """, (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                cursor.close()
                conn.close()
                return False
            
            current_hash, email = row
            
            # Verificar password antiga
            if not check_password_hash(current_hash, old_password):
                cursor.close()
                conn.close()
                return False
            
            # Actualitzar amb nova password
            new_hash = generate_password_hash(new_password)
            cursor.execute("""
                UPDATE users
                SET password_hash = %s
                WHERE id = %s
            """, (new_hash, user_id))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            print(f"✅ Password canviat per {email}")
            return True
        
        except Exception as e:
            print(f"❌ Error canviant password: {e}")
            return False

# Instància global
auth_manager = AuthManager()

# User loader per Flask-Login
@login_manager.user_loader
def load_user(user_id):
    """Carregar usuari per Flask-Login"""
    return auth_manager.get_user_by_id(int(user_id))

# Funció per enviar emails
def send_email(to_email, subject, html_content):
    """
    Enviar email amb SendGrid
    
    Retorna True si s'ha enviat correctament, False si hi ha error
    """
    try:
        sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
        from_email = os.getenv('FROM_EMAIL', 'noreply@amaru.com')
        
        if not sendgrid_api_key:
            print("⚠️ SENDGRID_API_KEY no configurat. Email NO enviat.")
            print(f"📧 Email que s'hauria d'enviar a {to_email}:")
            print(f"   Subject: {subject}")
            print(f"   Content: {html_content}")
            return False
        
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        
        print(f"✅ Email enviat a {to_email} (Status: {response.status_code})")
        return True
    
    except Exception as e:
        print(f"❌ Error enviant email a {to_email}: {e}")
        return False

# Decorador per requerir rol owner
def owner_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'owner':
            return jsonify({'error': 'Accés denegat. Només Owner.'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Decorador per requerir owner o admin
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['owner', 'admin']:
            return jsonify({'error': 'Accés denegat. Només Owner o Admin.'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Decorador per a operacions de lectura (staff, admin, owner)
def read_access(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        # Tots els rols poden llegir
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# ENDPOINTS D'AUTENTICACIÓ
# ==========================================

@auth_bp.route('/setup', methods=['POST'])
def setup_first_user():
    """
    🔐 Setup inicial: Crear primer Owner
    
    Només funciona si:
    - No hi ha cap usuari a la BD
    - Es proporciona el SETUP_KEY correcte del .env
    
    Body:
    {
        "email": "owner@amaru.com",
        "password": "password123",
        "full_name": "Tu Nom",
        "setup_key": "clau-del-env"
    }
    """
    try:
        data = request.json
        
        # Validar camps
        required = ['email', 'password', 'full_name', 'setup_key']
        for field in required:
            if field not in data:
                return jsonify({'error': f'Camp obligatori: {field}'}), 400
        
        # Verificar SETUP_KEY
        setup_key = os.getenv('SETUP_KEY')
        if not setup_key or data['setup_key'] != setup_key:
            return jsonify({'error': 'SETUP_KEY incorrecte'}), 403
        
        # Verificar que no hi ha usuaris
        if auth_manager.count_users() > 0:
            return jsonify({'error': 'Ja existeixen usuaris. Setup només funciona amb BD buida.'}), 409
        
        # Crear Owner
        user_id = auth_manager.create_user(
            email=data['email'],
            password=data['password'],
            full_name=data['full_name'],
            role='owner'
        )
        
        if user_id:
            return jsonify({
                'message': 'Owner creat correctament! Ja pots fer login.',
                'user_id': user_id
            }), 201
        else:
            return jsonify({'error': 'Error creant Owner'}), 500
    
    except Exception as e:
        print(f"❌ Error en setup: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/invite', methods=['POST'])
@owner_required
def send_invitation():
    """
    📧 Enviar invitació (només Owner)
    
    Body:
    {
        "email": "admin@restaurant.com",
        "role": "admin"
    }
    
    Envia un email amb el link de registre
    """
    try:
        data = request.json
        
        # Validar camps
        if 'email' not in data or 'role' not in data:
            return jsonify({'error': 'Email i role són obligatoris'}), 400
        
        # Validar role
        if data['role'] not in ['admin', 'staff']:
            return jsonify({'error': 'Role invàlid. Usa: admin o staff'}), 400
        
        # Verificar que l'email no està ja registrat
        if auth_manager.get_user_by_email(data['email']):
            return jsonify({'error': 'Aquest email ja està registrat'}), 409
        
        # Crear invitació
        invitation = auth_manager.create_invitation(
            email=data['email'],
            role=data['role'],
            invited_by_id=current_user.id
        )
        
        if not invitation:
            return jsonify({'error': 'Error creant invitació'}), 500
        
        # Generar link de registre
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        register_link = f"{base_url}/register?token={invitation['token']}"
        
        # Preparar email
        role_names = {
            'admin': 'Administrador',
            'staff': 'Personal (només lectura)'
        }
        
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #2c3e50;">Invitació al Sistema de Gestió</h2>
                <p>Hola,</p>
                <p><strong>{current_user.full_name}</strong> t'ha convidat a unir-te al sistema de gestió del restaurant com a <strong>{role_names.get(data['role'], data['role'])}</strong>.</p>
                <p>Per completar el registre, fes clic al següent enllaç:</p>
                <p style="margin: 20px 0;">
                    <a href="{register_link}" 
                       style="background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
                        Completar Registre
                    </a>
                </p>
                <p style="color: #7f8c8d; font-size: 14px;">
                    Aquest enllaç expirarà en 7 dies.<br>
                    Si no has sol·licitat aquesta invitació, pots ignorar aquest email.
                </p>
                <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 30px 0;">
                <p style="color: #95a5a6; font-size: 12px;">
                    Sistema de Gestió de Reserves<br>
                    Aquest és un email automàtic, si us plau no responguis.
                </p>
            </body>
        </html>
        """
        
        # Enviar email
        email_sent = send_email(
            to_email=data['email'],
            subject='Invitació al Sistema de Gestió',
            html_content=html_content
        )
        
        response_data = {
            'message': 'Invitació creada correctament',
            'email_sent': email_sent,
            'expires_at': invitation['expires_at']
        }
        
        # Si l'email no s'ha pogut enviar, retornar el link (només per development)
        if not email_sent:
            response_data['register_link'] = register_link
            response_data['warning'] = 'Email no enviat. Usa el link manual.'
        
        return jsonify(response_data), 201
    
    except Exception as e:
        print(f"❌ Error enviant invitació: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    📝 Registrar nou usuari amb token d'invitació
    
    Body:
    {
        "token": "abc123...",
        "password": "password123",
        "full_name": "Nom Complet"
    }
    """
    try:
        data = request.json
        
        # Validar camps
        required = ['token', 'password', 'full_name']
        for field in required:
            if field not in data:
                return jsonify({'error': f'Camp obligatori: {field}'}), 400
        
        # Validar token
        invitation = auth_manager.get_invitation_by_token(data['token'])
        
        if not invitation:
            return jsonify({'error': 'Token invàlid'}), 404
        
        # Verificar expiració
        if invitation['expires_at'] < datetime.now():
            return jsonify({'error': 'Token expirat'}), 410
        
        # Verificar que no s'ha usat
        if invitation['used']:
            return jsonify({'error': 'Token ja utilitzat'}), 410
        
        # Crear usuari
        user_id = auth_manager.create_user(
            email=invitation['email'],
            password=data['password'],
            full_name=data['full_name'],
            role=invitation['role']
        )
        
        if user_id:
            # Marcar invitació com usada
            auth_manager.mark_invitation_used(data['token'])
            
            return jsonify({
                'message': 'Usuari registrat correctament! Ja pots fer login.',
                'user_id': user_id
            }), 201
        else:
            return jsonify({'error': 'Error creant usuari'}), 500
    
    except Exception as e:
        print(f"❌ Error en registre: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    🔐 Login amb email + password
    
    Body:
    {
        "email": "admin@restaurant.com",
        "password": "password123"
    }
    """
    try:
        data = request.json
        
        # Validar camps
        if 'email' not in data or 'password' not in data:
            return jsonify({'error': 'Email i password són obligatoris'}), 400
        
        # Obtenir usuari
        user_data = auth_manager.get_user_by_email(data['email'])
        
        if not user_data:
            return jsonify({'error': 'Email o password incorrectes'}), 401
        
        # Verificar password
        if not check_password_hash(user_data['password_hash'], data['password']):
            return jsonify({'error': 'Email o password incorrectes'}), 401
        
        # Verificar que està actiu
        if not user_data['is_active']:
            return jsonify({'error': 'Usuari desactivat'}), 403
        
        # Crear objecte User per Flask-Login
        user = User(
            user_data['id'],
            user_data['email'],
            user_data['full_name'],
            user_data['role'],
            user_data['is_active']
        )
        
        # Login
        login_user(user, remember=True)
        
        # Actualitzar last_login
        auth_manager.update_last_login(user_data['id'])
        
        print(f"✅ Login exitós: {user_data['email']}")
        
        return jsonify({
            'message': 'Login correcte',
            'user': {
                'id': user_data['id'],
                'email': user_data['email'],
                'full_name': user_data['full_name'],
                'role': user_data['role']
            }
        }), 200
    
    except Exception as e:
        print(f"❌ Error en login: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """🚪 Logout"""
    logout_user()
    return jsonify({'message': 'Logout correcte'}), 200


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """👤 Obtenir usuari actual"""
    return jsonify({
        'id': current_user.id,
        'email': current_user.email,
        'full_name': current_user.full_name,
        'role': current_user.role
    }), 200


@auth_bp.route('/users', methods=['GET'])
@owner_required
def list_users():
    """📋 Llistar tots els usuaris (només Owner)"""
    try:
        conn = auth_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, email, full_name, role, is_active, created_at, last_login
            FROM users
            ORDER BY created_at DESC
        """)
        
        users = []
        for row in cursor.fetchall():
            users.append({
                'id': row[0],
                'email': row[1],
                'full_name': row[2],
                'role': row[3],
                'is_active': row[4],
                'created_at': row[5].isoformat() if row[5] else None,
                'last_login': row[6].isoformat() if row[6] else None
            })
        
        cursor.close()
        conn.close()
        
        return jsonify(users), 200
    
    except Exception as e:
        print(f"❌ Error llistant usuaris: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/users/<int:user_id>/deactivate', methods=['PUT'])
@owner_required
def deactivate_user(user_id):
    """🚫 Desactivar usuari (només Owner)"""
    try:
        # No pots desactivar-te a tu mateix
        if user_id == current_user.id:
            return jsonify({'error': 'No pots desactivar-te a tu mateix'}), 400
        
        conn = auth_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE users
            SET is_active = FALSE
            WHERE id = %s
            RETURNING email
        """, (user_id,))
        
        result = cursor.fetchone()
        
        if not result:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Usuari no trobat'}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"✅ Usuari desactivat: {result[0]}")
        
        return jsonify({'message': 'Usuari desactivat correctament'}), 200
    
    except Exception as e:
        print(f"❌ Error desactivant usuari: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """
    🔑 Canviar password (requereix l'antiga)
    
    Body:
    {
        "old_password": "antiga123",
        "new_password": "nova456"
    }
    """
    try:
        data = request.json
        
        # Validar camps
        if 'old_password' not in data or 'new_password' not in data:
            return jsonify({'error': 'old_password i new_password són obligatoris'}), 400
        
        # Validar longitud nova password
        if len(data['new_password']) < 6:
            return jsonify({'error': 'La nova password ha de tenir mínim 6 caràcters'}), 400
        
        # Canviar password
        success = auth_manager.change_password(
            user_id=current_user.id,
            old_password=data['old_password'],
            new_password=data['new_password']
        )
        
        if success:
            return jsonify({'message': 'Password canviat correctament'}), 200
        else:
            return jsonify({'error': 'Password antiga incorrecte'}), 401
    
    except Exception as e:
        print(f"❌ Error canviant password: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """
    📧 Sol·licitar recuperació de password
    
    Body:
    {
        "email": "admin@restaurant.com"
    }
    
    Envia un email amb el link de recuperació
    """
    try:
        data = request.json
        
        if 'email' not in data:
            return jsonify({'error': 'Email és obligatori'}), 400
        
        # Crear token de recuperació
        reset_data = auth_manager.create_password_reset_token(data['email'])
        
        if not reset_data:
            # Per seguretat, sempre retornem OK encara que l'email no existeixi
            # Això evita que es pugui descobrir si un email està registrat
            return jsonify({
                'message': 'Si l\'email existeix, rebràs instruccions per recuperar la password'
            }), 200
        
        # Generar link de reset
        base_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        reset_link = f"{base_url}/reset-password?token={reset_data['token']}"
        
        # Preparar email
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <h2 style="color: #2c3e50;">Recuperació de Password</h2>
                <p>Hola,</p>
                <p>Has sol·licitat recuperar la teva password del sistema de gestió.</p>
                <p>Per crear una nova password, fes clic al següent enllaç:</p>
                <p style="margin: 20px 0;">
                    <a href="{reset_link}" 
                       style="background-color: #e74c3c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block;">
                        Recuperar Password
                    </a>
                </p>
                <p style="color: #7f8c8d; font-size: 14px;">
                    Aquest enllaç expirarà en <strong>1 hora</strong>.<br>
                    Si no has sol·licitat aquesta recuperació, pots ignorar aquest email.
                </p>
                <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 30px 0;">
                <p style="color: #95a5a6; font-size: 12px;">
                    Sistema de Gestió de Reserves<br>
                    Aquest és un email automàtic, si us plau no responguis.
                </p>
            </body>
        </html>
        """
        
        # Enviar email
        email_sent = send_email(
            to_email=data['email'],
            subject='Recuperació de Password',
            html_content=html_content
        )
        
        if email_sent:
            return jsonify({
                'message': 'Si l\'email existeix, rebràs instruccions per recuperar la password'
            }), 200
        else:
            # Si l'email no s'ha pogut enviar (per development), retornar el link
            return jsonify({
                'message': 'Si l\'email existeix, rebràs instruccions per recuperar la password',
                'reset_link': reset_link,  # Només per development
                'warning': 'Email no enviat. Usa el link manual.',
                'expires_at': reset_data['expires_at']
            }), 200
    
    except Exception as e:
        print(f"❌ Error en forgot-password: {e}")
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """
    🔐 Resetear password amb token
    
    Body:
    {
        "token": "abc123...",
        "new_password": "nova456"
    }
    """
    try:
        data = request.json
        
        # Validar camps
        if 'token' not in data or 'new_password' not in data:
            return jsonify({'error': 'token i new_password són obligatoris'}), 400
        
        # Validar longitud password
        if len(data['new_password']) < 6:
            return jsonify({'error': 'La password ha de tenir mínim 6 caràcters'}), 400
        
        # Resetear password
        success = auth_manager.reset_password(
            token=data['token'],
            new_password=data['new_password']
        )
        
        if success:
            return jsonify({'message': 'Password resetejat correctament. Ja pots fer login.'}), 200
        else:
            return jsonify({'error': 'Token invàlid o expirat'}), 400
    
    except Exception as e:
        print(f"❌ Error resetejant password: {e}")
        return jsonify({'error': str(e)}), 500
