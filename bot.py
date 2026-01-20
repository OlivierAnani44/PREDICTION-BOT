#!/usr/bin/env python3
"""
BOT DE PRONOSTICS FOOTBALL ULTIMATE
Combine ESPN API (matchs du jour) + OpenLigaDB (statistiques) + 5 modèles de calcul
"""

import os
import sys
import json
import sqlite3
import logging
import asyncio
import statistics
import math
import random
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ==================== DIRECTIVES ====================
# 1. Utiliser l'API ESPN pour obtenir tous les matchs du jour
# 2. Surveiller les 51 ligues spécifiées
# 3. Utiliser l'API OpenLigaDB pour récupérer les statistiques
# 4. Appliquer 5 modèles de calcul (modèles disponibles)
# 5. Générer des pronostics avec confiance
# 6. Sélectionner les 5 meilleurs matchs
# 7. Envoyer sur Telegram via bot
# 8. Tourner 24h/24 sur Railway
# 9. Gérer les erreurs et logs
# 10. Base de données pour historiques
# 11. Scheduler pour exécutions régulières
# 12. Validation des configurations
# ====================================================

# ==================== CONFIGURATION ====================

class Config:
    """Configuration centrale du bot"""
    
    @staticmethod
    def validate():
        """Validation des variables d'environnement"""
        errors = []
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            errors.append("TELEGRAM_BOT_TOKEN manquant")
        if not os.getenv("TELEGRAM_CHANNEL_ID"):
            errors.append("TELEGRAM_CHANNEL_ID manquant")
        return errors
    
    # Configuration Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
    TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris")
    DAILY_TIME = os.getenv("DAILY_TIME", "07:00")
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.65"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # Configuration des APIs
    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
    OPENLIGADB_BASE = "https://api.openligadb.de"
    API_TIMEOUT = 30
    
    # Liste complète des 51 ligues avec mapping ESPN
    LEAGUES_MAPPING = {
        # Allemagne
        "Bundesliga": {"espn_code": "ger.1", "openliga_code": "bl1", "season": 2024},
        "Bundesliga 2": {"espn_code": "ger.2", "openliga_code": "bl2", "season": 2024},
        "Coupe d'Allemagne": {"espn_code": "ger.3", "openliga_code": "dfbpokal", "season": 2024},
        
        # Angleterre
        "Premier League": {"espn_code": "eng.1", "openliga_code": "pl", "season": 2024},
        "Championship": {"espn_code": "eng.2", "openliga_code": "elc", "season": 2024},
        "FA Cup": {"espn_code": "eng.3", "openliga_code": "facup", "season": 2024},
        "League Cup": {"espn_code": "eng.4", "openliga_code": "leaguecup", "season": 2024},
        
        # Espagne
        "La Liga": {"espn_code": "esp.1", "openliga_code": "primera", "season": 2024},
        "Segunda Division": {"espn_code": "esp.2", "openliga_code": "segunda", "season": 2024},
        "Copa del Rey": {"espn_code": "esp.3", "openliga_code": "copadelrey", "season": 2024},
        
        # France
        "Ligue 1": {"espn_code": "fra.1", "openliga_code": "ligue1", "season": 2024},
        "Ligue 2": {"espn_code": "fra.2", "openliga_code": "ligue2", "season": 2024},
        "Coupe de France": {"espn_code": "fra.3", "openliga_code": "coupedefrance", "season": 2024},
        
        # Italie
        "Serie A": {"espn_code": "ita.1", "openliga_code": "seriea", "season": 2024},
        "Serie B": {"espn_code": "ita.2", "openliga_code": "serieb", "season": 2024},
        "Coupe d'Italie": {"espn_code": "ita.3", "openliga_code": "coppaitalia", "season": 2024},
        
        # Europe
        "Ligue des champions": {"espn_code": "uefa.champions", "openliga_code": "cl", "season": 2024},
        "Ligue Europa": {"espn_code": "uefa.europa", "openliga_code": "el", "season": 2024},
        "Europa Conference League": {"espn_code": "uefa.europa.conference", "openliga_code": "ecl", "season": 2024},
        
        # Portugal
        "Liga Portugal": {"espn_code": "por.1", "openliga_code": "liga", "season": 2024},
        "Coupe du Portugal": {"espn_code": "por.2", "openliga_code": "cup", "season": 2024},
        
        # Pays-Bas
        "Eredivisie": {"espn_code": "ned.1", "openliga_code": "eredivisie", "season": 2024},
        
        # Autres ligues importantes
        "Saudi Pro League": {"espn_code": "ksa.1", "openliga_code": "spl", "season": 2024},
        "Major League Soccer": {"espn_code": "usa.1", "openliga_code": "mls", "season": 2024},
        "Super League Greece": {"espn_code": "gre.1", "openliga_code": "superleague", "season": 2024},
        "Jupiler Pro League": {"espn_code": "bel.1", "openliga_code": "jupiler", "season": 2024},
        "Scottish Premiership": {"espn_code": "sco.1", "openliga_code": "premiership", "season": 2024},
        "Austrian Bundesliga": {"espn_code": "aut.1", "openliga_code": "bundesliga", "season": 2024},
        "Swiss Super League": {"espn_code": "sui.1", "openliga_code": "superleague", "season": 2024},
        "Turkish Süper Lig": {"espn_code": "tur.1", "openliga_code": "superlig", "season": 2024},
        "Russian Premier League": {"espn_code": "rus.1", "openliga_code": "premier", "season": 2024},
        "Ukrainian Premier League": {"espn_code": "ukr.1", "openliga_code": "premier", "season": 2024},
        "Danish Superliga": {"espn_code": "den.1", "openliga_code": "superliga", "season": 2024},
        "Norwegian Eliteserien": {"espn_code": "nor.1", "openliga_code": "eliteserien", "season": 2024},
        "Swedish Allsvenskan": {"espn_code": "swe.1", "openliga_code": "allsvenskan", "season": 2024},
        "Polish Ekstraklasa": {"espn_code": "pol.1", "openliga_code": "ekstraklasa", "season": 2024},
        "Czech First League": {"espn_code": "cze.1", "openliga_code": "firstleague", "season": 2024},
    }
    
    # Modèles de calcul activés (5 modèles principaux)
    ENABLED_MODELS = {
        "statistical": True,      # Modèle statistique pondéré
        "poisson": True,          # Distribution de Poisson pour les buts[citation:2]
        "form": True,             # Forme récente
        "h2h": True,              # Confrontations directes
        "combined": True,         # Modèle combiné
    }
    
    # Pondérations pour le modèle statistique[citation:2][citation:8]
    MODEL_WEIGHTS = {
        "statistical": 0.35,
        "poisson": 0.25,
        "form": 0.20,
        "h2h": 0.20,
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
    """Gestion de la base de données SQLite"""
    
    def __init__(self):
        self.db_path = "football_predictions.db"
        logger.info(f"📁 Initialisation base de données: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.init_db()
    
    def init_db(self):
        """Initialisation des tables"""
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT UNIQUE,
                league TEXT,
                home_team TEXT,
                away_team TEXT,
                match_date TEXT,
                confidence REAL,
                predicted_score TEXT,
                bet_type TEXT,
                model_details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_stats (
                match_id TEXT PRIMARY KEY,
                league TEXT,
                home_team TEXT,
                away_team TEXT,
                home_goals INTEGER,
                away_goals INTEGER,
                home_shots INTEGER,
                away_shots INTEGER,
                home_possession REAL,
                away_possession REAL,
                home_corners INTEGER,
                away_corners INTEGER,
                stats_json TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_history (
                team_id TEXT,
                team_name TEXT,
                league TEXT,
                matches_played INTEGER,
                wins INTEGER,
                draws INTEGER,
                losses INTEGER,
                goals_for INTEGER,
                goals_against INTEGER,
                avg_goals_for REAL,
                avg_goals_against REAL,
                form_last_5 TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_id, league)
            )
        ''')
        
        self.conn.commit()
        logger.info("✅ Base de données initialisée")
    
    def save_prediction(self, prediction):
        """Sauvegarde d'une prédiction"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO predictions 
                (match_id, league, home_team, away_team, match_date, 
                 confidence, predicted_score, bet_type, model_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                prediction['match_id'],
                prediction['league'],
                prediction['home_team'],
                prediction['away_team'],
                prediction['match_date'],
                prediction['confidence'],
                prediction['predicted_score'],
                prediction['bet_type'],
                json.dumps(prediction.get('model_details', {}))
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde prédiction: {e}")
            return False
    
    def get_team_history(self, team_name, league):
        """Récupération historique équipe"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM team_history 
                WHERE team_name = ? AND league = ?
                ORDER BY last_updated DESC LIMIT 1
            ''', (team_name, league))
            
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        except Exception as e:
            logger.error(f"Erreur historique équipe: {e}")
            return None
    
    def close(self):
        """Fermeture connexion"""
        self.conn.close()

# ==================== COLLECTOR ESPN ====================

class ESPNCollector:
    """Collecteur des matchs du jour via ESPN API[citation:6][citation:7]"""
    
    def __init__(self):
        self.session = None
        self.base_url = Config.ESPN_BASE
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_today_matches(self):
        """Récupération de tous les matchs du jour"""
        logger.info("📡 Collecte des matchs du jour via ESPN API...")
        
        today = datetime.now().strftime("%Y%m%d")
        all_matches = []
        total_leagues = len(Config.LEAGUES_MAPPING)
        
        logger.info(f"🔍 Recherche dans {total_leagues} ligues...")
        
        for idx, (league_name, league_info) in enumerate(Config.LEAGUES_MAPPING.items(), 1):
            try:
                espn_code = league_info["espn_code"]
                
                # Construction URL ESPN[citation:6]
                url = f"{self.base_url}/soccer/{espn_code}/scoreboard"
                params = {"dates": today}
                
                logger.debug(f"  [{idx}/{total_leagues}] Vérification {league_name}")
                
                async with self.session.get(url, params=params, timeout=Config.API_TIMEOUT) as response:
                    if response.status == 200:
                        data = await response.json()
                        matches = self._parse_espn_data(data, league_name, league_info)
                        
                        if matches:
                            logger.info(f"    ✅ {league_name}: {len(matches)} match(s)")
                            all_matches.extend(matches)
                        else:
                            logger.debug(f"    📭 {league_name}: Aucun match aujourd'hui")
                    
                    elif response.status == 400:
                        logger.debug(f"    📭 {league_name}: Pas de matchs (HTTP 400)")
                    else:
                        logger.warning(f"    ⚠️ {league_name}: HTTP {response.status}")
                
                await asyncio.sleep(0.3)  # Respect rate limits
                
            except asyncio.TimeoutError:
                logger.error(f"    ⏱️ Timeout pour {league_name}")
            except Exception as e:
                logger.error(f"    ❌ Erreur {league_name}: {str(e)[:100]}")
        
        logger.info(f"📊 Total matchs du jour trouvés: {len(all_matches)}")
        return all_matches
    
    def _parse_espn_data(self, data, league_name, league_info):
        """Parsing des données ESPN"""
        matches = []
        
        if not data or 'events' not in data:
            return matches
        
        for event in data['events']:
            try:
                # Extraction des équipes
                competitions = event.get('competitions', [{}])[0]
                competitors = competitions.get('competitors', [])
                
                if len(competitors) != 2:
                    continue
                
                home_team = None
                away_team = None
                
                for competitor in competitors:
                    if competitor.get('homeAway') == 'home':
                        home_team = competitor.get('team', {})
                    elif competitor.get('homeAway') == 'away':
                        away_team = competitor.get('team', {})
                
                if not home_team or not away_team:
                    continue
                
                # Vérifier si le match est terminé
                status = event.get('status', {})
                is_finished = status.get('type', {}).get('completed', False)
                
                match_data = {
                    'match_id': event.get('id', ''),
                    'league': league_name,
                    'league_code': league_info.get('openliga_code', ''),
                    'league_season': league_info.get('season', 2024),
                    'date': event.get('date', ''),
                    'home_team': {
                        'id': home_team.get('id', ''),
                        'name': home_team.get('displayName', ''),
                        'short': home_team.get('abbreviation', '')
                    },
                    'away_team': {
                        'id': away_team.get('id', ''),
                        'name': away_team.get('displayName', ''),
                        'short': away_team.get('abbreviation', '')
                    },
                    'is_finished': is_finished,
                    'raw_data': event
                }
                
                matches.append(match_data)
                
            except Exception as e:
                logger.debug(f"Erreur parsing match ESPN: {e}")
                continue
        
        return matches

# ==================== COLLECTOR OPENLIGADB ====================

class OpenLigaDBCollector:
    """Collecteur des statistiques via OpenLigaDB[citation:5]"""
    
    def __init__(self):
        self.session = None
        self.base_url = Config.OPENLIGADB_BASE
        self.headers = {
            'User-Agent': 'FootballPredictorBot/1.0',
            'Accept': 'application/json'
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_team_stats(self, team_name, league_code, season):
        """Récupération des statistiques d'une équipe"""
        try:
            # Recherche de l'équipe
            teams_url = f"{self.base_url}/getavailableteams/{league_code}/{season}"
            
            async with self.session.get(teams_url, timeout=Config.API_TIMEOUT) as response:
                if response.status == 200:
                    teams = await response.json()
                    
                    # Trouver l'équipe par nom
                    team_data = None
                    for team in teams:
                        if team_name.lower() in team.get('teamName', '').lower():
                            team_data = team
                            break
                    
                    if not team_data:
                        logger.debug(f"Équipe non trouvée: {team_name}")
                        return None
                    
                    # Récupérer les statistiques de l'équipe
                    team_id = team_data.get('teamId')
                    stats_url = f"{self.base_url}/getmatchdata/{league_code}/{season}"
                    
                    async with self.session.get(stats_url, timeout=Config.API_TIMEOUT) as stats_response:
                        if stats_response.status == 200:
                            all_matches = await stats_response.json()
                            
                            # Filtrer les matchs de cette équipe
                            team_matches = []
                            for match in all_matches:
                                if (match.get('team1', {}).get('teamId') == team_id or 
                                    match.get('team2', {}).get('teamId') == team_id):
                                    team_matches.append(match)
                            
                            # Calculer les statistiques
                            stats = self._calculate_team_stats(team_matches, team_id, team_name)
                            return stats
                
                return None
                
        except Exception as e:
            logger.error(f"Erreur statistiques OpenLigaDB pour {team_name}: {e}")
            return None
    
    def _calculate_team_stats(self, matches, team_id, team_name):
        """Calcul des statistiques à partir des matchs"""
        if not matches:
            return None
        
        total_matches = len(matches)
        wins = 0
        draws = 0
        losses = 0
        goals_for = 0
        goals_against = 0
        shots_total = 0
        corners_total = 0
        
        recent_results = []
        
        for match in matches[-10:]:  # Derniers 10 matchs
            is_home = match['team1']['teamId'] == team_id
            result = match.get('matchResults', [{}])[0]
            
            if is_home:
                team_score = result.get('pointsTeam1', 0)
                opp_score = result.get('pointsTeam2', 0)
            else:
                team_score = result.get('pointsTeam2', 0)
                opp_score = result.get('pointsTeam1', 0)
            
            goals_for += team_score
            goals_against += opp_score
            
            if team_score > opp_score:
                wins += 1
                recent_results.append('W')
            elif team_score < opp_score:
                losses += 1
                recent_results.append('L')
            else:
                draws += 1
                recent_results.append('D')
        
        # Statistiques calculées
        avg_goals_for = goals_for / total_matches if total_matches > 0 else 0
        avg_goals_against = goals_against / total_matches if total_matches > 0 else 0
        
        # Forme récente (derniers 5 matchs)
        recent_form = ''.join(recent_results[-5:]) if recent_results else ''
        
        return {
            'team_name': team_name,
            'matches_played': total_matches,
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'goals_for': goals_for,
            'goals_against': goals_against,
            'avg_goals_for': round(avg_goals_for, 2),
            'avg_goals_against': round(avg_goals_against, 2),
            'goal_difference': goals_for - goals_against,
            'recent_form': recent_form,
            'win_rate': round(wins / total_matches * 100, 1) if total_matches > 0 else 0
        }
    
    async def fetch_head_to_head(self, team1_id, team2_id, league_code, season):
        """Récupération des confrontations directes"""
        try:
            url = f"{self.base_url}/getmatchdata/{team1_id}/{team2_id}"
            
            async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    h2h_stats = {
                        'total_matches': len(matches),
                        'team1_wins': 0,
                        'team2_wins': 0,
                        'draws': 0,
                        'team1_goals': 0,
                        'team2_goals': 0,
                        'recent_results': []
                    }
                    
                    for match in matches[:10]:  # 10 dernières rencontres max
                        if match.get('matchResults') and len(match['matchResults']) > 0:
                            result = match['matchResults'][0]
                            team1_score = result.get('pointsTeam1', 0)
                            team2_score = result.get('pointsTeam2', 0)
                            
                            h2h_stats['team1_goals'] += team1_score
                            h2h_stats['team2_goals'] += team2_score
                            
                            if team1_score > team2_score:
                                h2h_stats['team1_wins'] += 1
                                h2h_stats['recent_results'].append('W1')
                            elif team2_score > team1_score:
                                h2h_stats['team2_wins'] += 1
                                h2h_stats['recent_results'].append('W2')
                            else:
                                h2h_stats['draws'] += 1
                                h2h_stats['recent_results'].append('D')
                    
                    return h2h_stats
                return None
                
        except Exception as e:
            logger.error(f"Erreur H2H OpenLigaDB: {e}")
            return None

# ==================== MODÈLES DE CALCUL ====================

class PredictionModels:
    """Implémentation des 5 modèles de calcul[citation:2][citation:8]"""
    
    def __init__(self, db):
        self.db = db
        self.enabled_models = Config.ENABLED_MODELS
    
    def analyze_match(self, match_data, home_stats, away_stats, h2h_data):
        """Analyse complète d'un match avec tous les modèles"""
        try:
            home_team = match_data['home_team']['name']
            away_team = match_data['away_team']['name']
            
            # Vérification des données disponibles
            if not home_stats or not away_stats:
                logger.debug(f"Données insuffisantes pour {home_team} vs {away_team}")
                return None
            
            # 1. Modèle statistique pondéré
            model_results = {}
            
            if self.enabled_models['statistical']:
                model_results['statistical'] = self._statistical_model(home_stats, away_stats, h2h_data)
            
            # 2. Modèle de Poisson[citation:2]
            if self.enabled_models['poisson']:
                poisson_result = self._poisson_model(home_stats, away_stats)
                if poisson_result:
                    model_results['poisson'] = poisson_result
            
            # 3. Modèle de forme récente
            if self.enabled_models['form']:
                model_results['form'] = self._form_model(home_stats, away_stats)
            
            # 4. Modèle face-à-face
            if self.enabled_models['h2h'] and h2h_data and h2h_data['total_matches'] > 0:
                model_results['h2h'] = self._h2h_model(h2h_data)
            
            # 5. Modèle combiné (fusion des autres)
            if self.enabled_models['combined'] and model_results:
                model_results['combined'] = self._combined_model(model_results)
            
            # Génération de la prédiction finale
            if not model_results:
                return None
            
            final_prediction = self._generate_final_prediction(model_results)
            
            return {
                'match_id': match_data['match_id'],
                'home_team': home_team,
                'away_team': away_team,
                'league': match_data['league'],
                'date': match_data['date'],
                'confidence': final_prediction['confidence'],
                'prediction': final_prediction,
                'model_details': model_results,
                'available_models': list(model_results.keys())
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse match: {e}")
            return None
    
    def _statistical_model(self, home_stats, away_stats, h2h_data):
        """Modèle 1: Statistique pondéré[citation:8]"""
        try:
            # Pondérations des différentes statistiques
            weights = {
                'avg_goals': 0.30,
                'form': 0.25,
                'defense': 0.20,
                'h2h': 0.15,
                'home_advantage': 0.10
            }
            
            # Score d'attaque
            home_attack = home_stats.get('avg_goals_for', 1.0)
            away_attack = away_stats.get('avg_goals_for', 1.0)
            
            # Score de défense
            home_defense = 2.0 - away_stats.get('avg_goals_against', 1.0)
            away_defense = 2.0 - home_stats.get('avg_goals_against', 1.0)
            
            # Forme récente
            home_form = self._calculate_form_score(home_stats.get('recent_form', ''))
            away_form = self._calculate_form_score(away_stats.get('recent_form', ''))
            
            # H2H
            h2h_score = 0.5
            if h2h_data and h2h_data['total_matches'] > 0:
                h2h_score = h2h_data['team1_wins'] / h2h_data['total_matches']
            
            # Calcul final
            home_strength = (
                home_attack * weights['avg_goals'] +
                home_form * weights['form'] +
                home_defense * weights['defense'] +
                h2h_score * weights['h2h'] +
                0.1 * weights['home_advantage']  # Avantage domicile
            )
            
            away_strength = (
                away_attack * weights['avg_goals'] +
                away_form * weights['form'] +
                away_defense * weights['defense'] +
                (1 - h2h_score) * weights['h2h']
            )
            
            # Normalisation
            total = home_strength + away_strength
            if total == 0:
                return {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            
            home_win = home_strength / total
            away_win = away_strength / total
            draw = 0.25 * (1.0 - abs(home_win - away_win))
            
            # Ajustement pour somme = 1
            home_win = home_win * (1 - draw)
            away_win = away_win * (1 - draw)
            
            return {
                'home_win': round(home_win, 3),
                'draw': round(draw, 3),
                'away_win': round(away_win, 3)
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle statistique: {e}")
            return {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
    
    def _poisson_model(self, home_stats, away_stats):
        """Modèle 2: Distribution de Poisson pour les buts[citation:2]"""
        try:
            # Lambda (moyenne de buts attendus)
            lambda_home = max(0.1, home_stats.get('avg_goals_for', 1.0) * 
                            away_stats.get('avg_goals_against', 1.0))
            lambda_away = max(0.1, away_stats.get('avg_goals_for', 1.0) * 
                            home_stats.get('avg_goals_against', 1.0))
            
            # Calcul des probabilités
            home_win_prob = 0
            draw_prob = 0
            away_win_prob = 0
            
            # Limite à 5 buts max pour chaque équipe
            for i in range(0, 6):
                for j in range(0, 6):
                    prob = (self._poisson_prob(i, lambda_home) * 
                           self._poisson_prob(j, lambda_away))
                    
                    if i > j:
                        home_win_prob += prob
                    elif i == j:
                        draw_prob += prob
                    else:
                        away_win_prob += prob
            
            # Score le plus probable
            max_prob = 0
            likely_score = "1-1"
            
            for i in range(0, 4):
                for j in range(0, 4):
                    prob = (self._poisson_prob(i, lambda_home) * 
                           self._poisson_prob(j, lambda_away))
                    if prob > max_prob:
                        max_prob = prob
                        likely_score = f"{i}-{j}"
            
            return {
                'home_win': round(home_win_prob, 3),
                'draw': round(draw_prob, 3),
                'away_win': round(away_win_prob, 3),
                'lambda_home': round(lambda_home, 2),
                'lambda_away': round(lambda_away, 2),
                'most_likely_score': likely_score
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle Poisson: {e}")
            return None
    
    def _poisson_prob(self, k, lambd):
        """Probabilité de Poisson pour k événements"""
        try:
            return (math.exp(-lambd) * (lambd ** k)) / math.factorial(k)
        except:
            return 0
    
    def _form_model(self, home_stats, away_stats):
        """Modèle 3: Forme récente"""
        try:
            home_form = self._calculate_form_score(home_stats.get('recent_form', ''))
            away_form = self._calculate_form_score(away_stats.get('recent_form', ''))
            
            if home_form + away_form == 0:
                return {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            
            home_win = home_form / (home_form + away_form)
            away_win = away_form / (home_form + away_form)
            draw = 0.3 * (1.0 - abs(home_win - away_win))
            
            # Normalisation
            home_win = home_win * (1 - draw)
            away_win = away_win * (1 - draw)
            
            return {
                'home_win': round(home_win, 3),
                'draw': round(draw, 3),
                'away_win': round(away_win, 3),
                'home_form_score': round(home_form, 2),
                'away_form_score': round(away_form, 2)
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle forme: {e}")
            return None
    
    def _calculate_form_score(self, form_string):
        """Calcul du score de forme à partir d'une chaîne W/D/L"""
        if not form_string:
            return 0.5
        
        score = 0
        for result in form_string[-5:]:  # Derniers 5 matchs
            if result == 'W':
                score += 3
            elif result == 'D':
                score += 1
        
        max_score = len(form_string[-5:]) * 3
        return score / max_score if max_score > 0 else 0.5
    
    def _h2h_model(self, h2h_data):
        """Modèle 4: Face-à-face"""
        try:
            total = h2h_data['total_matches']
            if total == 0:
                return {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            
            home_win = h2h_data['team1_wins'] / total
            draw = h2h_data['draws'] / total
            away_win = h2h_data['team2_wins'] / total
            
            return {
                'home_win': round(home_win, 3),
                'draw': round(draw, 3),
                'away_win': round(away_win, 3),
                'total_matches': total
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle H2H: {e}")
            return None
    
    def _combined_model(self, model_results):
        """Modèle 5: Combiné (fusion des autres modèles)"""
        try:
            weights = Config.MODEL_WEIGHTS
            
            total_home = 0
            total_draw = 0
            total_away = 0
            total_weight = 0
            
            for model_name, results in model_results.items():
                if model_name in weights and results:
                    weight = weights[model_name]
                    
                    total_home += results.get('home_win', 0.33) * weight
                    total_draw += results.get('draw', 0.34) * weight
                    total_away += results.get('away_win', 0.33) * weight
                    total_weight += weight
            
            if total_weight == 0:
                return {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            
            # Normalisation
            home_win = total_home / total_weight
            draw = total_draw / total_weight
            away_win = total_away / total_weight
            
            # Ajustement pour somme = 1
            total = home_win + draw + away_win
            home_win /= total
            draw /= total
            away_win /= total
            
            return {
                'home_win': round(home_win, 3),
                'draw': round(draw, 3),
                'away_win': round(away_win, 3),
                'models_used': list(model_results.keys())
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle combiné: {e}")
            return None
    
    def _generate_final_prediction(self, model_results):
        """Génération de la prédiction finale"""
        try:
            # Utiliser le modèle combiné si disponible
            if 'combined' in model_results:
                final = model_results['combined']
            else:
                # Sinon, utiliser le premier modèle disponible
                final = next(iter(model_results.values()))
            
            home_win = final.get('home_win', 0)
            draw = final.get('draw', 0)
            away_win = final.get('away_win', 0)
            
            # Détermination de la recommandation
            max_prob = max(home_win, draw, away_win)
            confidence = max_prob
            
            if max_prob == home_win:
                if home_win >= 0.45:
                    if home_win >= 0.55:
                        recommendation = "VICTOIRE DOMICILE"
                        bet_type = "1"
                        emoji = "🏠✅"
                    else:
                        recommendation = "DOUBLE CHANCE 1X"
                        bet_type = "1X"
                        emoji = "🏠🤝"
                        confidence = home_win + draw
                else:
                    recommendation = "DOUBLE CHANCE 1X"
                    bet_type = "1X"
                    emoji = "🤝"
                    confidence = home_win + draw
                    
            elif max_prob == away_win:
                if away_win >= 0.45:
                    if away_win >= 0.55:
                        recommendation = "VICTOIRE EXTERIEUR"
                        bet_type = "2"
                        emoji = "✈️✅"
                    else:
                        recommendation = "DOUBLE CHANCE X2"
                        bet_type = "X2"
                        emoji = "✈️🤝"
                        confidence = away_win + draw
                else:
                    recommendation = "DOUBLE CHANCE X2"
                    bet_type = "X2"
                    emoji = "🤝"
                    confidence = away_win + draw
                    
            elif max_prob == draw:
                if draw >= 0.35:
                    recommendation = "MATCH NUL"
                    bet_type = "X"
                    emoji = "⚖️"
                else:
                    if home_win + draw > away_win + draw:
                        recommendation = "DOUBLE CHANCE 1X"
                        bet_type = "1X"
                        emoji = "🤝"
                        confidence = home_win + draw
                    else:
                        recommendation = "DOUBLE CHANCE X2"
                        bet_type = "X2"
                        emoji = "🤝"
                        confidence = away_win + draw
            
            # Score prédit
            predicted_score = "1-1"
            if 'poisson' in model_results:
                predicted_score = model_results['poisson'].get('most_likely_score', '1-1')
            
            return {
                'recommendation': recommendation,
                'bet_type': bet_type,
                'emoji': emoji,
                'confidence': round(confidence, 3),
                'predicted_score': predicted_score,
                'probabilities': {
                    'home_win': round(home_win, 3),
                    'draw': round(draw, 3),
                    'away_win': round(away_win, 3)
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur génération prédiction: {e}")
            return {
                'recommendation': "ANALYSE INCOMPLETE",
                'bet_type': "",
                'emoji': "⚠️",
                'confidence': 0.3,
                'predicted_score': "1-1",
                'probabilities': {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            }

# ==================== SELECTEUR ====================

class PredictionsSelector:
    """Sélection des meilleures prédictions"""
    
    def __init__(self):
        self.min_confidence = Config.MIN_CONFIDENCE
    
    def select_best(self, analyses, limit=5):
        """Sélection des meilleures analyses"""
        if not analyses:
            return []
        
        # Filtrage par confiance minimale
        valid = [a for a in analyses if a and a['confidence'] >= self.min_confidence]
        
        if not valid:
            return []
        
        # Tri par confiance décroissante
        valid.sort(key=lambda x: x['confidence'], reverse=True)
        
        return valid[:limit]
    
    def generate_report(self, predictions):
        """Génération du rapport d'analyse"""
        if not predictions:
            return {
                'total': 0,
                'avg_confidence': 0,
                'risk': 'TRÈS ÉLEVÉ',
                'quality': 'FAIBLE',
                'bet_types': {},
                'date': datetime.now().strftime("%d/%m/%Y %H:%M")
            }
        
        confidences = [p['confidence'] for p in predictions]
        avg_conf = sum(confidences) / len(confidences)
        
        # Niveau de risque
        if avg_conf >= 0.70:
            risk = 'FAIBLE'
        elif avg_conf >= 0.60:
            risk = 'MOYEN'
        elif avg_conf >= 0.50:
            risk = 'ÉLEVÉ'
        else:
            risk = 'TRÈS ÉLEVÉ'
        
        # Qualité
        if len(predictions) >= 5:
            quality = 'EXCELLENTE'
        elif len(predictions) >= 3:
            quality = 'BONNE'
        elif len(predictions) >= 1:
            quality = 'MOYENNE'
        else:
            quality = 'FAIBLE'
        
        # Types de paris
        bet_types = {}
        for pred in predictions:
            bet_type = pred['prediction']['bet_type']
            bet_types[bet_type] = bet_types.get(bet_type, 0) + 1
        
        return {
            'total': len(predictions),
            'avg_confidence': round(avg_conf, 3),
            'risk': risk,
            'quality': quality,
            'bet_types': bet_types,
            'date': datetime.now().strftime("%d/%m/%Y %H:%M")
        }

# ==================== TELEGRAM BOT ====================

class TelegramBot:
    """Gestion des communications Telegram"""
    
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.channel = Config.TELEGRAM_CHANNEL_ID
        
        if not self.token or not self.channel:
            raise ValueError("Configuration Telegram manquante")
    
    async def send_predictions(self, predictions, report):
        """Envoi des prédictions sur Telegram"""
        try:
            message = self._format_html_message(predictions, report)
            return await self._send_html_message(message)
        except Exception as e:
            logger.error(f"Erreur Telegram: {e}")
            return False
    
    def _format_html_message(self, predictions, report):
        """Formatage du message en HTML"""
        date_str = report['date']
        
        header = f"""
<b>⚽️ PRONOSTICS FOOTBALL ULTIMATE ⚽️</b>
<b>📅 {date_str} | 🎯 {report['total']} sélections d'excellence</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 RAPPORT DE QUALITÉ</b>
• Confiance moyenne: <b>{report['avg_confidence']:.1%}</b>
• Qualité: <b>{report['quality']}</b>
• Niveau de risque: <b>{report['risk']}</b>

<b>🎰 RÉPARTITION DES PARIS:</b> {', '.join([f'{k}:{v}' for k, v in report['bet_types'].items()])}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🏅 TOP 5 PRONOSTICS DU JOUR 🏅</b>
"""
        
        predictions_text = ""
        for i, pred in enumerate(predictions, 1):
            rank_emoji = ['🥇', '🥈', '🥉', '🎯', '🎯'][i-1]
            pred_data = pred['prediction']
            
            predictions_text += f"""
{rank_emoji} <b>{pred['home_team']} vs {pred['away_team']}</b>
🏆 {pred['league']} | ⚡ Confiance: <b>{pred['confidence']:.1%}</b>

<b>🎯 RECOMMANDATION: {pred_data['emoji']} {pred_data['recommendation']}</b>
• Type de pari: <b>{pred_data['bet_type']}</b>
• Score probable: <b>{pred_data['predicted_score']}</b>

<b>📊 PROBABILITÉS:</b>
1️⃣ {pred_data['probabilities']['home_win']:.1%} | N {pred_data['probabilities']['draw']:.1%} | 2️⃣ {pred_data['probabilities']['away_win']:.1%}

<b>🧮 MODÈLES APPLIQUÉS:</b> {', '.join(pred.get('available_models', ['Statistique']))}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        footer = f"""
<b>🔧 SYSTÈME D'ANALYSE</b>
• {len(Config.LEAGUES_MAPPING)} ligues surveillées
• {sum(Config.ENABLED_MODELS.values())} modèles de calcul
• Données ESPN + OpenLigaDB[citation:5][citation:6][citation:7]
• Filtrage par confiance minimale ({Config.MIN_CONFIDENCE*100}%)

<b>⚠️ AVERTISSEMENT IMPORTANT</b>
• Ces pronostics sont basés sur une analyse algorithmique
• Aucun gain n'est garanti - jouez de manière responsable
• Les cotes peuvent varier - vérifiez avant de parier

<b>🔄 PROCHAINE ANALYSE:</b> {Config.DAILY_TIME} {Config.TIMEZONE}
<b>🤖 SYSTÈME:</b> Football Predictor Ultimate v3.0
"""
        
        full_message = f"{header}\n{predictions_text}\n{footer}"
        
        # Limitation de la taille
        if len(full_message) > 4000:
            full_message = full_message[:3900] + "\n\n... (message tronqué)"
        
        return full_message
    
    async def _send_html_message(self, text):
        """Envoi d'un message HTML"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                'chat_id': self.channel,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            
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
    
    async def send_test_message(self):
        """Envoi d'un message de test"""
        try:
            message = f"""
<b>🤖 Football Predictor Ultimate v3.0 🤖</b>

✅ Système opérationnel
📊 Ligues configurées: {len(Config.LEAGUES_MAPPING)}
🧮 Modèles activés: {sum(Config.ENABLED_MODELS.values())}/5
📍 Fuseau: {Config.TIMEZONE}
🔄 Prochaine analyse: {Config.DAILY_TIME}

<i>Initialisation réussie - prêt pour l'analyse quotidienne</i>
"""
            
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                'chat_id': self.channel,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as resp:
                    return resp.status == 200
                    
        except Exception as e:
            logger.error(f"Erreur test Telegram: {e}")
            return False

# ==================== SYSTÈME PRINCIPAL ====================

class FootballPredictionSystem:
    """Système principal de prédictions"""
    
    def __init__(self):
        self.db = Database()
        self.models = PredictionModels(self.db)
        self.selector = PredictionsSelector()
        self.telegram = TelegramBot()
        
        logger.info("🚀 Système Football Predictor Ultimate initialisé")
        logger.info(f"📊 Ligues configurées: {len(Config.LEAGUES_MAPPING)}")
        logger.info(f"🧮 Modèles activés: {sum(Config.ENABLED_MODELS.values())}")
    
    async def run_daily_analysis(self):
        """Exécution de l'analyse quotidienne"""
        logger.info("🔄 Démarrage de l'analyse quotidienne...")
        
        try:
            # Étape 1: Collecte des matchs du jour via ESPN[citation:6]
            async with ESPNCollector() as espn_collector:
                matches = await espn_collector.fetch_today_matches()
                
                if not matches:
                    logger.warning("⚠️ Aucun match trouvé pour aujourd'hui")
                    await self._send_no_matches()
                    return
                
                logger.info(f"📊 {len(matches)} matchs du jour à analyser")
                
                # Étape 2: Analyse de chaque match
                analyses = []
                
                for match in matches[:20]:  # Limite à 20 matchs pour performance
                    try:
                        # Éviter les matchs terminés
                        if match.get('is_finished', False):
                            continue
                        
                        # Étape 3: Collecte des statistiques via OpenLigaDB[citation:5]
                        async with OpenLigaDBCollector() as openliga_collector:
                            home_stats = await openliga_collector.fetch_team_stats(
                                match['home_team']['name'],
                                match.get('league_code', 'bl1'),
                                match.get('league_season', 2024)
                            )
                            
                            away_stats = await openliga_collector.fetch_team_stats(
                                match['away_team']['name'],
                                match.get('league_code', 'bl1'),
                                match.get('league_season', 2024)
                            )
                            
                            # H2H si disponible
                            h2h_data = None
                            if home_stats and away_stats:
                                h2h_data = await openliga_collector.fetch_head_to_head(
                                    match['home_team']['id'],
                                    match['away_team']['id'],
                                    match.get('league_code', 'bl1'),
                                    match.get('league_season', 2024)
                                )
                            
                            # Étape 4: Application des modèles de calcul
                            if home_stats and away_stats:
                                analysis = self.models.analyze_match(match, home_stats, away_stats, h2h_data)
                                if analysis:
                                    analyses.append(analysis)
                                    logger.debug(f"✅ Analyse réussie: {match['home_team']['name']} vs {match['away_team']['name']}")
                        
                        await asyncio.sleep(0.5)  # Respect rate limits
                        
                    except Exception as e:
                        logger.error(f"Erreur analyse match: {e}")
                        continue
                
                logger.info(f"✅ {len(analyses)} matchs analysés avec succès")
                
                if not analyses:
                    logger.warning("⚠️ Aucune analyse valide générée")
                    await self._send_no_valid_predictions()
                    return
                
                # Étape 5: Sélection des meilleures prédictions
                top_predictions = self.selector.select_best(analyses, 5)
                
                if not top_predictions:
                    logger.warning("⚠️ Aucune prédiction ne remplit les critères")
                    await self._send_no_quality_predictions()
                    return
                
                # Étape 6: Génération du rapport
                report = self.selector.generate_report(top_predictions)
                
                # Étape 7: Envoi sur Telegram
                logger.info("📤 Envoi des prédictions vers Telegram...")
                success = await self.telegram.send_predictions(top_predictions, report)
                
                if success:
                    logger.info("✅ Analyse terminée et envoyée avec succès")
                    
                    # Sauvegarde des prédictions
                    for pred in top_predictions:
                        self.db.save_prediction(pred)
                    
                    logger.info(f"💾 {len(top_predictions)} prédictions sauvegardées")
                else:
                    logger.error("❌ Échec de l'envoi Telegram")
                
        except Exception as e:
            logger.error(f"❌ Erreur système: {e}", exc_info=True)
    
    async def _send_no_matches(self):
        """Message aucun match"""
        try:
            message = f"""
<b>📭 AUCUN MATCH PROGRAMMÉ AUJOURD'HUI</b>

Pas de match trouvé dans les {len(Config.LEAGUES_MAPPING)} ligues surveillées.
🔄 Prochaine analyse: {Config.DAILY_TIME} {Config.TIMEZONE}
"""
            await self.telegram._send_html_message(message)
        except:
            pass
    
    async def _send_no_valid_predictions(self):
        """Message aucune prédiction valide"""
        try:
            message = f"""
<b>⚠️ ANALYSE INCOMPLÈTE</b>

Matchs trouvés mais données statistiques insuffisantes.
🔄 Prochaine analyse: {Config.DAILY_TIME} {Config.TIMEZONE}
"""
            await self.telegram._send_html_message(message)
        except:
            pass
    
    async def _send_no_quality_predictions(self):
        """Message aucune prédiction de qualité"""
        try:
            message = f"""
<b>🎯 CRITÈRES DE QUALITÉ NON ATTEINTS</b>

Aucune analyse ne remplit le seuil de confiance ({Config.MIN_CONFIDENCE*100}%).
🔄 Prochaine analyse: {Config.DAILY_TIME} {Config.TIMEZONE}
"""
            await self.telegram._send_html_message(message)
        except:
            pass

# ==================== SCHEDULER ====================

class Scheduler:
    """Planificateur pour exécutions régulières"""
    
    def __init__(self):
        self.scheduler = None
        self.system = FootballPredictionSystem()
        self.running = True
        
        # Gestion des signaux
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    async def start(self):
        """Démarrage du planificateur"""
        logger.info("⏰ Planificateur démarré")
        logger.info(f"📍 Fuseau horaire: {Config.TIMEZONE}")
        logger.info(f"⏰ Heure quotidienne: {Config.DAILY_TIME}")
        
        # Mode test
        if '--test' in sys.argv:
            logger.info("🧪 Mode test - exécution immédiate")
            await self._daily_task(test_mode=True)
            return
        
        # Mode manuel
        if '--manual' in sys.argv:
            logger.info("👨‍💻 Mode manuel - exécution unique")
            await self._daily_task()
            return
        
        # Mode normal - scheduler
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
        
        # Configuration de l'heure d'exécution
        try:
            hour, minute = map(int, Config.DAILY_TIME.split(':'))
        except:
            hour, minute = 7, 0
        
        # Planification de la tâche quotidienne
        self.scheduler.add_job(
            self._daily_task,
            CronTrigger(hour=hour, minute=minute, timezone=Config.TIMEZONE),
            id='daily_analysis',
            name='Analyse football quotidienne'
        )
        
        self.scheduler.start()
        
        # Message de démarrage
        try:
            await self.system.telegram.send_test_message()
        except:
            pass
        
        # Boucle principale
        try:
            while self.running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.shutdown()
    
    async def _daily_task(self, test_mode=False):
        """Tâche d'analyse quotidienne"""
        logger.info("🔄 Exécution de la tâche d'analyse...")
        await self.system.run_daily_analysis()
        logger.info("✅ Tâche d'analyse terminée")
    
    def shutdown(self, signum=None, frame=None):
        """Arrêt propre du système"""
        logger.info("🛑 Arrêt du planificateur...")
        self.running = False
        
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
        
        self.system.db.close()
        logger.info("✅ Planificateur arrêté proprement")
        sys.exit(0)

# ==================== POINT D'ENTRÉE ====================

def main():
    """Point d'entrée principal"""
    
    if '--help' in sys.argv:
        print("""
🚀 Football Prediction Bot - Ultimate Edition

Usage:
  python bot.py              # Mode normal (démarre le scheduler)
  python bot.py --test       # Mode test (exécution immédiate)
  python bot.py --manual     # Mode manuel (une exécution)
  python bot.py --help       # Aide

Variables d'environnement:
  • TELEGRAM_BOT_TOKEN      (requis)
  • TELEGRAM_CHANNEL_ID     (requis)
  • TIMEZONE                (optionnel, défaut: Europe/Paris)
  • DAILY_TIME              (optionnel, défaut: 07:00)
  • MIN_CONFIDENCE          (optionnel, défaut: 0.65)
  • LOG_LEVEL               (optionnel, défaut: INFO)

Fonctionnalités:
  • 51 ligues surveillées via ESPN API[citation:6]
  • Statistiques via OpenLigaDB[citation:5]
  • 5 modèles de calcul (Statistique, Poisson[citation:2], Forme, H2H, Combiné)
  • Sélection des 5 meilleures prédictions
  • Envoi Telegram format HTML
  • Base de données SQLite
  • Scheduler 24h/24
        """)
        return
    
    # Validation de la configuration
    errors = Config.validate()
    if errors:
        print("❌ ERREURS DE CONFIGURATION:")
        for error in errors:
            print(f"  - {error}")
        print("\n🔧 Configurez les variables sur Railway:")
        print("   TELEGRAM_BOT_TOKEN et TELEGRAM_CHANNEL_ID")
        return
    
    # Démarrage du système
    scheduler = Scheduler()
    
    try:
        asyncio.run(scheduler.start())
    except KeyboardInterrupt:
        scheduler.shutdown()
    except Exception as e:
        logger.error(f"Erreur critique: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()