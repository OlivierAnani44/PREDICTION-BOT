"""
Base de données pour cache et historique
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class PredictionDatabase:
    def __init__(self, db_path: str = "predictions.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialise la base de données"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table des matchs analysés
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analyzed_matches (
                match_id TEXT PRIMARY KEY,
                league TEXT,
                home_team TEXT,
                away_team TEXT,
                match_date TEXT,
                analysis_data TEXT,
                confidence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table des prédictions sélectionnées
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS selected_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                selection_date TEXT,
                match_id TEXT,
                rank INTEGER,
                telegram_sent BOOLEAN DEFAULT 0,
                sent_at TIMESTAMP,
                FOREIGN KEY (match_id) REFERENCES analyzed_matches (match_id)
            )
        ''')
        
        # Table cache ESPN
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS espn_cache (
                cache_key TEXT PRIMARY KEY,
                data TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_analysis(self, match_id: str, league: str, 
                     home_team: str, away_team: str,
                     match_date: str, analysis: Dict) -> bool:
        """Sauvegarde une analyse"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO analyzed_matches 
                (match_id, league, home_team, away_team, match_date, analysis_data, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                match_id,
                league,
                home_team,
                away_team,
                match_date,
                json.dumps(analysis),
                analysis.get('confidence', 0.0)
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde analyse: {e}")
            return False
    
    def save_selection(self, selection_date: str, predictions: List[Dict]) -> bool:
        """Sauvegarde une sélection de pronostics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for i, pred in enumerate(predictions, 1):
                cursor.execute('''
                    INSERT INTO selected_predictions 
                    (selection_date, match_id, rank)
                    VALUES (?, ?, ?)
                ''', (selection_date, pred['match_id'], i))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde sélection: {e}")
            return False
    
    def mark_telegram_sent(self, match_id: str) -> bool:
        """Marque un pronostic comme envoyé sur Telegram"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE selected_predictions 
                SET telegram_sent = 1, sent_at = CURRENT_TIMESTAMP
                WHERE match_id = ? AND telegram_sent = 0
            ''', (match_id,))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Erreur marquage Telegram: {e}")
            return False
    
    def get_recent_predictions(self, days: int = 7) -> List[Dict]:
        """Récupère les prédictions récentes"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT sp.*, am.*
                FROM selected_predictions sp
                JOIN analyzed_matches am ON sp.match_id = am.match_id
                WHERE date(sp.selection_date) >= date('now', ?)
                ORDER BY sp.selection_date DESC, sp.rank ASC
            ''', (f'-{days} days',))
            
            rows = cursor.fetchall()
            predictions = []
            
            for row in rows:
                pred = dict(row)
                if pred.get('analysis_data'):
                    pred['analysis'] = json.loads(pred['analysis_data'])
                    del pred['analysis_data']
                predictions.append(pred)
            
            conn.close()
            return predictions
            
        except Exception as e:
            logger.error(f"Erreur récupération prédictions: {e}")
            return []
    
    def set_cache(self, key: str, data: Dict, ttl_hours: int = 6):
        """Met en cache des données ESPN"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            expires_at = datetime.now() + timedelta(hours=ttl_hours)
            
            cursor.execute('''
                INSERT OR REPLACE INTO espn_cache 
                (cache_key, data, expires_at)
                VALUES (?, ?, ?)
            ''', (key, json.dumps(data), expires_at.isoformat()))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Erreur cache: {e}")
    
    def get_cache(self, key: str) -> Optional[Dict]:
        """Récupère des données du cache"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT data, expires_at 
                FROM espn_cache 
                WHERE cache_key = ? AND expires_at > CURRENT_TIMESTAMP
            ''', (key,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return json.loads(row[0])
            return None
            
        except Exception as e:
            logger.error(f"Erreur récupération cache: {e}")
            return None
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Nettoie les anciennes données"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Nettoyer analyses anciennes
            cursor.execute('''
                DELETE FROM analyzed_matches 
                WHERE date(created_at) < date('now', ?)
            ''', (f'-{days_to_keep} days',))
            
            # Nettoyer cache expiré
            cursor.execute('''
                DELETE FROM espn_cache 
                WHERE expires_at <= CURRENT_TIMESTAMP
            ''')
            
            conn.commit()
            conn.close()
            logger.info(f"Nettoyage données > {days_to_keep} jours")
            
        except Exception as e:
            logger.error(f"Erreur nettoyage: {e}")