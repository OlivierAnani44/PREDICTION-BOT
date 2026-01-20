"""
Gestion centralisée des variables d'environnement
"""

import os
import sys
from typing import Optional, List

class EnvironmentManager:
    """Gère les variables d'environnement de Railway"""
    
    REQUIRED_VARS = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHANNEL_ID"
    ]
    
    OPTIONAL_VARS = {
        "TIMEZONE": "Europe/Paris",
        "DAILY_TIME": "07:00",
        "MIN_CONFIDENCE": "0.65",
        "MIN_H2H_MATCHES": "3",
        "RECENT_MATCHES_COUNT": "10",
        "WEIGHT_H2H": "0.30",
        "WEIGHT_FORM": "0.25",
        "WEIGHT_STATS": "0.25",
        "WEIGHT_VENUE": "0.20",
        "DATA_FRESHNESS_DAYS": "30",
        "LOG_LEVEL": "INFO",
        "CLEANUP_DAYS": "30",
        "RETRY_ATTEMPTS": "3",
        "CACHE_DURATION": "3600",
        "BACKUP_ENABLED": "false",
        "TELEGRAM_ADMIN_ID": "",
        "DB_PATH": "predictions.db"
    }
    
    @classmethod
    def validate_environment(cls) -> List[str]:
        """Valide que toutes les variables requises sont présentes"""
        errors = []
        
        for var in cls.REQUIRED_VARS:
            if not os.getenv(var):
                errors.append(f"{var} est requis mais non défini")
        
        return errors
    
    @classmethod
    def get_required(cls, var_name: str) -> str:
        """Récupère une variable requise"""
        value = os.getenv(var_name)
        if not value:
            raise ValueError(f"Variable requise manquante: {var_name}")
        return value
    
    @classmethod
    def get_optional(cls, var_name: str, default: Optional[str] = None) -> str:
        """Récupère une variable optionnelle"""
        return os.getenv(var_name, default or cls.OPTIONAL_VARS.get(var_name, ""))
    
    @classmethod
    def get_int(cls, var_name: str, default: int = 0) -> int:
        """Récupère un entier depuis l'environnement"""
        try:
            return int(cls.get_optional(var_name, str(default)))
        except ValueError:
            return default
    
    @classmethod
    def get_float(cls, var_name: str, default: float = 0.0) -> float:
        """Récupère un float depuis l'environnement"""
        try:
            return float(cls.get_optional(var_name, str(default)))
        except ValueError:
            return default
    
    @classmethod
    def get_bool(cls, var_name: str, default: bool = False) -> bool:
        """Récupère un booléen depuis l'environnement"""
        value = cls.get_optional(var_name, str(default)).lower()
        return value in ["true", "1", "yes", "y", "on"]
    
    @classmethod
    def print_environment(cls):
        """Affiche la configuration de l'environnement"""
        print("🔧 CONFIGURATION ENVIRONNEMENT RAILWAY")
        print("=" * 50)
        
        print("\n📋 VARIABLES REQUISES:")
        for var in cls.REQUIRED_VARS:
            value = os.getenv(var)
            status = "✅ Défini" if value else "❌ Manquant"
            masked = f"{value[:5]}..." + "***" if value and len(value) > 8 else "Non défini"
            print(f"  {var}: {status} ({masked})")
        
        print("\n⚙️ VARIABLES OPTIONNELLES:")
        for var, default in cls.OPTIONAL_VARS.items():
            value = os.getenv(var, default)
            source = "Environnement" if os.getenv(var) else "Défaut"
            print(f"  {var}: {value} ({source})")
        
        print("\n" + "=" * 50)
    
    @classmethod
    def generate_railway_template(cls) -> str:
        """Génère un template pour Railway variables"""
        template = "# Railway Environment Variables Template\n\n"
        
        template += "# REQUIRED VARIABLES - MUST BE SET\n"
        for var in cls.REQUIRED_VARS:
            template += f"{var}=\n"
        
        template += "\n# OPTIONAL VARIABLES\n"
        for var, default in cls.OPTIONAL_VARS.items():
            template += f"# {var}={default}\n"
        
        return template