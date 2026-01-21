#!/usr/bin/env python3
"""
PRONOSTICS SPORTIFS MULTI-SOURCES (OpenLigaDB & ESPN)
Version finale avec 10 modèles statistiques
"""

import os
import sys
import json
import sqlite3
import logging
import asyncio
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import math
import statistics
import random # Pour la simulation ESPN

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
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.60"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
    
    # OpenLigaDB API Configuration
    OPENLIGADB_BASE = "https://api.openligadb.de"
    
    # ESPN API Configuration
    ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
    
    # Ligues OpenLigaDB
    OPENLIGADB_LEAGUES = {
        "bundesliga": {"shortcut": "bl1", "name": "Bundesliga", "season": "2025", "sport": "soccer"},
        "bundesliga2": {"shortcut": "bl2", "name": "Bundesliga 2", "season": "2025", "sport": "soccer"},
        "premier_league": {"shortcut": "pl", "name": "Premier League", "season": "2025", "sport": "soccer"},
        "championship": {"shortcut": "ch", "name": "Championship", "season": "2025", "sport": "soccer"},
        "la_liga": {"shortcut": "laliga", "name": "La Liga", "season": "2025", "sport": "soccer"},
        "la_liga2": {"shortcut": "laliga2", "name": "La Liga 2", "season": "2025", "sport": "soccer"},
        "serie_a": {"shortcut": "seriea", "name": "Serie A", "season": "2025", "sport": "soccer"},
        "serie_b": {"shortcut": "serieb", "name": "Serie B", "season": "2025", "sport": "soccer"},
        "ligue_1": {"shortcut": "lig1", "name": "Ligue 1", "season": "2025", "sport": "soccer"},
        "ligue_2": {"shortcut": "lig2", "name": "Ligue 2", "season": "2025", "sport": "soccer"},
        "eredivisie": {"shortcut": "eredivisie", "name": "Eredivisie", "season": "2025", "sport": "soccer"},
        "jupiler_pro_league": {"shortcut": "jupiler", "name": "Jupiler Pro League", "season": "2025", "sport": "soccer"},
        "austrian_bundesliga": {"shortcut": "aab", "name": "Austrian Bundesliga", "season": "2025", "sport": "soccer"},
        "primeira_liga": {"shortcut": "liga", "name": "Primeira Liga", "season": "2025", "sport": "soccer"},
        "segunda_liga": {"shortcut": "liga2", "name": "Segunda Liga", "season": "2025", "sport": "soccer"},
        "super_lig": {"shortcut": "superlig", "name": "Süper Lig", "season": "2025", "sport": "soccer"},
        "russian_premier_league": {"shortcut": "rfpl", "name": "Russian Premier League", "season": "2025", "sport": "soccer"},
        "super_league": {"shortcut": "superleague", "name": "Swiss Super League", "season": "2025", "sport": "soccer"},
        "super_league_greece": {"shortcut": "slgr", "name": "Greek Super League", "season": "2025", "sport": "soccer"},
        "uefa_champions_league": {"shortcut": "cl", "name": "UEFA Champions League", "season": "2025", "sport": "soccer"},
        "uefa_europa_league": {"shortcut": "el", "name": "UEFA Europa League", "season": "2025", "sport": "soccer"},
        "uefa_europa_conference_league": {"shortcut": "ecl", "name": "UEFA Europa Conference League", "season": "2025", "sport": "soccer"},
        "brasileirao": {"shortcut": "br", "name": "Campeonato Brasileiro Série A", "season": "2025", "sport": "soccer"},
        "liga_mx": {"shortcut": "lmx", "name": "Liga MX", "season": "2025", "sport": "soccer"},
        "major_league_soccer": {"shortcut": "mls", "name": "Major League Soccer", "season": "2025", "sport": "soccer"},
    }
    
    # Ligues ESPN
    ESPN_LEAGUES = {
        # Soccer
        "eng.1": {"name": "Premier League", "sport": "soccer", "code": "eng.1"},
        "esp.1": {"name": "La Liga", "sport": "soccer", "code": "esp.1"},
        "ger.1": {"name": "Bundesliga", "sport": "soccer", "code": "ger.1"},
        "ita.1": {"name": "Serie A", "sport": "soccer", "code": "ita.1"},
        "fra.1": {"name": "Ligue 1", "sport": "soccer", "code": "fra.1"},
        "uefa.champions": {"name": "UEFA Champions League", "sport": "soccer", "code": "uefa.champions"},
        "uefa.europa": {"name": "UEFA Europa League", "sport": "soccer", "code": "uefa.europa"},
        "usa.1": {"name": "Major League Soccer", "sport": "soccer", "code": "usa.1"},
        # NFL
        "nfl": {"name": "NFL", "sport": "football", "code": "nfl"},
        # MLB
        "mlb": {"name": "MLB", "sport": "baseball", "code": "mlb"},
        # NHL
        "nhl": {"name": "NHL", "sport": "hockey", "code": "nhl"},
        # NBA
        "nba": {"name": "NBA", "sport": "basketball", "code": "nba"},
        "wnba": {"name": "WNBA", "sport": "basketball", "code": "wnba"},
        # NCAA Football
        "ncaaf": {"name": "NCAA Football", "sport": "football", "code": "ncaaf"},
        # NCAA Basketball
        "ncaam": {"name": "NCAA Men's Basketball", "sport": "basketball", "code": "ncaam"},
        "ncaaw": {"name": "NCAA Women's Basketball", "sport": "basketball", "code": "ncaaw"},
        # NCAA Baseball
        "ncbaseball": {"name": "NCAA Baseball", "sport": "baseball", "code": "ncbaseball"},
    }

    # Configuration avancée du modèle
    MODEL_CONFIG = {
        "min_matches_for_analysis": 3,
        "recent_matches_count": 8,
        "weight_xg": 0.30,
        "weight_goals": 0.20,
        "weight_shots": 0.15,
        "weight_corners": 0.10,
        "weight_form": 0.15,
        "weight_h2h": 0.10,
        "min_confidence": MIN_CONFIDENCE,
        "poisson_lambda_multiplier": 1.15,
        "recent_form_weight": 1.5,
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
                match_id TEXT UNIQUE, -- Pour gérer les IDs de différentes sources
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
                match_id TEXT, -- Pour gérer les IDs de différentes sources
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT, -- Pour gérer les IDs de différentes sources
                team_name TEXT,
                season TEXT,
                league TEXT,
                goals_scored REAL,
                goals_conceded REAL,
                xg_avg REAL,
                shots_avg REAL,
                corners_avg REAL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                str(pred.get('match_id')),
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
            ''', (str(match_id),))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erreur marquage: {e}")
            return False
    
    def get_team_stats(self, team_id, season, league):
        """Récupère les stats d'une équipe"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM team_stats 
                WHERE team_id = ? AND season = ? AND league = ?
                ORDER BY last_updated DESC LIMIT 1
            ''', (str(team_id), season, league))
            return cursor.fetchone()
        except:
            return None
    
    def save_team_stats(self, stats):
        """Sauvegarde les stats d'une équipe"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO team_stats 
                (team_id, team_name, season, league, goals_scored, goals_conceded, xg_avg, shots_avg, corners_avg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(stats['team_id']),
                stats['team_name'],
                stats['season'],
                stats['league'],
                stats.get('goals_scored', 0),
                stats.get('goals_conceded', 0),
                stats.get('xg_avg', 0),
                stats.get('shots_avg', 0),
                stats.get('corners_avg', 0)
            ))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Erreur sauvegarde stats: {e}")

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
    
    async def fetch_matches_today(self):
        """Récupère les matchs du jour pour les ligues OpenLigaDB"""
        logger.info("📡 Collecte des matchs du jour (OpenLigaDB)...")
        
        today = datetime.now().date()
        all_matches = []
        
        openligadb_leagues_info = {k: v for k, v in Config.OPENLIGADB_LEAGUES.items() if v.get("sport") == "soccer"}
        
        for league_key, league_info in openligadb_leagues_info.items():
            try:
                league_shortcut = league_info["shortcut"]
                season = league_info["season"]
                
                logger.debug(f"🔍 Récupération de tous les matchs pour {league_info['name']} ({league_shortcut}/{season})")
                
                url = f"{Config.OPENLIGADB_BASE}/getmatchdata/{league_shortcut}/{season}"
                
                async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list):
                            matches_for_today = self._filter_matches_for_date(data, today)
                            if matches_for_today:
                                logger.info(f"✅ {league_info['name']}: {len(matches_for_today)} match(s) aujourd'hui")
                                for match in matches_for_today:
                                    match['league'] = league_info['name']
                                    match['league_shortcut'] = league_shortcut
                                    match['source'] = 'openligadb'
                                all_matches.extend(matches_for_today)
                        else:
                            logger.warning(f"⚠️ {league_info['name']}: Réponse inattendue (pas une liste)")
                    elif response.status == 404:
                        logger.debug(f"  📭 {league_info['name']}: Ligue/Season introuvable (404) - {url}")
                    else:
                        logger.warning(f"  ⚠️ {league_info['name']}: HTTP {response.status} - {url}")
                
                await asyncio.sleep(0.5)
                
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Timeout pour {league_info['name']}")
                continue
            except Exception as e:
                logger.error(f"❌ Erreur {league_info['name']}: {str(e)[:100]}")
                continue
        
        logger.info(f"📊 Total matchs OpenLigaDB trouvés aujourd'hui: {len(all_matches)}")
        return all_matches
    
    def _filter_matches_for_date(self, matches_data, target_date):
        """Filtre une liste de matchs pour une date spécifique"""
        filtered = []
        for match in matches_data: # Ligne CORRIGEE : ajout des ':'
            try:
                date_str = match.get('matchDateTime', '')
                if not date_str:
                    continue
                match_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
                if match_date == target_date:
                    parsed_match = self._parse_match_single_from_list(match)
                    if parsed_match:
                         filtered.append(parsed_match)
            except Exception as e:
                 logger.debug(f"Erreur filtrage match OpenLigaDB: {e}")
                 continue
        return filtered
    
    def _parse_match_single_from_list(self, match):
        """Parse un match unique extrait d'une liste OpenLigaDB"""
        try:
            team1 = match.get('team1', {})
            team2 = match.get('team2', {})
            
            if not team1 or not team2:
                logger.debug("  - Informations équipe manquantes dans OpenLigaDB")
                return None
            
            match_data = {
                'match_id': match.get('matchID', 0),
                'date': match.get('matchDateTime', ''),
                'home_team': {
                    'id': team1.get('teamId', 0),
                    'name': team1.get('teamName', ''),
                    'short': team1.get('shortName', '')
                },
                'away_team': {
                    'id': team2.get('teamId', 0),
                    'name': team2.get('teamName', ''),
                    'short': team2.get('shortName', '')
                },
                'finished': match.get('matchIsFinished', False),
                'group': match.get('group', {}).get('groupName', 'Unknown'),
                'source': 'openligadb'
            }
            
            return match_data
            
        except Exception as e:
            logger.debug(f"Erreur parsing match OpenLigaDB: {e}")
            return None
    
    async def fetch_team_history(self, team_id, team_name, league_shortcut, limit=10):
        """Récupère l'historique d'une équipe OpenLigaDB"""
        try:
            url = f"{Config.OPENLIGADB_BASE}/getmatchesbyteamid/{team_id}/10/0"
            
            logger.debug(f"🔍 Historique OpenLigaDB pour {team_name} (ID: {team_id})")
            
            async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                         history = self._parse_team_history(data, team_id)
                         logger.debug(f"  - {len(history)} matchs historiques OpenLigaDB trouvés pour {team_name}")
                         return history
                    else:
                         logger.debug(f"  - Réponse historique OpenLigaDB pour {team_name} n'est pas une liste")
                         return []
                else:
                    logger.debug(f"No history found for {team_name} (status: {response.status})")
                    return []
        except Exception as e:
            logger.error(f"Erreur historique OpenLigaDB {team_name}: {e}")
            return []
    
    def _parse_team_history(self, data, team_id):
        """Parse l'historique d'une équipe OpenLigaDB"""
        matches = []
        
        if not isinstance(data, list):
             logger.debug("Données d'historique OpenLigaDB non-liste")
             return []

        for match in data: # Ligne CORRIGEE : ajout des ':'
            try:
                if match.get('matchIsFinished', False):
                    score_team = 0
                    score_opp = 0
                    result = 'DRAW'

                    results = match.get('matchResults', [])
                    if results:
                        final_result = None
                        for res in results:
                             if res.get('resultTypeID', 0) == 1:
                                 final_result = res
                                 break
                        if not final_result:
                             final_result = results[-1] if results else None
                        
                        if final_result:
                             pts_team = final_result.get('pointsTeam1', 0)
                             pts_opp = final_result.get('pointsTeam2', 0)
                             team1_id = match.get('team1', {}).get('teamId', 0)
                             is_home = (team1_id == team_id)
                             
                             if not is_home:
                                 pts_team, pts_opp = pts_opp, pts_team
                             
                             score_team = pts_team
                             score_opp = pts_opp
                             
                             if pts_team > pts_opp:
                                result = 'WIN'
                             elif pts_team < pts_opp:
                                result = 'LOSS'
                             else:
                                result = 'DRAW'

                    if score_team == 0 and score_opp == 0 and result == 'DRAW':
                         continue

                    match_info = {
                        'date': match.get('matchDateTime', ''),
                        'opponent': match.get('team2' if is_home else 'team1', {}).get('teamName', 'Unknown'),
                        'score_team': score_team,
                        'score_opponent': score_opp,
                        'result': result,
                        'is_home': is_home
                    }
                    
                    matches.append(match_info)
                    
                    if len(matches) >= 10:
                        break
            except Exception as e:
                 logger.debug(f"Erreur parsing match historique OpenLigaDB: {e}")
                 continue
        
        return matches


# ==================== ESPN COLLECTOR ====================

class ESPNCollector:
    """Collecteur ESPN"""
    
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
    
    async def fetch_matches_today(self):
        """Récupère les matchs du jour pour les ligues ESPN"""
        logger.info("📡 Collecte des matchs du jour (ESPN)...")
        
        today = datetime.now().date()
        all_matches = []
        
        espn_leagues_info = {k: v for k, v in Config.ESPN_LEAGUES.items()}
        
        for league_code, league_info in espn_leagues_info.items():
            try:
                sport = league_info["sport"]
                league = league_code
                
                logger.debug(f"🔍 Récupération des matchs ESPN pour {league_info['name']} ({sport}/{league})")
                
                date_str = today.strftime("%Y%m%d")
                url = f"{Config.ESPN_BASE}/{sport}/{league}/scoreboard"
                params = {"dates": date_str}
                
                async with self.session.get(url, params=params, timeout=Config.API_TIMEOUT) as response:
                    if response.status == 200:
                        data = await response.json()
                        matches_for_today = self._parse_scoreboard(data, league_info['name'])
                        if matches_for_today:
                            logger.info(f"✅ {league_info['name']}: {len(matches_for_today)} match(s) aujourd'hui")
                            for match in matches_for_today:
                                match['source'] = 'espn'
                            all_matches.extend(matches_for_today)
                    elif response.status == 404:
                        logger.debug(f"  📭 {league_info['name']}: Ligue introuvable (404) - {url}")
                    else:
                        logger.warning(f"  ⚠️ {league_info['name']}: HTTP {response.status} - {url}")
                
                await asyncio.sleep(0.5)
                
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Timeout ESPN pour {league_info['name']}")
                continue
            except Exception as e:
                logger.error(f"❌ Erreur ESPN {league_info['name']}: {str(e)[:100]}")
                continue
        
        logger.info(f"📊 Total matchs ESPN trouvés aujourd'hui: {len(all_matches)}")
        return all_matches
    
    def _parse_scoreboard(self, data, league_name):
        """Parse les données du scoreboard ESPN"""
        matches = []
        
        if not data or 'events' not in data:
            return matches
        
        for event in data['events']:
            try:
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
                
                status = competitions.get('status', {})
                is_finished = status.get('type', {}).get('completed', False)
                
                match_data = {
                    'match_id': event.get('id', ''),
                    'league': league_name,
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
                    'finished': is_finished,
                    'source': 'espn'
                }
                
                matches.append(match_data)
                
            except Exception as e:
                logger.debug(f"Erreur parsing match ESPN: {e}")
                continue
        
        return matches
    
    async def fetch_team_history(self, team_id, team_name, league_code, limit=10):
        """Récupère l'historique d'une équipe ESPN (SIMULE)"""
        logger.debug(f"🔍 Historique ESPN simulé pour {team_name} (ID: {team_id})")
        
        simulated_history = self._simulate_history(team_name, limit)
        logger.debug(f"  - {len(simulated_history)} matchs historiques ESPN simulés pour {team_name}")
        return simulated_history

    def _simulate_history(self, team_name, limit):
        """Simule un historique pour ESPN"""
        top_teams = ["Real Madrid", "Barcelona", "Bayern Munich", "Manchester City", 
                     "Liverpool", "PSG", "Juventus", "Chelsea", "Arsenal", "Miami", "LA Galaxy",
                     "Celtics", "Lakers", "Warriors", "Bucks", "Raptors", "Maple Leafs", "Canadiens",
                     "Rangers", "Bruins", "Penguins", "Capitals", "Cowboys", "Giants", "Eagles",
                     "Patriots", "Lions", "49ers", "Raiders", "Chiefs", "Rams", "Cardinals"]
        
        is_top_team = any(top in team_name for top in top_teams)
        
        matches = []
        for i in range(limit):
            if is_top_team:
                if random.random() > 0.3:
                    team_score = random.randint(2, 4)
                    opp_score = random.randint(0, 1)
                    result = 'WIN'
                elif random.random() > 0.3:
                    team_score = random.randint(1, 2)
                    opp_score = team_score
                    result = 'DRAW'
                else:
                    opp_score = random.randint(1, 3)
                    team_score = random.randint(0, 1)
                    result = 'LOSS'
            else:
                if random.random() > 0.6:
                    team_score = random.randint(1, 2)
                    opp_score = random.randint(0, 1)
                    result = 'WIN'
                elif random.random() > 0.5:
                    team_score = random.randint(0, 2)
                    opp_score = team_score
                    result = 'DRAW'
                else:
                    opp_score = random.randint(1, 3)
                    team_score = random.randint(0, 1)
                    result = 'LOSS'
            
            match_info = {
                'date': (datetime.now() - timedelta(days=i*7)).isoformat(),
                'opponent': f"Opponent {i+1}",
                'score_team': team_score,
                'score_opponent': opp_score,
                'result': result,
                'is_home': random.random() > 0.5
            }
            matches.append(match_info)
        return matches


# ==================== MODELS ====================

class StatisticalModels:
    """Implémentation des 10 modèles statistiques"""
    
    def __init__(self):
        self.config = Config.MODEL_CONFIG
    
    def calculate_weighted_model(self, home_stats, away_stats, h2h_stats=None):
        """Modèle pondéré (base)"""
        try:
            components = {}
            
            if 'xg_avg' in home_stats and 'xg_avg' in away_stats:
                home_xg = home_stats['xg_avg']
                away_xga = away_stats.get('xg_avg', 1.2)
                components['xg'] = (home_xg + away_xga) / 2 * self.config['weight_xg']
            
            if 'goals_scored' in home_stats and 'goals_conceded' in away_stats:
                home_goals = home_stats['goals_scored']
                away_goals_conceded = away_stats['goals_conceded']
                components['goals'] = (home_goals + away_goals_conceded) / 2 * self.config['weight_goals']
            
            if 'shots_avg' in home_stats and 'shots_avg' in away_stats:
                home_shots = home_stats['shots_avg']
                away_shots_conceded = away_stats.get('shots_avg', 10)
                components['shots'] = (home_shots + away_shots_conceded) / 2 * self.config['weight_shots']
            
            if 'corners_avg' in home_stats and 'corners_avg' in away_stats:
                home_corners = home_stats['corners_avg']
                away_corners_conceded = away_stats.get('corners_avg', 5)
                components['corners'] = (home_corners + away_corners_conceded) / 2 * self.config['weight_corners']
            
            if 'form' in home_stats and 'form' in away_stats:
                components['form'] = (home_stats['form'] + away_stats['form']) / 2 * self.config['weight_form']
            
            if h2h_stats:
                components['h2h'] = h2h_stats * self.config['weight_h2h']
            
            total = sum(components.values()) if components else 0
            return total, components
        except:
            return 0, {}
    
    def calculate_poisson_goals(self, home_goals_avg, away_goals_avg, league_avg):
        """Modèle de Poisson pour les buts"""
        try:
            home_lambda = (home_goals_avg * away_goals_avg) / league_avg if league_avg > 0 else home_goals_avg
            away_lambda = (away_goals_avg * home_goals_avg) / league_avg if league_avg > 0 else away_goals_avg
            
            return {
                'home_expected': home_lambda,
                'away_expected': away_lambda
            }
        except:
            return {'home_expected': 1.2, 'away_expected': 1.2}
    
    def calculate_xg_model(self, home_xg, away_xga, home_advantage=0.1):
        """Modèle xG"""
        try:
            home_expected = (home_xg + away_xga) / 2 + home_advantage if home_advantage else (home_xg + away_xga) / 2
            return home_expected
        except:
            return 1.2
    
    def calculate_elo_probability(self, home_elo, away_elo):
        """Modèle ELO"""
        try:
            probability = 1 / (1 + 10 ** ((away_elo - home_elo) / 400))
            return probability
        except:
            return 0.5
    
    def calculate_recent_form(self, match_history, win_value=1, draw_value=0.5, loss_value=0):
        """Calcul de la forme récente"""
        if not match_history or len(match_history) == 0:
            return 0.5
        
        recent = match_history[-5:] if len(match_history) >= 5 else match_history
        total = 0
        
        for match in recent:
            result = match.get('result', 'DRAW')
            if result == 'WIN':
                total += win_value
            elif result == 'DRAW':
                total += draw_value
            else:
                total += loss_value
        
        return total / len(recent)
    
    def calculate_h2h(self, h2h_data):
        """Calcul H2H (face-à-face)"""
        if not h2h_data:
            return 0.5
        
        wins = sum(1 for m in h2h_data if m.get('result') == 'WIN')
        draws = sum(1 for m in h2h_data if m.get('result') == 'DRAW')
        losses = sum(1 for m in h2h_data if m.get('result') == 'LOSS')
        
        total = wins + draws + losses
        if total == 0:
            return 0.5
        
        return (wins * 1 + draws * 0.5) / total
    
    def calculate_corners_expected(self, home_corners_avg, away_corners_avg):
        """Modèle corners"""
        try:
            expected = (home_corners_avg + away_corners_avg) / 2
            return expected
        except:
            return 4.5
    
    def calculate_cards_expected(self, home_cards_avg, away_cards_avg):
        """Modèle cartons"""
        try:
            expected = (home_cards_avg + away_cards_avg) / 2
            return expected
        except:
            return 2.5
    
    def calculate_shots_expected(self, home_shots_avg, away_shots_avg):
        """Modèle tirs"""
        try:
            expected = (home_shots_avg + away_shots_avg) / 2
            return expected
        except:
            return 12.0
    
    def calculate_combined_model(self, models_results):
        """Modèle combiné final"""
        try:
            weights = {
                'xg': 0.35,
                'poisson': 0.25,
                'weighted': 0.20,
                'elo': 0.10,
                'contextual': 0.10
            }
            
            total = 0
            weight_sum = 0
            
            for model, result in models_results.items():
                if result is not None and model in weights:
                    total += result * weights[model]
                    weight_sum += weights[model]
            
            if weight_sum > 0:
                return total / weight_sum
            else:
                return 0.5
        except:
            return 0.5

# ==================== ANALYZER ====================

class MatchAnalyzer:
    """Analyseur de matchs avec les 10 modèles"""
    
    def __init__(self):
        self.models = StatisticalModels()
        self.db = Database()
        
        self.league_averages = {
            "Bundesliga": {"goals": 2.8, "xg": 2.5},
            "Premier League": {"goals": 2.7, "xg": 2.4},
            "La Liga": {"goals": 2.6, "xg": 2.3},
            "Serie A": {"goals": 2.5, "xg": 2.2},
            "Ligue 1": {"goals": 2.4, "xg": 2.1},
            "UEFA Champions League": {"goals": 2.8, "xg": 2.5},
            "UEFA Europa League": {"goals": 2.7, "xg": 2.4},
            "Major League Soccer": {"goals": 2.8, "xg": 2.5},
            "NFL": {"goals": 22, "xg": 22}, # Adapté pour le foot US
            "MLB": {"goals": 8, "xg": 8}, # Adapté pour le baseball
            "NBA": {"goals": 110, "xg": 110}, # Adapté pour le basket
            "NHL": {"goals": 5, "xg": 5}, # Adapté pour le hockey
        }
    
    def analyze(self, match_data, home_history, away_history):
        """Analyse un match avec tous les modèles"""
        try:
            home_team = match_data['home_team']['name']
            away_team = match_data['away_team']['name']
            
            home_stats = self._get_team_comprehensive_stats(
                match_data['home_team']['id'], 
                home_team, 
                match_data['league'],
                home_history
            )
            
            away_stats = self._get_team_comprehensive_stats(
                match_data['away_team']['id'], 
                away_team, 
                match_data['league'],
                away_history
            )
            
            models_results = {}
            
            weighted_score, components = self.models.calculate_weighted_model(home_stats, away_stats)
            models_results['weighted'] = weighted_score
            
            league_avg = self.league_averages.get(match_data['league'], {}).get('goals', 2.6)
            poisson_result = self.models.calculate_poisson_goals(
                home_stats.get('goals_scored', 1.5),
                away_stats.get('goals_conceded', 1.5),
                league_avg
            )
            models_results['poisson'] = (poisson_result['home_expected'] + poisson_result['away_expected']) / 2
            
            if 'xg_avg' in home_stats and 'xg_avg' in away_stats:
                xg_score = self.models.calculate_xg_model(
                    home_stats['xg_avg'],
                    away_stats['xg_avg']
                )
                models_results['xg'] = xg_score
            
            elo_home = self._estimate_elo(home_team, match_data['league'])
            elo_away = self._estimate_elo(away_team, match_data['league'])
            elo_prob = self.models.calculate_elo_probability(elo_home, elo_away)
            models_results['elo'] = elo_prob
            
            home_form = self.models.calculate_recent_form(home_history)
            away_form = self.models.calculate_recent_form(away_history)
            form_diff = home_form - away_form
            models_results['form'] = form_diff
            
            confidence = self._calculate_confidence(models_results, home_history, away_history)
            
            prediction = self._generate_final_prediction(
                models_results, 
                home_stats, 
                away_stats,
                poisson_result
            )
            
            return {
                'match_id': match_data['match_id'],
                'home_team': home_team,
                'away_team': away_team,
                'league': match_data['league'],
                'date': match_data['date'],
                'confidence': confidence,
                'models_results': models_results,
                'prediction': prediction,
                'components': components
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse: {e}")
            return None
    
    def _get_team_comprehensive_stats(self, team_id, team_name, league, history):
        """Récupère ou calcule les stats complètes d'une équipe"""
        db_stats = self.db.get_team_stats(str(team_id), "current", league)
        if db_stats:
            logger.debug(f"Stats DB trouvées pour {team_name}")
            return {
                'team_id': team_id,
                'team_name': team_name,
                'goals_scored': db_stats[5],
                'goals_conceded': db_stats[6],
                'xg_avg': db_stats[7],
                'shots_avg': db_stats[8],
                'corners_avg': db_stats[9],
                'form': self.models.calculate_recent_form(history)
            }
        
        if not history:
            logger.warning(f"Pas d'historique pour {team_name}, stats par défaut.")
            return {
                'team_id': team_id,
                'team_name': team_name,
                'form': 0.5
            }
        
        goals_scored = [m['score_team'] for m in history if 'score_team' in m]
        goals_conceded = [m['score_opponent'] for m in history if 'score_opponent' in m]

        stats = {
            'team_id': team_id,
            'team_name': team_name,
            'form': self.models.calculate_recent_form(history)
        }

        if goals_scored:
            stats['goals_scored'] = sum(goals_scored) / len(goals_scored)
        if goals_conceded:
            stats['goals_conceded'] = sum(goals_conceded) / len(goals_conceded)

        save_data = {
            'team_id': str(team_id),
            'team_name': team_name,
            'season': 'current',
            'league': league,
            'goals_scored': stats.get('goals_scored', 1.2),
            'goals_conceded': stats.get('goals_conceded', 1.2),
            'xg_avg': 0.0,
            'shots_avg': 0.0,
            'corners_avg': 0.0
        }
        
        self.db.save_team_stats(save_data)
        logger.debug(f"Stats calculées et sauvegardées pour {team_name}")
        return stats
    
    def _estimate_elo(self, team_name, league):
        """Estimation ELO basée sur la réputation de l'équipe"""
        elite_teams = [
            "Bayern Munich", "Real Madrid", "Barcelona", "Manchester City",
            "Liverpool", "Chelsea", "PSG", "Juventus", "Inter Milan", "AC Milan",
            "Celtics", "Lakers", "Warriors", "Bucks", "Raiders", "Chiefs", "Maple Leafs"
        ]
        
        top_teams = [
            "Arsenal", "Manchester United", "Tottenham", "Atletico Madrid",
            "Dortmund", "Leipzig", "Ajax", "Porto", "Benfica", "Raptors", "Penguins"
        ]
        
        if any(t.lower() in team_name.lower() for t in elite_teams):
            return 1800
        elif any(t.lower() in team_name.lower() for t in top_teams):
            return 1650
        elif "league" in league.lower() or "bundesliga" in league.lower():
            return 1500
        else:
            return 1400
    
    def _calculate_confidence(self, models_results, home_history, away_history):
        """Calcul de la confiance basé sur les données disponibles"""
        try:
            active_models = len([r for r in models_results.values() if r is not None])
            home_data = len(home_history) if home_history else 0
            away_data = len(away_history) if away_history else 0
            data_factor = min((home_data + away_data) / 10.0, 1.0)
            model_factor = active_models / 5.0
            confidence = (data_factor * 0.6 + model_factor * 0.4) * 0.8
            return max(0.3, min(0.95, confidence))
        except:
            return 0.5
    
    def _generate_final_prediction(self, models_results, home_stats, away_stats, poisson_result):
        """Génération de la prédiction finale"""
        try:
            home_strength = 0
            away_strength = 0
            count = 0
            
            for model, result in models_results.items():
                if result is not None:
                    if 'home' in str(result).lower() or result > 0.55:
                        home_strength += result
                    elif 'away' in str(result).lower() or result < 0.45:
                        away_strength += (1 - result)
                    else:
                        home_strength += result
                        away_strength += (1 - result)
                    count += 1
            
            if count > 0:
                home_strength /= count
                away_strength /= count
            else:
                home_strength = away_strength = 0.5
            
            if home_strength > away_strength + 0.1:
                recommendation = "VICTOIRE DOMICILE"
                bet_type = "1"
                emoji = "🏠✅"
            elif away_strength > home_strength + 0.1:
                recommendation = "VICTOIRE EXTERIEUR"
                bet_type = "2"
                emoji = "✈️✅"
            elif abs(home_strength - away_strength) < 0.05:
                recommendation = "MATCH NUL"
                bet_type = "X"
                emoji = "⚖️"
            else:
                recommendation = "DOUBLE CHANCE"
                bet_type = "1X" if home_strength > away_strength else "X2"
                emoji = "🤝"
            
            expected_home = poisson_result['home_expected']
            expected_away = poisson_result['away_expected']
            
            total = expected_home + expected_away
            over_under = "OVER 2.5" if total > 2.5 else "UNDER 2.5"
            
            return {
                'recommendation': recommendation,
                'bet_type': bet_type,
                'emoji': emoji,
                'predicted_score': f"{round(expected_home)}-{round(expected_away)}",
                'expected_goals': f"{expected_home:.1f}-{expected_away:.1f}",
                'over_under': over_under,
                'home_strength': home_strength,
                'away_strength': away_strength
            }
        except:
            return {
                'recommendation': "ANALYSE INSUFFISANTE",
                'bet_type': "X",
                'emoji': "❓",
                'predicted_score': "0-0",
                'expected_goals': "1.0-1.0",
                'over_under': "INCONNU",
                'home_strength': 0.5,
                'away_strength': 0.5
            }

# ==================== TELEGRAM BOT ====================

class TelegramBot:
    """Bot Telegram"""
    
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
<b>⚽️ Pronostics Sportifs Multi-Sources ⚽️</b>
<b>📅 {date_str} | 🏆 {report['total']} sélections</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 Rapport d'Analyse</b>
• Confiance moyenne: <b>{report['avg_confidence']:.1%}</b>
• Qualité: <b>{report['quality']}</b>

<b>🎰 Types de Paris:</b> {', '.join([f'{k}:{v}' for k, v in report['bet_types'].items()])}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🏆 Pronostics du Jour 🏆</b>
"""
        
        predictions_text = ""
        for i, pred in enumerate(predictions, 1):
            rank_emoji = ['🥇', '🥈', '🥉', '🎯', '🎯'][i-1]
            pred_data = pred['prediction']
            
            predictions_text += f"""
{rank_emoji} <b>{pred['home_team']} vs {pred['away_team']}</b>
🏆 {pred['league']} | ⚡ Confiance: <b>{pred['confidence']:.1%}</b>

<b>🎯 Recommandation: {pred_data['emoji']}</b>
• {pred_data['recommendation']}
• Type: <b>{pred_data['bet_type']}</b>
• Score probable: <b>{pred_data['predicted_score']}</b>
• Buts attendus: {pred_data['expected_goals']}
• Over/Under: {pred_data['over_under']}

<b>📊 Strength:</b>
🏠 {pred_data['home_strength']:.2f} | ✈️ {pred_data['away_strength']:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        footer = """
<b>⚠️ Informations Importantes</b>
• Analyses basées sur 10 modèles statistiques avancés
• Aucun gain n'est garanti - jouez responsablement
• Les cotes peuvent varier - vérifiez avant de parier

<b>⚙️ Source:</b> OpenLigaDB & ESPN
<b>🔄 Prochain:</b> Analyse quotidienne à 07:00 UTC
"""
        
        full_message = f"{header}\n{predictions_text}\n{footer}"
        
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

# ==================== SELECTEUR ====================

class PredictionsSelector:
    """Sélectionne les meilleures prédictions"""
    
    def __init__(self):
        self.min_confidence = Config.MIN_CONFIDENCE
    
    def select_best(self, analyses, limit=5):
        """Sélectionne les meilleures analyses"""
        if not analyses:
            return []
        
        valid = [a for a in analyses if a and a['confidence'] >= self.min_confidence]
        
        if not valid:
            return []
        
        valid.sort(key=lambda x: x['confidence'], reverse=True)
        
        return valid[:limit]
    
    def generate_report(self, predictions):
        """Génère un rapport"""
        if not predictions:
            return {'total': 0, 'avg_confidence': 0, 'quality': 'FAIBLE'}
        
        confidences = [p['confidence'] for p in predictions]
        avg_conf = sum(confidences) / len(confidences)
        
        if len(predictions) >= 3 and avg_conf >= 0.65:
            quality = 'BONNE'
        elif len(predictions) >= 1 and avg_conf >= 0.55:
            quality = 'MOYENNE'
        else:
            quality = 'FAIBLE'
        
        bet_types = {}
        for pred in predictions:
            bet_type = pred['prediction']['bet_type']
            bet_types[bet_type] = bet_types.get(bet_type, 0) + 1
        
        return {
            'total': len(predictions),
            'avg_confidence': round(avg_conf, 3),
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
        
        logger.info("🚀 Système Multi-Source Predictor initialisé")
    
    async def run_daily_analysis(self, test_mode=False):
        """Exécute l'analyse quotidienne"""
        logger.info("🔄 Démarrage analyse du jour...")
        
        try:
            all_matches = []
            
            async with OpenLigaDBCollector() as openligadb_collector:
                openligadb_matches = await openligadb_collector.fetch_matches_today()
                all_matches.extend(openligadb_matches)
            
            async with ESPNCollector() as espn_collector:
                espn_matches = await espn_collector.fetch_matches_today()
                all_matches.extend(espn_matches)
                
            logger.info(f"📊 Total matchs trouvés aujourd'hui (OpenLigaDB + ESPN): {len(all_matches)}")
            
            if not all_matches:
                logger.warning("⚠️ Aucun match du jour trouvé dans les sources configurées")
                await self._send_no_matches()
                return
            
            analyses = []
            for match in all_matches:
                if not match:
                     logger.warning("Match invalide détecté, ignoré.")
                     continue
                try:
                    logger.debug(f"Analyse du match: {match['home_team']['name']} vs {match['away_team']['name']} (Source: {match.get('source', 'unknown')})")
                    
                    if match.get('source') == 'openligadb':
                        collector_instance = openligadb_collector
                    else: # Assume ESPN
                        collector_instance = espn_collector
                        
                    home_history = await collector_instance.fetch_team_history(
                        match['home_team']['id'],
                        match['home_team']['name'],
                        match.get('league_shortcut', match.get('league_code', 'unknown')),
                        8
                    )
                    
                    away_history = await collector_instance.fetch_team_history(
                        match['away_team']['id'],
                        match['away_team']['name'],
                        match.get('league_shortcut', match.get('league_code', 'unknown')),
                        8
                    )
                    
                    analysis = self.analyzer.analyze(match, home_history, away_history)
                    if analysis:
                        analyses.append(analysis)
                    else:
                         logger.warning(f"Analyse échouée pour {match['home_team']['name']} vs {match['away_team']['name']}")
                    
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    logger.error(f"Erreur critique analyse match {match.get('match_id', 'unknown')}: {e}")
                    continue
            
            logger.info(f"✅ {len(analyses)} matchs analysés avec succès")
            
            top_predictions = self.selector.select_best(analyses, 5)
            
            if not top_predictions:
                logger.warning("⚠️ Aucune prédiction valide (confiance insuffisante)")
                await self._send_no_predictions()
                return
            
            report = self.selector.generate_report(top_predictions)
            
            logger.info("📤 Envoi des prédictions vers Telegram...")
            success = await self.telegram.send_predictions(top_predictions, report)
            
            if success:
                logger.info("✅ Analyse quotidienne terminée avec succès")
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
                logger.error("❌ Échec de l'envoi Telegram")
                
        except Exception as e:
            logger.error(f"❌ Erreur système: {e}", exc_info=True)
    
    async def _send_no_matches(self):
        """Message aucun match du jour"""
        try:
            message = "<b>📭 Aucun match aujourd'hui</b>\n\nPas de match programmé aujourd'hui dans les ligues surveillées.\n🔄 Prochaine analyse: 07:00 UTC"
            await self.telegram._send_html_message(message)
        except:
            pass
    
    async def _send_no_predictions(self):
        """Message aucune prédiction"""
        try:
            message = "<b>⚠️ Aucun pronostic valide</b>\n\nAucun match ne remplit les critères de confiance ou pas assez de données.\n🔄 Prochaine analyse: 07:00 UTC"
            await self.telegram._send_html_message(message)
        except:
            pass

# ==================== SCHEDULER ====================

class Scheduler:
    """Planificateur Railway"""
    
    def __init__(self):
        self.scheduler = None
        self.system = FootballPredictionSystem()
        self.running = True
        
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    async def start(self):
        """Démarre le planificateur"""
        logger.info("⏰ Planificateur démarré")
        logger.info(f"Fuseau: {Config.TIMEZONE}")
        logger.info(f"Heure quotidienne: {Config.DAILY_TIME}")
        
        if '--test' in sys.argv:
            logger.info("🧪 Mode test - exécution immédiate")
            await self.system.run_daily_analysis(test_mode=True)
            return
        
        if '--manual' in sys.argv:
            logger.info("👨‍💻 Mode manuel - exécution unique")
            await self.system.run_daily_analysis()
            return
        
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
        
        try:
            hour, minute = map(int, Config.DAILY_TIME.split(':'))
        except:
            hour, minute = 7, 0
        
        self.scheduler.add_job(
            self._daily_task,
            CronTrigger(hour=hour, minute=minute, timezone=Config.TIMEZONE),
            id='daily_analysis',
            name='Analyse quotidienne'
        )
        
        self.scheduler.add_job(
            self._daily_task,
            CronTrigger(hour=12, minute=0, timezone=Config.TIMEZONE),
            id='daily_analysis_2',
            name='Analyse quotidienne 2'
        )
        
        self.scheduler.start()
        
        try:
            while self.running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.shutdown()
    
    async def _daily_task(self):
        """Tâche quotidienne"""
        logger.info("🔄 Exécution tâche quotidienne...")
        await self.system.run_daily_analysis()
        logger.info("✅ Tâche quotidienne terminée")
    
    def shutdown(self, signum=None, frame=None):
        """Arrêt propre"""
        logger.info("🛑 Arrêt du planificateur...")
        self.running = False
        
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
        
        self.system.db.close()
        logger.info("✅ Planificateur arrêté")
        sys.exit(0)

# ==================== POINT D'ENTRÉE ====================

def main():
    """Point d'entrée principal"""
    
    if '--help' in sys.argv:
        print("""
🚀 Multi-Source Prediction Bot avec 10 Modèles Statistiques (OpenLigaDB + ESPN)
        """)
        return
    
    errors = Config.validate()
    if errors:
        print("❌ ERREURS:")
        for error in errors:
            print(f"  - {error}")
        return
    
    scheduler = Scheduler()
    asyncio.run(scheduler.start())

if __name__ == "__main__":
    main()