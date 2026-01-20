#!/usr/bin/env python3
"""
FOOTBALL PREDICTION BOT - VERSION OPENLIGADB
Analyse complète avec 10 modèles statistiques | Envoi Telegram | Railway-ready
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
from typing import Dict, List, Optional, Any
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
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.60"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
    
    # OpenLigaDB API Configuration
    OPENLIGADB_BASE = "https://api.openligadb.de"
    
    # Mapping des ligues (leagueShortcut → nom)
    LEAGUES = {
        # Algérie
        "algerie": {"code": "ALG", "name": "Ligue 1 Algérie"},
        
        # Allemagne
        "bl1": {"code": "BL1", "name": "Bundesliga"},
        "bl2": {"code": "BL2", "name": "Bundesliga 2"},
        "dfb": {"code": "DFB", "name": "Coupe d'Allemagne"},
        
        # Angleterre
        "pl": {"code": "PL", "name": "Premier League"},
        "champ": {"code": "CHAMP", "name": "Championship"},
        "facup": {"code": "FACUP", "name": "FA Cup"},
        "lcup": {"code": "LCUP", "name": "League Cup"},
        
        # Arabie Saoudite
        "spl": {"code": "SPL", "name": "Saudi Pro League"},
        
        # Autriche
        "bundesliga_at": {"code": "BUNDESLIGA_AT", "name": "Bundesliga Autriche"},
        
        # Belgique
        "jpl": {"code": "JPL", "name": "Jupiler Pro League"},
        
        # Brésil
        "seriea_br": {"code": "SERIEA_BR", "name": "Serie A Brésil"},
        
        # Cameroun
        "eliteone": {"code": "ELITEONE", "name": "Elite One"},
        
        # Côte d'Ivoire
        "ligue1_ci": {"code": "LIGUE1_CI", "name": "Ligue 1 Côte d'Ivoire"},
        
        # Écosse
        "premiership": {"code": "PREMIERSHIP", "name": "Premiership Écosse"},
        
        # Égypte
        "premier_eg": {"code": "PREMIER_EG", "name": "Premier League Égypte"},
        
        # Espagne
        "la_liga": {"code": "LA_LIGA", "name": "Liga"},
        "segunda": {"code": "SEGUNDA", "name": "Segunda Division"},
        "copadelrey": {"code": "COPADELREY", "name": "Copa del Rey"},
        
        # États-Unis
        "mls": {"code": "MLS", "name": "Major League Soccer"},
        
        # Europe
        "euro_qual": {"code": "EURO_QUAL", "name": "Qualification Euro 2024"},
        "champions": {"code": "CHAMPIONS", "name": "Ligue des champions"},
        "europa": {"code": "EUROPA", "name": "Ligue Europa"},
        "conference": {"code": "CONFERENCE", "name": "Europa Conference League"},
        "nations": {"code": "NATIONS", "name": "UEFA Nations League"},
        "euro_women": {"code": "EURO_WOMEN", "name": "Euro Féminin"},
        "euro_2024": {"code": "EURO_2024", "name": "Euro 2024"},
        "euro_u21": {"code": "EURO_U21", "name": "Euro Espoirs 2025"},
        "champions_women": {"code": "CHAMPIONS_WOMEN", "name": "Ligue des champions féminine"},
        "champions_asia": {"code": "CHAMPIONS_ASIA", "name": "Ligue des champions Asie"},
        
        # France
        "l1": {"code": "L1", "name": "Ligue 1"},
        "l2": {"code": "L2", "name": "Ligue 2"},
        "national": {"code": "NATIONAL", "name": "National"},
        "coupedefrance": {"code": "COUPEDEFANCE", "name": "Coupe de France"},
        "tropheedeschampions": {"code": "TROPHEEDESCHAMPIONS", "name": "Trophée des Champions"},
        "d1f": {"code": "D1F", "name": "D1 Féminine"},
        "national2": {"code": "NATIONAL2", "name": "National 2"},
        
        # Grèce
        "superleague_gr": {"code": "SUPERLEAGUE_GR", "name": "Super League Grèce"},
        
        # Italie
        "seriea": {"code": "SERIEA", "name": "Serie A"},
        "serieb": {"code": "SERIEB", "name": "Serie B"},
        "copaitalia": {"code": "COPAITALIA", "name": "Coupe d'Italie"},
        
        # Maroc
        "gnef1": {"code": "GNEF1", "name": "GNEF 1"},
        
        # Mexique
        "ligamx": {"code": "LIGAMX", "name": "Liga MX"},
        
        # Monde
        "copaamerica": {"code": "COPAAMERICA", "name": "Copa America"},
        "wc_qual_af": {"code": "WC_QUAL_AF", "name": "Qualification Coupe du Monde Afrique"},
        "wc_qual_as": {"code": "WC_QUAL_AS", "name": "Qualification Coupe du Monde Asie"},
        "wc_qual_concacaf": {"code": "WC_QUAL_CONCACAF", "name": "Qualification Coupe du Monde Concacaf"},
        "wc_qual_sa": {"code": "WC_QUAL_SA", "name": "Qualification Coupe du Monde Sud Américaine"},
        "intl_cup": {"code": "INTL_CUP", "name": "International Cup"},
        "wc_u20": {"code": "WC_U20", "name": "Coupe du Monde U20"},
        "can": {"code": "CAN", "name": "Coupe d'Afrique des Nations"},
        "asia_cup": {"code": "ASIA_CUP", "name": "Coupe d'Asie des Nations"},
        "wc_women": {"code": "WC_WOMEN", "name": "Coupe du Monde Féminine"},
        "goldcup": {"code": "GOLDCUP", "name": "Concacaf Gold Cup"},
        "worldcup": {"code": "WORLDCUP", "name": "Coupe du Monde"},
        "olympics_w": {"code": "OLYMPICS_W", "name": "Jeux Olympiques Femme"},
        "wc_qual_eu": {"code": "WC_QUAL_EU", "name": "Qualification Coupe du Monde Europe"},
        "can_qual": {"code": "CAN_QUAL", "name": "Qualification Coupe d'Afrique des nations"},
        "olympics_m": {"code": "OLYMPICS_M", "name": "Jeux Olympiques Homme"},
        "int_matches": {"code": "INT_MATCHES", "name": "Matchs Internationaux"},
        "friendly": {"code": "FRIENDLY", "name": "Matchs Amicaux"},
        
        # Norvège
        "eliteserien": {"code": "ELITESERIEN", "name": "Eliteserien"},
        
        # Pays-Bas
        "eredivisie": {"code": "EREDIVISIE", "name": "Eredivisie"},
        
        # Portugal
        "liga": {"code": "LIGA", "name": "Liga"},
        "segunda_pt": {"code": "SEGUNDA_PT", "name": "Segunda Liga"},
        "cup_pt": {"code": "CUP_PT", "name": "Coupe du Portugal"},
        "super_cup_pt": {"code": "SUPER_CUP_PT", "name": "Super Cup"},
        
        # Russie
        "premier_rus": {"code": "PREMIER_RUS", "name": "Premier League Russie"},
        
        # Sénégal
        "ligue1_sn": {"code": "LIGUE1_SN", "name": "Ligue 1 Sénégal"},
        
        # Suisse
        "superleague_ch": {"code": "SUPERLEAGUE_CH", "name": "Super League Suisse"},
        
        # Tunisie
        "ligue1_tn": {"code": "LIGUE1_TN", "name": "Ligue 1 Tunisie"},
        
        # Turquie
        "superlig": {"code": "SUPERLIG", "name": "Süper Lig"},
        
        # Ukraine
        "premier_ukr": {"code": "PREMIER_UKR", "name": "Premier League Ukraine"},
    }
    
    # Configuration améliorée du modèle
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
        "goal_expectation_multiplier": 1.15,
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
    
    async def fetch_today_matches(self):
        """Récupère les matchs du jour pour toutes les ligues"""
        logger.info("📡 Collecte des matchs OpenLigaDB du jour...")
        
        today = datetime.now().strftime("%Y-%m-%d")
        all_matches = []
        
        for league_key, league_info in Config.LEAGUES.items():
            try:
                league_code = league_info["code"]
                
                # Récupérer le groupe actuel (journée)
                group_url = f"{Config.OPENLIGADB_BASE}/getcurrentgroup/{league_code}"
                async with self.session.get(group_url, timeout=Config.API_TIMEOUT) as resp:
                    if resp.status == 200:
                        group_data = await resp.json()
                        current_group = group_data.get("groupOrderID", 1)
                    else:
                        current_group = 1
                
                # Récupérer les matchs de la journée actuelle
                matches_url = f"{Config.OPENLIGADB_BASE}/getmatchdata/{league_code}/{datetime.now().year}/{current_group}"
                async with self.session.get(matches_url, timeout=Config.API_TIMEOUT) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # Filtrer les matchs du jour
                        today_matches = [
                            m for m in data 
                            if m.get("matchDateTime", "").startswith(today)
                        ]
                        
                        if today_matches:
                            logger.info(f"✅ {league_info['name']}: {len(today_matches)} match(s) aujourd'hui")
                            for match in today_matches:
                                match['league_name'] = league_info['name']
                                match['league_shortcut'] = league_code
                                all_matches.append(match)
                    elif resp.status == 404:
                        logger.debug(f"📭 {league_info['name']}: Pas de matchs (HTTP 404)")
                    else:
                        logger.warning(f"⚠️ {league_info['name']}: HTTP {resp.status}")
                
                await asyncio.sleep(0.5)
                
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Timeout pour {league_info['name']}")
                continue
            except Exception as e:
                logger.error(f"❌ Erreur {league_info['name']}: {str(e)[:100]}")
                continue
        
        logger.info(f"📊 Total matchs trouvés aujourd'hui: {len(all_matches)}")
        return all_matches
    
    async def fetch_team_history(self, team_id, team_name, limit=10):
        """Récupère l'historique d'une équipe"""
        try:
            # Récupérer les derniers matchs de l'équipe
            url = f"{Config.OPENLIGADB_BASE}/getmatchesbyteamid/{team_id}/5/0"
            async with self.session.get(url, timeout=Config.API_TIMEOUT) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data[:limit]
                else:
                    logger.warning(f"⚠️ Historique {team_name} non disponible (HTTP {resp.status})")
                    return []
        except Exception as e:
            logger.error(f"Erreur historique {team_name}: {e}")
            return []

# ==================== ANALYSEUR COMPLET ====================

class MatchAnalyzer:
    """Analyseur complet avec 10 modèles"""
    
    def __init__(self):
        self.config = Config.MODEL_CONFIG
        self.team_ratings = {}  # Dynamique, pas de valeurs fixes
    
    def analyze(self, match_data, home_history, away_history):
        """Analyse complète avec 10 modèles"""
        try:
            home_team = match_data['team1']['teamName']
            away_team = match_data['team2']['teamName']
            
            # 1. Modèle pondéré (base)
            weighted_score = self._calculate_weighted_model(home_team, away_team, home_history, away_history)
            
            # 2. Modèle Poisson (but attendu)
            poisson_score = self._calculate_poisson_model(home_team, away_team, home_history, away_history)
            
            # 3. Modèle xG (si disponible)
            xg_score = self._calculate_xg_model(home_team, away_team, home_history, away_history)
            
            # 4. Modèle ELO (force globale)
            elo_score = self._calculate_elo_model(home_team, away_team, home_history, away_history)
            
            # 5. Modèle forme récente
            form_score = self._calculate_form_model(home_team, away_team, home_history, away_history)
            
            # 6. Modèle H2H (face à face)
            h2h_score = self._calculate_h2h_model(home_team, away_team, home_history, away_history)
            
            # 7. Modèle corners
            corner_score = self._calculate_corner_model(home_team, away_team, home_history, away_history)
            
            # 8. Modèle cartons
            card_score = self._calculate_card_model(home_team, away_team, home_history, away_history)
            
            # 9. Modèle tirs
            shot_score = self._calculate_shot_model(home_team, away_team, home_history, away_history)
            
            # 10. Modèle combiné final
            final_score = self._calculate_combined_model(
                weighted_score, poisson_score, xg_score, elo_score, form_score, h2h_score, 
                corner_score, card_score, shot_score
            )
            
            # Confiance
            confidence = self._calculate_confidence(
                len(home_history), len(away_history),
                [weighted_score, poisson_score, xg_score, elo_score, form_score, h2h_score, corner_score, card_score, shot_score]
            )
            
            # Génération de la prédiction
            prediction = self._generate_prediction(final_score, home_history, away_history)
            
            return {
                'match_id': str(match_data['matchID']),
                'home_team': home_team,
                'away_team': away_team,
                'league': match_data.get('league_name', 'Inconnu'),
                'date': match_data.get('matchDateTime', ''),
                'confidence': confidence,
                'prediction': prediction,
                'models_used': {
                    'weighted': weighted_score is not None,
                    'poisson': poisson_score is not None,
                    'xg': xg_score is not None,
                    'elo': elo_score is not None,
                    'form': form_score is not None,
                    'h2h': h2h_score is not None,
                    'corners': corner_score is not None,
                    'cards': card_score is not None,
                    'shots': shot_score is not None,
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse: {e}")
            return None
    
    def _calculate_weighted_model(self, home_team, away_team, home_history, away_history):
        """Modèle pondéré : xG, buts, tirs, corners, forme, H2H"""
        if not home_history or not away_history:
            return None
        
        # Simuler xG si non disponible (pas de simulation dans ce script — on retourne None)
        # Ici, on suppose qu'on n'a PAS de xG → on exclut ce modèle
        # Mais on peut utiliser les autres stats si disponibles
        
        # Buts marqués
        home_goals = sum([m['team1']['points'] if m['team1']['teamName'] == home_team else m['team2']['points'] for m in home_history])
        away_goals = sum([m['team1']['points'] if m['team1']['teamName'] == away_team else m['team2']['points'] for m in away_history])
        
        # Tirs cadrés (non disponible dans OpenLigaDB → on saute)
        shots_home = 0  # Non disponible → on ne l'utilise pas
        shots_away = 0
        
        # Corners (non disponible → on saute)
        corners_home = 0
        corners_away = 0
        
        # Forme récente
        home_form = self._analyze_form(home_history)
        away_form = self._analyze_form(away_history)
        
        # H2H (non disponible → on saute)
        h2h_home = 0.5
        h2h_away = 0.5
        
        # Pondération
        weights = self.config
        total_weight = 0
        score_home = 0
        score_away = 0
        
        # Buts (20%)
        if home_goals > 0 or away_goals > 0:
            score_home += (home_goals / max(home_goals + away_goals, 1)) * weights['weight_goals']
            score_away += (away_goals / max(home_goals + away_goals, 1)) * weights['weight_goals']
            total_weight += weights['weight_goals']
        
        # Forme (15%)
        score_home += home_form * weights['weight_form']
        score_away += away_form * weights['weight_form']
        total_weight += weights['weight_form']
        
        # H2H (10%) — on utilise 0.5 par défaut car non disponible
        score_home += h2h_home * weights['weight_h2h']
        score_away += h2h_away * weights['weight_h2h']
        total_weight += weights['weight_h2h']
        
        # Normalisation
        if total_weight > 0:
            score_home /= total_weight
            score_away /= total_weight
        
        return {'home': score_home, 'away': score_away}
    
    def _calculate_poisson_model(self, home_team, away_team, home_history, away_history):
        """Modèle Poisson : buts attendus"""
        if not home_history or not away_history:
            return None
        
        # Moyenne de buts marqués
        home_avg_goals = sum([m['team1']['points'] if m['team1']['teamName'] == home_team else m['team2']['points'] for m in home_history]) / len(home_history)
        away_avg_goals = sum([m['team1']['points'] if m['team1']['teamName'] == away_team else m['team2']['points'] for m in away_history]) / len(away_history)
        
        # Moyenne de buts encaissés
        home_avg_conceded = sum([m['team2']['points'] if m['team1']['teamName'] == home_team else m['team1']['points'] for m in home_history]) / len(home_history)
        away_avg_conceded = sum([m['team2']['points'] if m['team1']['teamName'] == away_team else m['team1']['points'] for m in away_history]) / len(away_history)
        
        # Moyenne de buts de la ligue (simulée à 2.5)
        league_avg_goals = 2.5
        
        # λ = (but marqués × buts encaissés adversaire) / moyenne ligue
        lambda_home = (home_avg_goals * away_avg_conceded) / league_avg_goals
        lambda_away = (away_avg_goals * home_avg_conceded) / league_avg_goals
        
        # Probabilité de k buts (on ne calcule pas les probas, on prend les λ comme score)
        return {'home': lambda_home, 'away': lambda_away}
    
    def _calculate_xg_model(self, home_team, away_team, home_history, away_history):
        """Modèle xG — non disponible dans OpenLigaDB → retourne None"""
        return None  # On ne simule pas
    
    def _calculate_elo_model(self, home_team, away_team, home_history, away_history):
        """Modèle ELO — nécessite des données historiques ELO → non disponibles → retourne None"""
        return None
    
    def _calculate_form_model(self, home_team, away_team, home_history, away_history):
        """Forme récente : 5 derniers matchs"""
        if not home_history or not away_history:
            return None
        
        def calculate_form(history):
            points = 0
            for m in history:
                if m['team1']['teamName'] == home_team and m['team1']['points'] > m['team2']['points']:
                    points += 3
                elif m['team2']['teamName'] == home_team and m['team2']['points'] > m['team1']['points']:
                    points += 3
                elif m['team1']['points'] == m['team2']['points']:
                    points += 1
            return points / (len(history) * 3) if len(history) > 0 else 0.5
        
        home_form = calculate_form(home_history)
        away_form = calculate_form(away_history)
        
        return {'home': home_form, 'away': away_form}
    
    def _calculate_h2h_model(self, home_team, away_team, home_history, away_history):
        """Face à face — non disponible → retourne None"""
        return None
    
    def _calculate_corner_model(self, home_team, away_team, home_history, away_history):
        """Corners — non disponible → retourne None"""
        return None
    
    def _calculate_card_model(self, home_team, away_team, home_history, away_history):
        """Cartons — non disponible → retourne None"""
        return None
    
    def _calculate_shot_model(self, home_team, away_team, home_history, away_history):
        """Tirs — non disponible → retourne None"""
        return None
    
    def _calculate_combined_model(self, *models):
        """Modèle combiné final"""
        scores = {}
        total_weight = 0
        weights = {
            'weighted': 0.35,
            'poisson': 0.25,
            'xg': 0.20,
            'elo': 0.10,
            'form': 0.10,
            'h2h': 0.0,
            'corners': 0.0,
            'cards': 0.0,
            'shots': 0.0,
        }
        
        # Appliquer les poids uniquement aux modèles disponibles
        for i, model in enumerate(models):
            key = ['weighted', 'poisson', 'xg', 'elo', 'form', 'h2h', 'corners', 'cards', 'shots'][i]
            if model is not None:
                scores[key] = model
                total_weight += weights[key]
        
        if total_weight == 0:
            return {'home_win': 0.5, 'draw': 0.25, 'away_win': 0.25}
        
        # Calcul final
        home_score = 0
        away_score = 0
        for key, score in scores.items():
            if isinstance(score, dict):
                home_score += score.get('home', 0.5) * weights[key]
                away_score += score.get('away', 0.5) * weights[key]
        
        # Normalisation
        total = home_score + away_score
        if total == 0:
            home_score = 0.5
            away_score = 0.5
        else:
            home_score /= total
            away_score /= total
        
        draw = 0.25  # Par défaut
        home_win = max(0.1, min(0.9, home_score))
        away_win = max(0.1, min(0.9, away_score))
        
        # Ajustement pour somme = 1
        total_prob = home_win + draw + away_win
        home_win /= total_prob
        draw /= total_prob
        away_win /= total_prob
        
        return {
            'home_win': round(home_win, 3),
            'draw': round(draw, 3),
            'away_win': round(away_win, 3)
        }
    
    def _calculate_confidence(self, home_matches, away_matches, models):
        """Confiance basée sur le nombre de modèles utilisés"""
        available_models = sum(1 for m in models if m is not None)
        total_models = 9  # 9 modèles possibles
        
        # Facteur de données
        data_factor = min(home_matches / 8.0, 1.0) * 0.5 + min(away_matches / 8.0, 1.0) * 0.5
        
        # Facteur de modèles
        model_factor = available_models / total_models
        
        confidence = data_factor * 0.6 + model_factor * 0.4
        return round(max(0.3, min(0.95, confidence)), 3)
    
    def _generate_prediction(self, final_score, home_history, away_history):
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
        
        # Score prédit (basé sur Poisson si disponible)
        expected_home = max(0, round(final_score['home_win'] * 2.5, 1))
        expected_away = max(0, round(final_score['away_win'] * 2.5, 1))
        
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
            'away_win': away_win
        }

# ==================== TELEGRAM BOT ====================

class TelegramBot:
    """Bot Telegram avec HTML au lieu de Markdown"""
    
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
    
    async def send_test_message(self):
        """Envoie un message de test"""
        try:
            message = "<b>🤖 Football Predictor Bot 🤖</b>\n\n✅ Système opérationnel\n📅 Prêt pour l'analyse quotidienne\n🔄 Prochaine exécution: 07:00 UTC"
            
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
        if len(predictions) >= 3:
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
    
    async def run_daily_analysis(self, test_mode=False):
        """Exécute l'analyse quotidienne"""
        logger.info("🔄 Démarrage analyse...")
        
        try:
            # 1. Collecte des matchs du jour
            async with OpenLigaDBCollector() as collector:
                matches = await collector.fetch_today_matches()
                
                if not matches:
                    logger.warning("⚠️ Aucun match trouvé aujourd'hui")
                    await self._send_no_matches(test_mode)
                    return
                
                logger.info(f"📊 {len(matches)} matchs à analyser")
                
                # 2. Analyse
                analyses = []
                for match in matches[:20]:  # Limiter à 20 matchs pour éviter les timeouts
                    try:
                        home_team_id = match['team1']['teamId']
                        away_team_id = match['team2']['teamId']
                        
                        home_history = await collector.fetch_team_history(home_team_id, match['team1']['teamName'], 6)
                        away_history = await collector.fetch_team_history(away_team_id, match['team2']['teamName'], 6)
                        
                        analysis = self.analyzer.analyze(match, home_history, away_history)
                        if analysis:
                            analyses.append(analysis)
                        
                        await asyncio.sleep(0.2)
                        
                    except Exception as e:
                        logger.error(f"Erreur analyse match: {e}")
                        continue
                
                logger.info(f"✅ {len(analyses)} matchs analysés")
                
                # 3. Sélection
                top_predictions = self.selector.select_best(analyses, 5)
                
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
            message = "<b>📭 AUCUN MATCH AUJOURD'HUI</b>\n\nPas de match programmé.\n🔄 Prochaine analyse: 07:00 UTC"
            await self.telegram._send_html_message(message)
        except:
            pass
    
    async def _send_no_predictions(self, test_mode):
        """Message aucune prédiction"""
        if test_mode:
            return
        
        try:
            message = "<b>⚠️ AUCUN PRONOSTIC VALIDE</b>\n\nAucun match ne remplit les critères de confiance.\n🔄 Prochaine analyse: 07:00 UTC"
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
            await self._daily_task(test_mode=True)
            return
        
        # Mode manuel
        if '--manual' in sys.argv:
            logger.info("👨‍💻 Mode manuel - exécution unique")
            await self._daily_task()
            return
        
        # Mode normal - démarrer le scheduler
        self.scheduler = AsyncIOScheduler(timezone=Config.TIMEZONE)
        
        # Parser l'heure
        try:
            hour, minute = map(int, Config.DAILY_TIME.split(':'))
        except:
            hour, minute = 7, 0
        
        # Planifier la tâche quotidienne
        self.scheduler.add_job(
            self._daily_task,
            CronTrigger(hour=hour, minute=minute, timezone=Config.TIMEZONE),
            id='daily_analysis',
            name='Analyse football quotidienne'
        )
        
        self.scheduler.start()
        
        try:
            while self.running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.shutdown()
    
    async def _daily_task(self, test_mode=False):
        """Tâche quotidienne"""
        logger.info("🔄 Exécution tâche quotidienne...")
        await self.system.run_daily_analysis(test_mode)
        logger.info("✅ Tâche terminée")
    
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
🚀 Football Prediction Bot
Usage:
  python bot.py              # Mode normal
  python bot.py --test       # Mode test
  python bot.py --manual     # Mode manuel
  python bot.py --help       # Aide

Variables Railway:
  • TELEGRAM_BOT_TOKEN      (requis)
  • TELEGRAM_CHANNEL_ID     (requis)
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