# 🤖 Bot de Reserves per Restaurant

Bot intel·ligent per gestionar reserves de restaurant via Telegram i WhatsApp.

## 🚀 PASSOS PER DESPLEGAR A RAILWAY

### 1️⃣ Resetear la Base de Dades (PRIMER PAS)

**IMPORTANT**: Executa això ABANS de fer deploy a Railway:

```bash
cd /Users/administrador/Desktop/whatsapp-ai-agent
python reset_database.py
```

Escriu `SI` quan et pregunti per confirmar. Això crearà la base de dades amb l'estructura correcta.

### 2️⃣ Netejar Arxius Innecessaris

```bash
python cleanup_files.py
```

### 3️⃣ Fer Push a Railway

```bash
git add .
git commit -m "Fixed: idioma default castellano, no usar 'Usuario' si no conoce el nombre"
git push
```

### 4️⃣ Verificar que funciona

Després del deploy:
1. Envia "Hola" al bot de Telegram → hauria de respondre en **castellà**
2. Envia "Quiero hacer una reserva" → hauria de respondre en **castellà** sense dir "Usuario"
3. Si en el segon missatge dius "Vull fer una reserva" → detectarà **català** i guardarà aquest idioma

---

## 📋 CANVIS APLICATS

### ✅ Problema 1: Diu "Usuario" quan no sap el nom
**SOLUCIONAT**: Ara el bot:
- NO diu cap nom si no el coneix
- Només saluda amb "¡Hola!" sense nom
- Quan el client diu el seu nom, el guarda i a partir d'aquí el saluda pel nom

### ✅ Problema 2: No detecta castellà
**SOLUCIONAT**: 
- **Idioma per defecte**: Castellà
- **1r missatge**: Detecta idioma però NO el guarda si és només "hola"
- **2n missatge**: Detecta idioma i el guarda a la base de dades
- **Missatges següents**: Usa l'idioma guardat

### ✅ Problema 3: Error "start_time does not exist"
**SOLUCIONAT**: 
- La taula `appointments` ara usa `start_time` i `end_time` (TIMESTAMP)
- Eliminada la columna antiga `time`
- Les reserves ara tenen hora d'inici i fi

---

## 🗄️ ESTRUCTURA DE LA BASE DE DADES

### Taula `customers`
```sql
- phone (VARCHAR) - Telèfon únic
- name (VARCHAR) - Nom del client
- language (VARCHAR) - Idioma preferit ('es', 'ca', 'en')
- last_visit (TIMESTAMP)
```

### Taula `appointments`
```sql
- phone (VARCHAR)
- client_name (VARCHAR)
- date (DATE)
- start_time (TIMESTAMP) ← NOVA
- end_time (TIMESTAMP) ← NOVA
- num_people (INTEGER)
- table_id (INTEGER)
- language (VARCHAR)
- status (VARCHAR)
```

### Taula `tables`
```sql
- table_number (INTEGER) - Número de taula
- capacity (INTEGER) - 2 o 4 persones
- status (VARCHAR)
```

**Capacitat total**: 20 taules de 4 persones + 8 taules de 2 persones

---

## 🔧 ARXIUS PRINCIPALS

```
whatsapp-ai-agent/
├── app.py                    # Servidor Flask (WhatsApp)
├── telegram_bot.py           # Bot de Telegram
├── run_both.py              # Executa ambdós bots
├── railway.json             # Configuració Railway
├── requirements.txt         # Dependències Python
├── reset_database.py        # Reset BD (executar 1 cop)
├── cleanup_files.py         # Netejar arxius
├── .env                     # Variables d'entorn
└── utils/
    ├── ai_processor.py      # Processament amb GPT-4
    ├── appointments.py      # Gestió de reserves
    ├── conversation_state.py
    ├── telegram_keyboards.py
    └── transcription.py
```

---

## 🌍 FUNCIONAMENT DE L'IDIOMA

### Primera Conversa
```
Usuari: "Hola"
Bot: "¡Hola! ¿En qué puedo ayudarte?" [castellà per defecte]

Usuari: "Vull fer una reserva"
Bot: "Perfecte! Per a quantes persones?" [detecta català, guarda i canvia]

[Tots els missatges següents seran en català]
```

### Client Conegut
```
Usuari: "Hola" [2a vegada]
Bot: "Hola de nou, Marc! Com puc ajudar-te avui?" [usa idioma guardat + nom]
```

---

## 📱 VARIABLES D'ENTORN (.env)

```bash
# OpenAI
OPENAI_API_KEY=sk-proj-...

# Twilio (WhatsApp)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Telegram
TELEGRAM_BOT_TOKEN=...

# Base de dades (Railway la crea automàticament)
DATABASE_URL=postgresql://...
```

---

## ⚠️ IMPORTANT

1. **Sempre executa `reset_database.py` ABANS de fer deploy** si canvies l'estructura de la BD
2. El bot ara **només accepta reserves de màxim 4 persones** (abans eren 8)
3. L'idioma per defecte és **castellà** (abans era català)
4. El bot **no dirà "Usuario"** mai més si no coneix el nom

---

## 🐛 Debugging

Si hi ha errors, mira els logs a Railway:
```bash
railway logs
```

Busca aquestes línies:
- `✅ Base de datos lista` → BD OK
- `🌍 Idioma guardado: X → ca/es` → Detecció idioma OK
- `📝 Missatge rebut: 'X'` → Missatge processat

---

## 📞 Suport

Si tens problemes:
1. Comprova que la BD està resetejada
2. Verifica que tots els arxius innecessaris estan eliminats
3. Mira els logs de Railway per errors
4. Contacta amb l'equip de desenvolupament

---

**Fet amb ❤️ per automatitzar reserves de restaurant**
