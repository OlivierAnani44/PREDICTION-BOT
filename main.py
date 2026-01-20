#!/usr/bin/env python3
"""
Script principal sécurisé avec Railway variables
"""

import asyncio
import sys
import logging
from datetime import datetime

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Imports sécurisés
from config import (
    TELEGRAM_CONFIG, SYSTEM_CONFIG, 
    validate_telegram_config, RAILWAY_CONFIG
)
from espn_collector import ESPNDataCollector
from analyzer import MatchAnalyzer
from selector import PredictionSelector
from telegram_bot import SecureTelegramFormatter
from database import PredictionDatabase

class SecureFootballSystem:
    def __init__(self):
        # Vérifier la configuration
        self._validate_config()
        
        # Initialiser les composants
        self.db = PredictionDatabase()
        self.analyzer = MatchAnalyzer()
        self.selector = PredictionSelector()
        self.telegram = SecureTelegramFormatter()
        
        logger.info(f"🚀 Système démarré - Version {SYSTEM_CONFIG['version']}")
    
    def _validate_config(self):
        """Valide la configuration avant démarrage"""
        if not TELEGRAM_CONFIG['bot_token']:
            raise ValueError("TELEGRAM_BOT_TOKEN manquant")
        if not TELEGRAM_CONFIG['channel_id']:
            raise ValueError("TELEGRAM_CHANNEL_ID manquant")
        
        logger.info("✅ Configuration validée")
    
    async def run_daily_analysis(self):
        """Exécution quotidienne sécurisée"""
        logger.info("🔄 Démarrage analyse quotidienne...")
        
        try:
            # 1. Collecte des données
            async with ESPNDataCollector() as collector:
                matches = await collector.fetch_all_today_matches()
                
                if not matches:
                    logger.warning("Aucun match trouvé")
                    await self._send_no_matches_message()
                    return
                
                # 2. Analyse
                analyses = []
                for match in matches[:50]:  # Limite pour performance
                    analysis = await self._analyze_match(match, collector)
                    if analysis:
                        analyses.append(analysis)
                
                # 3. Sélection
                top_predictions = await self.selector.select_top_predictions(analyses)
                
                if not top_predictions:
                    logger.warning("Aucun pronostic sélectionné")
                    await self._send_no_predictions_message()
                    return
                
                # 4. Rapport
                report = self.selector.generate_selection_report(top_predictions)
                
                # 5. Envoi Telegram
                success = await self.telegram.send_predictions(top_predictions, report)
                
                if success:
                    logger.info("✅ Analyse terminée avec succès")
                    # Sauvegarder
                    selection_date = datetime.now().strftime("%Y-%m-%d")
                    self.db.save_selection(selection_date, top_predictions)
                else:
                    logger.error("❌ Échec envoi Telegram")
        
        except Exception as e:
            logger.error(f"❌ Erreur système: {e}", exc_info=True)
            await self._send_error_message(str(e))
    
    async def _analyze_match(self, match: dict, collector: ESPNDataCollector):
        """Analyse sécurisée d'un match"""
        try:
            # Récupérer historiques
            home_history = await collector.fetch_team_history(
                match['home_team']['id'], 
                match['league'], 
                10
            )
            
            away_history = await collector.fetch_team_history(
                match['away_team']['id'], 
                match['league'], 
                10
            )
            
            # Analyser
            return self.analyzer.analyze_match(
                match, home_history, away_history, []
            )
        
        except Exception as e:
            logger.error(f"Erreur analyse match: {e}")
            return None
    
    async def _send_no_matches_message(self):
        """Message pas de matchs"""
        try:
            message = """
📭 *AUCUN MATCH AUJOURD'HUI*

Aucun match programmé aujourd'hui dans les ligues suivies.

🔄 Prochaine analyse: demain 07:00
"""
            await self.telegram._send_secure_message(message)
        except:
            pass
    
    async def _send_no_predictions_message(self):
        """Message pas de pronostics"""
        try:
            message = """
⚠️ *AUCUN PRONOSTIC VALIDE*

Aucun match ne remplit les critères de confiance aujourd'hui.

📊 Causes possibles:
• Données historiques insuffisantes
• Matchs trop incertains
• Données ESPN incomplètes

🔄 Prochaine analyse: demain 07:00
"""
            await self.telegram._send_secure_message(message)
        except:
            pass
    
    async def _send_error_message(self, error: str):
        """Message d'erreur"""
        try:
            message = f"""
🚨 *ERREUR SYSTÈME*

Une erreur est survenue lors de l'analyse:

`{error[:100]}`

🔧 L'équipe technique a été notifiée.
🔄 Le système redémarrera automatiquement.
"""
            await self.telegram._send_secure_message(message)
        except:
            pass

async def main():
    """Fonction principale"""
    system = SecureFootballSystem()
    await system.run_daily_analysis()

if __name__ == "__main__":
    # Vérifier les arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--check-env":
        from environment import EnvironmentManager
        EnvironmentManager.print_environment()
        sys.exit(0)
    
    # Exécuter
    asyncio.run(main())