"""
BOT DE PRONOSTICS FOOTBALL 24/7 - UTILISE OPENLIGADB.DE ET ENVOIE SUR TELEGRAM
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
from apscheduler.triggers.interval import IntervalTrigger

# --- Configuration ---
class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
    MIN_DATA_CONFIDENCE = float(os.getenv("MIN_DATA_CONFIDENCE", "0.60"))
    RUN_INTERVAL_MINUTES = int(os.getenv("RUN_INTERVAL_MINUTES", "30"))

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise ValueError("TELEGRAM_BOT_TOKEN et TELEGRAM_CHANNEL_ID doivent être définis.")

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Base de Données ---
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('predictions.db', check_same_thread=False)
        self.init_db()

    def init_db(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER UNIQUE,
                league_name TEXT,
                team1_name TEXT,
                team2_name TEXT,
                match_date TEXT,
                confidence REAL,
                prediction TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def save_prediction(self, match_id, league, team1, team2, date, confidence, pred):
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO predictions (match_id, league_name, team1_name, team2_name, match_date, confidence, prediction)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (match_id, league, team1, team2, date, confidence, json.dumps(pred)))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde DB: {e}")
            return False

    def was_sent_today(self, match_id):
        cursor = self.conn.cursor()
        today = datetime.now().date().isoformat()
        cursor.execute('SELECT 1 FROM predictions WHERE match_id = ? AND created_at LIKE ?', (match_id, f"{today}%"))
        return cursor.fetchone() is not None

    def close(self):
        self.conn.close()

# --- Collecteur OpenLigaDB ---
class OpenLigaDBCollector:
    BASE_URL = "https://api.openligadb.de"

    def __init__(self):
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_available_leagues(self) -> List[Dict]:
        """Récupère la liste de toutes les ligues disponibles."""
        url = f"{self.BASE_URL}/getavailableleagues"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"Récupéré {len(data)} ligues depuis OpenLigaDB.")
                    return data
                else:
                    logger.error(f"Erreur API getavailableleagues: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Exception lors de la récupération des ligues: {e}")
            return []

    async def get_todays_matches(self, league_shortcut: str, league_season: int) -> List[Dict]:
        """Récupère les matchs d'aujourd'hui pour une ligue spécifique."""
        today = datetime.now().date()
        # Cette API ne filtre pas directement par date, donc on récupère la saison entière et on filtre localement.
        # Pour les ligues actives, on pourrait utiliser getcurrentgroup pour le matchday courant.
        # Pour simplifier ici, on récupère les matchs de la saison.
        url = f"{self.BASE_URL}/getmatchdata/{league_shortcut}/{league_season}"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    matches = await resp.json()
                    todays = [m for m in matches if datetime.fromisoformat(m['matchDateTime']).date() == today]
                    return todays
                else:
                    logger.debug(f"Erreur API getmatchdata pour {league_shortcut}: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Exception lors de la récupération des matchs pour {league_shortcut}: {e}")
            return []

    async def get_team_match_history(self, team_id: int, limit: int = 10) -> List[Dict]:
        """Récupère l'historique des matchs d'une équipe."""
        # Cette API ne permet pas directement de récupérer les matchs d'une seule équipe via son ID.
        # On peut utiliser le nom partiel dans l'URL.
        # Pour cette implémentation, on suppose qu'on a le nom de l'équipe.
        # Une alternative est de récupérer les dernières journées de la ligue.
        # Pour simplifier, on retourne une liste vide pour l'instant.
        # Si l'ID de l'équipe est disponible, on peut essayer /getmatchesbyteamid/{teamId}/{weekCountPast}/{weekCountFuture}
        url = f"{self.BASE_URL}/getmatchesbyteamid/{team_id}/4/0" # 4 semaines passées
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    matches = await resp.json()
                    # Trier par date et prendre les `limit` derniers
                    sorted_matches = sorted(matches, key=lambda x: x['matchDateTime'], reverse=True)
                    return sorted_matches[:limit]
                else:
                    logger.debug(f"Erreur API getmatchesbyteamid pour team {team_id}: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Exception lors de la récupération de l'historique pour team {team_id}: {e}")
            return []

    async def get_current_group(self, league_shortcut: str):
        """Récupère le groupe/journée actuelle."""
        url = f"{self.BASE_URL}/getcurrentgroup/{league_shortcut}"
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.debug(f"Erreur API getcurrentgroup pour {league_shortcut}: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Exception lors de la récupération du groupe courant pour {league_shortcut}: {e}")
            return None


# --- Analyseur de Match ---
class MatchAnalyzer:
    def __init__(self):
        self.models_used = []

    def analyze_match(self, match_data: Dict, team1_history: List[Dict], team2_history: List[Dict]):
        """
        Analyse un match en utilisant les 10 modèles disponibles.
        Calcule un score de confiance basé sur les données disponibles.
        """
        team1_id = match_data['team1']['teamId']
        team2_id = match_data['team2']['teamId']
        team1_name = match_data['team1']['teamName']
        team2_name = match_data['team2']['teamName']

        # --- Collecte des données ---
        data_availability = {
            'team1_history': len(team1_history) >= 3,
            'team2_history': len(team2_history) >= 3,
            'match_goals': 'matchResults' in match_data and len(match_data['matchResults']) > 0,
            'match_shots': any(goal.get('matchMinute') for goal in match_data.get('goals', [])), # Approximatif sans tirs
            'h2h_history': self._find_h2h(team1_history, team2_name) or self._find_h2h(team2_history, team1_name),
        }

        # Initialiser les scores bruts pour chaque modèle
        model_scores = {
            'weighted': {},
            'poisson': {},
            'xg': {},
            'elo': {},
            'form': {},
            'h2h': {},
            'corners': {},
            'cards': {},
            'shots': {},
        }
        self.models_used = []

        # --- Modèle Pondéré (1) ---
        if data_availability['team1_history'] and data_availability['team2_history']:
            self.models_used.append('weighted')
            t1_stats = self._aggregate_stats(team1_history)
            t2_stats = self._aggregate_stats(team2_history)
            
            # Simuler xG si non disponible, basé sur buts et tirs
            xG1 = t1_stats.get('goals_avg', 1.2)
            xG2 = t2_stats.get('goals_avg', 1.2)
            
            score_t1 = (
                0.30 * xG1 +
                0.20 * t1_stats.get('goals_avg', 0) +
                0.15 * t1_stats.get('shots_avg', 10) * 0.3 + # Estimation tirs cadrés
                0.10 * t1_stats.get('corners_avg', 4) +
                0.15 * t1_stats.get('form', 0.5) +
                0.10 * self._get_h2h_score(team1_name, team2_name, data_availability['h2h_history'])
            )
            score_t2 = (
                0.30 * xG2 +
                0.20 * t2_stats.get('goals_avg', 0) +
                0.15 * t2_stats.get('shots_avg', 10) * 0.3 +
                0.10 * t2_stats.get('corners_avg', 4) +
                0.15 * t2_stats.get('form', 0.5) +
                0.10 * self._get_h2h_score(team2_name, team1_name, data_availability['h2h_history'])
            )
            model_scores['weighted'] = {'team1': score_t1, 'team2': score_t2}

        # --- Modèle de Poisson (2) ---
        if data_availability['team1_history'] and data_availability['team2_history']:
            self.models_used.append('poisson')
            # Calcul lambda pour chaque équipe
            lg_avg_goals = 1.4 # Valeur moyenne approximative, devrait être spécifique à la ligue
            lambda_t1 = (t1_stats.get('goals_avg', 1.2) * t2_stats.get('opp_goals_avg', 1.2)) / lg_avg_goals
            lambda_t2 = (t2_stats.get('goals_avg', 1.2) * t1_stats.get('opp_goals_avg', 1.2)) / lg_avg_goals
            
            # Probabilité de gagner (approximative)
            # P(T1 > T2) est complexe, on simplifie avec une comparaison de lambda
            win_prob_t1 = lambda_t1 / (lambda_t1 + lambda_t2) if (lambda_t1 + lambda_t2) > 0 else 0.5
            win_prob_t2 = 1 - win_prob_t1
            model_scores['poisson'] = {'team1': win_prob_t1, 'team2': win_prob_t2}


        # --- Modèle xG (3) ---
        # Non applicable car xG n'est pas dans les données brutes d'OpenLigaDB
        
        # --- Modèle ELO (4) ---
        # Non applicable car pas de données ELO
        
        # --- Modèle de Forme (5) ---
        if data_availability['team1_history']:
            self.models_used.append('form')
            form_t1 = self._calculate_form(team1_history)
            model_scores['form']['team1'] = form_t1
        if data_availability['team2_history']:
            form_t2 = self._calculate_form(team2_history)
            model_scores['form']['team2'] = form_t2

        # --- Modèle H2H (6) ---
        if data_availability['h2h_history']:
            self.models_used.append('h2h')
            h2h_res = self._analyze_h2h(team1_name, team2_name, data_availability['h2h_history'])
            model_scores['h2h'] = h2h_res

        # --- Modèle Corners (7) ---
        if data_availability['team1_history'] and data_availability['team2_history']:
            self.models_used.append('corners')
            corner_t1 = t1_stats.get('corners_avg', 4)
            corner_t2 = t2_stats.get('corners_avg', 4)
            model_scores['corners'] = {'team1': corner_t1, 'team2': corner_t2}

        # --- Modèle Cartons (8) ---
        # Non applicable car pas de données précises sur les cartons dans OpenLigaDB
        
        # --- Modèle Tirs (9) ---
        # Non applicable car pas de données sur les tirs dans OpenLigaDB
        
        # --- Modèle Combiné Final (10) ---
        # Agréger les scores des modèles disponibles
        final_score_t1 = 0
        final_score_t2 = 0
        total_weight = 0

        # Poids pour les modèles disponibles
        weights = {
            'weighted': 0.35,
            'poisson': 0.25,
            'form': 0.15,
            'h2h': 0.10,
            'corners': 0.10,
            # Les autres modèles non disponibles ont un poids de 0
        }

        for model_name in self.models_used:
            w = weights.get(model_name, 0)
            if model_name in model_scores and 'team1' in model_scores[model_name]:
                final_score_t1 += w * model_scores[model_name]['team1']
                final_score_t2 += w * model_scores[model_name]['team2']
                total_weight += w

        if total_weight == 0:
             logger.warning(f"Pas assez de données pour analyser le match {team1_name} vs {team2_name}.")
             return None

        # Normaliser
        final_score_t1 /= total_weight
        final_score_t2 /= total_weight

        # Calcul de la confiance
        num_models_used = len(self.models_used)
        max_models_possible = len(weights.keys()) # 5 modèles possibles
        confidence = min(1.0, num_models_used / max_models_possible)

        # Générer la prédiction
        if final_score_t1 > final_score_t2 * 1.1: # Marge de 10%
            pred_type = "1"
            pred_desc = f"{team1_name} Gagne"
        elif final_score_t2 > final_score_t1 * 1.1:
            pred_type = "2"
            pred_desc = f"{team2_name} Gagne"
        else:
            pred_type = "X"
            pred_desc = "Match Nul"

        prediction_obj = {
            'match_id': match_data['matchID'],
            'league': match_data['leagueName'],
            'team1': team1_name,
            'team2': team2_name,
            'date': match_data['matchDateTime'],
            'final_score_t1': final_score_t1,
            'final_score_t2': final_score_t2,
            'models_used': self.models_used,
            'confidence': confidence,
            'prediction_type': pred_type,
            'prediction_description': pred_desc,
            'raw_model_scores': model_scores
        }

        return prediction_obj

    def _aggregate_stats(self, history: List[Dict]):
        if not history:
            return {}
        
        total_goals = 0
        total_opp_goals = 0
        total_corners = 0
        total_shots = 0 # Approximation
        wins = 0
        draws = 0
        played = len(history)

        for match in history:
            # Déterminer si l'équipe était team1 ou team2 dans le match historique
            # Pour simplification, on suppose qu'elle est toujours "team1" dans l'histo retourné par notre méthode.
            # Sinon, il faudrait passer l'ID de l'équipe cible.
            # On suppose donc que `pointsTeam1` est le score de l'équipe cible.
            goals = match.get('matchResults', [{}])[0].get('pointsTeam1', 0)
            opp_goals = match.get('matchResults', [{}])[0].get('pointsTeam2', 0)
            
            total_goals += goals
            total_opp_goals += opp_goals
            
            # Les corners ne sont pas dans la réponse par défaut. On met une valeur moyenne.
            total_corners += 4.5 # Valeur moyenne par défaut

            # Approximation des tirs à partir des buts et xG simulé
            total_shots += goals * 3 # Approximation grossière

            # Calcul de la forme
            if goals > opp_goals:
                wins += 1
            elif goals == opp_goals:
                draws += 1

        form = (wins * 3 + draws * 1) / (played * 3) if played > 0 else 0.5

        return {
            'goals_avg': total_goals / played if played > 0 else 0,
            'opp_goals_avg': total_opp_goals / played if played > 0 else 0,
            'corners_avg': total_corners / played if played > 0 else 0,
            'shots_avg': total_shots / played if played > 0 else 0,
            'form': form
        }

    def _calculate_form(self, history: List[Dict]):
        if not history:
            return 0.5
        wins = sum(1 for m in history if (m.get('matchResults', [{}])[0].get('pointsTeam1', 0) >
                                          m.get('matchResults', [{}])[0].get('pointsTeam2', 0)))
        played = len(history)
        return wins / played if played > 0 else 0.5

    def _find_h2h(self, history: List[Dict], opponent_name: str):
        h2h = [m for m in history if m['team2']['teamName'] == opponent_name]
        return h2h

    def _get_h2h_score(self, team1_name, team2_name, h2h_exists):
        # Si H2H existe, on donne un léger avantage basé sur les résultats
        # Pour simplification, si H2H existe, on renvoie un score neutre (0.5)
        # Une logique plus poussée pourrait analyser les résultats H2H.
        return 0.5 if h2h_exists else 0.0

    def _analyze_h2h(self, team1_name, team2_name, h2h_exists):
        # Pour simplification, on renvoie un score neutre si H2H existe
        if h2h_exists:
            # Trouver les matchs H2H dans l'history passée de team1
            # (On suppose que la fonction _find_h2h a déjà été appelée et que les données sont disponibles)
            # Pour cet exemple, on ne fait qu'un indicateur booléen.
            return {'team1': 0.55, 'team2': 0.45} # Exemple d'avantage H2H
        return {'team1': 0.5, 'team2': 0.5}


# --- Bot Telegram ---
class TelegramBot:
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.channel = Config.TELEGRAM_CHANNEL_ID

    async def send_predictions(self, predictions: List[Dict]):
        if not predictions:
            logger.info("Aucune prédiction à envoyer.")
            return

        message = self._format_message(predictions)
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                'chat_id': self.channel,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.info("Prédictions envoyées sur Telegram avec succès.")
                        return True
                    else:
                        logger.error(f"Erreur envoi Telegram: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"Exception envoi Telegram: {e}")
            return False

    def _format_message(self, predictions: List[Dict]):
        header = "<b>🏆 PRONOSTICS DU MOMENT (OpenLigaDB) 🏆</b>\n\n"
        body = ""
        for i, pred in enumerate(predictions, 1):
            models_str = ", ".join(pred.get('models_used', []))
            body += (f"<b>{i}. {pred['team1']} vs {pred['team2']}</b>\n"
                     f"🏆 {pred['league']}\n"
                     f"⚡ Confiance: <b>{pred['confidence']:.2%}</b>\n"
                     f"🔮 Prédiction: <b>{pred['prediction_description']}</b>\n"
                     f"📊 Modèles: {models_str}\n"
                     f"🕐 {datetime.fromisoformat(pred['date']).strftime('%d/%m %H:%M')}\n\n")
        footer = "<i>Ces prédictions sont basées sur une analyse algorithmique des données disponibles. Jouez de manière responsable.</i>"
        return header + body + footer


# --- Système Principal ---
class FootballPredictionSystem:
    def __init__(self):
        self.db = Database()
        self.analyzer = MatchAnalyzer()
        self.telegram_bot = TelegramBot()

    async def run_analysis_cycle(self):
        logger.info("--- Démarrage du cycle d'analyse ---")
        async with OpenLigaDBCollector() as collector:
            # 1. Obtenir les ligues
            leagues = await collector.get_available_leagues()
            if not leagues:
                 logger.error("Impossible de récupérer les ligues. Arrêt du cycle.")
                 return

            # Filtrer les ligues pertinentes (exemple basé sur les raccourcis communs ou noms)
            # La structure réelle de `leagues` est [{'leagueShortcut': '...', 'leagueName': '...', ...}]
            relevant_shortcuts = set()
            for item in [
                # Ajouter les raccourcis correspondant à votre liste ici.
                # Ces valeurs sont des exemples et doivent être vérifiées sur OpenLigaDB.
                # Par exemple, pour Bundesliga : 'bl1', 'bl2', 'dfb'
                # Pour Premier League : 'pl' (probable), 'fa' (pour FA Cup)
                # Pour Ligue 1 : 'l1' (probable)
                # Pour Serie A : 'sa' (probable)
                # Pour La Liga : 'll' (probable)
                # Pour d'autres, il faut vérifier l'API.
                # En attendant, on utilise une liste basée sur les noms.
                # On va filtrer par nom pour trouver les codes.
                "Premier League", "Championship", "Ligue 1", "Ligue 2",
                "Bundesliga", "2. Bundesliga", "Serie A", "Serie B",
                "Primera División", "Segunda División", "Eredivisie",
                "Jupiler Pro League", "Primeira Liga", "Liga Portugal 2",
                "Super League", "Süper Lig", "Premier League Russia",
                "Major League Soccer", "Liga MX", "Brasileirão",
                # Coupes
                "DFB-Pokal", "FA Cup", "Coupe de France", "Copa del Rey",
                "Serie A TIM", # Alias possible pour Serie A ?
                # Les sélections internationales sont moins probables d'être disponibles en continu
                # ou nécessitent des codes spécifiques.
                # On se concentre sur les ligues nationales régulières.
            ]:
                for league in leagues:
                    if item.lower() in league.get('leagueName', '').lower():
                         relevant_shortcuts.add(league['leagueShortcut'])
            logger.info(f"Ligues ciblées trouvées: {list(relevant_shortcuts)}")

            all_predictions = []
            # 2. Pour chaque ligue pertinente
            for league_shortcut in relevant_shortcuts:
                # Obtenir la saison courante de la ligue (approximation)
                # On peut essayer d'obtenir le groupe courant pour déduire la saison.
                current_group_info = await collector.get_current_group(league_shortcut)
                # La saison n'est pas directement dans current_group_info.
                # On va supposer une saison plausible, par exemple, 2025 pour les saisons 2024/2025.
                # Une meilleure méthode est de lister les saisons possibles pour un shortcut.
                # Pour l'instant, on fixe à 2025.
                season = 2025 
                logger.debug(f"Recherche matchs pour {league_shortcut} saison {season}")
                matches = await collector.get_todays_matches(league_shortcut, season)
                
                for match in matches:
                    if self.db.was_sent_today(match['matchID']):
                        logger.debug(f"Match {match['matchID']} déjà envoyé aujourd'hui.")
                        continue
                    
                    # Récupérer l'historique des deux équipes
                    hist1 = await collector.get_team_match_history(match['team1']['teamId'])
                    hist2 = await collector.get_team_match_history(match['team2']['teamId'])

                    # Analyser le match
                    prediction = self.analyzer.analyze_match(match, hist1, hist2)
                    
                    if prediction and prediction['confidence'] >= Config.MIN_DATA_CONFIDENCE:
                        all_predictions.append(prediction)
                        self.db.save_prediction(
                            prediction['match_id'], prediction['league'], prediction['team1'], prediction['team2'],
                            prediction['date'], prediction['confidence'], prediction
                        )

            # 3. Trier par confiance et sélectionner les 5 meilleurs
            all_predictions.sort(key=lambda x: x['confidence'], reverse=True)
            top_5_predictions = all_predictions[:5]

            # 4. Envoyer sur Telegram
            await self.telegram_bot.send_predictions(top_5_predictions)

        logger.info("--- Fin du cycle d'analyse ---")


# --- Programme Principal ---
async def main():
    system = FootballPredictionSystem()
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        system.run_analysis_cycle,
        trigger=IntervalTrigger(minutes=Config.RUN_INTERVAL_MINUTES),
        id='analysis_job',
        name='Analyse Football Toutes Ligues',
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Planificateur démarré, intervalle: {Config.RUN_INTERVAL_MINUTES} minutes.")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Arrêt demandé...")
        scheduler.shutdown(wait=True)
        system.db.close()

if __name__ == "__main__":
    asyncio.run(main())