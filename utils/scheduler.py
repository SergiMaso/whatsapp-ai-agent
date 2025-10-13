"""
Scheduler per tasques automàtiques del sistema
Executa manteniment setmanal cada dilluns a les 2:00 AM
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz

def start_scheduler(weekly_defaults_manager):
    """
    Iniciar el scheduler amb les tasques programades
    
    Args:
        weekly_defaults_manager: Instància de WeeklyDefaultsManager
    """
    
    scheduler = BackgroundScheduler()
    
    # Timezone de Barcelona (Catalunya)
    barcelona_tz = pytz.timezone('Europe/Madrid')
    
    # ⏰ TASCA: Manteniment setmanal
    # Executa cada dilluns a les 2:00 AM (hora de Barcelona)
    scheduler.add_job(
        func=weekly_defaults_manager.weekly_maintenance,
        trigger=CronTrigger(
            day_of_week='mon',  # Dilluns
            hour=2,             # 2:00 AM
            minute=0,
            timezone=barcelona_tz
        ),
        id='weekly_maintenance',
        name='Manteniment Setmanal (Generar/Eliminar Horaris)',
        replace_existing=True
    )
    
    scheduler.start()
    
    print("=" * 70)
    print("⏰ SCHEDULER INICIALITZAT")
    print("=" * 70)
    print(f"📅 Manteniment setmanal programat: Cada dilluns a les 2:00 AM")
    print(f"🕐 Hora actual: {datetime.now(barcelona_tz).strftime('%d/%m/%Y %H:%M:%S %Z')}")
    
    # Mostrar propera execució
    next_run = scheduler.get_job('weekly_maintenance').next_run_time
    if next_run:
        print(f"▶️  Propera execució: {next_run.strftime('%d/%m/%Y a les %H:%M')}")
    
    print("=" * 70)
    
    return scheduler


def stop_scheduler(scheduler):
    """
    Aturar el scheduler de forma segura
    """
    if scheduler:
        scheduler.shutdown()
        print("⏹️  Scheduler aturat")
