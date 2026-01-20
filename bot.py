#!/usr/bin/env python3
"""
FOOTBALL PREDICTION BOT - COMPLETE SINGLE FILE
Automatisation complète des prédictions ESPN avec Telegram
Déployé sur Railway - Variables d'environnement uniquement
"""

import os
import sys
import json
import math
import sqlite3
import logging
import asyncio
import signal
import statistics
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Tuple
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ==================== CONFIGURATION ====================

class Config:
    """Configuration depuis variables d'environnement Railway"""
    
    # Validation des variables requises
    @staticmethod
    def validate():
        errors = []
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            errors.append("TELEGRAM_BOT_TOKEN manquant")
        if not os.getenv("TELEGRAM_CHANNEL_ID"):
            errors.append("TELEGRAM_CHANNEL_ID manquant")
        return errors
    
    # Variables requises
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
    
    # Variables optionnelles avec valeurs par défaut
    TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris")
    DAILY_TIME = os.getenv("DAILY_TIME", "07:00")
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.65"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    CLEANUP_DAYS = int(os.getenv("CLEANUP_DAYS", "30"))
    
    # Configuration ESPN
    ESPN_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"
    
    # Toutes les ligues ESPN
    LEAGUE_MAPPING = {
        "DZA.1": "soccer/dza.1", "GER.1": "soccer/ger.1", "GER.2": "soccer/ger.2",
        "GER.3": "soccer/ger.cup", "ENG.1": "soccer/eng.1", "ENG.2": "soccer/eng.2",
        "ENG.FA": "soccer/eng.fa", "ENG.LEAGUE_CUP": "soccer/eng.league_cup",
        "KSA.1": "soccer/ksa.1", "AUT.1": "soccer/aut.1", "BEL.1": "soccer/bel.1",
        "BRA.1": "soccer/bra.1", "CMR.1": "soccer/cmr.1", "CIV.1": "soccer/civ.1",
        "SCO.1": "soccer/sco.1", "EGY.1": "soccer/egy.1", "ESP.1": "soccer/esp.1",
        "ESP.2": "soccer/esp.2", "ESP.CUP": "soccer/esp.cup", "USA.1": "soccer/usa.1",
        "UEFA.EURO_QUAL": "soccer/uefa.euro_qual", "UEFA.CL": "soccer/uefa.champions",
        "UEFA.EL": "soccer/uefa.europa", "UEFA.ECL": "soccer/uefa.europa_conference",
        "UEFA.NATIONS": "soccer/uefa.nations", "FRA.1": "soccer/fra.1",
        "FRA.2": "soccer/fra.2", "FRA.3": "soccer/fra.3", "FRA.CUP": "soccer/fra.cup",
        "GRE.1": "soccer/gre.1", "ITA.1": "soccer/ita.1", "ITA.2": "soccer/ita.2",
        "ITA.CUP": "soccer/ita.cup", "MAR.1": "soccer/mar.1", "MEX.1": "soccer/mex.1",
        "INT.COPA_AMERICA": "soccer/int.copa_america", "INT.AFCON": "soccer/int.africa_cup",
        "INT.ASIAN_CUP": "soccer/int.asian_cup", "INT.WORLD_CUP": "soccer/fifa.world",
        "INT.FRIENDLY": "soccer/int.friendly", "NOR.1": "soccer/nor.1",
        "NED.1": "soccer/ned.1", "POR.1": "soccer/por.1", "POR.2": "soccer/por.2",
        "POR.CUP": "soccer/por.cup", "RUS.1": "soccer/rus.1", "SEN.1": "soccer/sen.1",
        "SUI.1": "soccer/sui.1", "TUN.1": "soccer/tun.1", "TUR.1": "soccer/tur.1",
        "UKR.1": "soccer/ukr.1"
    }
    
    PRIORITY_LEAGUES = [
        "ENG.1", "ESP.1", "GER.1", "ITA.1", "FRA.1",
        "UEFA.CL", "UEFA.EL", "INT.WORLD_CUP", "INT.AFCON"
    ]
    
    MODEL_CONFIG = {
        "min_h2h_matches": 3,
        "recent_matches_count": 10,
        "weight_h2h": 0.30,
        "weight_form": 0.25,
        "weight_stats": 0.25,
        "weight_venue": 0.20,
        "min_confidence": MIN_CONFIDENCE,
        "data_freshness_days": 30
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
    """Base de données SQLite"""
    
    def __init__(self, path="predictions.db"):
        self.path = path
        self._init_db()
    
    def _init_db(self):
        """Initialise la base de données"""
        conn = sqlite3.connect(self.path)
        cursor = conn.cursor()
        
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
                recommendation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                match_id TEXT,
                telegram_sent BOOLEAN DEFAULT 0,
                sent_at TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_prediction(self, prediction: Dict):
        """Sauvegarde une prédiction"""
        try:
            conn = sqlite3.connect(self.path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO predictions 
                (match_id, league, home_team, away_team, match_date, 
                 confidence, predicted_score, recommendation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                prediction.get('match_id'),
                prediction.get('league'),
                prediction.get('home_team'),
                prediction.get('away_team'),
                prediction.get('date'),
                prediction.get('confidence', 0),
                prediction.get('predicted_score', ''),
                prediction.get('recommendation', '')
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde: {e}")
            return False
    
    def mark_sent(self, match_id: str):
        """Marque un match comme envoyé"""
        try:
            conn = sqlite3.connect(self.path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sent_messages (date, match_id, telegram_sent, sent_at)
                VALUES (DATE('now'), ?, 1, CURRENT_TIMESTAMP)
            ''', (match_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Erreur marquage: {e}")
            return False
    
    def cleanup_old_data(self, days=30):
        """Nettoie les anciennes données"""
        try:
            conn = sqlite3.connect(self.path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM predictions 
                WHERE date(created_at) < date('now', ?)
            ''', (f'-{days} days',))
            
            conn.commit()
            conn.close()
            logger.info(f"Données nettoyées (> {days} jours)")
        except Exception as e:
            logger.error(f"Erreur nettoyage: {e}")

# ==================== ESPN COLLECTOR ====================

class ESPNCollector:
    """Collecte des données ESPN"""
    
    def __init__(self):
        self.session = None
        self.base_url = Config.ESPN_BASE_URL
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
    
    async def fetch_today_matches(self):
        """Récupère tous les matchs du jour"""
        logger.info("📡 Collecte des matchs ESPN...")
        
        all_matches = []
        today = datetime.now().strftime("%Y%m%d")
        
        for league_code, league_path in Config.LEAGUE_MAPPING.items():
            try:
                url = f"{self.base_url}/{league_path}/scoreboard"
                params = {"dates": today}
                
                async with self.session.get(url, params=params, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        matches = self._extract_matches(data, league_code)
                        if matches:
                            logger.debug(f"✅ {league_code}: {len(matches)} match(s)")
                            all_matches.extend(matches)
                
                await asyncio.sleep(0.5)  # Respect rate limits
                
            except Exception as e:
                logger.error(f"❌ Erreur {league_code}: {e}")
                continue
        
        logger.info(f"📊 Total: {len(all_matches)} matchs collectés")
        return all_matches
    
    def _extract_matches(self, data: Dict, league_code: str) -> List[Dict]:
        """Extrait les données de match"""
        matches = []
        
        if 'events' not in data:
            return matches
        
        for event in data['events']:
            try:
                competition = event.get('competitions', [{}])[0]
                competitors = competition.get('competitors', [])
                
                if len(competitors) != 2:
                    continue
                
                home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                
                if not home or not away:
                    continue
                
                match_data = {
                    'match_id': event.get('id'),
                    'league': league_code,
                    'date': event.get('date'),
                    'home_team': {
                        'id': home.get('team', {}).get('id'),
                        'name': home.get('team', {}).get('displayName'),
                        'score': int(home.get('score', 0))
                    },
                    'away_team': {
                        'id': away.get('team', {}).get('id'),
                        'name': away.get('team', {}).get('displayName'),
                        'score': int(away.get('score', 0))
                    }
                }
                
                matches.append(match_data)
                
            except Exception as e:
                logger.error(f"Erreur extraction: {e}")
                continue
        
        return matches
    
    async def fetch_team_history(self, team_id: str, league_code: str, limit: int = 10):
        """Récupère l'historique d'une équipe"""
        try:
            league_path = Config.LEAGUE_MAPPING.get(league_code)
            if not league_path:
                return []
            
            url = f"{self.base_url}/{league_path}/teams/{team_id}/schedule"
            
            async with self.session.get(url, timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._extract_team_history(data, team_id, limit)
                    
        except Exception as e:
            logger.error(f"Erreur historique équipe {team_id}: {e}")
        
        return []
    
    def _extract_team_history(self, data: Dict, team_id: str, limit: int) -> List[Dict]:
        """Extrait l'historique d'équipe"""
        matches = []
        
        if 'events' not in data:
            return matches
        
        for event in data['events'][-limit:]:
            try:
                competition = event.get('competitions', [{}])[0]
                competitors = competition.get('competitors', [])
                
                if len(competitors) != 2:
                    continue
                
                # Trouver notre équipe
                team_data = None
                opponent_data = None
                
                for competitor in competitors:
                    comp_team_id = competitor.get('team', {}).get('id')
                    if str(comp_team_id) == str(team_id):
                        team_data = competitor
                    else:
                        opponent_data = competitor
                
                if not team_data or not opponent_data:
                    continue
                
                # Déterminer résultat
                team_score = int(team_data.get('score', 0))
                opponent_score = int(opponent_data.get('score', 0))
                
                if team_score > opponent_score:
                    result = 'WIN'
                elif team_score < opponent_score:
                    result = 'LOSS'
                else:
                    result = 'DRAW'
                
                match_info = {
                    'date': event.get('date'),
                    'home_away': team_data.get('homeAway'),
                    'opponent': opponent_data.get('team', {}).get('displayName'),
                    'opponent_id': opponent_data.get('team', {}).get('id'),
                    'score_team': team_score,
                    'score_opponent': opponent_score,
                    'result': result,
                    'is_home': team_data.get('homeAway') == 'home'
                }
                
                matches.append(match_info)
                
            except Exception as e:
                logger.error(f"Erreur extraction historique: {e}")
                continue
        
        return matches

# ==================== ANALYZER ====================

class MatchAnalyzer:
    """Analyseur de matchs"""
    
    def __init__(self):
        self.config = Config.MODEL_CONFIG
    
    def analyze(self, match_data: Dict, home_history: List[Dict], 
                away_history: List[Dict]) -> Dict:
        """Analyse complète d'un match"""
        try:
            home_team = match_data['home_team']['name']
            away_team = match_data['away_team']['name']
            
            # 1. Analyse forme
            home_form = self._analyze_form(home_history)
            away_form = self._analyze_form(away_history)
            
            # 2. Analyse statistiques
            home_stats = self._analyze_stats(home_history)
            away_stats = self._analyze_stats(away_history)
            
            # 3. Avantage domicile
            venue_advantage = self._analyze_venue(home_history)
            
            # 4. Calcul score final
            final_score = self._calculate_score(
                home_form, away_form, home_stats, away_stats, venue_advantage
            )
            
            # 5. Confiance
            confidence = self._calculate_confidence(
                len(home_history), len(away_history), 
                home_stats['consistency'], away_stats['consistency']
            )
            
            # 6. Prédictions
            predictions = self._generate_predictions(
                final_score, home_stats, away_stats
            )
            
            return {
                'match_id': match_data['match_id'],
                'home_team': home_team,
                'away_team': away_team,
                'league': match_data['league'],
                'date': match_data['date'],
                'confidence': confidence,
                'home_form': home_form,
                'away_form': away_form,
                'home_stats': home_stats,
                'away_stats': away_stats,
                'venue_advantage': venue_advantage,
                'final_score': final_score,
                'predictions': predictions
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse: {e}")
            return None
    
    def _analyze_form(self, history: List[Dict]) -> Dict:
        """Analyse de la forme récente"""
        if not history:
            return {'score': 0.5, 'form': 'UNKNOWN'}
        
        recent = history[-5:] if len(history) >= 5 else history
        total_points = 0
        
        for match in recent:
            if match['result'] == 'WIN':
                total_points += 3
            elif match['result'] == 'DRAW':
                total_points += 1
        
        max_points = len(recent) * 3
        form_score = total_points / max_points if max_points > 0 else 0.5
        
        if form_score >= 0.7:
            form = 'EXCELLENT'
        elif form_score >= 0.6:
            form = 'GOOD'
        elif form_score >= 0.4:
            form = 'AVERAGE'
        elif form_score >= 0.3:
            form = 'POOR'
        else:
            form = 'VERY_POOR'
        
        return {'score': form_score, 'form': form}
    
    def _analyze_stats(self, history: List[Dict]) -> Dict:
        """Analyse statistique"""
        if not history:
            return {'score': 0.5, 'consistency': 0.5}
        
        goals_scored = [m['score_team'] for m in history]
        goals_conceded = [m['score_opponent'] for m in history]
        
        avg_scored = statistics.mean(goals_scored) if goals_scored else 0
        avg_conceded = statistics.mean(goals_conceded) if goals_conceded else 0
        
        offense_score = min(avg_scored / 3.0, 1.0)
        defense_score = 1.0 - min(avg_conceded / 3.0, 1.0)
        
        stats_score = (offense_score * 0.6 + defense_score * 0.4)
        
        if len(goals_scored) > 1:
            consistency = 1.0 / (1.0 + statistics.stdev(goals_scored))
        else:
            consistency = 0.5
        
        return {
            'score': stats_score,
            'consistency': consistency,
            'offense': offense_score,
            'defense': defense_score,
            'avg_scored': avg_scored,
            'avg_conceded': avg_conceded
        }
    
    def _analyze_venue(self, history: List[Dict]) -> Dict:
        """Analyse avantage domicile"""
        if not history:
            return {'score': 0.55, 'advantage': 'NORMAL'}
        
        home_matches = [m for m in history if m.get('is_home')]
        away_matches = [m for m in history if not m.get('is_home')]
        
        if not home_matches or not away_matches:
            return {'score': 0.55, 'advantage': 'NORMAL'}
        
        home_points = sum([
            3 if m['result'] == 'WIN' else 1 if m['result'] == 'DRAW' else 0 
            for m in home_matches
        ])
        away_points = sum([
            3 if m['result'] == 'WIN' else 1 if m['result'] == 'DRAW' else 0 
            for m in away_matches
        ])
        
        home_ppg = home_points / len(home_matches)
        away_ppg = away_points / len(away_matches)
        
        if away_ppg > 0:
            venue_score = min(home_ppg / away_ppg / 3, 1.0)
        else:
            venue_score = 0.7
        
        venue_score = 0.5 + (venue_score - 0.5) * 0.5
        
        if venue_score >= 0.65:
            advantage = 'STRONG'
        elif venue_score >= 0.6:
            advantage = 'MODERATE'
        elif venue_score >= 0.55:
            advantage = 'SLIGHT'
        else:
            advantage = 'NONE'
        
        return {'score': venue_score, 'advantage': advantage}
    
    def _calculate_score(self, home_form: Dict, away_form: Dict,
                        home_stats: Dict, away_stats: Dict, 
                        venue: Dict) -> Dict:
        """Calcule le score final"""
        weights = self.config
        
        base_score = venue['score']
        form_diff = home_form['score'] - away_form['score']
        stats_diff = home_stats['score'] - away_stats['score']
        
        final_raw = base_score + (form_diff * weights['weight_form']) + \
                   (stats_diff * weights['weight_stats'])
        
        final_score = max(0.0, min(1.0, final_raw))
        
        return {
            'home_win_prob': final_score,
            'draw_prob': 0.15,
            'away_win_prob': 1.0 - final_score - 0.15
        }
    
    def _calculate_confidence(self, home_matches: int, away_matches: int,
                            home_consistency: float, away_consistency: float) -> float:
        """Calcule la confiance"""
        home_factor = min(home_matches / 10.0, 1.0)
        away_factor = min(away_matches / 10.0, 1.0)
        
        data_factor = (home_factor + away_factor) / 2
        consistency_factor = (home_consistency + away_consistency) / 2
        
        confidence = (data_factor * 0.6 + consistency_factor * 0.4)
        return round(confidence, 3)
    
    def _generate_predictions(self, final_score: Dict, 
                             home_stats: Dict, away_stats: Dict) -> Dict:
        """Génère les prédictions"""
        home_win_prob = final_score['home_win_prob']
        
        if home_win_prob >= 0.7:
            recommendation = 'STRONG_HOME_WIN'
        elif home_win_prob >= 0.6:
            recommendation = 'HOME_WIN'
        elif home_win_prob >= 0.55:
            recommendation = 'HOME_WIN_OR_DRAW'
        elif home_win_prob <= 0.3:
            recommendation = 'STRONG_AWAY_WIN'
        elif home_win_prob <= 0.4:
            recommendation = 'AWAY_WIN'
        elif home_win_prob <= 0.45:
            recommendation = 'AWAY_WIN_OR_DRAW'
        else:
            recommendation = 'DRAW_OR_UNDER'
        
        predicted_home = round(home_stats['avg_scored'] * 1.1, 1)
        predicted_away = round(away_stats['avg_scored'] * 0.9, 1)
        
        return {
            'recommendation': recommendation,
            'predicted_score': f"{int(predicted_home)}-{int(predicted_away)}",
            'expected_goals': f"{predicted_home:.1f}-{predicted_away:.1f}",
            'over_under': 'OVER 2.5' if (predicted_home + predicted_away) > 2.5 else 'UNDER 2.5'
        }

# ==================== SELECTOR ====================

class PredictionSelector:
    """Sélectionne les meilleurs pronostics"""
    
    def __init__(self):
        self.min_confidence = Config.MIN_CONFIDENCE
    
    def select_top_predictions(self, analyses: List[Dict], limit: int = 5) -> List[Dict]:
        """Sélectionne les meilleurs pronostics"""
        valid_analyses = []
        
        for analysis in analyses:
            if analysis and analysis['confidence'] >= self.min_confidence:
                valid_analyses.append(analysis)
        
        if not valid_analyses:
            return []
        
        # Trier par confiance
        sorted_analyses = sorted(
            valid_analyses,
            key=lambda x: x['confidence'],
            reverse=True
        )
        
        return sorted_analyses[:limit]
    
    def generate_report(self, predictions: List[Dict]) -> Dict:
        """Génère un rapport"""
        if not predictions:
            return {'total': 0, 'average_confidence': 0}
        
        confidences = [p['confidence'] for p in predictions]
        
        return {
            'total': len(predictions),
            'average_confidence': round(sum(confidences) / len(confidences), 3),
            'selection_date': datetime.now().strftime("%Y-%m-%d")
        }

# ==================== TELEGRAM BOT ====================

class TelegramBot:
    """Bot Telegram"""
    
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.channel_id = Config.TELEGRAM_CHANNEL_ID
        
        if not self.token or not self.channel_id:
            raise ValueError("Tokens Telegram manquants")
    
    async def send_predictions(self, predictions: List[Dict], report: Dict) -> bool:
        """Envoie les prédictions sur Telegram"""
        try:
            message = self.format_message(predictions, report)
            return await self._send_message(message)
        except Exception as e:
            logger.error(f"Erreur envoi Telegram: {e}")
            return False
    
    def format_message(self, predictions: List[Dict], report: Dict) -> str:
        """Formate le message Telegram"""
        date_str = datetime.now().strftime("%d/%m/%Y")
        
        header = f"""
⚽️ *PRONOSTICS FOOTBALL DU JOUR* ⚽️
📅 {date_str}
━━━━━━━━━━━━━━━━━━━━━━━━

🎯 *ANALYSE COMPLÈTE*
• Matchs analysés: {report.get('total', 0)}
• Confiance moyenne: {report.get('average_confidence', 0):.1%}
• Sélection: Top {len(predictions)} pronostics
"""
        
        predictions_text = "🏆 *TOP PRONOSTICS* 🏆\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, pred in enumerate(predictions, 1):
            rank_emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
            confidence = pred['confidence']
            
            conf_emoji = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.7 else "🔴"
            
            predictions_text += f"{rank_emoji} *{pred['home_team']} vs {pred['away_team']}*\n"
            predictions_text += f"🏆 {pred['league']} | {conf_emoji} Confiance: {confidence:.1%}\n\n"
            
            predictions_text += f"📊 *ANALYSE:*\n"
            predictions_text += f"  • Forme: {pred['home_form']['form']} vs {pred['away_form']['form']}\n"
            predictions_text += f"  • Attaque: {pred['home_stats']['offense']:.2f} vs {pred['away_stats']['offense']:.2f}\n"
            predictions_text += f"  • Défense: {pred['home_stats']['defense']:.2f} vs {pred['away_stats']['defense']:.2f}\n"
            predictions_text += f"  • Domicile: {pred['venue_advantage']['advantage']}\n\n"
            
            pred_data = pred['predictions']
            predictions_text += f"🎯 *PRÉDICTION:*\n"
            predictions_text += f"  • {pred_data['recommendation'].replace('_', ' ')}\n"
            predictions_text += f"  • Score probable: *{pred_data['predicted_score']}*\n"
            predictions_text += f"  • Over/Under: {pred_data['over_under']}\n"
            
            predictions_text += "\n" + "─" * 30 + "\n\n"
        
        footer = """
━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *INFORMATIONS IMPORTANTES:*
• Analyse algorithmique ESPN
• Données mises à jour quotidiennement
• Aucune garantie de gain
• Jouez responsablement

⚙️ *SYSTÈME:* Football Predictor v2.0
🔄 *PROCHAIN:* 07:00 demain
"""
        
        return f"{header}\n\n{predictions_text}\n\n{footer}"
    
    async def _send_message(self, text: str) -> bool:
        """Envoie le message sur Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            
            # Diviser si trop long
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
    
    async def _send_part(self, text: str) -> bool:
        """Envoie une partie du message"""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            'chat_id': self.channel_id,
            'text': text,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=30) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Erreur partie: {e}")
            return False
    
    def _split_text(self, text: str, max_len: int = 4000) -> List[str]:
        """Divise le texte"""
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

# ==================== MAIN SYSTEM ====================

class FootballPredictionSystem:
    """Système principal"""
    
    def __init__(self):
        self.db = Database()
        self.analyzer = MatchAnalyzer()
        self.selector = PredictionSelector()
        self.telegram = TelegramBot()
        
        logger.info("🚀 Système Football Predictor initialisé")
    
    async def run_daily_analysis(self):
        """Exécute l'analyse quotidienne"""
        logger.info("🔄 Démarrage analyse quotidienne...")
        
        try:
            # 1. Collecte des données
            async with ESPNCollector() as collector:
                matches = await collector.fetch_today_matches()
                
                if not matches:
                    logger.warning("Aucun match trouvé aujourd'hui")
                    await self._send_no_matches()
                    return
                
                logger.info(f"📊 {len(matches)} matchs à analyser")
                
                # 2. Analyse
                analyses = []
                analyzed = 0
                
                for match in matches:
                    try:
                        # Récupérer historiques
                        home_history = await collector.fetch_team_history(
                            match['home_team']['id'], match['league'], 10
                        )
                        away_history = await collector.fetch_team_history(
                            match['away_team']['id'], match['league'], 10
                        )
                        
                        # Analyser
                        analysis = self.analyzer.analyze(match, home_history, away_history)
                        if analysis:
                            analyses.append(analysis)
                            analyzed += 1
                        
                        await asyncio.sleep(0.3)  # Rate limiting
                        
                    except Exception as e:
                        logger.error(f"Erreur match {match.get('match_id', 'N/A')}: {e}")
                        continue
                
                logger.info(f"✅ {analyzed}/{len(matches)} matchs analysés")
                
                # 3. Sélection
                top_predictions = self.selector.select_top_predictions(analyses, 5)
                
                if not top_predictions:
                    logger.warning("Aucun pronostic valide")
                    await self._send_no_predictions()
                    return
                
                # 4. Rapport
                report = self.selector.generate_report(top_predictions)
                
                # 5. Envoi Telegram
                success = await self.telegram.send_predictions(top_predictions, report)
                
                if success:
                    logger.info("✅ Pronostics envoyés avec succès")
                    # Sauvegarder
                    for pred in top_predictions:
                        self.db.save_prediction(pred)
                        self.db.mark_sent(pred['match_id'])
                else:
                    logger.error("❌ Échec envoi Telegram")
                
                # 6. Nettoyage
                self.db.cleanup_old_data(Config.CLEANUP_DAYS)
                
        except Exception as e:
            logger.error(f"❌ Erreur système: {e}", exc_info=True)
            await self._send_error(str(e))
    
    async def _send_no_matches(self):
        """Message aucun match"""
        try:
            message = "📭 *AUCUN MATCH AUJOURD'HUI*\n\nPas de match programmé.\n🔄 Prochaine analyse: 07:00 demain"
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': Config.TELEGRAM_CHANNEL_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error("Erreur envoi message aucun match")
        except:
            pass
    
    async def _send_no_predictions(self):
        """Message aucun pronostic"""
        try:
            message = "⚠️ *AUCUN PRONOSTIC VALIDE*\n\nAucun match ne remplit les critères de confiance.\n🔄 Prochaine analyse: 07:00 demain"
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': Config.TELEGRAM_CHANNEL_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error("Erreur envoi message aucun pronostic")
        except:
            pass
    
    async def _send_error(self, error: str):
        """Message d'erreur"""
        try:
            message = f"🚨 *ERREUR SYSTÈME*\n\nUne erreur est survenue:\n`{error[:100]}`\n\n🔧 L'équipe technique a été notifiée."
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': Config.TELEGRAM_CHANNEL_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error("Erreur envoi message d'erreur")
        except:
            pass

# ==================== SCHEDULER ====================

class Scheduler:
    """Planificateur Railway"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
        self.system = None
        self.running = True
        
        # Gestion signaux
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    def start(self):
        """Démarre le planificateur"""
        logger.info("⏰ Planificateur Railway démarré")
        logger.info(f"📍 Fuseau: {Config.TIMEZONE}")
        logger.info(f"⏰ Heure quotidienne: {Config.DAILY_TIME}")
        
        # Parser l'heure
        try:
            hour, minute = map(int, Config.DAILY_TIME.split(':'))
        except:
            hour, minute = 7, 0
        
        # Planifier tâche quotidienne
        self.scheduler.add_job(
            self._daily_task,
            CronTrigger(hour=hour, minute=minute, timezone=Config.TIMEZONE),
            id='daily_football',
            name='Analyse football quotidienne'
        )
        
        # Mode test immédiat
        if '--test' in sys.argv:
            logger.info("🧪 Mode test - exécution immédiate")
            self.scheduler.add_job(
                self._daily_task,
                'date',
                run_date=datetime.now()
            )
        
        # Démarrer
        self.scheduler.start()
        
        # Maintenir en vie
        try:
            import time
            while self.running:
                time.sleep(60)
        except KeyboardInterrupt:
            self.shutdown()
    
    async def _daily_task(self):
        """Tâche quotidienne"""
        logger.info("🔄 Exécution tâche quotidienne...")
        self.system = FootballPredictionSystem()
        await self.system.run_daily_analysis()
        logger.info("✅ Tâche terminée")
    
    def shutdown(self, signum=None, frame=None):
        """Arrêt propre"""
        logger.info("🛑 Arrêt du planificateur...")
        self.running = False
        self.scheduler.shutdown(wait=False)
        logger.info("✅ Planificateur arrêté")
        sys.exit(0)

# ==================== MAIN ENTRY POINT ====================

def main():
    """Point d'entrée principal"""
    
    # Vérifier les arguments
    if '--help' in sys.argv:
        print("""
🚀 Football Prediction Bot - Single File
        
Usage:
  python bot.py          # Mode normal
  python bot.py --test   # Exécution test immédiate
        
Variables d'environnement Railway requises:
  • TELEGRAM_BOT_TOKEN
  • TELEGRAM_CHANNEL_ID
        
Variables optionnelles:
  • TIMEZONE (Europe/Paris)
  • DAILY_TIME (07:00)
  • MIN_CONFIDENCE (0.65)
  • LOG_LEVEL (INFO)
  • CLEANUP_DAYS (30)
        """)
        return
    
    # Valider configuration
    errors = Config.validate()
    if errors:
        print("❌ ERREURS DE CONFIGURATION:")
        for error in errors:
            print(f"  - {error}")
        print("\n⚠️  Configurez dans Railway Dashboard:")
        print("  Settings → Variables → New Variable")
        return
    
    # Démarrer
    scheduler = Scheduler()
    scheduler.start()

if __name__ == "__main__":
    main()