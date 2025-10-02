# 🤖 Bot de Reservas - Dual (WhatsApp + Telegram)

Bot inteligente de reservas para restaurante que funciona en **WhatsApp** Y **Telegram** simultáneamente.

## 📱 Características

- ✅ Funciona en WhatsApp (vía Twilio)
- ✅ Funciona en Telegram (gratis, ilimitado)
- ✅ Transcripción de audio con Whisper
- ✅ IA conversacional con GPT-4
- ✅ Gestión de reservas (crear, ver, cancelar)
- ✅ Multiidioma (español, catalán, inglés)
- ✅ Base de datos PostgreSQL
- ✅ Asignación automática de mesas

## 🚀 Deploy en Railway

### Variables de Entorno Necesarias:

```env
# OpenAI
OPENAI_API_KEY=tu_key_aqui

# WhatsApp (Twilio) - OPCIONAL si solo usas Telegram
TWILIO_ACCOUNT_SID=tu_sid
TWILIO_AUTH_TOKEN=tu_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Telegram - GRATIS Y SIN LÍMITES
TELEGRAM_BOT_TOKEN=tu_bot_token_aqui

# Base de datos (Railway la crea automáticamente)
DATABASE_URL=postgresql://...
```

## 🔧 Configuración

### Para WhatsApp:
1. Crea cuenta en Twilio
2. Configura Sandbox de WhatsApp
3. Webhook: `https://tu-dominio.railway.app/whatsapp`

### Para Telegram:
1. Habla con @BotFather en Telegram
2. Envía `/newbot`
3. Copia el token que te da
4. Agrégalo a las variables de entorno
5. ¡Listo! Busca tu bot y envía `/start`

## 🧪 Pruebas Locales

### Telegram (recomendado):
```bash
python telegram_bot.py
```

### WhatsApp (requiere ngrok):
```bash
python app.py
ngrok http 5000
# Configura la URL de ngrok en Twilio
```

### Simulación sin mensajería:
```bash
python test_local.py
```

## 📊 Arquitectura

```
Usuario (WhatsApp/Telegram)
         ↓
    Servidor Flask / Telegram Bot
         ↓
   Procesador de IA (GPT-4)
         ↓
  Base de Datos PostgreSQL
```

## 🎯 Comandos

### WhatsApp:
- Envía cualquier mensaje para empezar
- Envía audio para transcripción automática

### Telegram:
- `/start` - Iniciar conversación
- Envía mensaje de texto o audio
- El bot entiende lenguaje natural

## 📝 Ejemplos de Uso

```
Usuario: "Quiero hacer una reserva para 4 personas hoy a las 2"
Bot: "¿Cuál es tu nombre?"
Usuario: "Sergi"
Bot: "Reserva confirmada! ..."
```

## 🔄 Modo Dual

Este bot corre **ambos** servicios simultáneamente:
- Puerto 8080: Webhook de WhatsApp (Flask)
- Polling: Bot de Telegram

Puedes usar uno, otro, o ambos. Son completamente independientes pero comparten:
- Misma IA
- Misma base de datos
- Misma lógica de negocio

## 💡 Recomendaciones

- **Para desarrollo**: Usa Telegram (gratis, sin límites)
- **Para producción**: Usa WhatsApp (más usuarios lo tienen)
- **Para máximo alcance**: Usa ambos
