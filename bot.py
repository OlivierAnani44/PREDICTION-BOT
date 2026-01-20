#!/usr/bin/env python3
"""
FOOTBALL PREDICTION BOT - FONCTIONNEL
API ESPN avec structure éprouvée
"""

import os
import sys
import json
import sqlite3
import logging
import asyncio
import signal
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ==================== CONFIGURATION ====================

class Config:
    """Configuration Railway"""
    
    @staticmethod
    def validate():
        errors = []
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            errors.append("TELEGRAM_BOT_TOKEN manquant")
        if not os.getenv("TELEGRAM_CHANNEL_ID"):
            errors.append("TELEGRAM_CHANNEL_ID manquant")
        return errors
    
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
    TIMEZONE = os.getenv("TIMEZONE", "UTC")
    DAILY_TIME = os.getenv("DAILY_TIME", "07:00")
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.65"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # ESPN API Configuration
    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
    
    # Ligues principales (format ESPN)
    LEAGUES = {
        "premier_league": {"code": "eng.1", "name": "Premier League"},
        "la_liga": {"code": "esp.1", "name": "La Liga"},
        "bundesliga": {"code": "ger.1", "name": "Bundesliga"},
        "serie_a": {"code": "ita.1", "name": "Serie A"},
        "ligue_1": {"code": "fra.1", "name": "Ligue 1"},
        "champions_league": {"code": "uefa.champions", "name": "UEFA Champions League"},
        "europa_league": {"code": "uefa.europa", "name": "UEFA Europa League"},
    }
    
    # Configuration des modèles
    MODEL_CONFIG = {
        "min_h2h_matches": 3,
        "recent_matches_count": 10,
        "weight_h2h": 0.30,
        "weight_form": 0.25,
        "weight_stats": 0.25,
        "weight_venue": 0.20,
        "min_confidence": MIN_CONFIDENCE,
    }

# ==================== LOGGING ====================

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==================== DATABASE ====================

class Database:
    """Base de données SQLite simplifiée"""
    
    def __init__(self):
        self.conn = sqlite3.connect('predictions.db', check_same_thread=False)
        self.init_db()
    
    def init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT,
                league TEXT,
                home_team TEXT,
                away_team TEXT,
                match_date TEXT,
                confidence REAL,
                predicted_score TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()
    
    def save_prediction(self, pred):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO predictions 
            (match_id, league, home_team, away_team, match_date, confidence, predicted_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            pred.get('match_id'),
            pred.get('league'),
            pred.get('home_team'),
            pred.get('away_team'),
            pred.get('date'),
            pred.get('confidence', 0),
            pred.get('predicted_score', '')
        ))
        self.conn.commit()
    
    def close(self):
        self.conn.close()

# ==================== ESPN COLLECTOR ====================

class ESPNCollector:
    """Collecteur ESPN avec structure éprouvée"""
    
    def __init__(self):
        self.session = None
        self.cache = {}
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
    
    async def fetch_matches(self, days_from_now=0):
        """Récupère les matchs pour une date spécifique"""
        logger.info("📡 Collecte des matchs ESPN...")
        
        target_date = datetime.now() + timedelta(days=days_from_now)
        date_str = target_date.strftime("%Y%m%d")
        logger.info(f"📅 Date cible: {date_str}")
        
        all_matches = []
        
        for league_key, league_info in Config.LEAGUES.items():
            try:
                league_code = league_info["code"]
                
                # URL principale ESPN pour les scoreboards
                url = f"{Config.ESPN_BASE}/soccer/{league_code}/scoreboard"
                params = {
                    "dates": date_str,
                    "limit": 100
                }
                
                logger.info(f"🔗 API: {league_key} ({league_code})")
                
                async with self.session.get(url, params=params, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        matches = self._parse_scoreboard(data, league_key, league_info["name"])
                        if matches:
                            logger.info(f"✅ {league_key}: {len(matches)} match(s)")
                            all_matches.extend(matches)
                    else:
                        logger.warning(f"⚠️ {league_key}: HTTP {response.status}")
                        
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ Erreur {league_key}: {str(e)}")
                continue
        
        logger.info(f"📊 Total: {len(all_matches)} matchs collectés")
        return all_matches
    
    def _parse_scoreboard(self, data, league_key, league_name):
        """Parse le JSON des scoreboards ESPN"""
        matches = []
        
        if not data or 'events' not in data:
            return matches
        
        for event in data['events']:
            try:
                # Vérifier le statut du match
                status = event.get('status', {}).get('type', {})
                if status.get('completed'):
                    continue  # Ignorer les matchs terminés
                
                # Extraire les compétiteurs
                competitions = event.get('competitions', [])
                if not competitions:
                    continue
                
                competitors = competitions[0].get('competitors', [])
                if len(competitors) != 2:
                    continue
                
                # Identifier domicile/extérieur
                home = None
                away = None
                for competitor in competitors:
                    if competitor.get('homeAway') == 'home':
                        home = competitor
                    elif competitor.get('homeAway') == 'away':
                        away = competitor
                
                if not home or not away:
                    continue
                
                # Créer l'objet match
                match_data = {
                    'match_id': event.get('id', ''),
                    'league': league_key,
                    'league_name': league_name,
                    'date': event.get('date', ''),
                    'home_team': {
                        'id': home.get('team', {}).get('id', ''),
                        'name': home.get('team', {}).get('displayName', ''),
                        'short': home.get('team', {}).get('abbreviation', ''),
                        'score': int(home.get('score', 0))
                    },
                    'away_team': {
                        'id': away.get('team', {}).get('id', ''),
                        'name': away.get('team', {}).get('displayName', ''),
                        'short': away.get('team', {}).get('abbreviation', ''),
                        'score': int(away.get('score', 0))
                    },
                    'status': status.get('description', 'Scheduled')
                }
                
                matches.append(match_data)
                
            except Exception as e:
                logger.error(f"Erreur parsing match: {e}")
                continue
        
        return matches
    
    async def fetch_team_history(self, team_id, league_key, limit=5):
        """Récupère l'historique d'une équipe"""
        try:
            league_info = Config.LEAGUES.get(league_key)
            if not league_info:
                return []
            
            league_code = league_info["code"]
            url = f"{Config.ESPN_BASE}/soccer/{league_code}/teams/{team_id}/schedule"
            
            async with self.session.get(url, timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_team_history(data, team_id)
                else:
                    logger.warning(f"Historique équipe {team_id}: HTTP {response.status}")
                    
        except Exception as e:
            logger.error(f"Erreur historique {team_id}: {e}")
        
        return []
    
    def _parse_team_history(self, data, team_id):
        """Parse l'historique d'une équipe"""
        matches = []
        
        if not data or 'events' not in data:
            return matches
        
        for event in data['events'][-10:]:  # 10 derniers matchs
            try:
                competitions = event.get('competitions', [])
                if not competitions:
                    continue
                
                competitors = competitions[0].get('competitors', [])
                if len(competitors) != 2:
                    continue
                
                # Trouver notre équipe et l'adversaire
                team_data = None
                opponent_data = None
                
                for competitor in competitors:
                    comp_id = competitor.get('team', {}).get('id')
                    if str(comp_id) == str(team_id):
                        team_data = competitor
                    else:
                        opponent_data = competitor
                
                if not team_data or not opponent_data:
                    continue
                
                # Score et résultat
                team_score = int(team_data.get('score', 0))
                opponent_score = int(opponent_data.get('score', 0))
                
                if team_score > opponent_score:
                    result = 'WIN'
                elif team_score < opponent_score:
                    result = 'LOSS'
                else:
                    result = 'DRAW'
                
                match_info = {
                    'date': event.get('date', ''),
                    'opponent': opponent_data.get('team', {}).get('displayName', ''),
                    'opponent_id': opponent_data.get('team', {}).get('id', ''),
                    'score_team': team_score,
                    'score_opponent': opponent_score,
                    'result': result,
                    'is_home': team_data.get('homeAway') == 'home'
                }
                
                matches.append(match_info)
                
            except Exception as e:
                logger.error(f"Erreur parsing historique: {e}")
                continue
        
        return matches

# ==================== ANALYSEUR ====================

class MatchAnalyzer:
    """Analyseur de matchs simplifié"""
    
    def __init__(self):
        self.config = Config.MODEL_CONFIG
    
    def analyze(self, match_data, home_history, away_history):
        """Analyse un match"""
        try:
            home_team = match_data['home_team']['name']
            away_team = match_data['away_team']['name']
            
            # 1. Forme récente
            home_form = self._calculate_form(home_history)
            away_form = self._calculate_form(away_history)
            
            # 2. Statistiques de base
            home_stats = self._calculate_stats(home_history)
            away_stats = self._calculate_stats(away_history)
            
            # 3. Avantage domicile
            home_advantage = self._calculate_home_advantage(home_history)
            
            # 4. Score final pondéré
            final_score = self._weighted_score(home_form, away_form, 
                                              home_stats, away_stats, 
                                              home_advantage)
            
            # 5. Confiance
            confidence = self._calculate_confidence(len(home_history), 
                                                  len(away_history),
                                                  home_stats['consistency'],
                                                  away_stats['consistency'])
            
            # 6. Prédiction
            prediction = self._generate_prediction(final_score, home_stats, away_stats)
            
            return {
                'match_id': match_data['match_id'],
                'home_team': home_team,
                'away_team': away_team,
                'league': match_data['league_name'],
                'date': match_data['date'],
                'confidence': confidence,
                'home_form': home_form,
                'away_form': away_form,
                'home_stats': home_stats,
                'away_stats': away_stats,
                'home_advantage': home_advantage,
                'prediction': prediction
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse: {e}")
            return None
    
    def _calculate_form(self, history):
        """Calcule la forme récente (5 derniers matchs)"""
        if not history:
            return {'score': 0.5, 'label': 'UNKNOWN'}
        
        recent = history[-5:] if len(history) >= 5 else history
        points = 0
        
        for match in recent:
            if match['result'] == 'WIN':
                points += 3
            elif match['result'] == 'DRAW':
                points += 1
        
        max_points = len(recent) * 3
        score = points / max_points if max_points > 0 else 0.5
        
        if score >= 0.7:
            label = 'EXCELLENT'
        elif score >= 0.6:
            label = 'GOOD'
        elif score >= 0.4:
            label = 'AVERAGE'
        elif score >= 0.3:
            label = 'POOR'
        else:
            label = 'VERY_POOR'
        
        return {'score': score, 'label': label}
    
    def _calculate_stats(self, history):
        """Calcule les statistiques de base"""
        if not history:
            return {'score': 0.5, 'consistency': 0.5, 'avg_scored': 1.0, 'avg_conceded': 1.0}
        
        goals_scored = [m['score_team'] for m in history]
        goals_conceded = [m['score_opponent'] for m in history]
        
        avg_scored = statistics.mean(goals_scored) if goals_scored else 0
        avg_conceded = statistics.mean(goals_conceded) if goals_conceded else 0
        
        # Score offensif (0-1)
        offense = min(avg_scored / 3.0, 1.0)
        # Score défensif (0-1, plus c'est haut, mieux c'est)
        defense = 1.0 - min(avg_conceded / 3.0, 1.0)
        
        # Score global
        score = (offense * 0.6 + defense * 0.4)
        
        # Consistance (inverse de l'écart-type)
        if len(goals_scored) > 1:
            consistency = 1.0 / (1.0 + statistics.stdev(goals_scored))
        else:
            consistency = 0.5
        
        return {
            'score': score,
            'consistency': consistency,
            'offense': offense,
            'defense': defense,
            'avg_scored': avg_scored,
            'avg_conceded': avg_conceded
        }
    
    def _calculate_home_advantage(self, history):
        """Calcule l'avantage domicile"""
        if not history:
            return {'score': 0.55, 'label': 'NORMAL'}
        
        home_matches = [m for m in history if m.get('is_home')]
        away_matches = [m for m in history if not m.get('is_home')]
        
        if not home_matches or not away_matches:
            return {'score': 0.55, 'label': 'NORMAL'}
        
        # Points par match
        home_ppg = sum([3 if m['result'] == 'WIN' else 1 if m['result'] == 'DRAW' else 0 
                       for m in home_matches]) / len(home_matches)
        away_ppg = sum([3 if m['result'] == 'WIN' else 1 if m['result'] == 'DRAW' else 0 
                       for m in away_matches]) / len(away_matches)
        
        if away_ppg > 0:
            advantage = min(home_ppg / away_ppg / 3, 1.0)
        else:
            advantage = 0.7
        
        # Normaliser
        score = 0.5 + (advantage - 0.5) * 0.5
        
        if score >= 0.65:
            label = 'STRONG'
        elif score >= 0.6:
            label = 'MODERATE'
        elif score >= 0.55:
            label = 'SLIGHT'
        else:
            label = 'NONE'
        
        return {'score': score, 'label': label}
    
    def _weighted_score(self, home_form, away_form, home_stats, away_stats, home_adv):
        """Calcule le score pondéré final"""
        weights = self.config
        
        # Score de base = avantage domicile
        base = home_adv['score']
        
        # Différence de forme
        form_diff = home_form['score'] - away_form['score']
        
        # Différence de stats
        stats_diff = home_stats['score'] - away_stats['score']
        
        # Calcul final
        raw_score = base + (form_diff * weights['weight_form']) + \
                   (stats_diff * weights['weight_stats'])
        
        # Normaliser entre 0 et 1
        final_score = max(0.0, min(1.0, raw_score))
        
        return {
            'home_win': final_score,
            'draw': 0.15,
            'away_win': 1.0 - final_score - 0.15
        }
    
    def _calculate_confidence(self, home_matches, away_matches, home_consistency, away_consistency):
        """Calcule le score de confiance"""
        home_factor = min(home_matches / 10.0, 1.0)
        away_factor = min(away_matches / 10.0, 1.0)
        
        data_factor = (home_factor + away_factor) / 2
        consistency_factor = (home_consistency + away_consistency) / 2
        
        confidence = (data_factor * 0.6 + consistency_factor * 0.4)
        return round(confidence, 3)
    
    def _generate_prediction(self, final_score, home_stats, away_stats):
        """Génère la prédiction finale"""
        home_win_prob = final_score['home_win']
        
        # Recommandation
        if home_win_prob >= 0.7:
            recommendation = 'HOME WIN'
            emoji = '🏠✅'
        elif home_win_prob >= 0.6:
            recommendation = 'HOME WIN OR DRAW'
            emoji = '🏠🤝'
        elif home_win_prob >= 0.55:
            recommendation = 'HOME WIN OR DRAW'
            emoji = '🏠🤝'
        elif home_win_prob <= 0.3:
            recommendation = 'AWAY WIN'
            emoji = '✈️✅'
        elif home_win_prob <= 0.4:
            recommendation = 'AWAY WIN OR DRAW'
            emoji = '✈️🤝'
        else:
            recommendation = 'DRAW'
            emoji = '⚖️'
        
        # Score prédit
        pred_home = round(home_stats['avg_scored'] * 1.1, 1)
        pred_away = round(away_stats['avg_scored'] * 0.9, 1)
        
        # Over/Under
        total_goals = pred_home + pred_away
        over_under = 'OVER 2.5' if total_goals > 2.5 else 'UNDER 2.5'
        
        # Both teams to score
        btts = 'YES' if pred_home > 0.5 and pred_away > 0.5 else 'NO'
        
        return {
            'recommendation': recommendation,
            'emoji': emoji,
            'predicted_score': f"{int(pred_home)}-{int(pred_away)}",
            'expected_goals': f"{pred_home:.1f}-{pred_away:.1f}",
            'over_under': over_under,
            'btts': btts,
            'home_win_prob': home_win_prob,
            'draw_prob': final_score['draw'],
            'away_win_prob': final_score['away_win']
        }

# ==================== SELECTEUR ====================

class PredictionsSelector:
    """Sélectionne les meilleures prédictions"""
    
    def __init__(self):
        self.min_confidence = Config.MIN_CONFIDENCE
    
    def select_best(self, analyses, limit=5):
        """Sélectionne les meilleures analyses"""
        valid = [a for a in analyses if a and a['confidence'] >= self.min_confidence]
        
        if not valid:
            return []
        
        # Trier par confiance décroissante
        sorted_analyses = sorted(valid, key=lambda x: x['confidence'], reverse=True)
        
        return sorted_analyses[:limit]
    
    def generate_report(self, predictions):
        """Génère un rapport de sélection"""
        if not predictions:
            return {'total': 0, 'avg_confidence': 0, 'risk': 'UNKNOWN'}
        
        confidences = [p['confidence'] for p in predictions]
        avg_conf = sum(confidences) / len(confidences)
        
        # Profil de risque
        if avg_conf >= 0.8:
            risk = 'LOW'
        elif avg_conf >= 0.7:
            risk = 'MODERATE'
        elif avg_conf >= 0.65:
            risk = 'HIGH'
        else:
            risk = 'VERY_HIGH'
        
        return {
            'total': len(predictions),
            'avg_confidence': round(avg_conf, 3),
            'risk': risk,
            'date': datetime.now().strftime("%Y-%m-%d")
        }

# ==================== TELEGRAM ====================

class TelegramBot:
    """Gestionnaire Telegram"""
    
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.channel = Config.TELEGRAM_CHANNEL_ID
        
        if not self.token or not self.channel:
            raise ValueError("Configuration Telegram manquante")
    
    async def send_predictions(self, predictions, report):
        """Envoie les prédictions sur Telegram"""
        try:
            message = self._format_message(predictions, report)
            return await self._send(message)
        except Exception as e:
            logger.error(f"Erreur Telegram: {e}")
            return False
    
    def _format_message(self, predictions, report):
        """Formate le message Telegram"""
        date_str = datetime.now().strftime("%d/%m/%Y")
        
        # En-tête
        header = f"""
⚽️ *PRONOSTICS FOOTBALL* ⚽️
📅 {date_str}
━━━━━━━━━━━━━━━━━━━━━━━━

📊 *RAPPORT D'ANALYSE*
• Matchs analysés: {report['total']}
• Confiance moyenne: {report['avg_confidence']:.1%}
• Profil de risque: {report['risk']}

🏆 *TOP {len(predictions)} PRONOSTICS*
━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Pronostics
        predictions_text = ""
        for i, pred in enumerate(predictions, 1):
            rank_emoji = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'][i-1]
            pred_data = pred['prediction']
            
            predictions_text += f"""
{rank_emoji} *{pred['home_team']} vs {pred['away_team']}*
🏆 {pred['league']} | 🔍 Confiance: {pred['confidence']:.1%}

📈 *ANALYSE:*
  • Forme: {pred['home_form']['label']} vs {pred['away_form']['label']}
  • Attaque: {pred['home_stats']['offense']:.2f} vs {pred['away_stats']['offense']:.2f}
  • Défense: {pred['home_stats']['defense']:.2f} vs {pred['away_stats']['defense']:.2f}
  • Domicile: {pred['home_advantage']['label']}

🎯 *PRÉDICTION:* {pred_data['emoji']}
  • {pred_data['recommendation']}
  • Score probable: *{pred_data['predicted_score']}*
  • Over/Under 2.5: {pred_data['over_under']}
  • Les deux marquent: {pred_data['btts']}

📊 *PROBABILITÉS:*
  1️⃣ {pred_data['home_win_prob']:.1%} | N {pred_data['draw_prob']:.1%} | 2️⃣ {pred_data['away_win_prob']:.1%}
────────────────────
"""
        
        # Pied de page
        footer = """
⚠️ *INFORMATIONS IMPORTANTES*
• Analyse algorithmique basée sur données ESPN
• Aucune garantie de gain
• Jouez responsablement

⚙️ Système: Football Predictor v3.0
🔄 Prochaine analyse: 07:00 UTC
"""
        
        return f"{header}\n{predictions_text}\n{footer}"
    
    async def _send(self, text):
        """Envoie le message"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            
            # Vérifier la longueur
            if len(text) > 4000:
                parts = self._split_text(text)
                for part in parts:
                    if not await self._send_part(part):
                        return False
                    await asyncio.sleep(1)
                return True
            else:
                return await self._send_part(text)
                
        except Exception as e:
            logger.error(f"Erreur envoi: {e}")
            return False
    
    async def _send_part(self, text):
        """Envoie une partie du message"""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            'chat_id': self.channel,
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
                        error = await resp.text()
                        logger.error(f"❌ Telegram error: {resp.status} - {error}")
                        return False
        except Exception as e:
            logger.error(f"❌ Exception Telegram: {e}")
            return False
    
    def _split_text(self, text, max_len=4000):
        """Divise un long texte"""
        parts = []
        while len(text) > max_len:
            split_at = text.rfind('\n', 0, max_len)
            if split_at == -1:
                split_at = max_len
            parts.append(text[:split_at])
            text = text[split_at:].lstrip()
        
        if text:
            parts.append(text)
        
        return parts

# ==================== SYSTÈME PRINCIPAL ====================

class PredictionSystem:
    """Système principal de prédiction"""
    
    def __init__(self):
        self.db = Database()
        self.analyzer = MatchAnalyzer()
        self.selector = PredictionsSelector()
        self.telegram = TelegramBot()
        
        logger.info("🚀 Système initialisé")
    
    async def run_analysis(self, days_ahead=1):
        """Exécute l'analyse complète"""
        logger.info("🔄 Démarrage analyse...")
        
        try:
            # 1. Collecte des matchs
            async with ESPNCollector() as collector:
                matches = await collector.fetch_matches(days_ahead)
                
                if not matches:
                    logger.warning("Aucun match trouvé")
                    await self._send_no_matches()
                    return
                
                logger.info(f"📊 {len(matches)} matchs à analyser")
                
                # 2. Analyse des matchs
                analyses = []
                for match in matches:
                    try:
                        home_history = await collector.fetch_team_history(
                            match['home_team']['id'], match['league'], 5
                        )
                        away_history = await collector.fetch_team_history(
                            match['away_team']['id'], match['league'], 5
                        )
                        
                        analysis = self.analyzer.analyze(match, home_history, away_history)
                        if analysis:
                            analyses.append(analysis)
                        
                        await asyncio.sleep(0.3)
                        
                    except Exception as e:
                        logger.error(f"Erreur analyse match: {e}")
                        continue
                
                logger.info(f"✅ {len(analyses)} matchs analysés")
                
                # 3. Sélection des meilleurs
                top_predictions = self.selector.select_best(analyses, 5)
                
                if not top_predictions:
                    logger.warning("Aucune prédiction valide")
                    await self._send_no_predictions()
                    return
                
                # 4. Rapport
                report = self.selector.generate_report(top_predictions)
                
                # 5. Envoi Telegram
                success = await self.telegram.send_predictions(top_predictions, report)
                
                if success:
                    logger.info("✅ Analyse terminée avec succès")
                    # Sauvegarde
                    for pred in top_predictions:
                        self.db.save_prediction(pred)
                else:
                    logger.error("❌ Échec envoi Telegram")
                
        except Exception as e:
            logger.error(f"❌ Erreur système: {e}", exc_info=True)
            await self._send_error(str(e))
    
    async def _send_no_matches(self):
        """Message aucun match"""
        try:
            message = "📭 *AUCUN MATCH*\\n\\nAucun match programmé aujourd'hui.\\n🔄 Prochaine analyse: 07:00"
            await self.telegram._send_part(message)
        except:
            pass
    
    async def _send_no_predictions(self):
        """Message aucune prédiction"""
        try:
            message = "⚠️ *AUCUNE PRÉDICTION VALIDE*\\n\\nAucun match ne remplit les critères de confiance.\\n🔄 Prochaine analyse: 07:00"
            await self.telegram._send_part(message)
        except:
            pass
    
    async def _send_error(self, error):
        """Message d'erreur"""
        try:
            message = f"🚨 *ERREUR SYSTÈME*\\n\\nUne erreur est survenue:\\n`{error[:100]}`\\n\\n🔧 L'équipe a été notifiée."
            await self.telegram._send_part(message)
        except:
            pass

# ==================== SCHEDULER ====================

class Scheduler:
    """Planificateur Railway"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
        self.system = PredictionSystem()
        self.running = True
        
        # Gestion des signaux
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    async def start(self):
        """Démarre le planificateur"""
        logger.info("⏰ Planificateur démarré")
        logger.info(f"📍 Fuseau: {Config.TIMEZONE}")
        logger.info(f"⏰ Heure quotidienne: {Config.DAILY_TIME}")
        
        # Parser l'heure
        try:
            hour, minute = map(int, Config.DAILY_TIME.split(':'))
        except:
            hour, minute = 7, 0
        
        # Planifier la tâche quotidienne
        self.scheduler.add_job(
            self._daily_task,
            CronTrigger(hour=hour, minute=minute, timezone=Config.TIMEZONE),
            id='daily_prediction',
            name='Analyse quotidienne'
        )
        
        # Mode test
        if '--test' in sys.argv:
            logger.info("🧪 Mode test - exécution immédiate")
            await self._daily_task()
        
        # Démarrer et maintenir
        self.scheduler.start()
        try:
            while self.running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.shutdown()
    
    async def _daily_task(self):
        """Tâche quotidienne"""
        logger.info("🔄 Exécution tâche quotidienne...")
        await self.system.run_analysis(days_ahead=1)
        logger.info("✅ Tâche terminée")
    
    def shutdown(self, signum=None, frame=None):
        """Arrêt propre"""
        logger.info("🛑 Arrêt du planificateur...")
        self.running = False
        self.scheduler.shutdown(wait=False)
        logger.info("✅ Planificateur arrêté")
        sys.exit(0)

# ==================== POINT D'ENTRÉE ====================

def main():
    """Point d'entrée principal"""
    
    if '--help' in sys.argv:
        print("""
🚀 Football Prediction Bot
Usage:
  python bot.py          # Mode normal
  python bot.py --test   # Mode test
        
Variables Railway requises:
  • TELEGRAM_BOT_TOKEN
  • TELEGRAM_CHANNEL_ID
        
Variables optionnelles:
  • TIMEZONE (UTC)
  • DAILY_TIME (07:00)
  • MIN_CONFIDENCE (0.65)
  • LOG_LEVEL (INFO)
        """)
        return
    
    # Validation
    errors = Config.validate()
    if errors:
        print("❌ ERREURS:")
        for error in errors:
            print(f"  - {error}")
        print("\n⚠️  Configurez dans Railway Dashboard")
        return
    
    # Démarrer
    scheduler = Scheduler()
    asyncio.run(scheduler.start())

if __name__ == "__main__":
    main()