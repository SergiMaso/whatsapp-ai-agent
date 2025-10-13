# 🤖 Restaurant Reservation Bot

Intelligent bot to manage restaurant reservations via Telegram and WhatsApp.

## 🐳 RUN WITH DOCKER (RECOMMENDED)

### 1️⃣ Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your real API keys
```

### 2️⃣ Run with Docker Compose

```bash
docker-compose up --build
```

The application will be available on port **8080** with PostgreSQL included.

### 3️⃣ How to Interact with the App

Once Docker is running:

**📱 Telegram:**
- Search for your bot on Telegram (use the token from .env)
- Send "Hello" to start

**💬 WhatsApp:**
- Configure Twilio webhook pointing to: `http://localhost:8080/webhook`
- Send messages to the configured WhatsApp number

**🔍 Logs:**
```bash
# View all logs
docker-compose logs -f

# Enable debug mode for detailed interaction logs
# Add to .env: DEBUG_MODE=true
# Then restart: docker-compose up --build
```

**🧪 Test Mode:**
```bash
# Local testing
python test_bot.py

# Docker testing
docker-compose run --rm test
```

### 4️⃣ Docker Only (without database)

```bash
docker build -t whatsapp-bot .
docker run -p 8080:8080 --env-file .env whatsapp-bot
```

---

## 🚀 RAILWAY DEPLOYMENT STEPS

### 1️⃣ Reset Database (FIRST STEP)

**IMPORTANT**: Run this BEFORE deploying to Railway:

```bash
cd /path/to/whatsapp-ai-agent
python reset_database.py
```

Type `YES` when prompted to confirm. This will create the database with the correct structure.

### 2️⃣ Clean Unnecessary Files

```bash
python cleanup_files.py
```

### 3️⃣ Push to Railway

```bash
git add .
git commit -m "Updated: default language English, improved user handling"
git push
```

### 4️⃣ Verify it Works

After deployment:
1. Send "Hello" to the Telegram bot → should respond in **English**
2. Send "I want to make a reservation" → should respond in **English** without saying "User"
3. If you send a message in another language → it will detect and save that language

---

## 📋 APPLIED CHANGES

### ✅ Problem 1: Says "User" when name is unknown
**SOLVED**: Now the bot:
- Does NOT say any name if it doesn't know it
- Only greets with "Hello!" without name
- When the client says their name, it saves it and greets them by name from then on

### ✅ Problem 2: Language detection issues
**SOLVED**: 
- **Default language**: English
- **1st message**: Detects language but does NOT save it if it's just "hello"
- **2nd message**: Detects language and saves it to database
- **Following messages**: Uses saved language

### ✅ Problem 3: Error "start_time does not exist"
**SOLVED**: 
- The `appointments` table now uses `start_time` and `end_time` (TIMESTAMP)
- Removed old `time` column
- Reservations now have start and end times

---

## 🗄️ DATABASE STRUCTURE

### Table `customers`
```sql
- phone (VARCHAR) - Unique phone number
- name (VARCHAR) - Client name
- language (VARCHAR) - Preferred language ('es', 'ca', 'en')
- last_visit (TIMESTAMP)
```

### Table `appointments`
```sql
- phone (VARCHAR)
- client_name (VARCHAR)
- date (DATE)
- start_time (TIMESTAMP) ← NEW
- end_time (TIMESTAMP) ← NEW
- num_people (INTEGER)
- table_id (INTEGER)
- language (VARCHAR)
- status (VARCHAR)
```

### Table `tables`
```sql
- table_number (INTEGER) - Table number
- capacity (INTEGER) - 2 or 4 people
- status (VARCHAR)
```

**Total capacity**: 20 tables for 4 people + 8 tables for 2 people

---

## 🔧 MAIN FILES

```
whatsapp-ai-agent/
├── src/
│   ├── config/
│   │   └── settings.py          # Environment variables & config
│   ├── core/
│   │   ├── ai_processor.py      # AI logic
│   │   └── appointments.py      # Business logic & database
│   ├── platforms/
│   │   ├── whatsapp/
│   │   │   └── app.py           # WhatsApp Flask app
│   │   └── telegram/
│   │       └── bot.py           # Telegram bot
│   └── utils/
│       ├── conversation_state.py
│       ├── phone_utils.py
│       ├── telegram_keyboards.py
│       └── user_identifier.py
├── tests/
│   └── test_basic.py            # Basic tests
├── main.py                      # Application entry point
├── test_bot.py                  # Test mode for direct interaction
├── Dockerfile                   # Docker configuration
├── docker-compose.yml           # Docker with PostgreSQL
├── .dockerignore                # Files excluded from Docker
├── railway.json                 # Railway configuration
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables
└── .env.example                 # Variables template
```

---

## 🌍 LANGUAGE FUNCTIONALITY

### First Conversation
```
User: "Hello"
Bot: "Hello! How can I help you?" [English by default]

User: "Quiero hacer una reserva"
Bot: "¡Perfecto! ¿Para cuántas personas?" [detects Spanish, saves and switches]

[All following messages will be in Spanish]
```

### Known Client
```
User: "Hello" [2nd time]
Bot: "Hello again, Marc! How can I help you today?" [uses saved language + name]
```

---

## 📱 ENVIRONMENT VARIABLES (.env)

### 🤖 AI Provider Configuration
```bash
AI_PROVIDER=openai  # Choose 'openai' or 'bedrock'
```

### 🔑 OpenAI (Option 1)
```bash
OPENAI_API_KEY=sk-proj-your-key-here
```
- **Where to get it**: https://platform.openai.com/api-keys
- **Required for**: Natural language processing and bot AI
- **Cost**: Pay per use (GPT-4)

### ☁️ AWS Bedrock (Option 2)
```bash
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_REGION=us-east-1
```
- **Where to get them**: AWS IAM Console
- **Required for**: Claude 3 Sonnet via AWS Bedrock
- **Cost**: AWS Bedrock pricing
- **Note**: Requires Bedrock model access in your AWS account

### 📞 Twilio - WhatsApp (OPTIONAL)
```bash
TWILIO_ACCOUNT_SID=ACyour-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```
- **Where to get them**: https://console.twilio.com/
- **Required for**: Receiving WhatsApp messages
- **Cost**: Twilio charges per message
- **Note**: If not configured, only Telegram will work

### 🤖 Telegram (OPTIONAL)
```bash
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```
- **Where to get it**: Talk to @BotFather on Telegram
- **Required for**: Telegram Bot
- **Cost**: Free
- **Note**: If not configured, only WhatsApp will work

### 🗄️ Database
```bash
# For Docker (automatic)
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/restaurant_bot

# For Railway (created automatically)
DATABASE_URL=postgresql://postgres:password@host:5432/database
```
- **Docker**: PostgreSQL included, no configuration needed
- **Railway**: Created automatically on deploy
- **Others**: You can use any external PostgreSQL

### ⚙️ Optional
```bash
PORT=8080  # Server port (default 8080)
DEBUG_MODE=true  # Enable detailed logging (default false)
```

---

## 🚨 MINIMUM REQUIRED CONFIGURATION

**To work, you need AT LEAST:**
- ✅ `AI_PROVIDER` set to 'openai' or 'bedrock'
- ✅ Either `OPENAI_API_KEY` OR AWS credentials (depending on AI_PROVIDER)
- ✅ `DATABASE_URL` (Docker does this automatically)
- ✅ Either: `TELEGRAM_BOT_TOKEN` OR the 3 Twilio variables

**Configuration examples:**

**Telegram only (OpenAI):**
```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
TELEGRAM_BOT_TOKEN=1234567890:ABC...
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/restaurant_bot
```

**WhatsApp only (AWS Bedrock):**
```bash
AI_PROVIDER=bedrock
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/restaurant_bot
```

**Both platforms (recommended):**
```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-...
TELEGRAM_BOT_TOKEN=1234567890:ABC...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/restaurant_bot
```

---

## ⚠️ IMPORTANT

1. **Always run `reset_database.py` BEFORE deploying** if you change the DB structure
2. The bot now **supports both OpenAI and AWS Bedrock** for AI processing
3. The bot now **only accepts reservations for maximum 4 people** (previously 8)
4. The default language is **English** (previously Spanish)
5. The bot **will never say "User"** if it doesn't know the name

---

## 🐛 Debugging

If there are errors, check Railway logs:
```bash
railway logs
```

Look for these lines:
- `✅ Database ready` → DB OK
- `🌍 Language saved: X → en/es/ca` → Language detection OK
- `📝 Message received: 'X'` → Message processed

---

## 📞 Support

If you have problems:
1. Check that the DB is reset
2. Verify that all unnecessary files are deleted
3. Check Railway logs for errors
4. Contact the development team

---

**Made with ❤️ to automate restaurant reservations**
