"""
Collecte toutes les données ESPN pour toutes les ligues
"""

import requests
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
from config import ESPN_BASE_URL, LEAGUE_MAPPING

logger = logging.getLogger(__name__)

class ESPNDataCollector:
    def __init__(self):
        self.session = None
        self.cache = {}
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
    
    async def fetch_all_today_matches(self) -> List[Dict]:
        """Récupère TOUS les matchs du jour pour TOUTES les ligues"""
        logger.info("📡 Début collecte de TOUTES les ligues ESPN...")
        
        all_matches = []
        today = datetime.now().strftime("%Y%m%d")
        
        # Limiter le nombre de requêtes simultanées
        semaphore = asyncio.Semaphore(10)
        
        async def fetch_league(league_code, league_path):
            async with semaphore:
                try:
                    url = f"{ESPN_BASE_URL}/{league_path}/scoreboard"
                    params = {"dates": today, "limit": 100}
                    
                    async with self.session.get(url, params=params, timeout=30) as response:
                        if response.status == 200:
                            data = await response.json()
                            matches = self._extract_matches(data, league_code)
                            
                            if matches:
                                logger.info(f"✅ {league_code}: {len(matches)} match(s)")
                                return matches
                except Exception as e:
                    logger.error(f"❌ Erreur {league_code}: {str(e)[:50]}")
                return []
        
        # Lancer toutes les requêtes en parallèle
        tasks = []
        for league_code, league_path in LEAGUE_MAPPING.items():
            task = fetch_league(league_code, league_path)
            tasks.append(task)
        
        # Attendre tous les résultats
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combiner tous les matchs
        for result in results:
            if isinstance(result, list):
                all_matches.extend(result)
        
        logger.info(f"📊 Total: {len(all_matches)} matchs collectés")
        return all_matches
    
    def _extract_matches(self, data: Dict, league_code: str) -> List[Dict]:
        """Extrait les données de match depuis la réponse ESPN"""
        matches = []
        
        if 'events' not in data:
            return matches
        
        for event in data['events']:
            try:
                # Extraire les équipes
                competition = event.get('competitions', [{}])[0]
                competitors = competition.get('competitors', [])
                
                if len(competitors) != 2:
                    continue
                
                home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                
                if not home or not away:
                    continue
                
                # Informations de base
                match_data = {
                    'match_id': event.get('id'),
                    'league': league_code,
                    'date': event.get('date'),
                    'status': event.get('status', {}).get('type', {}).get('description', 'SCHEDULED'),
                    
                    'home_team': {
                        'id': home.get('team', {}).get('id'),
                        'name': home.get('team', {}).get('displayName'),
                        'short_name': home.get('team', {}).get('abbreviation', ''),
                        'score': int(home.get('score', 0)),
                    },
                    
                    'away_team': {
                        'id': away.get('team', {}).get('id'),
                        'name': away.get('team', {}).get('displayName'),
                        'short_name': away.get('team', {}).get('abbreviation', ''),
                        'score': int(away.get('score', 0)),
                    },
                    
                    'competition': {
                        'name': competition.get('name', ''),
                        'type': competition.get('type', ''),
                    },
                    
                    'raw_data': event  # Conserver pour analyse approfondie
                }
                
                matches.append(match_data)
                
            except Exception as e:
                logger.error(f"Erreur extraction match: {e}")
                continue
        
        return matches
    
    async def fetch_team_history(self, team_id: str, league_code: str, limit: int = 15) -> List[Dict]:
        """Récupère l'historique d'une équipe"""
        try:
            league_path = LEAGUE_MAPPING.get(league_code)
            if not league_path:
                return []
            
            # ESPN endpoint pour historique équipe
            url = f"{ESPN_BASE_URL}/{league_path}/teams/{team_id}/schedule"
            
            async with self.session.get(url, timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._extract_team_history(data, team_id, limit)
                    
        except Exception as e:
            logger.error(f"Erreur historique équipe {team_id}: {e}")
        
        return []
    
    def _extract_team_history(self, data: Dict, team_id: str, limit: int) -> List[Dict]:
        """Extrait l'historique de matchs d'une équipe"""
        matches = []
        
        if 'events' not in data:
            return matches
        
        for event in data['events'][-limit:]:  # Derniers matchs
            try:
                competition = event.get('competitions', [{}])[0]
                competitors = competition.get('competitors', [])
                
                if len(competitors) != 2:
                    continue
                
                # Trouver notre équipe et l'adversaire
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
                
                # Déterminer le résultat
                result = self._determine_result(team_data, opponent_data)
                
                match_info = {
                    'date': event.get('date'),
                    'competition': competition.get('name', ''),
                    'home_away': team_data.get('homeAway'),
                    'opponent': opponent_data.get('team', {}).get('displayName'),
                    'opponent_id': opponent_data.get('team', {}).get('id'),
                    'score_team': int(team_data.get('score', 0)),
                    'score_opponent': int(opponent_data.get('score', 0)),
                    'result': result,  # WIN/DRAW/LOSS
                    'is_home': team_data.get('homeAway') == 'home',
                }
                
                matches.append(match_info)
                
            except Exception as e:
                logger.error(f"Erreur extraction historique: {e}")
                continue
        
        return matches
    
    async def fetch_h2h_history(self, team1_id: str, team2_id: str, league_code: str) -> List[Dict]:
        """Récupère l'historique des confrontations directes"""
        try:
            # Pour ESPN, on doit chercher dans les historiques des deux équipes
            team1_history = await self.fetch_team_history(team1_id, league_code, 50)
            team2_history = await self.fetch_team_history(team2_id, league_code, 50)
            
            # Filtrer pour trouver les matchs communs
            h2h_matches = []
            
            # Créer un set d'identifiants de matchs pour équipe 1
            team1_match_ids = set()
            team1_match_map = {}
            
            for match in team1_history:
                if match.get('opponent_id') == team2_id:
                    # Créer un ID unique basé sur la date et les équipes
                    match_date = match.get('date', '')[:10]  # YYYY-MM-DD
                    match_id = f"{match_date}_{team1_id}_{team2_id}"
                    team1_match_ids.add(match_id)
                    team1_match_map[match_id] = match
            
            # Vérifier dans l'historique équipe 2
            for match in team2_history:
                if match.get('opponent_id') == team1_id:
                    match_date = match.get('date', '')[:10]
                    match_id = f"{match_date}_{team2_id}_{team1_id}"
                    
                    if match_id in team1_match_ids:
                        # Trouvé un match H2H
                        h2h_match = team1_match_map.get(match_id)
                        if h2h_match:
                            h2h_matches.append(h2h_match)
            
            return h2h_matches
            
        except Exception as e:
            logger.error(f"Erreur H2H {team1_id}-{team2_id}: {e}")
            return []
    
    def _determine_result(self, team_data: Dict, opponent_data: Dict) -> str:
        """Détermine le résultat d'un match"""
        team_score = int(team_data.get('score', 0))
        opponent_score = int(opponent_data.get('score', 0))
        
        if team_score > opponent_score:
            return 'WIN'
        elif team_score < opponent_score:
            return 'LOSS'
        else:
            return 'DRAW'