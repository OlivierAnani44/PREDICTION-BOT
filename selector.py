"""
Sélectionne les 5 meilleurs pronostics selon plusieurs critères
"""

import asyncio
from typing import List, Dict, Tuple
import logging
from datetime import datetime
from config import PRIORITY_LEAGUES, MODEL_CONFIG

logger = logging.getLogger(__name__)

class PredictionSelector:
    def __init__(self):
        self.min_confidence = MODEL_CONFIG['min_confidence']
    
    async def select_top_predictions(self, all_analyses: List[Dict], limit: int = 5) -> List[Dict]:
        """
        Sélectionne les meilleurs pronostics selon:
        1. Score de confiance
        2. Quantité de données H2H
        3. Fraîcheur des données
        4. Priorité de la ligue
        5. Consistance des indicateurs
        """
        logger.info(f"🎯 Sélection parmi {len(all_analyses)} analyses...")
        
        if not all_analyses:
            return []
        
        # Filtrer les analyses valides
        valid_analyses = []
        for analysis in all_analyses:
            if analysis and self._is_valid_analysis(analysis):
                valid_analyses.append(analysis)
        
        logger.info(f"✅ Analyses valides: {len(valid_analyses)}")
        
        if not valid_analyses:
            return []
        
        # Trier par score composite
        sorted_analyses = sorted(
            valid_analyses,
            key=lambda x: self._calculate_composite_score(x),
            reverse=True
        )
        
        # Prendre les meilleurs
        top_predictions = sorted_analyses[:limit]
        
        # Log des sélections
        for i, pred in enumerate(top_predictions, 1):
            logger.info(f"🏆 Top {i}: {pred['home_team']} vs {pred['away_team']} "
                       f"(Conf: {pred['confidence']})")
        
        return top_predictions
    
    def _is_valid_analysis(self, analysis: Dict) -> bool:
        """Vérifie si l'analyse est valide pour sélection"""
        
        # Vérifier confiance minimale
        if analysis['confidence'] < self.min_confidence:
            return False
        
        # Vérifier données minimales
        data_quality = analysis['data_quality']
        
        if data_quality['data_freshness'] in ["STALE", "INSUFFICIENT_DATA"]:
            return False
        
        # Vérifier suffisamment de données H2H pour les matchs prioritaires
        league = analysis['league']
        h2h_matches = data_quality['h2h_matches']
        
        if league in PRIORITY_LEAGUES and h2h_matches < 2:
            return False
        
        # Vérifier consistance
        consistency = analysis['final_score']['consistency']
        if consistency < 0.3:  # Trop d'incohérence
            return False
        
        return True
    
    def _calculate_composite_score(self, analysis: Dict) -> float:
        """
        Calcule un score composite pour le classement
        Plus le score est élevé, meilleur est le pronostic
        """
        
        # 1. Score de confiance de base (40%)
        base_score = analysis['confidence'] * 0.4
        
        # 2. Bonus pour données H2H (25%)
        h2h_bonus = self._calculate_h2h_bonus(analysis)
        
        # 3. Bonus pour ligue prioritaire (15%)
        league_bonus = self._calculate_league_bonus(analysis['league'])
        
        # 4. Bonus pour fraîcheur des données (10%)
        freshness_bonus = self._calculate_freshness_bonus(analysis['data_quality']['data_freshness'])
        
        # 5. Bonus pour consistance (10%)
        consistency_bonus = analysis['final_score']['consistency'] * 0.1
        
        # Score total
        total_score = (base_score + h2h_bonus + league_bonus + 
                      freshness_bonus + consistency_bonus)
        
        return total_score
    
    def _calculate_h2h_bonus(self, analysis: Dict) -> float:
        """Bonus basé sur la qualité des données H2H"""
        h2h_matches = analysis['data_quality']['h2h_matches']
        
        if h2h_matches >= 5:
            return 0.25  # Maximum
        elif h2h_matches >= 3:
            return 0.20
        elif h2h_matches >= 2:
            return 0.15
        elif h2h_matches == 1:
            return 0.10
        else:
            return 0.05
    
    def _calculate_league_bonus(self, league_code: str) -> float:
        """Bonus pour ligue prioritaire"""
        if league_code in PRIORITY_LEAGUES:
            return 0.15
        else:
            return 0.05
    
    def _calculate_freshness_bonus(self, freshness: str) -> float:
        """Bonus pour fraîcheur des données"""
        if freshness == "VERY_FRESH":
            return 0.10
        elif freshness == "FRESH":
            return 0.08
        elif freshness == "ACCEPTABLE":
            return 0.05
        else:
            return 0.0
    
    def generate_selection_report(self, top_predictions: List[Dict]) -> Dict:
        """Génère un rapport de sélection"""
        
        report = {
            'total_analyzed': len(top_predictions),
            'selection_date': datetime.now().isoformat(),
            'average_confidence': 0.0,
            'by_league': {},
            'risk_profile': self._calculate_risk_profile(top_predictions),
            'predictions': []
        }
        
        # Calculer statistiques
        confidences = []
        for pred in top_predictions:
            confidences.append(pred['confidence'])
            
            # Statistiques par ligue
            league = pred['league']
            report['by_league'][league] = report['by_league'].get(league, 0) + 1
            
            # Ajouter prédiction formatée
            report['predictions'].append({
                'match': f"{pred['home_team']} vs {pred['away_team']}",
                'league': league,
                'confidence': pred['confidence'],
                'recommendation': pred['predictions']['recommendation'],
                'predicted_score': pred['predictions']['predicted_score'],
                'data_quality': pred['data_quality'],
            })
        
        if confidences:
            report['average_confidence'] = round(sum(confidences) / len(confidences), 3)
        
        return report
    
    def _calculate_risk_profile(self, predictions: List[Dict]) -> str:
        """Détermine le profil de risque global"""
        if not predictions:
            return "UNKNOWN"
        
        avg_confidence = sum(p['confidence'] for p in predictions) / len(predictions)
        
        if avg_confidence >= 0.8:
            return "LOW_RISK"
        elif avg_confidence >= 0.7:
            return "MODERATE_RISK"
        elif avg_confidence >= 0.65:
            return "HIGH_RISK"
        else:
            return "VERY_HIGH_RISK"