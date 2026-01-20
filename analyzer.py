"""
Analyse statistique complète avec modèles mathématiques
"""

import math
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
from config import MODEL_CONFIG

logger = logging.getLogger(__name__)

class MatchAnalyzer:
    def __init__(self):
        self.config = MODEL_CONFIG
    
    def analyze_match(self, match_data: Dict, 
                     team1_history: List[Dict], 
                     team2_history: List[Dict],
                     h2h_history: List[Dict]) -> Dict:
        """
        Analyse complète d'un match avec toutes les données
        Retourne un score de confiance et des prédictions
        """
        try:
            home_team = match_data['home_team']
            away_team = match_data['away_team']
            
            # 1. Analyse H2H (Confrontations directes)
            h2h_score = self._analyze_h2h(h2h_history, home_team['id'], away_team['id'])
            
            # 2. Analyse forme récente
            home_form = self._analyze_recent_form(team1_history)
            away_form = self._analyze_recent_form(team2_history)
            
            # 3. Analyse statistiques avancées
            home_stats = self._analyze_team_stats(team1_history)
            away_stats = self._analyze_team_stats(team2_history)
            
            # 4. Avantage domicile
            venue_advantage = self._analyze_venue_advantage(home_team['id'], team1_history)
            
            # 5. Calcul du score global
            final_score = self._calculate_final_score(
                h2h_score, home_form, away_form, home_stats, away_stats, venue_advantage
            )
            
            # 6. Prédictions spécifiques
            predictions = self._generate_predictions(
                h2h_score, home_form, away_form, home_stats, away_stats, venue_advantage
            )
            
            # 7. Score de confiance
            confidence_score = self._calculate_confidence(
                len(h2h_history),
                len(team1_history),
                len(team2_history),
                final_score['consistency']
            )
            
            return {
                'match_id': match_data['match_id'],
                'home_team': home_team['name'],
                'away_team': away_team['name'],
                'league': match_data['league'],
                'date': match_data['date'],
                
                'analysis': {
                    'h2h_analysis': h2h_score,
                    'home_form': home_form,
                    'away_form': away_form,
                    'home_stats': home_stats,
                    'away_stats': away_stats,
                    'venue_advantage': venue_advantage,
                },
                
                'final_score': final_score,
                'predictions': predictions,
                'confidence': confidence_score,
                
                'data_quality': {
                    'h2h_matches': len(h2h_history),
                    'home_matches': len(team1_history),
                    'away_matches': len(team2_history),
                    'data_freshness': self._check_data_freshness(h2h_history, team1_history, team2_history),
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse match: {e}")
            return None
    
    def _analyze_h2h(self, h2h_matches: List[Dict], home_id: str, away_id: str) -> Dict:
        """Analyse des confrontations directes"""
        if not h2h_matches:
            return {'score': 0.5, 'trend': 'NEUTRAL', 'details': 'Aucune donnée H2H'}
        
        # Filtrer les matchs récents (derniers 2 ans)
        recent_h2h = []
        cutoff_date = datetime.now() - timedelta(days=730)
        
        for match in h2h_matches:
            try:
                match_date = datetime.fromisoformat(match['date'].replace('Z', '+00:00'))
                if match_date > cutoff_date:
                    recent_h2h.append(match)
            except:
                continue
        
        if not recent_h2h:
            return {'score': 0.5, 'trend': 'NEUTRAL', 'details': 'Données H2H trop anciennes'}
        
        # Calculer les statistiques H2H
        home_wins = 0
        away_wins = 0
        draws = 0
        home_goals = 0
        away_goals = 0
        
        for match in recent_h2h:
            if match['result'] == 'WIN':
                home_wins += 1
            elif match['result'] == 'LOSS':
                away_wins += 1
            else:
                draws += 1
            
            home_goals += match['score_team']
            away_goals += match['score_opponent']
        
        total_matches = len(recent_h2h)
        
        # Score H2H (0 à 1, 0.5 = neutre)
        h2h_score = (home_wins + (draws * 0.5)) / total_matches
        
        # Déterminer la tendance
        if h2h_score >= 0.7:
            trend = 'STRONG_HOME'
        elif h2h_score >= 0.6:
            trend = 'MODERATE_HOME'
        elif h2h_score <= 0.3:
            trend = 'STRONG_AWAY'
        elif h2h_score <= 0.4:
            trend = 'MODERATE_AWAY'
        else:
            trend = 'BALANCED'
        
        return {
            'score': round(h2h_score, 3),
            'trend': trend,
            'details': {
                'matches': total_matches,
                'home_wins': home_wins,
                'away_wins': away_wins,
                'draws': draws,
                'avg_home_goals': round(home_goals / total_matches, 2),
                'avg_away_goals': round(away_goals / total_matches, 2),
                'recent_matches': len(recent_h2h),
            }
        }
    
    def _analyze_recent_form(self, team_history: List[Dict]) -> Dict:
        """Analyse de la forme récente (10 derniers matchs)"""
        if not team_history:
            return {'score': 0.5, 'form': 'UNKNOWN', 'momentum': 0}
        
        recent_matches = team_history[-10:]  # 10 derniers matchs
        if not recent_matches:
            return {'score': 0.5, 'form': 'UNKNOWN', 'momentum': 0}
        
        # Calculer les points (3 pour win, 1 pour draw, 0 pour loss)
        total_points = 0
        results = []
        
        for match in recent_matches:
            if match['result'] == 'WIN':
                total_points += 3
                results.append(1.0)
            elif match['result'] == 'DRAW':
                total_points += 1
                results.append(0.5)
            else:
                results.append(0.0)
        
        max_points = len(recent_matches) * 3
        form_score = total_points / max_points
        
        # Calculer le momentum (tendance des 5 derniers vs 5 précédents)
        if len(results) >= 5:
            last_5 = statistics.mean(results[-5:])
            previous_5 = statistics.mean(results[-10:-5]) if len(results) >= 10 else 0.5
            momentum = last_5 - previous_5
        else:
            momentum = 0
        
        # Déterminer la forme
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
        
        return {
            'score': round(form_score, 3),
            'form': form,
            'momentum': round(momentum, 3),
            'details': {
                'matches': len(recent_matches),
                'points': total_points,
                'max_points': max_points,
                'last_results': results[-5:] if len(results) >= 5 else results,
            }
        }
    
    def _analyze_team_stats(self, team_history: List[Dict]) -> Dict:
        """Analyse statistique avancée de l'équipe"""
        if not team_history:
            return {'score': 0.5, 'offense': 0.5, 'defense': 0.5}
        
        # Calculer les moyennes
        goals_scored = []
        goals_conceded = []
        
        for match in team_history:
            goals_scored.append(match['score_team'])
            goals_conceded.append(match['score_opponent'])
        
        if not goals_scored:
            return {'score': 0.5, 'offense': 0.5, 'defense': 0.5}
        
        avg_scored = statistics.mean(goals_scored)
        avg_conceded = statistics.mean(goals_conceded)
        
        # Normaliser (basé sur des moyennes de ligue)
        # Note: À ajuster selon la ligue
        max_avg_goals = 3.0  # Maximum moyen de buts par match
        
        offense_score = min(avg_scored / max_avg_goals, 1.0)
        defense_score = 1.0 - min(avg_conceded / max_avg_goals, 1.0)
        
        # Score global
        stats_score = (offense_score * 0.6 + defense_score * 0.4)
        
        # Consistance (écart-type inverse)
        if len(goals_scored) > 1:
            consistency = 1.0 / (1.0 + statistics.stdev(goals_scored))
        else:
            consistency = 0.5
        
        return {
            'score': round(stats_score, 3),
            'offense': round(offense_score, 3),
            'defense': round(defense_score, 3),
            'consistency': round(consistency, 3),
            'details': {
                'avg_goals_scored': round(avg_scored, 2),
                'avg_goals_conceded': round(avg_conceded, 2),
                'matches_analyzed': len(team_history),
            }
        }
    
    def _analyze_venue_advantage(self, team_id: str, team_history: List[Dict]) -> Dict:
        """Analyse de l'avantage à domicile"""
        if not team_history:
            return {'score': 0.55, 'advantage': 'NORMAL'}  # Léger avantage domicile par défaut
        
        home_matches = [m for m in team_history if m.get('is_home')]
        away_matches = [m for m in team_history if not m.get('is_home')]
        
        if not home_matches or not away_matches:
            return {'score': 0.55, 'advantage': 'NORMAL'}
        
        # Calculer les performances
        home_points = sum([3 if m['result'] == 'WIN' else 1 if m['result'] == 'DRAW' else 0 
                          for m in home_matches])
        away_points = sum([3 if m['result'] == 'WIN' else 1 if m['result'] == 'DRAW' else 0 
                          for m in away_matches])
        
        home_ppg = home_points / len(home_matches)
        away_ppg = away_points / len(away_matches)
        
        # Score d'avantage (normalisé)
        if away_ppg > 0:
            venue_score = min(home_ppg / away_ppg / 3, 1.0)  # Cap à 1.0
        else:
            venue_score = 0.7  # Valeur par défaut si pas de points à l'extérieur
        
        # Ajuster pour la moyenne
        venue_score = 0.5 + (venue_score - 0.5) * 0.5
        
        # Déterminer le niveau d'avantage
        if venue_score >= 0.65:
            advantage = 'STRONG'
        elif venue_score >= 0.6:
            advantage = 'MODERATE'
        elif venue_score >= 0.55:
            advantage = 'SLIGHT'
        else:
            advantage = 'NONE'
        
        return {
            'score': round(venue_score, 3),
            'advantage': advantage,
            'details': {
                'home_matches': len(home_matches),
                'away_matches': len(away_matches),
                'home_ppg': round(home_ppg, 2),
                'away_ppg': round(away_ppg, 2),
            }
        }
    
    def _calculate_final_score(self, h2h: Dict, home_form: Dict, away_form: Dict,
                              home_stats: Dict, away_stats: Dict, venue: Dict) -> Dict:
        """Calcule le score final pondéré"""
        
        weights = self.config
        
        # Scores individuels
        h2h_val = h2h['score']
        home_form_val = home_form['score']
        away_form_val = away_form['score']
        home_stats_val = home_stats['score']
        away_stats_val = away_stats['score']
        venue_val = venue['score']
        
        # Formule: Home advantage + Différence de forme + Différence stats + H2H
        base_score = venue_val
        
        # Ajouter différence de forme
        form_diff = home_form_val - away_form_val
        form_impact = form_diff * weights['weight_form']
        
        # Ajouter différence de stats
        stats_diff = home_stats_val - away_stats_val
        stats_impact = stats_diff * weights['weight_stats']
        
        # Ajouter H2H (ajusté pour l'avantage domicile)
        h2h_impact = (h2h_val - 0.5) * weights['weight_h2h']
        
        # Calcul final
        final_raw = base_score + form_impact + stats_impact + h2h_impact
        
        # Normaliser entre 0 et 1
        final_score = max(0.0, min(1.0, final_raw))
        
        # Calculer la consistance
        scores = [h2h_val, home_form_val, away_form_val, home_stats_val, away_stats_val, venue_val]
        consistency = 1.0 - statistics.stdev(scores) if len(scores) > 1 else 0.5
        
        return {
            'home_win_prob': round(final_score, 3),
            'draw_prob': round(0.1, 3),  # Approximation
            'away_win_prob': round(1.0 - final_score - 0.1, 3),
            'consistency': round(consistency, 3),
            'raw_score': final_raw,
        }
    
    def _generate_predictions(self, h2h: Dict, home_form: Dict, away_form: Dict,
                             home_stats: Dict, away_stats: Dict, venue: Dict) -> Dict:
        """Génère des prédictions spécifiques"""
        
        final = self._calculate_final_score(h2h, home_form, away_form, home_stats, away_stats, venue)
        
        # Probabilité de victoire domicile
        home_win_prob = final['home_win_prob']
        
        # Recommandation
        if home_win_prob >= 0.7:
            recommendation = 'STRONG_HOME_WIN'
            confidence = 'HIGH'
        elif home_win_prob >= 0.6:
            recommendation = 'HOME_WIN'
            confidence = 'MEDIUM'
        elif home_win_prob >= 0.55:
            recommendation = 'HOME_WIN_OR_DRAW'
            confidence = 'LOW_MEDIUM'
        elif home_win_prob <= 0.3:
            recommendation = 'STRONG_AWAY_WIN'
            confidence = 'HIGH'
        elif home_win_prob <= 0.4:
            recommendation = 'AWAY_WIN'
            confidence = 'MEDIUM'
        elif home_win_prob <= 0.45:
            recommendation = 'AWAY_WIN_OR_DRAW'
            confidence = 'LOW_MEDIUM'
        else:
            recommendation = 'DRAW_OR_UNDER'
            confidence = 'LOW'
        
        # Prédiction de score (simplifiée)
        avg_home_goals = h2h.get('details', {}).get('avg_home_goals', 1.5)
        avg_away_goals = h2h.get('details', {}).get('avg_away_goals', 1.0)
        
        predicted_home = round(avg_home_goals * home_stats['offense'] * venue['score'], 1)
        predicted_away = round(avg_away_goals * away_stats['offense'] * (1.0 / venue['score']), 1)
        
        # Ajuster pour les scores entiers probables
        likely_home = round(predicted_home)
        likely_away = round(predicted_away)
        
        return {
            'recommendation': recommendation,
            'confidence_level': confidence,
            'predicted_score': f"{likely_home}-{likely_away}",
            'expected_goals': f"{predicted_home:.1f}-{predicted_away:.1f}",
            'over_under': 'OVER 2.5' if (predicted_home + predicted_away) > 2.5 else 'UNDER 2.5',
            'both_teams_score': 'YES' if predicted_home > 0.5 and predicted_away > 0.5 else 'NO',
        }
    
    def _calculate_confidence(self, h2h_count: int, home_history_count: int,
                            away_history_count: int, consistency: float) -> float:
        """Calcule le score de confiance global"""
        
        # Facteur quantité de données H2H
        if h2h_count >= 5:
            h2h_factor = 1.0
        elif h2h_count >= 3:
            h2h_factor = 0.8
        elif h2h_count >= 1:
            h2h_factor = 0.6
        else:
            h2h_factor = 0.3
        
        # Facteur données historiques
        home_data_factor = min(home_history_count / 10, 1.0)
        away_data_factor = min(away_history_count / 10, 1.0)
        data_factor = (home_data_factor + away_data_factor) / 2
        
        # Facteur consistance
        consistency_factor = consistency
        
        # Calcul final
        confidence = (h2h_factor * 0.4 + data_factor * 0.4 + consistency_factor * 0.2)
        
        return round(confidence, 3)
    
    def _check_data_freshness(self, h2h_history: List[Dict], 
                            home_history: List[Dict], 
                            away_history: List[Dict]) -> str:
        """Vérifie la fraîcheur des données"""
        
        all_matches = h2h_history + home_history + away_history
        if not all_matches:
            return "INSUFFICIENT_DATA"
        
        # Trouver le match le plus récent
        recent_dates = []
        
        for match in all_matches:
            try:
                match_date = datetime.fromisoformat(match['date'].replace('Z', '+00:00'))
                recent_dates.append(match_date)
            except:
                continue
        
        if not recent_dates:
            return "UNKNOWN"
        
        most_recent = max(recent_dates)
        days_ago = (datetime.now() - most_recent).days
        
        if days_ago <= 7:
            return "VERY_FRESH"
        elif days_ago <= 30:
            return "FRESH"
        elif days_ago <= 90:
            return "ACCEPTABLE"
        else:
            return "STALE"