"""
Bot Telegram avec variables d'environnement
"""

import asyncio
import logging
from typing import List, Dict
from datetime import datetime

# Import de la configuration sécurisée
from config import TELEGRAM_CONFIG

logger = logging.getLogger(__name__)

class SecureTelegramFormatter:
    def __init__(self):
        # Récupérer les tokens depuis la configuration
        self.bot_token = TELEGRAM_CONFIG['bot_token']
        self.channel_id = TELEGRAM_CONFIG['channel_id']
        
        # Validation
        if not self.bot_token or not self.channel_id:
            raise ValueError("Tokens Telegram manquants dans l'environnement")
    
    async def send_predictions(self, predictions: List[Dict], report: Dict) -> bool:
        """Envoie les prédictions sécurisées"""
        try:
            message = self.format_predictions(predictions, report)
            return await self._send_secure_message(message)
        except Exception as e:
            logger.error(f"Erreur envoi Telegram: {e}")
            return False
    
    def format_predictions(self, predictions: List[Dict], report: Dict) -> str:
        """Formate les prédictions"""
        if not predictions:
            return self._format_no_data()
        
        # Formatage sécurisé (pas de données sensibles)
        header = self._format_header(report)
        predictions_text = self._format_predictions_list(predictions)
        footer = self._format_footer()
        
        return f"{header}\n\n{predictions_text}\n\n{footer}"
    
    async def _send_secure_message(self, message: str) -> bool:
        """Envoi sécurisé avec token d'environnement"""
        try:
            import aiohttp
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            # Diviser si trop long
            if len(message) > 4000:
                parts = self._split_message(message)
                success = True
                for part in parts:
                    if not await self._send_message_part(part):
                        success = False
                return success
            else:
                return await self._send_message_part(message)
        
        except Exception as e:
            logger.error(f"Erreur envoi sécurisé: {e}")
            return False
    
    async def _send_message_part(self, text: str) -> bool:
        """Envoie une partie du message"""
        import aiohttp
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            'chat_id': self.channel_id,
            'text': text,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        logger.info("✅ Message Telegram envoyé")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"❌ Erreur Telegram {resp.status}: {error_text}")
                        return False
        except Exception as e:
            logger.error(f"❌ Exception Telegram: {e}")
            return False
    
    def _format_header(self, report: Dict) -> str:
        """En-tête sécurisé"""
        date_str = datetime.now().strftime("%d/%m/%Y")
        
        return f"""
⚽️ *PRONOSTICS FOOTBALL* ⚽️
📅 {date_str}
━━━━━━━━━━━━━━━━━━━━━━━━

🎯 *RAPPORT D'ANALYSE*
• Matchs analysés: {report.get('total_analyzed', 0)}
• Confiance moyenne: {report.get('average_confidence', 0):.1%}
• Profil de risque: {report.get('risk_profile', 'INCONNU')}
"""
    
    def _format_predictions_list(self, predictions: List[Dict]) -> str:
        """Liste des prédictions"""
        text = "🏆 *TOP 5 PRONOSTICS* 🏆\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, pred in enumerate(predictions[:5], 1):
            rank_emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
            confidence = pred.get('confidence', 0)
            
            text += f"{rank_emoji} *{pred.get('home_team', 'Inconnu')} vs {pred.get('away_team', 'Inconnu')}*\n"
            text += f"🏆 {pred.get('league', '')} | "
            text += f"Confiance: {confidence:.1%}\n"
            
            # Prédiction
            pred_data = pred.get('predictions', {})
            if pred_data:
                text += f"🎯 Score probable: *{pred_data.get('predicted_score', 'N/A')}*\n"
                text += f"📊 Recommendation: {pred_data.get('recommendation', 'N/A')}\n"
            
            text += "\n" + "─" * 30 + "\n\n"
        
        return text
    
    def _format_footer(self) -> str:
        """Pied de page sécurisé"""
        return """
━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *INFORMATIONS IMPORTANTES*
• Système automatisé ESPN Analytics
• Aucun token stocké dans le code
• Variables sécurisées Railway
• Jouez responsablement

⚙️ *SYSTÈME:* ESPN Bot v2.0
🔄 *PROCHAIN:* 07:00 demain
"""
    
    def _format_no_data(self) -> str:
        """Message quand pas de données"""
        return """
📭 *AUCUNE DONNÉE DISPONIBLE*

Aucun pronostic valide aujourd'hui.
Causes possibles:
• Pas de matchs programmés
• Données ESPN indisponibles
• Critères non remplis

🔄 Analyse reprendra demain 07:00
"""
    
    def _split_message(self, message: str, max_length: int = 4000) -> List[str]:
        """Divise le message"""
        parts = []
        while len(message) > max_length:
            split_at = message.rfind('\n', 0, max_length)
            if split_at == -1:
                split_at = max_length
            parts.append(message[:split_at])
            message = message[split_at:].lstrip()
        
        if message:
            parts.append(message)
        
        return parts