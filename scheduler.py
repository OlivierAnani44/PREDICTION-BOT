"""
Planificateur Railway avec variables d'environnement
"""

import asyncio
import signal
import sys
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from main import SecureFootballSystem
from config import RAILWAY_CONFIG

logger = logging.getLogger(__name__)

class RailwaySecureScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=RAILWAY_CONFIG['timezone'])
        self.system = None
        self.running = True
        
        # Configuration
        self.daily_time = RAILWAY_CONFIG.get('daily_time', '07:00')
        
        # Gestion des signaux
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def start(self):
        """Démarre le planificateur sécurisé"""
        logger.info("⏰ Planificateur Railway démarré")
        logger.info(f"📍 Fuseau horaire: {RAILWAY_CONFIG['timezone']}")
        logger.info(f"⏰ Heure quotidienne: {self.daily_time}")
        
        # Parser l'heure
        try:
            hour, minute = map(int, self.daily_time.split(':'))
        except:
            hour, minute = 7, 0  # Défaut
        
        # Planifier la tâche
        self.scheduler.add_job(
            self._execute_daily_task,
            CronTrigger(hour=hour, minute=minute),
            id='daily_football_analysis',
            name='Analyse football quotidienne',
            replace_existing=True
        )
        
        # Exécution immédiate en mode test
        if '--test' in sys.argv:
            logger.info("🧪 Mode test - exécution immédiate")
            self.scheduler.add_job(
                self._execute_daily_task,
                'date',
                run_date=datetime.now(),
                id='test_execution'
            )
        
        # Démarrage
        self.scheduler.start()
        
        # Boucle principale
        self._main_loop()
    
    async def _execute_daily_task(self):
        """Exécute la tâche quotidienne"""
        logger.info("🔄 Démarrage tâche quotidienne...")
        
        try:
            self.system = SecureFootballSystem()
            await self.system.run_daily_analysis()
            logger.info("✅ Tâche quotidienne terminée")
        except Exception as e:
            logger.error(f"❌ Erreur tâche quotidienne: {e}")
    
    def _main_loop(self):
        """Boucle principale"""
        logger.info("✅ Planificateur actif - Attente des tâches...")
        
        try:
            # Keep alive
            while self.running:
                signal.pause()
        except KeyboardInterrupt:
            self.shutdown()
    
    def _signal_handler(self, signum, frame):
        """Gestionnaire de signaux"""
        logger.info(f"📡 Signal reçu: {signum}")
        self.shutdown()
    
    def shutdown(self):
        """Arrêt propre"""
        logger.info("🛑 Arrêt du planificateur...")
        self.running = False
        self.scheduler.shutdown(wait=False)
        logger.info("✅ Planificateur arrêté")
        sys.exit(0)

def main():
    """Point d'entrée Railway"""
    scheduler = RailwaySecureScheduler()
    scheduler.start()

if __name__ == "__main__":
    # Options de ligne de commande
    if '--help' in sys.argv:
        print("""
🚀 ESPN Football Predictor - Railway
        
Usage:
  python scheduler_secure.py          # Mode normal
  python scheduler_secure.py --test   # Mode test immédiat
  python scheduler_secure.py --check  # Vérifier l'environnement
        
Variables d'environnement requises sur Railway:
  • TELEGRAM_BOT_TOKEN
  • TELEGRAM_CHANNEL_ID
        
Variables optionnelles:
  • TIMEZONE (défaut: Europe/Paris)
  • DAILY_TIME (défaut: 07:00)
  • MIN_CONFIDENCE (défaut: 0.65)
  • LOG_LEVEL (défaut: INFO)
        """)
        sys.exit(0)
    
    # Démarrer
    main()