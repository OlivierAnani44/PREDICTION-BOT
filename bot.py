#!/usr/bin/env python3
"""
FOOTBALL PREDICTION BOT - OpenLigaDB Edition
Utilise l'API OpenLigaDB et 10 modèles de calcul
"""

import os
import sys
import json
import sqlite3
import logging
import asyncio
import statistics
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ==================== CONFIGURATION ====================

class Config:
    """Configuration du bot"""
    
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
    TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris")
    DAILY_TIME = os.getenv("DAILY_TIME", "07:00")
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.65"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
    
    # Configuration OpenLigaDB
    OPENLIGADB_BASE = "https://api.openligadb.de"
    
    # Mapping des ligues avec codes OpenLigaDB
    LEAGUES_MAPPING = {
        # Allemagne
        "Bundesliga": {"code": "bl1", "season": 2025},
        "Bundesliga 2": {"code": "bl2", "season": 2025},
        "Coupe d'Allemagne": {"code": "dfbpokal", "season": 2025},
        
        # Angleterre  
        "Premier League": {"code": "pl", "season": 2025},
        "Championship": {"code": "elc", "season": 2025},
        "FA Cup": {"code": "facup", "season": 2025},
        
        # Espagne
        "Liga": {"code": "primera", "season": 2025},
        "Segunda Division": {"code": "segunda", "season": 2025},
        "Copa del Rey": {"code": "copadelrey", "season": 2025},
        
        # France
        "Ligue 1": {"code": "ligue1", "season": 2025},
        "Ligue 2": {"code": "ligue2", "season": 2025},
        "Coupe de France": {"code": "coupedefrance", "season": 2025},
        
        # Italie
        "Serie A": {"code": "seriea", "season": 2025},
        "Serie B": {"code": "serieb", "season": 2025},
        "Coupe d'Italie": {"code": "coppaitalia", "season": 2025},
        
        # Europe
        "Ligue des champions": {"code": "cl", "season": 2025},
        "Ligue Europa": {"code": "el", "season": 2025},
        "Europa Conference League": {"code": "ecl", "season": 2025},
        
        # Portugal
        "Liga": {"code": "liga", "season": 2025},
        
        # Pays-Bas
        "Eredivisie": {"code": "eredivisie", "season": 2025},
        
        # Autres
        "Saudi Pro League": {"code": "spl", "season": 2025},
        "Major League Soccer": {"code": "mls", "season": 2025},
    }
    
    # Modèles activés par défaut (seront ajustés selon données disponibles)
    ENABLED_MODELS = {
        "statistical": True,
        "poisson": True,
        "form": True,
        "h2h": True,
        "elo": False,  # Nécessite données historiques
        "corners": False,  # Données limitées dans OpenLigaDB
        "cards": False,
        "shots": False,
        "xG": False,
        "combined": True
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
    """Base de données pour stocker prédictions et données historiques"""
    
    def __init__(self):
        self.conn = sqlite3.connect('football_predictions.db', check_same_thread=False)
        self.init_db()
    
    def init_db(self):
        """Initialise les tables"""
        cursor = self.conn.cursor()
        
        # Table des prédictions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER UNIQUE,
                league TEXT,
                home_team TEXT,
                away_team TEXT,
                match_date TEXT,
                confidence REAL,
                predicted_score TEXT,
                bet_type TEXT,
                prediction_details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table des données historiques des équipes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_stats (
                team_id INTEGER,
                team_name TEXT,
                league TEXT,
                season INTEGER,
                matches_played INTEGER,
                wins INTEGER,
                draws INTEGER,
                losses INTEGER,
                goals_for INTEGER,
                goals_against INTEGER,
                avg_goals_for REAL,
                avg_goals_against REAL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_id, league, season)
            )
        ''')
        
        # Table des matchs historiques
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS match_history (
                match_id INTEGER PRIMARY KEY,
                league TEXT,
                season INTEGER,
                match_date TEXT,
                home_team_id INTEGER,
                home_team_name TEXT,
                away_team_id INTEGER,
                away_team_name TEXT,
                home_score INTEGER,
                away_score INTEGER,
                result TEXT,
                goals TEXT,
                location TEXT,
                spectators INTEGER
            )
        ''')
        
        self.conn.commit()
    
    def save_prediction(self, pred):
        """Sauvegarde une prédiction"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO predictions 
                (match_id, league, home_team, away_team, match_date, 
                 confidence, predicted_score, bet_type, prediction_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                pred.get('match_id'),
                pred.get('league'),
                pred.get('home_team'),
                pred.get('away_team'),
                pred.get('match_date'),
                pred.get('confidence', 0),
                pred.get('predicted_score', ''),
                pred.get('bet_type', ''),
                json.dumps(pred.get('details', {}))
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde prédiction: {e}")
            return False
    
    def get_team_history(self, team_id, league, limit=10):
        """Récupère l'historique d'une équipe"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM match_history 
                WHERE (home_team_id = ? OR away_team_id = ?) 
                AND league = ?
                ORDER BY match_date DESC 
                LIMIT ?
            ''', (team_id, team_id, league, limit))
            
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            history = []
            for row in rows:
                match = dict(zip(columns, row))
                
                # Déterminer le résultat pour cette équipe
                if match['home_team_id'] == team_id:
                    team_score = match['home_score']
                    opp_score = match['away_score']
                    is_home = True
                else:
                    team_score = match['away_score']
                    opp_score = match['home_score']
                    is_home = False
                
                # Déterminer le résultat
                if team_score > opp_score:
                    result = 'WIN'
                elif team_score < opp_score:
                    result = 'LOSS'
                else:
                    result = 'DRAW'
                
                history.append({
                    'date': match['match_date'],
                    'team_score': team_score,
                    'opponent_score': opp_score,
                    'result': result,
                    'is_home': is_home,
                    'opponent': match['away_team_name'] if is_home else match['home_team_name']
                })
            
            return history
        except Exception as e:
            logger.error(f"Erreur récupération historique: {e}")
            return []
    
    def save_match_data(self, match_data):
        """Sauvegarde les données d'un match"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO match_history 
                (match_id, league, season, match_date, home_team_id, home_team_name,
                 away_team_id, away_team_name, home_score, away_score, result, goals, location, spectators)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                match_data['matchID'],
                match_data.get('leagueShortcut', ''),
                match_data.get('leagueSeason', 0),
                match_data.get('matchDateTime', ''),
                match_data['team1']['teamId'],
                match_data['team1']['teamName'],
                match_data['team2']['teamId'],
                match_data['team2']['teamName'],
                match_data.get('matchResults', [{}])[0].get('pointsTeam1', 0) if match_data.get('matchResults') else 0,
                match_data.get('matchResults', [{}])[0].get('pointsTeam2', 0) if match_data.get('matchResults') else 0,
                'DRAW',  # À calculer
                json.dumps(match_data.get('goals', [])),
                json.dumps(match_data.get('location', {})),
                match_data.get('numberOfViewers', 0)
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde match: {e}")
            return False
    
    def close(self):
        self.conn.close()

# ==================== OPENLIGADB COLLECTOR ====================

class OpenLigaDBCollector:
    """Collecteur de données OpenLigaDB"""
    
    def __init__(self):
        self.session = None
        self.base_url = Config.OPENLIGADB_BASE
        self.headers = {
            'User-Agent': 'FootballPredictionBot/1.0',
            'Accept': 'application/json'
        }
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_today_matches(self):
        """Récupère les matchs du jour pour toutes les ligues"""
        logger.info("📡 Collecte des matchs du jour...")
        
        today = datetime.now().strftime("%Y-%m-%d")
        all_matches = []
        
        for league_name, league_info in Config.LEAGUES_MAPPING.items():
            try:
                league_code = league_info["code"]
                season = league_info["season"]
                
                # Essayer de récupérer le groupe/playday actuel
                current_group = await self._get_current_group(league_code)
                if not current_group:
                    logger.debug(f"⚠️ Pas de groupe actuel pour {league_name}")
                    continue
                
                # Récupérer les matchs du groupe actuel
                url = f"{self.base_url}/getmatchdata/{league_code}/{season}/{current_group}"
                
                async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                    if response.status == 200:
                        matches = await response.json()
                        
                        # Filtrer les matchs d'aujourd'hui
                        for match in matches:
                            match_date = match.get('matchDateTime', '')
                            if today in match_date:
                                match_data = {
                                    'match_id': match['matchID'],
                                    'league': league_name,
                                    'league_code': league_code,
                                    'date': match_date,
                                    'home_team': {
                                        'id': match['team1']['teamId'],
                                        'name': match['team1']['teamName'],
                                        'short': match['team1']['shortName']
                                    },
                                    'away_team': {
                                        'id': match['team2']['teamId'],
                                        'name': match['team2']['teamName'],
                                        'short': match['team2']['shortName']
                                    },
                                    'is_finished': match.get('matchIsFinished', False),
                                    'raw_data': match
                                }
                                
                                all_matches.append(match_data)
                                logger.debug(f"✅ Match trouvé: {match['team1']['teamName']} vs {match['team2']['teamName']}")
                    
                    else:
                        logger.warning(f"⚠️ {league_name}: HTTP {response.status}")
                
                await asyncio.sleep(0.3)  # Respect rate limit
                
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Timeout pour {league_name}")
                continue
            except Exception as e:
                logger.error(f"❌ Erreur {league_name}: {str(e)[:100]}")
                continue
        
        logger.info(f"📊 Total matchs du jour: {len(all_matches)}")
        return all_matches
    
    async def _get_current_group(self, league_code):
        """Récupère le groupe/playday actuel"""
        try:
            url = f"{self.base_url}/getcurrentgroup/{league_code}"
            async with self.session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('groupOrderID', 1)
        except:
            return 1  # Fallback au premier groupe
    
    async def fetch_team_history(self, team_id, team_name, league_code, season, limit=8):
        """Récupère l'historique récent d'une équipe"""
        try:
            # Utiliser l'endpoint getmatchesbyteamid
            url = f"{self.base_url}/getmatchesbyteamid/{team_id}/4/0"  # 4 semaines passées, 0 futures
            
            async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                if response.status == 200:
                    matches = await response.json()
                    
                    history = []
                    for match in matches[:limit]:  # Limiter aux derniers matchs
                        # Déterminer si c'est l'équipe à domicile ou à l'extérieur
                        is_home = match['team1']['teamId'] == team_id
                        
                        if is_home:
                            team_score = match.get('matchResults', [{}])[0].get('pointsTeam1', 0)
                            opp_score = match.get('matchResults', [{}])[0].get('pointsTeam2', 0)
                        else:
                            team_score = match.get('matchResults', [{}])[0].get('pointsTeam2', 0)
                            opp_score = match.get('matchResults', [{}])[0].get('pointsTeam1', 0)
                        
                        # Déterminer le résultat
                        if team_score > opp_score:
                            result = 'WIN'
                        elif team_score < opp_score:
                            result = 'LOSS'
                        else:
                            result = 'DRAW'
                        
                        history.append({
                            'date': match.get('matchDateTime', ''),
                            'team_score': team_score,
                            'opponent_score': opp_score,
                            'result': result,
                            'is_home': is_home,
                            'opponent': match['team2']['teamName'] if is_home else match['team1']['teamName']
                        })
                    
                    return history
                else:
                    logger.warning(f"⚠️ Pas d'historique pour {team_name}")
                    return []
                    
        except Exception as e:
            logger.error(f"Erreur historique {team_name}: {e}")
            return []
    
    async def fetch_head_to_head(self, team1_id, team2_id):
        """Récupère les confrontations directes"""
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
                        'recent_matches': []
                    }
                    
                    for match in matches[:5]:  # 5 dernières rencontres
                        result = match.get('matchResults', [{}])[0]
                        team1_score = result.get('pointsTeam1', 0)
                        team2_score = result.get('pointsTeam2', 0)
                        
                        h2h_stats['team1_goals'] += team1_score
                        h2h_stats['team2_goals'] += team2_score
                        
                        if team1_score > team2_score:
                            h2h_stats['team1_wins'] += 1
                        elif team2_score > team1_score:
                            h2h_stats['team2_wins'] += 1
                        else:
                            h2h_stats['draws'] += 1
                        
                        h2h_stats['recent_matches'].append({
                            'date': match.get('matchDateTime', ''),
                            'score': f"{team1_score}-{team2_score}",
                            'winner': 'team1' if team1_score > team2_score else 'team2' if team2_score > team1_score else 'draw'
                        })
                    
                    return h2h_stats
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"Erreur H2H: {e}")
            return None

# ==================== MODÈLES DE CALCUL ====================

class PredictionModels:
    """Implémentation des 10 modèles de calcul"""
    
    def __init__(self, db):
        self.db = db
        self.enabled_models = Config.ENABLED_MODELS
        
    def analyze_match(self, match_data, home_history, away_history, h2h_data):
        """Analyse un match avec tous les modèles disponibles"""
        try:
            home_team = match_data['home_team']['name']
            away_team = match_data['away_team']['name']
            
            # 1. Vérifier les données disponibles
            available_data = self._check_available_data(home_history, away_history, h2h_data)
            
            # 2. Exécuter les modèles disponibles
            model_results = {}
            
            # Modèle 1: Statistique pondéré
            if self.enabled_models['statistical'] and available_data['goals'] and available_data['form']:
                model_results['statistical'] = self._statistical_model(
                    home_history, away_history, h2h_data
                )
            
            # Modèle 2: Poisson (buts)
            if self.enabled_models['poisson'] and available_data['goals']:
                model_results['poisson'] = self._poisson_model(
                    home_history, away_history
                )
            
            # Modèle 3: Forme récente
            if self.enabled_models['form'] and available_data['form']:
                model_results['form'] = self._form_model(home_history, away_history)
            
            # Modèle 4: Face-à-face
            if self.enabled_models['h2h'] and h2h_data and h2h_data['total_matches'] > 0:
                model_results['h2h'] = self._h2h_model(h2h_data)
            
            # Modèle 10: Combiné (utilise les autres modèles)
            if self.enabled_models['combined'] and model_results:
                model_results['combined'] = self._combined_model(model_results)
            
            # 3. Générer la prédiction finale
            if not model_results:
                logger.warning(f"⚠️ Aucun modèle applicable pour {home_team} vs {away_team}")
                return None
            
            final_prediction = self._generate_final_prediction(model_results, available_data)
            
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
    
    def _check_available_data(self, home_history, away_history, h2h_data):
        """Vérifie quelles données sont disponibles"""
        return {
            'goals': len(home_history) >= 3 and len(away_history) >= 3,
            'form': len(home_history) >= 5 and len(away_history) >= 5,
            'h2h': h2h_data is not None and h2h_data['total_matches'] > 0,
            'shots': False,  # Non disponible dans OpenLigaDB
            'corners': False,  # Non disponible
            'cards': False,  # Non disponible
            'xG': False  # Non disponible
        }
    
    def _statistical_model(self, home_history, away_history, h2h_data):
        """Modèle 1: Statistique pondéré"""
        try:
            # Calculer les moyennes
            home_goals = [m['team_score'] for m in home_history]
            home_conceded = [m['opponent_score'] for m in home_history]
            
            away_goals = [m['team_score'] for m in away_history]
            away_conceded = [m['opponent_score'] for m in away_history]
            
            avg_home_goals = statistics.mean(home_goals) if home_goals else 1.0
            avg_home_conceded = statistics.mean(home_conceded) if home_conceded else 1.0
            avg_away_goals = statistics.mean(away_goals) if away_goals else 1.0
            avg_away_conceded = statistics.mean(away_conceded) if away_conceded else 1.0
            
            # Forme récente (derniers 5 matchs)
            home_recent = home_history[-5:] if len(home_history) >= 5 else home_history
            away_recent = away_history[-5:] if len(away_history) >= 5 else away_history
            
            home_form_score = self._calculate_form_score(home_recent)
            away_form_score = self._calculate_form_score(away_recent)
            
            # H2H (si disponible)
            h2h_score = 0.5  # Par défaut neutre
            if h2h_data and h2h_data['total_matches'] > 0:
                h2h_score = h2h_data['team1_wins'] / h2h_data['total_matches'] if h2h_data['total_matches'] > 0 else 0.5
            
            # Appliquer les pondérations
            home_attack = (avg_home_goals * 0.3 + (2.0 - avg_away_conceded) * 0.2) / 0.5
            away_attack = (avg_away_goals * 0.3 + (2.0 - avg_home_conceded) * 0.2) / 0.5
            
            home_advantage = 0.1  # Avantage domicile fixe
            
            home_strength = home_attack * 0.3 + home_form_score * 0.15 + h2h_score * 0.1 + home_advantage * 0.1
            away_strength = away_attack * 0.3 + away_form_score * 0.15 + (1 - h2h_score) * 0.1
            
            # Normaliser
            total = home_strength + away_strength
            home_win_prob = home_strength / total
            away_win_prob = away_strength / total
            draw_prob = 0.25 * (1.0 - abs(home_win_prob - away_win_prob))
            
            # Ajuster pour somme = 1
            home_win_prob = home_win_prob * (1 - draw_prob)
            away_win_prob = away_win_prob * (1 - draw_prob)
            
            return {
                'home_win': round(home_win_prob, 3),
                'draw': round(draw_prob, 3),
                'away_win': round(away_win_prob, 3),
                'expected_home_goals': round(avg_home_goals, 2),
                'expected_away_goals': round(avg_away_goals, 2)
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle statistique: {e}")
            return {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
    
    def _poisson_model(self, home_history, away_history):
        """Modèle 2: Distribution de Poisson pour les buts"""
        try:
            # Moyennes de buts
            home_goals = [m['team_score'] for m in home_history if m['is_home']]
            home_conceded = [m['opponent_score'] for m in home_history if m['is_home']]
            
            away_goals = [m['team_score'] for m in away_history if not m['is_home']]
            away_conceded = [m['opponent_score'] for m in away_history if not m['is_home']]
            
            if not home_goals or not away_goals:
                return None
            
            lambda_home = statistics.mean(home_goals) * statistics.mean(away_conceded)
            lambda_away = statistics.mean(away_goals) * statistics.mean(home_conceded)
            
            # Calculer les probabilités de score exact
            score_probs = {}
            max_goals = 4
            
            for i in range(max_goals + 1):
                for j in range(max_goals + 1):
                    prob = self._poisson_prob(i, lambda_home) * self._poisson_prob(j, lambda_away)
                    score_probs[f"{i}-{j}"] = round(prob, 4)
            
            # Probabilités 1X2
            home_win_prob = 0
            draw_prob = 0
            away_win_prob = 0
            
            for score, prob in score_probs.items():
                home, away = map(int, score.split('-'))
                if home > away:
                    home_win_prob += prob
                elif home == away:
                    draw_prob += prob
                else:
                    away_win_prob += prob
            
            # Over/Under
            over_25_prob = 0
            under_25_prob = 0
            
            for score, prob in score_probs.items():
                home, away = map(int, score.split('-'))
                if home + away > 2.5:
                    over_25_prob += prob
                else:
                    under_25_prob += prob
            
            # BTTS
            btts_prob = 0
            for score, prob in score_probs.items():
                home, away = map(int, score.split('-'))
                if home > 0 and away > 0:
                    btts_prob += prob
            
            return {
                'home_win': round(home_win_prob, 3),
                'draw': round(draw_prob, 3),
                'away_win': round(away_win_prob, 3),
                'over_25': round(over_25_prob, 3),
                'under_25': round(under_25_prob, 3),
                'btts': round(btts_prob, 3),
                'lambda_home': round(lambda_home, 2),
                'lambda_away': round(lambda_away, 2),
                'most_likely_score': max(score_probs, key=score_probs.get)
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle Poisson: {e}")
            return None
    
    def _poisson_prob(self, k, lambd):
        """Probabilité de Poisson"""
        return (math.exp(-lambd) * (lambd ** k)) / math.factorial(k)
    
    def _form_model(self, home_history, away_history):
        """Modèle 3: Forme récente"""
        try:
            # Derniers 8 matchs
            home_recent = home_history[-8:] if len(home_history) >= 8 else home_history
            away_recent = away_history[-8:] if len(away_history) >= 8 else away_history
            
            if not home_recent or not away_recent:
                return None
            
            home_form = self._calculate_form_score(home_recent)
            away_form = self._calculate_form_score(away_recent)
            
            # Consistance (écart-type bas = bonne consistance)
            home_results = [1 if m['result'] == 'WIN' else 0.5 if m['result'] == 'DRAW' else 0 for m in home_recent]
            away_results = [1 if m['result'] == 'WIN' else 0.5 if m['result'] == 'DRAW' else 0 for m in away_recent]
            
            home_consistency = 1.0 - (statistics.stdev(home_results) if len(home_results) > 1 else 0.5)
            away_consistency = 1.0 - (statistics.stdev(away_results) if len(away_results) > 1 else 0.5)
            
            # Force de forme pondérée
            home_strength = home_form * home_consistency
            away_strength = away_form * away_consistency
            
            total = home_strength + away_strength
            if total == 0:
                return {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            
            home_win_prob = home_strength / total
            away_win_prob = away_strength / total
            draw_prob = 0.3 * (1.0 - abs(home_win_prob - away_win_prob))
            
            # Normaliser
            home_win_prob *= (1 - draw_prob)
            away_win_prob *= (1 - draw_prob)
            
            return {
                'home_win': round(home_win_prob, 3),
                'draw': round(draw_prob, 3),
                'away_win': round(away_win_prob, 3),
                'home_form': round(home_form, 3),
                'away_form': round(away_form, 3),
                'home_consistency': round(home_consistency, 3),
                'away_consistency': round(away_consistency, 3)
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle forme: {e}")
            return None
    
    def _calculate_form_score(self, matches):
        """Calcule le score de forme (0-1)"""
        if not matches:
            return 0.5
        
        total_points = 0
        for match in matches:
            if match['result'] == 'WIN':
                total_points += 3
            elif match['result'] == 'DRAW':
                total_points += 1
        
        max_points = len(matches) * 3
        return total_points / max_points if max_points > 0 else 0.5
    
    def _h2h_model(self, h2h_data):
        """Modèle 4: Face-à-face"""
        try:
            total = h2h_data['total_matches']
            if total == 0:
                return {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            
            home_win_prob = h2h_data['team1_wins'] / total
            draw_prob = h2h_data['draws'] / total
            away_win_prob = h2h_data['team2_wins'] / total
            
            # Poids selon le nombre de matchs
            weight = min(total / 5.0, 1.0)  # Maximum poids 1.0 si 5+ matchs
            
            return {
                'home_win': round(home_win_prob, 3),
                'draw': round(draw_prob, 3),
                'away_win': round(away_win_prob, 3),
                'weight': round(weight, 2),
                'total_matches': total,
                'avg_home_goals': round(h2h_data['team1_goals'] / total, 2) if total > 0 else 0,
                'avg_away_goals': round(h2h_data['team2_goals'] / total, 2) if total > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle H2H: {e}")
            return None
    
    def _combined_model(self, model_results):
        """Modèle 10: Combiné (fusionne les autres modèles)"""
        try:
            weights = {
                'statistical': 0.35,
                'poisson': 0.25,
                'form': 0.20,
                'h2h': 0.10,
                'elo': 0.10
            }
            
            total_home = 0
            total_draw = 0
            total_away = 0
            total_weight = 0
            
            for model_name, results in model_results.items():
                if model_name in weights and results:
                    weight = weights.get(model_name, 0.10)
                    
                    total_home += results.get('home_win', 0.33) * weight
                    total_draw += results.get('draw', 0.34) * weight
                    total_away += results.get('away_win', 0.33) * weight
                    total_weight += weight
            
            if total_weight == 0:
                return {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            
            # Normaliser
            home_win_prob = total_home / total_weight
            draw_prob = total_draw / total_weight
            away_win_prob = total_away / total_weight
            
            # Ajuster pour somme = 1
            total = home_win_prob + draw_prob + away_win_prob
            home_win_prob /= total
            draw_prob /= total
            away_win_prob /= total
            
            return {
                'home_win': round(home_win_prob, 3),
                'draw': round(draw_prob, 3),
                'away_win': round(away_win_prob, 3),
                'models_used': list(model_results.keys()),
                'confidence': round(min(home_win_prob, draw_prob, away_win_prob) * 3, 3)  # Score de confiance
            }
            
        except Exception as e:
            logger.error(f"Erreur modèle combiné: {e}")
            return None
    
    def _generate_final_prediction(self, model_results, available_data):
        """Génère la prédiction finale"""
        try:
            # Utiliser le modèle combiné si disponible, sinon le meilleur modèle
            if 'combined' in model_results:
                final = model_results['combined']
            else:
                # Prendre le modèle avec la plus haute confiance
                best_model = None
                best_confidence = 0
                
                for model_name, results in model_results.items():
                    if results:
                        confidence = max(results.get('home_win', 0), 
                                       results.get('draw', 0), 
                                       results.get('away_win', 0))
                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_model = results
                
                final = best_model if best_model else {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            
            # Déterminer la recommandation
            home_win = final.get('home_win', 0)
            draw = final.get('draw', 0)
            away_win = final.get('away_win', 0)
            
            max_prob = max(home_win, draw, away_win)
            
            if max_prob == home_win and home_win >= 0.45:
                if home_win >= 0.55:
                    recommendation = "VICTOIRE DOMICILE"
                    bet_type = "1"
                    emoji = "🏠✅"
                    confidence_score = home_win
                else:
                    recommendation = "DOUBLE CHANCE 1X"
                    bet_type = "1X"
                    emoji = "🏠🤝"
                    confidence_score = home_win + draw
                    
            elif max_prob == away_win and away_win >= 0.45:
                if away_win >= 0.55:
                    recommendation = "VICTOIRE EXTERIEUR"
                    bet_type = "2"
                    emoji = "✈️✅"
                    confidence_score = away_win
                else:
                    recommendation = "DOUBLE CHANCE X2"
                    bet_type = "X2"
                    emoji = "✈️🤝"
                    confidence_score = away_win + draw
                    
            elif draw >= 0.35:
                recommendation = "MATCH NUL"
                bet_type = "X"
                emoji = "⚖️"
                confidence_score = draw
            else:
                # Par défaut: double chance la plus probable
                if home_win + draw > away_win + draw:
                    recommendation = "DOUBLE CHANCE 1X"
                    bet_type = "1X"
                    emoji = "🤝"
                    confidence_score = home_win + draw
                else:
                    recommendation = "DOUBLE CHANCE X2"
                    bet_type = "X2"
                    emoji = "🤝"
                    confidence_score = away_win + draw
            
            # Score prédit (basé sur Poisson si disponible)
            predicted_score = "1-1"  # Par défaut
            if 'poisson' in model_results and model_results['poisson']:
                predicted_score = model_results['poisson'].get('most_likely_score', '1-1')
            
            # Over/Under
            over_under = "OVER 2.5" if (home_win + away_win > 0.6) else "UNDER 2.5"
            
            # BTTS
            btts = "OUI" if ('poisson' in model_results and 
                           model_results['poisson'].get('btts', 0) > 0.5) else "NON"
            
            return {
                'recommendation': recommendation,
                'bet_type': bet_type,
                'emoji': emoji,
                'confidence': round(confidence_score, 3),
                'predicted_score': predicted_score,
                'over_under': over_under,
                'btts': btts,
                'probabilities': {
                    'home_win': round(home_win, 3),
                    'draw': round(draw, 3),
                    'away_win': round(away_win, 3)
                },
                'available_models': list(model_results.keys())
            }
            
        except Exception as e:
            logger.error(f"Erreur génération prédiction: {e}")
            return {
                'recommendation': "ANALYSE INCOMPLETE",
                'bet_type': "",
                'emoji': "⚠️",
                'confidence': 0.3,
                'predicted_score': "1-1",
                'over_under': "N/A",
                'btts': "N/A",
                'probabilities': {'home_win': 0.33, 'draw': 0.34, 'away_win': 0.33}
            }

# ==================== SELECTEUR DE PRÉDICTIONS ====================

class PredictionsSelector:
    """Sélectionne les 5 meilleures prédictions"""
    
    def __init__(self):
        self.min_confidence = Config.MIN_CONFIDENCE
        self.min_data_quality = 0.5  # Qualité minimale des données
    
    def select_best(self, analyses, limit=5):
        """Sélectionne les meilleures analyses basées sur la confiance et la qualité des données"""
        if not analyses:
            return []
        
        # Filtrer par confiance minimale et qualité
        valid = []
        for analysis in analyses:
            if analysis and analysis['confidence'] >= self.min_confidence:
                # Évaluer la qualité des données
                data_quality = self._evaluate_data_quality(analysis)
                if data_quality >= self.min_data_quality:
                    analysis['data_quality'] = data_quality
                    valid.append(analysis)
        
        if not valid:
            return []
        
        # Trier par confiance * qualité des données
        valid.sort(key=lambda x: x['confidence'] * x['data_quality'], reverse=True)
        
        return valid[:limit]
    
    def _evaluate_data_quality(self, analysis):
        """Évalue la qualité des données disponibles"""
        try:
            details = analysis.get('model_details', {})
            available = analysis.get('available_models', [])
            
            score = 0
            max_score = 0
            
            # Points pour chaque modèle disponible
            model_weights = {
                'statistical': 30,
                'poisson': 25,
                'form': 20,
                'h2h': 15,
                'combined': 10
            }
            
            for model in available:
                if model in model_weights:
                    score += model_weights[model]
                    max_score += model_weights[model]
            
            # Bonus pour la profondeur des données historiques
            if 'statistical' in details:
                stats = details['statistical']
                if stats.get('expected_home_goals', 0) > 0 and stats.get('expected_away_goals', 0) > 0:
                    score += 10
                    max_score += 10
            
            return score / max_score if max_score > 0 else 0
            
        except:
            return 0.5
    
    def generate_report(self, predictions):
        """Génère un rapport d'analyse"""
        if not predictions:
            return {
                'total': 0,
                'avg_confidence': 0,
                'avg_data_quality': 0,
                'risk': 'TRÈS ÉLEVÉ',
                'quality': 'FAIBLE',
                'bet_types': {},
                'leagues': {}
            }
        
        confidences = [p['confidence'] for p in predictions]
        qualities = [p.get('data_quality', 0.5) for p in predictions]
        
        avg_conf = sum(confidences) / len(confidences)
        avg_quality = sum(qualities) / len(qualities)
        
        # Niveau de risque
        if avg_conf >= 0.70 and avg_quality >= 0.70:
            risk = 'FAIBLE'
        elif avg_conf >= 0.60 and avg_quality >= 0.60:
            risk = 'MOYEN'
        elif avg_conf >= 0.50:
            risk = 'ÉLEVÉ'
        else:
            risk = 'TRÈS ÉLEVÉ'
        
        # Qualité globale
        overall_quality = (avg_conf + avg_quality) / 2
        if overall_quality >= 0.70:
            quality_label = 'EXCELLENTE'
        elif overall_quality >= 0.60:
            quality_label = 'BONNE'
        elif overall_quality >= 0.50:
            quality_label = 'MOYENNE'
        else:
            quality_label = 'FAIBLE'
        
        # Types de paris
        bet_types = {}
        leagues = {}
        
        for pred in predictions:
            bet_type = pred['prediction']['bet_type']
            league = pred['league']
            
            bet_types[bet_type] = bet_types.get(bet_type, 0) + 1
            leagues[league] = leagues.get(league, 0) + 1
        
        return {
            'total': len(predictions),
            'avg_confidence': round(avg_conf, 3),
            'avg_data_quality': round(avg_quality, 3),
            'overall_quality': round(overall_quality, 3),
            'risk': risk,
            'quality': quality_label,
            'bet_types': bet_types,
            'leagues': leagues,
            'date': datetime.now().strftime("%d/%m/%Y %H:%M")
        }

# ==================== TELEGRAM BOT ====================

class TelegramBot:
    """Bot Telegram pour l'envoi des prédictions"""
    
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.channel = Config.TELEGRAM_CHANNEL_ID
        
        if not self.token or not self.channel:
            raise ValueError("Configuration Telegram manquante")
    
    async def send_predictions(self, predictions, report):
        """Envoie les prédictions sur Telegram"""
        try:
            message = self._format_html_message(predictions, report)
            return await self._send_html_message(message)
        except Exception as e:
            logger.error(f"Erreur Telegram: {e}")
            return False
    
    def _format_html_message(self, predictions, report):
        """Formate le message en HTML"""
        date_str = report['date']
        
        header = f"""
<b>⚽️ PRONOSTICS FOOTBALL - ANALYSE MULTI-MODÈLES ⚽️</b>
<b>📅 {date_str} | 🎯 {report['total']} sélections d'excellence</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 RAPPORT DE QUALITÉ</b>
• Confiance moyenne: <b>{report['avg_confidence']:.1%}</b>
• Qualité des données: <b>{report['avg_data_quality']:.1%}</b>
• Qualité globale: <b>{report['quality']}</b>
• Niveau de risque: <b>{report['risk']}</b>

<b>🏆 RÉPARTITION DES LIGUES:</b>
"""
        
        # Ajouter les ligues
        for league, count in report['leagues'].items():
            header += f"• {league}: {count} match(s)\n"
        
        header += f"""
<b>🎰 TYPES DE PARIS:</b> {', '.join([f'{k}:{v}' for k, v in report['bet_types'].items()])}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🏅 TOP 5 PRONOSTICS DU JOUR 🏅</b>
"""
        
        predictions_text = ""
        for i, pred in enumerate(predictions, 1):
            rank_emoji = ['🥇', '🥈', '🥉', '🎯', '🎯'][i-1]
            pred_data = pred['prediction']
            quality = pred.get('data_quality', 0.5)
            
            predictions_text += f"""
{rank_emoji} <b>{pred['home_team']} vs {pred['away_team']}</b>
🏆 {pred['league']} | ⚡ Confiance: <b>{pred['confidence']:.1%}</b> | 📈 Qualité données: <b>{quality:.1%}</b>

<b>🎯 RECOMMANDATION: {pred_data['emoji']} {pred_data['recommendation']}</b>
• Type de pari: <b>{pred_data['bet_type']}</b>
• Score probable: <b>{pred_data['predicted_score']}</b>
• Over/Under 2.5: <b>{pred_data['over_under']}</b>
• BTTS: <b>{pred_data['btts']}</b>

<b>📊 PROBABILITÉS DÉTAILLÉES:</b>
1️⃣ {pred_data['probabilities']['home_win']:.1%} | N {pred_data['probabilities']['draw']:.1%} | 2️⃣ {pred_data['probabilities']['away_win']:.1%}

<b>🧮 MODÈLES UTILISÉS:</b> {', '.join(pred.get('available_models', ['Statistique']))}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        footer = f"""
<b>🔧 SYSTÈME D'ANALYSE</b>
• {len(predictions[0].get('available_models', []))} modèles mathématiques combinés
• Données temps réel OpenLigaDB
• Filtrage qualité des données

<b>⚠️ AVERTISSEMENT IMPORTANT</b>
• Ces pronostics sont basés sur une analyse algorithmique avancée
• Aucun gain n'est garanti - jouez de manière responsable
• Les cotes peuvent varier - vérifiez avant de parier

<b>🔄 PROCHAINE ANALYSE:</b> {Config.DAILY_TIME} {Config.TIMEZONE}
<b>🤖 SYSTÈME:</b> Football Predictor Pro v2.0
"""
        
        full_message = f"{header}\n{predictions_text}\n{footer}"
        
        # Limiter la taille si nécessaire
        if len(full_message) > 4000:
            full_message = full_message[:3900] + "\n\n... (message tronqué pour respecter les limites Telegram)"
        
        return full_message
    
    async def _send_html_message(self, text):
        """Envoie un message HTML sur Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                'chat_id': self.channel,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
                'disable_notification': False
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        logger.info("✅ Message Telegram envoyé avec succès")
                        return True
                    else:
                        error_text = await resp.text()
                        logger.error(f"❌ Erreur Telegram {resp.status}: {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ Exception Telegram: {e}")
            return False
    
    async def send_test_message(self):
        """Envoie un message de test"""
        try:
            message = f"""
<b>🤖 Football Predictor Bot v2.0 🤖</b>

✅ Système opérationnel avec {len(Config.LEAGUES_MAPPING)} ligues
🧮 Modèles activés: {sum(Config.ENABLED_MODELS.values())}/10
📡 Source: API OpenLigaDB
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
    """Système principal de prédictions football"""
    
    def __init__(self):
        self.db = Database()
        self.models = PredictionModels(self.db)
        self.selector = PredictionsSelector()
        self.telegram = TelegramBot()
        
        logger.info("🚀 Système Football Predictor initialisé")
        logger.info(f"📊 Ligues configurées: {len(Config.LEAGUES_MAPPING)}")
        logger.info(f"🧮 Modèles activés: {sum(Config.ENABLED_MODELS.values())}")
    
    async def run_daily_analysis(self):
        """Exécute l'analyse quotidienne"""
        logger.info("🔄 Démarrage de l'analyse quotidienne...")
        
        try:
            # 1. Collecte des matchs du jour
            async with OpenLigaDBCollector() as collector:
                matches = await collector.fetch_today_matches()
                
                if not matches:
                    logger.warning("⚠️ Aucun match trouvé pour aujourd'hui")
                    await self._send_no_matches()
                    return
                
                logger.info(f"📊 {len(matches)} matchs du jour à analyser")
                
                # 2. Analyse de chaque match
                analyses = []
                analyzed_count = 0
                
                for match in matches:
                    try:
                        # Éviter les matchs déjà terminés
                        if match.get('is_finished', False):
                            logger.debug(f"⏭️ Match terminé ignoré: {match['home_team']['name']} vs {match['away_team']['name']}")
                            continue
                        
                        # Récupérer l'historique des équipes
                        home_history = await collector.fetch_team_history(
                            match['home_team']['id'],
                            match['home_team']['name'],
                            match['league_code'],
                            Config.LEAGUES_MAPPING[match['league']]['season'],
                            8
                        )
                        
                        away_history = await collector.fetch_team_history(
                            match['away_team']['id'],
                            match['away_team']['name'],
                            match['league_code'],
                            Config.LEAGUES_MAPPING[match['league']]['season'],
                            8
                        )
                        
                        # Récupérer les confrontations directes
                        h2h_data = await collector.fetch_head_to_head(
                            match['home_team']['id'],
                            match['away_team']['id']
                        )
                        
                        # Vérifier si on a assez de données
                        if len(home_history) < 3 or len(away_history) < 3:
                            logger.debug(f"📉 Données insuffisantes pour {match['home_team']['name']} vs {match['away_team']['name']}")
                            continue
                        
                        # Analyser le match
                        analysis = self.models.analyze_match(match, home_history, away_history, h2h_data)
                        
                        if analysis:
                            analyses.append(analysis)
                            analyzed_count += 1
                            
                            # Sauvegarder les données pour usage futur
                            self.db.save_match_data(match['raw_data'])
                        
                        await asyncio.sleep(0.5)  # Respect rate limit
                        
                    except Exception as e:
                        logger.error(f"Erreur analyse match {match['home_team']['name']} vs {match['away_team']['name']}: {e}")
                        continue
                
                logger.info(f"✅ {analyzed_count} matchs analysés avec succès")
                
                if not analyses:
                    logger.warning("⚠️ Aucune analyse valide générée")
                    await self._send_no_valid_predictions()
                    return
                
                # 3. Sélection des meilleures prédictions
                top_predictions = self.selector.select_best(analyses, 5)
                
                if not top_predictions:
                    logger.warning("⚠️ Aucune prédiction ne remplit les critères de qualité")
                    await self._send_no_quality_predictions()
                    return
                
                # 4. Génération du rapport
                report = self.selector.generate_report(top_predictions)
                
                # 5. Envoi sur Telegram
                logger.info("📤 Envoi des prédictions vers Telegram...")
                success = await self.telegram.send_predictions(top_predictions, report)
                
                if success:
                    logger.info("✅ Analyse terminée et envoyée avec succès")
                    
                    # Sauvegarde des prédictions
                    for pred in top_predictions:
                        pred_to_save = {
                            'match_id': pred['match_id'],
                            'league': pred['league'],
                            'home_team': pred['home_team'],
                            'away_team': pred['away_team'],
                            'match_date': pred['date'],
                            'confidence': pred['confidence'],
                            'predicted_score': pred['prediction']['predicted_score'],
                            'bet_type': pred['prediction']['bet_type'],
                            'details': pred
                        }
                        self.db.save_prediction(pred_to_save)
                        
                    logger.info(f"💾 {len(top_predictions)} prédictions sauvegardées")
                else:
                    logger.error("❌ Échec de l'envoi Telegram")
                
        except Exception as e:
            logger.error(f"❌ Erreur système: {e}", exc_info=True)
    
    async def _send_no_matches(self):
        """Message quand aucun match n'est trouvé"""
        try:
            message = f"""
<b>📭 AUCUN MATCH PROGRAMMÉ AUJOURD'HUI</b>

Pas de match trouvé dans les {len(Config.LEAGUES_MAPPING)} ligues surveillées.
Cela peut être dû à:
• Une journée sans match
• Problème temporaire d'API
• Saison terminée

🔄 Prochaine analyse: {Config.DAILY_TIME} {Config.TIMEZONE}
"""
            await self.telegram._send_html_message(message)
        except:
            pass
    
    async def _send_no_valid_predictions(self):
        """Message quand aucune prédiction valide"""
        try:
            message = f"""
<b>⚠️ ANALYSE INCOMPLÈTE</b>

Des matchs étaient programmés mais l'analyse n'a pas pu générer de prédictions valides.
Causes possibles:
• Données historiques insuffisantes
• Problème de connexion aux APIs
• Matchs très récents sans statistiques

🔄 Prochaine analyse: {Config.DAILY_TIME} {Config.TIMEZONE}
"""
            await self.telegram._send_html_message(message)
        except:
            pass
    
    async def _send_no_quality_predictions(self):
        """Message quand aucune prédiction de qualité"""
        try:
            message = f"""
<b>🎯 CRITÈRES DE QUALITÉ NON ATTEINTS</b>

Des analyses ont été effectuées mais aucune ne remplit les critères de qualité minimum.
Seuils configurés:
• Confiance minimum: {Config.MIN_CONFIDENCE*100}%
• Qualité données minimum: 50%

Aucun pronostic n'est émis pour garantir la fiabilité.

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
        import signal
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    async def start(self):
        """Démarre le planificateur"""
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
        
        # Mode normal - démarrer le scheduler
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
        
        # Parser l'heure d'exécution
        try:
            hour, minute = map(int, Config.DAILY_TIME.split(':'))
        except:
            hour, minute = 7, 0
        
        # Planifier la tâche quotidienne
        self.scheduler.add_job(
            self._daily_task,
            CronTrigger(hour=hour, minute=minute, timezone=Config.TIMEZONE),
            id='daily_analysis',
            name='Analyse football quotidienne',
            misfire_grace_time=300
        )
        
        # Optionnel: exécution toutes les 6 heures pour tests
        if '--frequent' in sys.argv:
            self.scheduler.add_job(
                self._daily_task,
                'interval',
                hours=6,
                id='frequent_analysis',
                name='Analyse fréquente'
            )
        
        self.scheduler.start()
        
        # Envoyer un message de démarrage
        try:
            await self.system.telegram.send_test_message()
        except:
            pass
        
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

# ==================== FICHIER REQUIREMENTS.TXT ====================

"""
# requirements.txt
aiohttp==3.9.1
apscheduler==3.10.4
python-telegram-bot==20.6
pytz==2023.3
sqlite3
"""

# ==================== FICHIER railway.json ====================

"""
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "python bot.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
"""

# ==================== INSTRUCTIONS DE DÉPLOIEMENT ====================

"""
INSTRUCTIONS POUR DÉPLOIEMENT SUR RAILWAY:

1. Créer un nouveau projet sur Railway.app
2. Ajouter les variables d'environnement:
   - TELEGRAM_BOT_TOKEN=votre_token
   - TELEGRAM_CHANNEL_ID=votre_channel_id
   - TIMEZONE=Europe/Paris
   - DAILY_TIME=07:00
   - MIN_CONFIDENCE=0.65
   - LOG_LEVEL=INFO

3. Copier les fichiers:
   - bot.py (ce fichier)
   - requirements.txt
   - railway.json

4. Déployer sur Railway

FONCTIONNALITÉS:
- Récupère les matchs du jour via OpenLigaDB
- Utilise 4-5 modèles de calcul selon données disponibles
- Sélectionne les 5 meilleures prédictions
- Envoie sur Telegram avec format HTML
- Tourne 24h/24 avec analyse quotidienne
"""

# ==================== POINT D'ENTRÉE ====================

def main():
    """Point d'entrée principal"""
    
    if '--help' in sys.argv:
        print("""
🚀 Football Prediction Bot - OpenLigaDB Edition

Usage:
  python bot.py              # Mode normal (démarre le scheduler)
  python bot.py --test       # Mode test (exécution immédiate)
  python bot.py --manual     # Mode manuel (une exécution)
  python bot.py --frequent   # Mode avec exécutions fréquentes
  python bot.py --help       # Affiche cette aide

Variables d'environnement Railway:
  • TELEGRAM_BOT_TOKEN      (requis) - Token du bot Telegram
  • TELEGRAM_CHANNEL_ID     (requis) - ID du canal Telegram
  • TIMEZONE                (optionnel, défaut: Europe/Paris)
  • DAILY_TIME              (optionnel, défaut: 07:00)
  • MIN_CONFIDENCE          (optionnel, défaut: 0.65)
  • LOG_LEVEL               (optionnel, défaut: INFO)

Fonctionnalités:
  • Surveillance de 20+ ligues
  • 10 modèles de calcul (4-5 activés selon données)
  • Sélection des 5 meilleures prédictions
  • Analyse de la qualité des données
  • Format HTML pour Telegram
  • Base de données SQLite locale
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
    
    # Démarrer le système
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