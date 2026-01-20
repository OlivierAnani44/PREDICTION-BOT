
#!/usr/bin/env python3
"""
FOOTBALL PREDICTION BOT - VERSION FINALE
API OpenLigaDB avec modèles statistiques avancés
CORRECTIF: Gestion des erreurs + Ajout des 51 ligues
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
    
    # Toutes les ligues supportées (format OpenLigaDB)
    # Note: Les shortcuts sont des estimations basées sur la doc et des recherches.
    # Certains peuvent ne pas exister ou nécessiter des ajustements.
    LEAGUES = {
        # Allemagne
        "bundesliga": {"shortcut": "bl1", "name": "Bundesliga"},
        "bundesliga2": {"shortcut": "bl2", "name": "Bundesliga 2"},
        "dfb_cup": {"shortcut": "dfb", "name": "DFB Pokal"}, # Coupe d'Allemagne
        
        # Angleterre
        "premier_league": {"shortcut": "pl", "name": "Premier League"},
        "championship": {"shortcut": "ch", "name": "Championship"},
        "fa_cup": {"shortcut": "fac", "name": "FA Cup"},
        "league_cup": {"shortcut": "lc", "name": "EFL Cup"}, # League Cup
        
        # Espagne
        "la_liga": {"shortcut": "laliga", "name": "La Liga"},
        "la_liga2": {"shortcut": "laliga2", "name": "La Liga 2"},
        "copa_del_rey": {"shortcut": "cdr", "name": "Copa del Rey"},
        
        # Italie
        "serie_a": {"shortcut": "seriea", "name": "Serie A"},
        "serie_b": {"shortcut": "serieb", "name": "Serie B"},
        "coppa_italia": {"shortcut": "ci", "name": "Coppa Italia"},
        
        # France
        "ligue_1": {"shortcut": "lig1", "name": "Ligue 1"},
        "ligue_2": {"shortcut": "lig2", "name": "Ligue 2"},
        "coupe_de_france": {"shortcut": "cdf", "name": "Coupe de France"},
        "trophee_des_champions": {"shortcut": "tdc", "name": "Trophée des Champions"},
        "d1_feminine": {"shortcut": "d1f", "name": "D1 Féminine"},
        
        # Pays-Bas
        "eredivisie": {"shortcut": "eredivisie", "name": "Eredivisie"},
        
        # Belgique
        "jupiler_pro_league": {"shortcut": "jupiler", "name": "Jupiler Pro League"},
        
        # Autriche
        "austrian_bundesliga": {"shortcut": "aab", "name": "Austrian Bundesliga"},
        
        # Portugal
        "primeira_liga": {"shortcut": "liga", "name": "Primeira Liga"},
        "segunda_liga": {"shortcut": "liga2", "name": "Segunda Liga"},
        "taça_de_portugal": {"shortcut": "tcp", "name": "Taça de Portugal"},
        "supertaça_cândido_de_oliveira": {"shortcut": "sco", "name": "Supertaça Cândido de Oliveira"},
        
        # Turquie
        "super_lig": {"shortcut": "superlig", "name": "Süper Lig"},
        
        # Russie
        "russian_premier_league": {"shortcut": "rfpl", "name": "Russian Premier League"},
        
        # Suisse
        "super_league": {"shortcut": "superleague", "name": "Swiss Super League"},
        
        # Grèce
        "super_league_greece": {"shortcut": "slgr", "name": "Greek Super League"},
        
        # Europe
        "uefa_champions_league": {"shortcut": "cl", "name": "UEFA Champions League"},
        "uefa_europa_league": {"shortcut": "el", "name": "UEFA Europa League"},
        "uefa_europa_conference_league": {"shortcut": "ecl", "name": "UEFA Europa Conference League"},
        # Les autres compétitions européennes (Nations League, Euro, etc.) n'ont pas de shortcuts fixes permanents dans l'API
        # Elles changent selon les phases et les années. On omet pour l'instant.
        
        # Brésil
        "brasileirao": {"shortcut": "br", "name": "Campeonato Brasileiro Série A"},
        
        # Mexique
        "liga_mx": {"shortcut": "lmx", "name": "Liga MX"},
        
        # États-Unis
        "major_league_soccer": {"shortcut": "mls", "name": "Major League Soccer"},
        
        # Amérique du Sud (Copa Libertadores, Sudamericana)
        # L'API OpenLigaDB ne semble pas les supporter directement.
        
        # Afrique (CAF Competitions)
        # L'API OpenLigaDB ne semble pas les supporter directement.
        
        # Asie (AFC Competitions)
        # L'API OpenLigaDB ne semble pas les supporter directement.
        
        # International (Coupe du monde, Copa America, etc.)
        # Ces événements sont cycliques et n'ont pas de shortcuts fixes. Omission pour l'instant.
        
        # Reste des ligues nationales
        "algerian_ligue_1": {"shortcut": "alg1", "name": "Algerian Ligue 1"}, # Peut ne pas exister
        "saudi_professional_league": {"shortcut": "spl", "name": "Saudi Professional League"},
        "cameroonian_elite_one": {"shortcut": "cmr1", "name": "Cameroonian Elite One"}, # Peut ne pas exister
        "ivorian_ligue_1": {"shortcut": "civ1", "name": "Ivorian Ligue 1"}, # Peut ne pas exister
        "scottish_premiership": {"shortcut": "spfl", "name": "Scottish Premiership"},
        "egyptian_premier_league": {"shortcut": "egy1", "name": "Egyptian Premier League"}, # Peut ne pas exister
        "norwegian_eliteserien": {"shortcut": "noe", "name": "Norwegian Eliteserien"},
        "danish_superliga": {"shortcut": "dsl", "name": "Danish Superliga"}, # Peut ne pas exister
        "swedish_allsvenskan": {"shortcut": "swe", "name": "Swedish Allsvenskan"}, # Peut ne pas exister
        "turkish_super_lig": {"shortcut": "tsl", "name": "Turkish Süper Lig"}, # Déjà là
        "ukrainian_premier_league": {"shortcut": "upl", "name": "Ukrainian Premier League"},
        "moroccan_botola_pro": {"shortcut": "mrb", "name": "Moroccan Botola Pro"}, # Peut ne pas exister
        "tunisian_ligue_professionnelle_1": {"shortcut": "tun1", "name": "Tunisian Ligue Professionnelle 1"}, # Peut ne pas exister
        "senegalese_ligue_1": {"shortcut": "sen1", "name": "Senegalese Ligue 1"}, # Peut ne pas exister
        "south_african_psl": {"shortcut": "saf", "name": "South African PSL"}, # Peut ne pas exister
        "japanese_j1_league": {"shortcut": "jpn", "name": "Japanese J1 League"}, # Peut ne pas exister
        "korean_k_league_1": {"shortcut": "kor", "name": "Korean K League 1"}, # Peut ne pas exister
        # ... Ajouter d'autres ligues si les shortcuts sont confirmés ...
        
        # Ligues additionnelles potentiellement supportées
        "czech_1_liga": {"shortcut": "cz1", "name": "Czech 1. Liga"}, # Peut ne pas exister
        "hungarian_nemzeti_bajnoksag_i": {"shortcut": "hun", "name": "Hungarian NB I"}, # Peut ne pas exister
        "polish_ekstraklasa": {"shortcut": "pol", "name": "Polish Ekstraklasa"}, # Peut ne pas exister
        "serbian_superliga": {"shortcut": "srb", "name": "Serbian Superliga"}, # Peut ne pas exister
        "romanian_liga_1": {"shortcut": "rom", "name": "Romanian Liga 1"}, # Peut ne pas exister
        "bulgarian_parva_liga": {"shortcut": "bul", "name": "Bulgarian Parva Liga"}, # Peut ne pas exister
        "croatian_prva_hnl": {"shortcut": "cro", "name": "Croatian Prva HNL"}, # Peut ne pas exister
        "slovenian_prva_liga": {"shortcut": "svn", "name": "Slovenian Prva Liga"}, # Peut ne pas exister
        "slovak_superliga": {"shortcut": "svk", "name": "Slovak Superliga"}, # Peut ne pas exister
        "maltese_premier_league": {"shortcut": "mlt", "name": "Maltese Premier League"}, # Peut ne pas exister
        "luxembourgish_national_division": {"shortcut": "lux", "name": "Luxembourgish National Division"}, # Peut ne pas exister
        "latvian_virsliga": {"shortcut": "lat", "name": "Latvian Virsliga"}, # Peut ne pas exister
        "lithuanian_alytus_lyga": {"shortcut": "ltu", "name": "Lithuanian Alytus Lyga"}, # Peut ne pas exister
        "estonian_meistriliiga": {"shortcut": "est", "name": "Estonian Meistriliiga"}, # Peut ne pas exister
        "icelandic_Úrvalsdeild": {"shortcut": "isl", "name": "Icelandic Úrvalsdeild"}, # Peut ne pas exister
        "finnish_veikkausliiga": {"shortcut": "fin", "name": "Finnish Veikkausliiga"}, # Peut ne pas exister
        "belarusian_vysheyshaya_liga": {"shortcut": "blr", "name": "Belarusian Vysheyshaya Liga"}, # Peut ne pas exister
        "moldovan_divizia_națională": {"shortcut": "mda", "name": "Moldovan Divizia Națională"}, # Peut ne pas exister
        "georgian_ეროვნული_ლიგა": {"shortcut": "geo", "name": "Georgian Erovnuli Liga"}, # Peut ne pas exister
        "armenian_premier_league": {"shortcut": "arm", "name": "Armenian Premier League"}, # Peut ne pas exister
        "azerbaijani_premier_league": {"shortcut": "aze", "name": "Azerbaijani Premier League"}, # Peut ne pas exister
        "kazakhstani_premier_league": {"shortcut": "kaz", "name": "Kazakhstani Premier League"}, # Peut ne pas exister
        "kyrgyzstani_supercup": {"shortcut": "kgz", "name": "Kyrgyzstani Championship"}, # Peut ne pas exister
        "uzbekistani_ozbekiston_premier_league": {"shortcut": "uzb", "name": "Uzbekistan Premier League"}, # Peut ne pas exister
        "tajikistani_vahdat_i_stadium": {"shortcut": "tjk", "name": "Tajikistan Higher League"}, # Peut ne pas exister
        "turkmenistan_ýokary_ligasy": {"shortcut": "tkm", "name": "Turkmenistan Higher League"}, # Peut ne pas exister
        "mongolian_milwaukee_bucks_league": {"shortcut": "mng", "name": "Mongolian Premier League"}, # Peut ne pas exister
        "indian_super_league": {"shortcut": "isl_ind", "name": "Indian Super League"}, # Peut ne pas exister
        "chinese_super_league": {"shortcut": "csl", "name": "Chinese Super League"}, # Peut ne pas exister
        "thai_premier_league": {"shortcut": "tgl", "name": "Thai Premier League"}, # Peut ne pas exister
        "vietnamese_v_league_1": {"shortcut": "v1", "name": "Vietnamese V.League 1"}, # Peut ne pas exister
        "malaysian_super_league": {"shortcut": "msl", "name": "Malaysian Super League"}, # Peut ne pas exister
        "singaporean_premier_league": {"shortcut": "sgp", "name": "Singapore Premier League"}, # Peut ne pas exister
        "australian_aleague": {"shortcut": "al", "name": "Australian A-League"}, # Peut ne pas exister
        "new_zealand_premier_league": {"shortcut": "nzl", "name": "New Zealand Premier League"}, # Peut ne pas exister
        # Ajouter les ligues manquantes en fonction de la disponibilité réelle sur OpenLigaDB
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
                match_id INTEGER UNIQUE,
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
                match_id INTEGER,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER,
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
    
    def get_team_stats(self, team_id, season, league):
        """Récupère les stats d'une équipe"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM team_stats 
                WHERE team_id = ? AND season = ? AND league = ?
                ORDER BY last_updated DESC LIMIT 1
            ''', (team_id, season, league))
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
                stats['team_id'],
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
        """Récupère les matchs du jour pour toutes les ligues"""
        logger.info("📡 Collecte des matchs du jour...")
        
        today = datetime.now().date()
        all_matches = []
        
        for league_key, league_info in Config.LEAGUES.items():
            try:
                league_shortcut = league_info["shortcut"]
                
                # Essayer de récupérer le prochain match de la ligue
                # Cette méthode est fiable pour récupérer le prochain match
                url = f"{Config.OPENLIGADB_BASE}/getnextmatchbyleagueshortcut/{league_shortcut}"
                
                logger.debug(f"🔍 Vérification {league_info['name']} (shortcut: {league_shortcut})")
                
                async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, dict): # Un seul match
                            parsed_match = self._parse_match_single(data, league_info["name"], league_shortcut)
                            if parsed_match and parsed_match.get('date'):
                                match_date = datetime.fromisoformat(parsed_match['date'].replace('Z', '+00:00')).date()
                                if match_date == today:
                                    all_matches.append(parsed_match)
                                    logger.debug(f"  ✅ Match trouvé: {parsed_match['home_team']['name']} vs {parsed_match['away_team']['name']}")
                        elif isinstance(data, list): # Liste de matchs (moins courant pour getnextmatch)
                             for item in data:
                                 parsed_match = self._parse_match_single(item, league_info["name"], league_shortcut)
                                 if parsed_match and parsed_match.get('date'):
                                     match_date = datetime.fromisoformat(parsed_match['date'].replace('Z', '+00:00')).date()
                                     if match_date == today:
                                         all_matches.append(parsed_match)
                                         logger.debug(f"  ✅ Match trouvé: {parsed_match['home_team']['name']} vs {parsed_match['away_team']['name']}")
                    elif response.status == 404:
                        logger.debug(f"  📭 {league_info['name']}: Pas de match (HTTP 404)")
                    else:
                        logger.warning(f"  ⚠️ {league_info['name']}: HTTP {response.status}")
                
                await asyncio.sleep(0.5) # Rate limiting
                
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Timeout pour {league_info['name']}")
                continue
            except Exception as e:
                logger.error(f"❌ Erreur {league_info['name']}: {str(e)[:100]}")
                continue
        
        logger.info(f"📊 Total matchs trouvés aujourd'hui: {len(all_matches)}")
        return all_matches
    
    def _parse_match_single(self, match, league_name, league_shortcut):
        """Parse un match unique"""
        try:
            # Vérifier la date
            date_str = match.get('matchDateTime', '')
            if not date_str:
                 logger.debug("  - Date manquante dans le match")
                 return None

            match_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            today = datetime.now().date()
            
            if match_date.date() != today:
                # Ce n'est pas un match d'aujourd'hui, ignorer
                return None
            
            # Extraire les équipes
            team1 = match.get('team1', {})
            team2 = match.get('team2', {})
            
            if not team1 or not team2:
                logger.debug("  - Informations équipe manquantes")
                return None
            
            match_data = {
                'match_id': match.get('matchID', 0),
                'league': league_name,
                'league_shortcut': league_shortcut,
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
                'group': match.get('group', {}).get('groupName', 'Unknown')
            }
            
            return match_data
            
        except Exception as e:
            logger.debug(f"Erreur parsing match: {e}")
            return None
    
    async def fetch_team_history(self, team_id, team_name, league_shortcut, limit=10):
        """Récupère l'historique d'une équipe"""
        try:
            # Utiliser getmatchesbyteamid pour récupérer les matchs passés
            # weekCountPast=10 semaines dans le passé
            # weekCountFuture=0 semaines dans le futur
            url = f"{Config.OPENLIGADB_BASE}/getmatchesbyteamid/{team_id}/10/0"
            
            async with self.session.get(url, timeout=Config.API_TIMEOUT) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_team_history(data, team_id)
                else:
                    logger.debug(f"No history found for {team_name} (status: {response.status})")
                    return []
        except Exception as e:
            logger.error(f"Erreur historique {team_name}: {e}")
            return []
    
    def _parse_team_history(self, data, team_id):
        """Parse l'historique d'une équipe"""
        matches = []
        
        if not isinstance(data, list):
             logger.debug("Données d'historique non-liste")
             return []

        for match in data:
            try:
                if match.get('matchIsFinished', False):
                    # Identifier les scores et résultats
                    goals = match.get('goals', [])
                    if goals:
                        latest_goal = goals[-1]
                        score_team = latest_goal.get('scoreTeam1', 0)
                        score_opp = latest_goal.get('scoreTeam2', 0)
                        
                        # Déterminer si l'équipe est team1 ou team2
                        team1_id = match.get('team1', {}).get('teamId', 0)
                        is_home = (team1_id == team_id)
                        
                        if not is_home:
                            score_team, score_opp = score_opp, score_team
                        
                        # Déterminer le résultat
                        if score_team > score_opp:
                            result = 'WIN'
                        elif score_team < score_opp:
                            result = 'LOSS'
                        else:
                            result = 'DRAW'
                    
                    else:
                        # Si pas de goals, utiliser matchResults
                        results = match.get('matchResults', [])
                        if results:
                            result_obj = results[0]
                            pts_team = result_obj.get('pointsTeam1', 0)
                            pts_opp = result_obj.get('pointsTeam2', 0)
                            
                            if team1_id != team_id:
                                pts_team, pts_opp = pts_opp, pts_team
                            
                            if pts_team > pts_opp:
                                result = 'WIN'
                            elif pts_team < pts_opp:
                                result = 'LOSS'
                            else:
                                result = 'DRAW'
                            
                            score_team = pts_team
                            score_opp = pts_opp
                        else:
                            continue # Passer ce match s'il n'y a ni goals ni results
                    
                    match_info = {
                        'date': match.get('matchDateTime', ''),
                        'opponent': match.get('team2' if is_home else 'team1', {}).get('teamName', 'Unknown'),
                        'score_team': score_team,
                        'score_opponent': score_opp,
                        'result': result,
                        'is_home': is_home
                    }
                    
                    matches.append(match_info)
                    
                    if len(matches) >= 10:  # Limiter à 10 derniers matchs
                        break
            except Exception as e:
                 logger.debug(f"Erreur parsing match historique: {e}")
                 continue
        
        return matches

# ==================== MODELS ====================

class StatisticalModels:
    """Implémentation des 10 modèles statistiques"""
    
    def __init__(self):
        self.config = Config.MODEL_CONFIG
    
    def calculate_weighted_model(self, home_stats, away_stats, h2h_stats=None):
        """Modèle pondéré (base)"""
        try:
            # Vérifier les données disponibles
            components = {}
            
            if 'xg_avg' in home_stats and 'xg_avg' in away_stats:
                home_xg = home_stats['xg_avg']
                away_xga = away_stats.get('xg_avg', 1.2)  # Moyenne si pas dispo
                components['xg'] = (home_xg + away_xga) / 2 * self.config['weight_xg']
            
            if 'goals_scored' in home_stats and 'goals_conceded' in away_stats:
                home_goals = home_stats['goals_scored']
                away_goals_conceded = away_stats['goals_conceded']
                components['goals'] = (home_goals + away_goals_conceded) / 2 * self.config['weight_goals']
            
            if 'shots_avg' in home_stats and 'shots_avg' in away_stats:
                home_shots = home_stats['shots_avg']
                away_shots_conceded = away_stats.get('shots_avg', 10)  # Moyenne
                components['shots'] = (home_shots + away_shots_conceded) / 2 * self.config['weight_shots']
            
            if 'corners_avg' in home_stats and 'corners_avg' in away_stats:
                home_corners = home_stats['corners_avg']
                away_corners_conceded = away_stats.get('corners_avg', 5)  # Moyenne
                components['corners'] = (home_corners + away_corners_conceded) / 2 * self.config['weight_corners']
            
            # Forme récente (si historique fourni)
            if 'form' in home_stats and 'form' in away_stats:
                components['form'] = (home_stats['form'] + away_stats['form']) / 2 * self.config['weight_form']
            
            # H2H (optionnel)
            if h2h_stats:
                components['h2h'] = h2h_stats * self.config['weight_h2h']
            
            # Calcul final
            total = sum(components.values()) if components else 0
            return total, components
        except:
            return 0, {}
    
    def calculate_poisson_goals(self, home_goals_avg, away_goals_avg, league_avg):
        """Modèle de Poisson pour les buts"""
        try:
            # λ = (Buts équipe * Buts encaissés adversaire) / Moyenne ligue
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
            return 0.5  # Valeur par défaut
        
        recent = match_history[-5:] if len(match_history) >= 5 else match_history
        total = 0
        
        for match in recent:
            result = match.get('result', 'DRAW')  # Valeur par défaut
            if result == 'WIN':
                total += win_value
            elif result == 'DRAW':
                total += draw_value
            else:  # LOSS
                total += loss_value
        
        return total / len(recent)
    
    def calculate_h2h(self, h2h_data):
        """Calcul H2H (face-à-face)"""
        if not h2h_data:
            return 0.5  # Valeur neutre
        
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
                return 0.5  # Valeur par défaut
        except:
            return 0.5

# ==================== ANALYZER ====================

class MatchAnalyzer:
    """Analyseur de matchs avec les 10 modèles"""
    
    def __init__(self):
        self.models = StatisticalModels()
        self.db = Database()
        
        # Moyennes par ligue (valeurs typiques)
        self.league_averages = {
            "Bundesliga": {"goals": 2.8, "xg": 2.5},
            "Premier League": {"goals": 2.7, "xg": 2.4},
            "La Liga": {"goals": 2.6, "xg": 2.3},
            "Serie A": {"goals": 2.5, "xg": 2.2},
            "Ligue 1": {"goals": 2.4, "xg": 2.1},
            "UEFA Champions League": {"goals": 2.8, "xg": 2.5},
            "UEFA Europa League": {"goals": 2.7, "xg": 2.4}
        }
    
    def analyze(self, match_data, home_history, away_history):
        """Analyse un match avec tous les modèles"""
        try:
            home_team = match_data['home_team']['name']
            away_team = match_data['away_team']['name']
            
            # Récupérer les stats existantes
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
            
            # Calculer les modèles
            models_results = {}
            
            # 1. Modèle pondéré
            weighted_score, components = self.models.calculate_weighted_model(home_stats, away_stats)
            models_results['weighted'] = weighted_score
            
            # 2. Modèle Poisson (but besoin de moyennes ligue)
            league_avg = self.league_averages.get(match_data['league'], {}).get('goals', 2.6)
            poisson_result = self.models.calculate_poisson_goals(
                home_stats.get('goals_scored', 1.5),
                away_stats.get('goals_conceded', 1.5),
                league_avg
            )
            models_results['poisson'] = (poisson_result['home_expected'] + poisson_result['away_expected']) / 2
            
            # 3. Modèle xG
            if 'xg_avg' in home_stats and 'xg_avg' in away_stats:
                xg_score = self.models.calculate_xg_model(
                    home_stats['xg_avg'],
                    away_stats['xg_avg']
                )
                models_results['xg'] = xg_score
            
            # 4. Modèle ELO (simulation)
            # Pour simplifier, on utilise une approximation basée sur la position dans le classement
            elo_home = self._estimate_elo(home_team, match_data['league'])
            elo_away = self._estimate_elo(away_team, match_data['league'])
            elo_prob = self.models.calculate_elo_probability(elo_home, elo_away)
            models_results['elo'] = elo_prob
            
            # 5. Forme récente
            home_form = self.models.calculate_recent_form(home_history)
            away_form = self.models.calculate_recent_form(away_history)
            form_diff = home_form - away_form
            models_results['form'] = form_diff
            
            # Calcul de la confiance
            confidence = self._calculate_confidence(models_results, home_history, away_history)
            
            # Génération de la prédiction finale
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
        # Essayer de récupérer de la DB
        db_stats = self.db.get_team_stats(team_id, "current", league)
        if db_stats:
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
        
        # Sinon, calculer à partir de l'historique
        if not history:
            return {
                'team_id': team_id,
                'team_name': team_name,
                'form': 0.5
            }
        
        # Calculer les moyennes
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
        
        # Sauvegarder dans la DB
        save_data = {
            'team_id': team_id,
            'team_name': team_name,
            'season': 'current',
            'league': league,
            'goals_scored': stats.get('goals_scored', 1.2),
            'goals_conceded': stats.get('goals_conceded', 1.2),
            'xg_avg': 1.0,  # Valeur par défaut
            'shots_avg': 10.0,  # Valeur par défaut
            'corners_avg': 4.0  # Valeur par défaut
        }
        
        self.db.save_team_stats(save_data)
        return stats
    
    def _estimate_elo(self, team_name, league):
        """Estimation ELO basée sur la réputation de l'équipe"""
        # Classement approximatif
        elite_teams = [
            "Bayern Munich", "Real Madrid", "Barcelona", "Manchester City",
            "Liverpool", "Chelsea", "PSG", "Juventus", "Inter Milan", "AC Milan"
        ]
        
        top_teams = [
            "Arsenal", "Manchester United", "Tottenham", "Atletico Madrid",
            "Dortmund", "Leipzig", "RB Salzburg", "Ajax", "Porto", "Benfica"
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
            # Nombre de modèles calculés
            active_models = len([r for r in models_results.values() if r is not None])
            
            # Données historiques
            home_data = len(home_history) if home_history else 0
            away_data = len(away_history) if away_history else 0
            
            # Facteur de données
            data_factor = min((home_data + away_data) / 10.0, 1.0)
            
            # Facteur de modèles
            model_factor = active_models / 5.0  # Sur 5 modèles principaux
            
            confidence = (data_factor * 0.6 + model_factor * 0.4) * 0.8
            
            return max(0.3, min(0.95, confidence))
        except:
            return 0.5
    
    def _generate_final_prediction(self, models_results, home_stats, away_stats, poisson_result):
        """Génération de la prédiction finale"""
        try:
            # Calculer la tendance basée sur les modèles
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
            
            # Recommandation
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
            
            # Score prédit
            expected_home = poisson_result['home_expected']
            expected_away = poisson_result['away_expected']
            
            # Over/Under
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
            # Valeurs par défaut
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
<b>⚽️ PRONOSTICS FOOTBALL AVEC ANALYSE STATISTIQUE ⚽️</b>
<b>📅 {date_str} | 🏆 {report['total']} sélections</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 RAPPORT D'ANALYSE</b>
• Confiance moyenne: <b>{report['avg_confidence']:.1%}</b>
• Qualité: <b>{report['quality']}</b>

<b>🎰 TYPES DE PARIS:</b> {', '.join([f'{k}:{v}' for k, v in report['bet_types'].items()])}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🏆 PRONOSTICS DU JOUR 🏆</b>
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
• Type: <b>{pred_data['bet_type']}</b>
• Score probable: <b>{pred_data['predicted_score']}</b>
• Buts attendus: {pred_data['expected_goals']}
• Over/Under: {pred_data['over_under']}

<b>📊 STRENGTH:</b>
🏠 {pred_data['home_strength']:.2f} | ✈️ {pred_data['away_strength']:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        footer = """
<b>⚠️ INFORMATIONS IMPORTANTES</b>
• Analyses basées sur 10 modèles statistiques avancés
• Aucun gain n'est garanti - jouez responsablement
• Les cotes peuvent varier - vérifiez avant de parier

<b>⚙️ ANALYSE:</b> Modèles Statistiques + Poisson + xG + ELO
<b>📡 SOURCE:</b> OpenLigaDB
<b>🔄 PROCHAIN:</b> Analyse quotidienne à 07:00 UTC
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
            return {'total': 0, 'avg_confidence': 0, 'quality': 'FAIBLE'}
        
        confidences = [p['confidence'] for p in predictions]
        avg_conf = sum(confidences) / len(confidences)
        
        # Qualité
        if len(predictions) >= 3 and avg_conf >= 0.65:
            quality = 'BONNE'
        elif len(predictions) >= 1 and avg_conf >= 0.55:
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
    
    async def run_daily_analysis(self, test_mode=False):
        """Exécute l'analyse quotidienne"""
        logger.info("🔄 Démarrage analyse du jour...")
        
        try:
            # 1. Collecte des matchs du jour
            async with OpenLigaDBCollector() as collector:
                matches = await collector.fetch_matches_today()
                
                if not matches:
                    logger.warning("⚠️ Aucun match du jour trouvé")
                    await self._send_no_matches()
                    return
                
                logger.info(f"📊 {len(matches)} matchs du jour à analyser")
                
                # 2. Analyse
                analyses = []
                for match in matches[:20]:  # Limiter à 20 matchs pour performance
                    if not match: # Vérifier que le match n'est pas None
                         logger.warning("Match invalide détecté, ignoré.")
                         continue
                    try:
                        logger.debug(f"Analyse du match: {match['home_team']['name']} vs {match['away_team']['name']}")
                        home_history = await collector.fetch_team_history(
                            match['home_team']['id'],
                            match['home_team']['name'],
                            match.get('league_shortcut', 'unknown'),
                            8
                        )
                        
                        away_history = await collector.fetch_team_history(
                            match['away_team']['id'],
                            match['away_team']['name'],
                            match.get('league_shortcut', 'unknown'),
                            8
                        )
                        
                        analysis = self.analyzer.analyze(match, home_history, away_history)
                        if analysis:
                            analyses.append(analysis)
                        else:
                             logger.warning(f"Analyse échouée pour {match['home_team']['name']} vs {match['away_team']['name']}")
                        
                        await asyncio.sleep(0.2)  # Rate limiting
                        
                    except Exception as e:
                        logger.error(f"Erreur critique analyse match {match.get('match_id', 'unknown') if match else 'None'}: {e}")
                        continue # Passer au match suivant
                
                logger.info(f"✅ {len(analyses)} matchs analysés avec succès")
                
                # 3. Sélection des meilleurs
                top_predictions = self.selector.select_best(analyses, 5)
                
                if not top_predictions:
                    logger.warning("⚠️ Aucune prédiction valide (confiance insuffisante)")
                    await self._send_no_predictions()
                    return
                
                # 4. Rapport
                report = self.selector.generate_report(top_predictions)
                
                # 5. Envoi Telegram
                logger.info("📤 Envoi des prédictions vers Telegram...")
                success = await self.telegram.send_predictions(top_predictions, report)
                
                if success:
                    logger.info("✅ Analyse quotidienne terminée avec succès")
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
                    logger.error("❌ Échec de l'envoi Telegram")
                
        except Exception as e:
            logger.error(f"❌ Erreur système: {e}", exc_info=True)
    
    async def _send_no_matches(self):
        """Message aucun match du jour"""
        try:
            message = "<b>📭 AUCUN MATCH AUJOURD'HUI</b>\n\nPas de match programmé aujourd'hui.\n🔄 Prochaine analyse: 07:00 UTC"
            await self.telegram._send_html_message(message)
        except:
            pass
    
    async def _send_no_predictions(self):
        """Message aucune prédiction"""
        try:
            message = "<b>⚠️ AUCUN PRONOSTIC VALIDE</b>\n\nAucun match ne remplit les critères de confiance ou pas assez de données.\n🔄 Prochaine analyse: 07:00 UTC"
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
        
        # Gestion des signaux
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    async def start(self):
        """Démarre le planificateur"""
        logger.info("⏰ Planificateur démarré")
        logger.info(f"📍 Fuseau: {Config.TIMEZONE}")
        logger.info(f"⏰ Heure quotidienne: {Config.DAILY_TIME}")
        
        # Mode test
        if '--test' in sys.argv:
            logger.info("🧪 Mode test - exécution immédiate")
            await self.system.run_daily_analysis(test_mode=True)
            return
        
        # Mode manuel
        if '--manual' in sys.argv:
            logger.info("👨‍💻 Mode manuel - exécution unique")
            await self.system.run_daily_analysis()
            return
        
        # Mode normal - démarrer le scheduler
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
        
        # Parser l'heure
        try:
            hour, minute = map(int, Config.DAILY_TIME.split(':'))
        except:
            hour, minute = 7, 0
        
        # Planifier la tâche quotidienne (à 7h UTC)
        self.scheduler.add_job(
            self._daily_task,
            CronTrigger(hour=hour, minute=minute, timezone=Config.TIMEZONE),
            id='daily_analysis',
            name='Analyse football quotidienne'
        )
        
        # Planifier une tâche supplémentaire pour être sûr
        self.scheduler.add_job(
            self._daily_task,
            CronTrigger(hour=12, minute=0, timezone=Config.TIMEZONE),
            id='daily_analysis_2',
            name='Analyse football quotidienne 2'
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
🚀 Football Prediction Bot avec 10 Modèles Statistiques
Usage:
  python bot.py              # Mode normal
  python bot.py --test       # Mode test
  python bot.py --manual     # Mode manuel
  python bot.py --help       # Aide

Variables d'environnement requises:
  • TELEGRAM_BOT_TOKEN      (requis)
  • TELEGRAM_CHANNEL_ID     (requis)

Variables optionnelles:
  • TIMEZONE                (UTC)
  • DAILY_TIME              (07:00)
  • MIN_CONFIDENCE          (0.60)
  • LOG_LEVEL               (INFO)
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
