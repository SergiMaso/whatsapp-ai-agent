"""
Script per netejar el webhook de Telegram i eliminar updates pendents
Executa això UNA VEGADA per resoldre conflictes
"""
from telegram import Bot
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

async def cleanup():
    bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
    
    print("🧹 Netejant webhook de Telegram...")
    
    # Eliminar webhook i updates pendents
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook eliminat i updates pendents netejats")
    
    # Verificar estat
    webhook_info = await bot.get_webhook_info()
    print(f"📊 Estat actual del webhook:")
    print(f"   URL: {webhook_info.url}")
    print(f"   Updates pendents: {webhook_info.pending_update_count}")
    
    print("\n✅ Neteja completada! Ara pots reiniciar el bot a Railway.")

if __name__ == '__main__':
    asyncio.run(cleanup())
