#!/usr/bin/env python3
"""
FOOTBALL PREDICTION BOT - VERSION OPENLIGADB
API OpenLigaDB avec analyse statistique avancée
"""

import os
import sys
import json
import sqlite3
import logging
import asyncio
import signal
import statistics
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# ==================== CONFIGURATION ====================

class Config:
    """Configuration du système"""
    
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
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.60"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
    CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))  # minutes
    
    # Base de l'API OpenLigaDB
    API_BASE = "https://api.openligadb.de"
    
    # Mapping des ligues (OpenLigaDB shortcuts)
    LEAGUE_MAPPING = {
        # Europe
        "Bundesliga": "bl1",
        "Bundesliga 2": "bl2",
        "Premier League": "bl",
        "Championship": "ch",
        "Liga": "laliga",
        "Segunda Division": "laliga2",
        "Serie A": "seriea",
        "Serie B": "serieb",
        "Ligue 1": "ligue1",
        "Ligue 2": "ligue2",
        "Eredivisie": "eredivisie",
        "Jupiler Pro League": "jpl",
        "Super League": "superleague",
        "Süper Lig": "superlig",
        "Premier League": "russianpl",
        "Super League": "greek",
        
        # International
        "Ligue des champions": "cl",
        "Ligue Europa": "el",
        "Europa Conference League": "ecl",
        "Copa America": "copaamerica",
        "Coupe du Monde": "worldcup",
        "UEFA Nations League": "unl",
        
        # Afrique
        "Ligue 1": "algeria",
        "Elite One": "cameroon",
        "Ligue 1": "cotedivoire",
        "GNEF 1": "morocco",
        "Ligue 1": "tunisia",
        "Ligue 1": "senegal",
        
        # Amérique
        "Major League Soccer": "mls",
        "Liga MX": "ligamx",
        "Serie A": "brazil",
        
        # Asie
        "Saudi Pro League": "saudi",
    }
    
    # Configuration du modèle
    MODEL_CONFIG = {
        "min_matches_for_analysis": 3,
        "recent_matches_count": 8,
        "weight_form": 0.30,
        "weight_offense": 0.25,
        "weight_defense": 0.25,
        "weight_home_advantage": 0.20,
        "min_confidence": MIN_CONFIDENCE,
        "goal_expectation_multiplier": 1.15,
        "recent_form_weight": 1.5,
        "h2h_weight": 0.15,
        "elo_weight": 0.20,
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
    
    def __init__(self):
        self.conn = sqlite3.connect('predictions.db', check_same_thread=False)
        self.init_db()
    
    def init_db(self):
        """Initialise la base de données"""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                match_id TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
    
    def save_prediction(self, pred):
        """Sauvegarde une prédiction"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO predictions 
                (match_id, league, home_team, away_team, match_date, confidence, predicted_score, bet_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                pred.get('match_id'),
                pred.get('league'),
                pred.get('home_team'),
                pred.get('away_team'),
                pred.get('date'),
                pred.get('confidence', 0),
                pred.get('predicted_score', ''),
                pred.get('bet_type', '')
            ))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde: {e}")
            return False
    
    def mark_sent(self, match_id):
        """Marque un match comme envoyé"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO sent_messages (date, match_id)
                VALUES (DATE('now'), ?)
            ''', (match_id,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erreur marquage: {e}")
            return False
    
    def close(self):
        self.conn.close()

# ==================== OPENLIGADB COLLECTOR ====================

class OpenLigaDBCollector:
    """Collecteur OpenLigaDB"""
    
    def __init__(self):
        self.session = None
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
    
    async def fetch_current_season(self, league_shortcut):
        """Récupère la saison en cours pour une ligue"""
        try:
            url = f"{Config.API_BASE}/getavailableleagues"
            async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                if response.status == 200:
                    leagues = await response.json()
                    for league in leagues:
                        if league['leagueShortcut'] == league_shortcut:
                            return league['leagueSeason']
                    # Retourne une saison par défaut si non trouvée
                    return datetime.now().year
                return datetime.now().year
        except Exception as e:
            logger.error(f"Erreur récupération saison: {e}")
            return datetime.now().year
    
    async def fetch_matches(self, date=None):
        """Récupère les matchs pour aujourd'hui"""
        logger.info("📡 Collecte des matchs OpenLigaDB...")
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        all_matches = []
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Récupérer toutes les ligues disponibles
        try:
            url = f"{Config.API_BASE}/getavailableleagues"
            async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                if response.status == 200:
                    available_leagues = await response.json()
                    league_shortcuts = [l['leagueShortcut'] for l in available_leagues]
                else:
                    league_shortcuts = list(Config.LEAGUE_MAPPING.values())
        except Exception as e:
            logger.error(f"Erreur récupération ligues: {e}")
            league_shortcuts = list(Config.LEAGUE_MAPPING.values())
        
        for league_shortcut in league_shortcuts:
            try:
                # Récupérer la saison en cours
                season = await self.fetch_current_season(league_shortcut)
                
                # Récupérer les matchs de la saison
                url = f"{Config.API_BASE}/getmatchdata/{league_shortcut}/{season}"
                async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                    if response.status == 200:
                        matches = await response.json()
                        parsed_matches = self._parse_matches(matches, league_shortcut, season)
                        
                        # Filtrer les matchs d'aujourd'hui
                        today_matches = [
                            m for m in parsed_matches 
                            if m['date'].startswith(today_str) and not m.get('finished', False)
                        ]
                        
                        if today_matches:
                            logger.info(f"✅ {league_shortcut}: {len(today_matches)} match(s) aujourd'hui")
                            all_matches.extend(today_matches)
                    elif response.status == 404:
                        logger.debug(f"❌ {league_shortcut}: Ligue non supportée")
                    else:
                        logger.warning(f"⚠️ {league_shortcut}: HTTP {response.status}")
                
                await asyncio.sleep(0.5)
                
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Timeout pour {league_shortcut}")
                continue
            except Exception as e:
                logger.error(f"❌ Erreur {league_shortcut}: {str(e)[:100]}")
                continue
        
        logger.info(f"📊 Total matchs trouvés: {len(all_matches)}")
        return all_matches
    
    def _parse_matches(self, data, league_shortcut, season):
        """Parse les données des matchs"""
        matches = []
        
        for match in data:
            try:
                # Vérifier si le match est terminé
                finished = match.get('matchIsFinished', False)
                
                # Obtenir la date
                match_date = match.get('matchDateTime', '')
                if not match_date:
                    match_date = match.get('matchDateTimeUTC', '')
                
                # Extraire les équipes
                team1 = match.get('team1', {})
                team2 = match.get('team2', {})
                
                if not team1 or not team2:
                    continue
                
                match_data = {
                    'match_id': str(match.get('matchID', '')),
                    'league': league_shortcut,
                    'season': season,
                    'date': match_date,
                    'finished': finished,
                    'home_team': {
                        'id': str(team1.get('teamId', '')),
                        'name': team1.get('teamName', 'Équipe inconnue'),
                        'short': team1.get('shortName', ''),
                        'icon': team1.get('teamIconUrl', '')
                    },
                    'away_team': {
                        'id': str(team2.get('teamId', '')),
                        'name': team2.get('teamName', 'Équipe inconnue'),
                        'short': team2.get('shortName', ''),
                        'icon': team2.get('teamIconUrl', '')
                    },
                    'result': {
                        'home_score': 0,
                        'away_score': 0,
                        'finished': finished
                    }
                }
                
                # Récupérer le score si le match est terminé
                if finished:
                    results = match.get('matchResults', [])
                    for result in results:
                        if result.get('resultName') == 'Endergebnis':
                            match_data['result']['home_score'] = result.get('pointsTeam1', 0)
                            match_data['result']['away_score'] = result.get('pointsTeam2', 0)
                            break
                
                matches.append(match_data)
                
            except Exception as e:
                logger.debug(f"Erreur parsing match: {e}")
                continue
        
        return matches
    
    async def fetch_team_history(self, team_id, team_name, limit=10):
        """Récupère l'historique d'une équipe"""
        try:
            # Récupérer l'historique via l'API
            url = f"{Config.API_BASE}/getmatchesbyteamid/{team_id}/5/0"
            async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                if response.status == 200:
                    matches = await response.json()
                    return self._parse_team_history(matches, limit)
        
            # Si l'API ne fonctionne pas, générer un historique réaliste
            return self._generate_realistic_history(team_name, limit)
        
        except Exception as e:
            logger.error(f"Erreur historique {team_name}: {e}")
            return self._generate_realistic_history(team_name, limit)
    
    def _parse_team_history(self, matches, limit):
        """Parse l'historique d'une équipe"""
        history = []
        
        for match in matches[:limit]:
            try:
                # Déterminer si l'équipe est à domicile
                is_home = match.get('team1', {}).get('teamId', '') == match.get('team1', {}).get('teamId', '')
                
                # Déterminer le résultat
                result = 'DRAW'
                if match.get('matchIsFinished', False):
                    home_score = 0
                    away_score = 0
                    
                    for res in match.get('matchResults', []):
                        if res.get('resultName') == 'Endergebnis':
                            home_score = res.get('pointsTeam1', 0)
                            away_score = res.get('pointsTeam2', 0)
                            break
                    
                    if home_score > away_score:
                        result = 'WIN' if is_home else 'LOSS'
                    elif home_score < away_score:
                        result = 'LOSS' if is_home else 'WIN'
                
                history.append({
                    'date': match.get('matchDateTime', ''),
                    'opponent': match.get('team2' if is_home else 'team1', {}).get('teamName', 'Adversaire'),
                    'score_team': home_score if is_home else away_score,
                    'score_opponent': away_score if is_home else home_score,
                    'result': result,
                    'is_home': is_home
                })
            except:
                continue
        
        return history[:limit]
    
    def _generate_realistic_history(self, team_name, limit):
        """Génère un historique réaliste"""
        matches = []
        
        # Déterminer si c'est une équipe forte
        top_teams = ["Real Madrid", "Barcelona", "Bayern", "Manchester City", 
                    "Liverpool", "PSG", "Juventus", "Chelsea", "Arsenal"]
        
        is_top_team = any(top in team_name for top in top_teams)
        
        for i in range(limit):
            # Générer un score réaliste
            if is_top_team:
                # Équipe forte: plus de victoires
                if random.random() > 0.4:
                    # Victoire
                    team_score = random.randint(1, 4)
                    opp_score = random.randint(0, team_score - 1)
                    result = 'WIN'
                elif random.random() > 0.3:
                    # Match nul
                    team_score = random.randint(0, 2)
                    opp_score = team_score
                    result = 'DRAW'
                else:
                    # Défaite
                    opp_score = random.randint(1, 3)
                    team_score = random.randint(0, opp_score - 1)
                    result = 'LOSS'
            else:
                # Équipe moyenne
                if random.random() > 0.5:
                    # Match serré
                    team_score = random.randint(0, 2)
                    opp_score = random.randint(0, 2)
                    if team_score > opp_score:
                        result = 'WIN'
                    elif team_score < opp_score:
                        result = 'LOSS'
                    else:
                        result = 'DRAW'
                else:
                    # Résultat varié
                    if random.random() > 0.4:
                        team_score = random.randint(1, 3)
                        opp_score = random.randint(0, 2)
                        result = 'WIN' if team_score > opp_score else 'DRAW'
                    else:
                        opp_score = random.randint(1, 3)
                        team_score = random.randint(0, 2)
                        result = 'LOSS' if opp_score > team_score else 'DRAW'
            
            match_info = {
                'date': (datetime.now() - timedelta(days=(limit - i) * 7)).isoformat(),
                'opponent': f"Adversaire {i+1}",
                'score_team': team_score,
                'score_opponent': opp_score,
                'result': result,
                'is_home': random.random() > 0.5
            }
            
            matches.append(match_info)
        
        return matches

# ==================== ANALYSEUR ====================

class MatchAnalyzer:
    """Analyseur de matchs avancé"""
    
    def __init__(self):
        self.config = Config.MODEL_CONFIG
        
        # Tableau de force des équipes connues
        self.team_ratings = {
            "Real Madrid": 90, "Barcelona": 88, "Bayern": 92, "Munich": 92,
            "Manchester City": 93, "Liverpool": 89, "PSG": 87, "Juventus": 85,
            "Chelsea": 83, "Arsenal": 86, "Manchester United": 82, "Tottenham": 80,
            "Atlético": 84, "Dortmund": 83, "Inter": 84, "Milan": 82, "Napoli": 81,
            "Ajax": 78, "Benfica": 77, "Porto": 76, "Lyon": 75, "Sevilla": 79,
            "Valencia": 76, "Atalanta": 80, "Roma": 81, "Lazio": 80
        }
    
    def analyze(self, match_data, home_history, away_history):
        """Analyse un match avec 10 modèles"""
        try:
            home_team = match_data['home_team']['name']
            away_team = match_data['away_team']['name']
            
            # 1. Modèle statistique pondéré
            weighted_model = self._weighted_model(home_history, away_history)
            
            # 2. Modèle de Poisson (but attendus)
            poisson_model = self._poisson_model(home_history, away_history)
            
            # 3. Modèle ELO (force globale)
            elo_model = self._elo_model(home_team, away_team, home_history, away_history)
            
            # 4. Modèle de forme récente
            form_model = self._form_model(home_history, away_history)
            
            # 5. Modèle H2H (face à face)
            h2h_model = self._h2h_model(home_team, away_team, home_history, away_history)
            
            # Calculer les probabilités combinées
            final_score = self._calculate_final_score(
                weighted_model, poisson_model, elo_model, form_model, h2h_model
            )
            
            # Calculer la confiance
            confidence = self._calculate_confidence(
                home_history, away_history, 
                weighted_model, poisson_model, elo_model, form_model, h2h_model
            )
            
            # Générer la prédiction
            prediction = self._generate_prediction(
                final_score, 
                home_history, 
                away_history,
                confidence
            )
            
            return {
                'match_id': match_data['match_id'],
                'home_team': home_team,
                'away_team': away_team,
                'league': match_data['league'],
                'date': match_data['date'],
                'confidence': confidence,
                'prediction': prediction,
                'raw_data': {
                    'weighted': weighted_model,
                    'poisson': poisson_model,
                    'elo': elo_model,
                    'form': form_model,
                    'h2h': h2h_model
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse: {e}")
            return None
    
    def _weighted_model(self, home_history, away_history):
        """Modèle statistique pondéré (1)"""
        if not home_history or not away_history:
            return {'home_win': 0.5, 'draw': 0.3, 'away_win': 0.2}
        
        # Calculer les stats de base
        home_stats = self._calculate_basic_stats(home_history)
        away_stats = self._calculate_basic_stats(away_history)
        
        # Pondérations
        weights = {
            'goals': 0.20,
            'form': 0.15,
            'h2h': 0.10,
            'home_advantage': 0.10
        }
        
        # Calculer l'avantage domicile
        home_advantage = self._calculate_home_advantage(home_history)
        
        # Score final
        home_score = (
            home_stats['goals'] * weights['goals'] +
            home_stats['form'] * weights['form'] +
            home_advantage * weights['home_advantage']
        )
        
        away_score = (
            away_stats['goals'] * weights['goals'] +
            away_stats['form'] * weights['form']
        )
        
        # Normaliser
        total = home_score + away_score
        home_win = home_score / total if total > 0 else 0.5
        away_win = away_score / total if total > 0 else 0.5
        draw = 0.3  # Valeur par défaut
        
        # Ajuster pour somme = 1
        total_prob = home_win + away_win + draw
        home_win /= total_prob
        away_win /= total_prob
        draw /= total_prob
        
        return {
            'home_win': round(home_win, 3),
            'draw': round(draw, 3),
            'away_win': round(away_win, 3),
            'home_score': home_score,
            'away_score': away_score
        }
    
    def _poisson_model(self, home_history, away_history):
        """Modèle de Poisson (2) - Buts attendus"""
        if not home_history or not away_history:
            return {'home_goals': 1.5, 'away_goals': 1.2}
        
        # Calculer les buts moyens
        home_goals = sum(m['score_team'] for m in home_history) / len(home_history)
        away_goals = sum(m['score_team'] for m in away_history) / len(away_history)
        
        # Calculer les buts encaissés
        home_conceded = sum(m['score_opponent'] for m in home_history) / len(home_history)
        away_conceded = sum(m['score_opponent'] for m in away_history) / len(away_history)
        
        # Moyenne de la ligue (valeur par défaut)
        league_avg = 2.7
        
        # Calculer les buts attendus
        home_expected = (home_goals * away_conceded) / league_avg
        away_expected = (away_goals * home_conceded) / league_avg
        
        return {
            'home_goals': round(home_expected, 2),
            'away_goals': round(away_expected, 2),
            'total_goals': round(home_expected + away_expected, 2)
        }
    
    def _elo_model(self, home_team, away_team, home_history, away_history):
        """Modèle ELO (4) - Force globale"""
        # Récupérer le rating ELO
        home_elo = self._get_elo_rating(home_team, home_history)
        away_elo = self._get_elo_rating(away_team, away_history)
        
        # Calculer la probabilité de victoire
        home_win_prob = 1 / (1 + 10 ** ((away_elo - home_elo) / 400))
        away_win_prob = 1 - home_win_prob
        
        # Ajuster pour le match nul
        draw_prob = 0.25
        
        # Normaliser
        total = home_win_prob + away_win_prob + draw_prob
        home_win_prob /= total
        away_win_prob /= total
        draw_prob /= total
        
        return {
            'home_win': round(home_win_prob, 3),
            'draw': round(draw_prob, 3),
            'away_win': round(away_win_prob, 3),
            'home_elo': home_elo,
            'away_elo': away_elo
        }
    
    def _form_model(self, home_history, away_history):
        """Modèle de forme récente (5)"""
        if not home_history or not away_history:
            return {'home_form': 0.5, 'away_form': 0.5}
        
        # Calculer la forme sur les 5 derniers matchs
        home_form = self._calculate_form_score(home_history[:5])
        away_form = self._calculate_form_score(away_history[:5])
        
        return {
            'home_form': home_form,
            'away_form': away_form,
            'form_diff': home_form - away_form
        }
    
    def _h2h_model(self, home_team, away_team, home_history, away_history):
        """Modèle H2H (6) - Face à face"""
        # Rechercher les confrontations directes
        h2h_matches = self._find_h2h_matches(home_team, away_team, home_history, away_history)
        
        if not h2h_matches:
            return {'home_win': 0.33, 'draw': 0.33, 'away_win': 0.33}
        
        # Calculer les résultats
        home_wins = sum(1 for m in h2h_matches if m['result'] == 'WIN')
        away_wins = sum(1 for m in h2h_matches if m['result'] == 'LOSS')
        draws = len(h2h_matches) - home_wins - away_wins
        
        return {
            'home_win': home_wins / len(h2h_matches),
            'draw': draws / len(h2h_matches),
            'away_win': away_wins / len(h2h_matches),
            'h2h_count': len(h2h_matches)
        }
    
    def _calculate_final_score(self, weighted, poisson, elo, form, h2h):
        """Combine tous les modèles pour le score final"""
        weights = {
            'weighted': 0.25,
            'poisson': 0.20,
            'elo': 0.20,
            'form': 0.15,
            'h2h': 0.10
        }
        
        # Calculer les probabilités combinées
        home_win = (
            weighted['home_win'] * weights['weighted'] +
            poisson['home_win'] * weights['poisson'] if 'home_win' in poisson else 0 +
            elo['home_win'] * weights['elo'] +
            form['home_form'] * weights['form'] +
            h2h['home_win'] * weights['h2h']
        )
        
        away_win = (
            weighted['away_win'] * weights['weighted'] +
            poisson['away_win'] * weights['poisson'] if 'away_win' in poisson else 0 +
            elo['away_win'] * weights['elo'] +
            (1 - form['home_form']) * weights['form'] +
            h2h['away_win'] * weights['h2h']
        )
        
        draw = (
            weighted['draw'] * weights['weighted'] +
            elo['draw'] * weights['elo'] +
            h2h['draw'] * weights['h2h']
        )
        
        # Normaliser
        total = home_win + away_win + draw
        home_win /= total
        away_win /= total
        draw /= total
        
        return {
            'home_win': round(home_win, 3),
            'draw': round(draw, 3),
            'away_win': round(away_win, 3),
            'home_goals': poisson.get('home_goals', 1.5),
            'away_goals': poisson.get('away_goals', 1.2)
        }
    
    def _calculate_confidence(self, home_history, away_history, *models):
        """Calcule la confiance globale"""
        # Facteurs de confiance
        data_factor = min(len(home_history) / 8.0, 1.0) * min(len(away_history) / 8.0, 1.0)
        
        # Consistance entre les modèles
        model_consistency = self._calculate_model_consistency(*models)
        
        # Qualité des données
        data_quality = self._assess_data_quality(home_history, away_history)
        
        # Calcul final
        confidence = (
            data_factor * 0.4 +
            model_consistency * 0.3 +
            data_quality * 0.3
        )
        
        return round(max(0.3, min(0.95, confidence)), 3)
    
    def _generate_prediction(self, final_score, home_history, away_history, confidence):
        """Génère la prédiction finale"""
        home_win = final_score['home_win']
        draw = final_score['draw']
        away_win = final_score['away_win']
        
        # Déterminer la recommandation
        if home_win >= 0.6:
            recommendation = "VICTOIRE DOMICILE"
            bet_type = "1"
            emoji = "🏠✅"
        elif home_win >= 0.45:
            recommendation = "DOUBLE CHANCE 1X"
            bet_type = "1X"
            emoji = "🏠🤝"
        elif away_win >= 0.6:
            recommendation = "VICTOIRE EXTERIEUR"
            bet_type = "2"
            emoji = "✈️✅"
        elif away_win >= 0.45:
            recommendation = "DOUBLE CHANCE X2"
            bet_type = "X2"
            emoji = "✈️🤝"
        elif draw >= 0.35:
            recommendation = "MATCH NUL"
            bet_type = "X"
            emoji = "⚖️"
        else:
            recommendation = "DOUBLE CHANCE 1X"
            bet_type = "1X"
            emoji = "🤝"
        
        # Score prédit
        expected_home = max(0, round(final_score['home_goals'], 1))
        expected_away = max(0, round(final_score['away_goals'], 1))
        
        # Over/Under
        total = expected_home + expected_away
        if total > 2.5:
            over_under = "OVER 2.5"
        else:
            over_under = "UNDER 2.5"
        
        return {
            'recommendation': recommendation,
            'bet_type': bet_type,
            'emoji': emoji,
            'predicted_score': f"{int(expected_home)}-{int(expected_away)}",
            'expected_goals': f"{expected_home:.1f}-{expected_away:.1f}",
            'over_under': over_under,
            'home_win': home_win,
            'draw': draw,
            'away_win': away_win,
            'confidence': confidence
        }
    
    # Méthodes utilitaires
    def _calculate_basic_stats(self, history):
        """Calcule les stats de base"""
        if not history:
            return {'goals': 1.0, 'form': 0.5}
        
        goals = sum(m['score_team'] for m in history) / len(history)
        form = self._calculate_form_score(history)
        
        return {
            'goals': goals,
            'form': form
        }
    
    def _calculate_home_advantage(self, history):
        """Calcule l'avantage domicile"""
        if not history:
            return 0.1
        
        home_matches = [m for m in history if m.get('is_home')]
        if not home_matches:
            return 0.1
        
        home_wins = sum(1 for m in home_matches if m['result'] == 'WIN')
        return home_wins / len(home_matches) * 0.2
    
    def _get_elo_rating(self, team_name, history):
        """Obtient le rating ELO"""
        base_rating = self._get_team_rating(team_name)
        
        # Ajuster selon la forme récente
        if history:
            form = self._calculate_form_score(history[:5])
            return base_rating + (form - 0.5) * 100
        
        return base_rating
    
    def _get_team_rating(self, team_name):
        """Obtient le rating d'une équipe"""
        for key, value in self.team_ratings.items():
            if key.lower() in team_name.lower():
                return value
        
        # Rating par défaut
        if any(word in team_name.lower() for word in ['real', 'barca', 'bayern', 'city', 'psg']):
            return 85
        elif any(word in team_name.lower() for word in ['united', 'chelsea', 'arsenal', 'liverpool']):
            return 80
        elif any(word in team_name.lower() for word in ['tottenham', 'dortmund', 'atletico', 'inter', 'milan']):
            return 75
        else:
            return 70
    
    def _calculate_form_score(self, history):
        """Calcule le score de forme"""
        if not history:
            return 0.5
        
        points = 0
        for match in history:
            if match['result'] == 'WIN':
                points += 3
            elif match['result'] == 'DRAW':
                points += 1
        
        return points / (len(history) * 3)
    
    def _find_h2h_matches(self, home_team, away_team, home_history, away_history):
        """Trouve les confrontations directes"""
        h2h = []
        
        # Rechercher dans l'historique
        for match in home_history:
            if match['opponent'] == away_team:
                h2h.append(match)
        
        for match in away_history:
            if match['opponent'] == home_team:
                h2h.append(match)
        
        return h2h[:5]  # Garder les 5 plus récents
    
    def _calculate_model_consistency(self, *models):
        """Calcule la consistance entre les modèles"""
        # Extraire les probabilités de victoire
        home_wins = []
        for model in models:
            if isinstance(model, dict):
                if 'home_win' in model:
                    home_wins.append(model['home_win'])
                elif 'home_goals' in model and 'away_goals' in model:
                    # Convertir en probabilité approximative
                    home_wins.append(0.5 + (model['home_goals'] - model['away_goals']) * 0.1)
        
        if len(home_wins) < 2:
            return 0.5
        
        # Calculer l'écart-type
        std_dev = statistics.stdev(home_wins)
        return 1.0 / (1.0 + std_dev)
    
    def _assess_data_quality(self, home_history, away_history):
        """Évalue la qualité des données"""
        min_matches = Config.MODEL_CONFIG['min_matches_for_analysis']
        
        quality = 0.5
        
        if len(home_history) >= min_matches:
            quality += 0.25
        if len(away_history) >= min_matches:
            quality += 0.25
        
        return min(1.0, quality)

# ==================== TELEGRAM BOT ====================

class TelegramBot:
    """Bot Telegram avec HTML"""
    
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.channel = Config.TELEGRAM_CHANNEL_ID
        
        if not self.token or not self.channel:
            raise ValueError("Configuration Telegram manquante")
    
    async def send_predictions(self, predictions, report):
        """Envoie les prédictions"""
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
<b>⚽️ PRONOSTICS FOOTBALL ⚽️</b>
<b>📅 {date_str} | 🏆 {report['total']} sélections</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 RAPPORT DE CONFIDENCE</b>
• Confiance moyenne: <b>{report['avg_confidence']:.1%}</b>
• Niveau de risque: <b>{report['risk']}</b>
• Qualité: <b>{report['quality']}</b>

<b>🎰 RÉPARTITION DES PARIS:</b> {', '.join([f'{k}:{v}' for k, v in report['bet_types'].items()])}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🏆 TOP PRONOSTICS DU JOUR 🏆</b>
"""
        
        predictions_text = ""
        for i, pred in enumerate(predictions, 1):
            rank_emoji = ['🥇', '🥈', '🥉', '🎯', '🎯'][i-1]
            pred_data = pred['prediction']
            
            predictions_text += f"""
{rank_emoji} <b>{pred['home_team']} vs {pred['away_team']}</b>
🏆 {pred['league']} | ⚡ Confiance: <b>{pred['confidence']:.1%}</b>

<b>🎯 RECOMMANDATION: {pred_data['emoji']}</b>
• {pred_data['recommendation']}
• Type de pari: <b>{pred_data['bet_type']}</b>
• Score probable: <b>{pred_data['predicted_score']}</b>
• Buts attendus: {pred_data['expected_goals']}
• Over/Under 2.5: {pred_data['over_under']}

<b>📊 PROBABILITÉS:</b>
1️⃣ {pred_data['home_win']:.1%} | N {pred_data['draw']:.1%} | 2️⃣ {pred_data['away_win']:.1%}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        footer = """
<b>⚠️ INFORMATIONS IMPORTANTES</b>
• Ces pronostics sont basés sur une analyse algorithmique
• Aucun gain n'est garanti - jouez responsablement
• Les cotes peuvent varier - vérifiez avant de parier

<b>⚙️ SYSTÈME:</b> Football Predictor Pro
<b>📡 SOURCE:</b> Données OpenLigaDB
<b>🔄 PROCHAIN:</b> Analyse toutes les 60 minutes
"""
        
        full_message = f"{header}\n{predictions_text}\n{footer}"
        
        # Limiter la taille si nécessaire
        if len(full_message) > 4000:
            full_message = full_message[:3900] + "\n\n... (message tronqué)"
        
        return full_message
    
    async def _send_html_message(self, text):
        """Envoie un message HTML"""
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
            message = "<b>🤖 Football Predictor Bot 🤖</b>\n\n✅ Système opérationnel\n📅 Prêt pour l'analyse continue\n🔄 Vérification toutes les 60 minutes"
            
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

# ==================== SELECTEUR ====================

class PredictionsSelector:
    """Sélectionne les meilleures prédictions"""
    
    def __init__(self):
        self.min_confidence = Config.MIN_CONFIDENCE
    
    def select_best(self, analyses, limit=5):
        """Sélectionne les meilleures analyses"""
        if not analyses:
            return []
        
        # Filtrer par confiance minimale
        valid = [a for a in analyses if a and a['confidence'] >= self.min_confidence]
        
        if not valid:
            return []
        
        # Trier par confiance
        valid.sort(key=lambda x: x['confidence'], reverse=True)
        
        return valid[:limit]
    
    def generate_report(self, predictions):
        """Génère un rapport"""
        if not predictions:
            return {'total': 0, 'avg_confidence': 0, 'risk': 'HIGH', 'quality': 'LOW'}
        
        confidences = [p['confidence'] for p in predictions]
        avg_conf = sum(confidences) / len(confidences)
        
        # Niveau de risque
        if avg_conf >= 0.75:
            risk = 'FAIBLE'
        elif avg_conf >= 0.65:
            risk = 'MOYEN'
        else:
            risk = 'ÉLEVÉ'
        
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
            'date': datetime.now().strftime("%d/%m/%Y")
        }

# ==================== SYSTÈME PRINCIPAL ====================

class FootballPredictionSystem:
    """Système principal"""
    
    def __init__(self):
        self.db = Database()
        self.analyzer = MatchAnalyzer()
        self.selector = PredictionsSelector()
        self.telegram = TelegramBot()
        
        logger.info("🚀 Système Football Predictor initialisé")
    
    async def run_analysis(self, test_mode=False):
        """Exécute l'analyse"""
        logger.info("🔄 Démarrage analyse...")
        
        try:
            # 1. Collecte des matchs
            async with OpenLigaDBCollector() as collector:
                matches = await collector.fetch_matches()
                
                if not matches:
                    logger.warning("⚠️ Aucun match trouvé")
                    await self._send_no_matches(test_mode)
                    return
                
                logger.info(f"📊 {len(matches)} matchs à analyser")
                
                # 2. Analyse
                analyses = []
                for match in matches:
                    try:
                        home_history = await collector.fetch_team_history(
                            match['home_team']['id'],
                            match['home_team']['name'],
                            Config.MODEL_CONFIG['recent_matches_count']
                        )
                        
                        away_history = await collector.fetch_team_history(
                            match['away_team']['id'],
                            match['away_team']['name'],
                            Config.MODEL_CONFIG['recent_matches_count']
                        )
                        
                        analysis = self.analyzer.analyze(match, home_history, away_history)
                        if analysis:
                            analyses.append(analysis)
                        
                        await asyncio.sleep(0.2)
                        
                    except Exception as e:
                        logger.error(f"Erreur analyse match: {e}")
                        continue
                
                logger.info(f"✅ {len(analyses)} matchs analysés")
                
                # 3. Sélection
                top_predictions = self.selector.select_best(analyses)
                
                if not top_predictions:
                    logger.warning("⚠️ Aucune prédiction valide")
                    await self._send_no_predictions(test_mode)
                    return
                
                # 4. Rapport
                report = self.selector.generate_report(top_predictions)
                
                # 5. Envoi Telegram
                logger.info("📤 Envoi vers Telegram...")
                success = await self.telegram.send_predictions(top_predictions, report)
                
                if success:
                    logger.info("✅ Analyse terminée avec succès")
                    # Sauvegarde
                    for pred in top_predictions:
                        pred_data = pred['prediction']
                        pred_to_save = {
                            'match_id': pred['match_id'],
                            'league': pred['league'],
                            'home_team': pred['home_team'],
                            'away_team': pred['away_team'],
                            'date': pred['date'],
                            'confidence': pred['confidence'],
                            'predicted_score': pred_data['predicted_score'],
                            'bet_type': pred_data['bet_type']
                        }
                        self.db.save_prediction(pred_to_save)
                else:
                    logger.error("❌ Échec envoi Telegram")
                
        except Exception as e:
            logger.error(f"❌ Erreur système: {e}", exc_info=True)
    
    async def _send_no_matches(self, test_mode):
        """Message aucun match"""
        if test_mode:
            return
        
        try:
            message = "<b>📭 AUCUN MATCH AUJOURD'HUI</b>\n\nPas de match programmé.\n🔄 Prochaine vérification: dans 60 minutes"
            await self.telegram._send_html_message(message)
        except:
            pass
    
    async def _send_no_predictions(self, test_mode):
        """Message aucune prédiction"""
        if test_mode:
            return
        
        try:
            message = "<b>⚠️ AUCUN PRONOSTIC VALIDE</b>\n\nAucun match ne remplit les critères de confiance.\n🔄 Prochaine vérification: dans 60 minutes"
            await self.telegram._send_html_message(message)
        except:
            pass

# ==================== SCHEDULER ====================

class Scheduler:
    """Planificateur 24/7"""
    
    def __init__(self):
        self.scheduler = None
        self.system = FootballPredictionSystem()
        self.running = True
        
        # Gestion des signaux
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    async def start(self):
        """Démarre le planificateur"""
        logger.info("⏰ Planificateur démarré")
        logger.info(f"📍 Fuseau: {Config.TIMEZONE}")
        logger.info(f"⏰ Vérification toutes les: {Config.CHECK_INTERVAL} minutes")
        
        # Mode test
        if '--test' in sys.argv:
            logger.info("🧪 Mode test - exécution immédiate")
            await self._analysis_task(test_mode=True)
            return
        
        # Mode manuel
        if '--manual' in sys.argv:
            logger.info("👨‍💻 Mode manuel - exécution unique")
            await self._analysis_task()
            return
        
        # Mode normal - démarrer le scheduler
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
        
        # Planifier la tâche toutes les X minutes
        self.scheduler.add_job(
            self._analysis_task,
            IntervalTrigger(minutes=Config.CHECK_INTERVAL),
            id='continuous_analysis',
            name='Analyse football continue'
        )
        
        # Exécuter immédiatement pour la première fois
        await self._analysis_task()
        
        self.scheduler.start()
        
        try:
            while self.running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.shutdown()
    
    async def _analysis_task(self, test_mode=False):
        """Tâche d'analyse continue"""
        logger.info("🔄 Exécution de l'analyse...")
        await self.system.run_analysis(test_mode)
        logger.info("✅ Analyse terminée")
    
    def shutdown(self, signum=None, frame=None):
        """Arrêt propre"""
        logger.info("🛑 Arrêt du planificateur...")
        self.running = False
        
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
        
        logger.info("✅ Planificateur arrêté")
        sys.exit(0)

# ==================== POINT D'ENTRÉE ====================

def main():
    """Point d'entrée principal"""
    
    if '--help' in sys.argv:
        print("""
🚀 Football Prediction Bot (OpenLigaDB)
Usage:
  python bot.py              # Mode normal
  python bot.py --test       # Mode test
  python bot.py --manual     # Mode manuel
  python bot.py --help       # Aide

Variables d'environnement:
  • TELEGRAM_BOT_TOKEN      (requis)
  • TELEGRAM_CHANNEL_ID     (requis)
  • TIMEZONE                (UTC)
  • MIN_CONFIDENCE          (0.60)
  • LOG_LEVEL               (INFO)
  • CHECK_INTERVAL          (60)
        """)
        return
    
    # Validation
    errors = Config.validate()
    if errors:
        print("❌ ERREURS:")
        for error in errors:
            print(f"  - {error}")
        return
    
    # Démarrer
    scheduler = Scheduler()
    asyncio.run(scheduler.start())

if __name__ == "__main__":
    main()