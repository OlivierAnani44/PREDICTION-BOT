"""
Configuration sécurisée avec validation Railway
"""

import os
import logging
from environment import EnvironmentManager

# Valider l'environnement au démarrage
env_errors = EnvironmentManager.validate_environment()
if env_errors:
    for error in env_errors:
        print(f"❌ {error}")
    print("\n🚨 Définissez les variables dans Railway Dashboard")
    print("   Settings → Variables → New Variable")
    exit(1)

# Configuration de logging
LOG_LEVEL = getattr(logging, EnvironmentManager.get_optional("LOG_LEVEL").upper(), logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

# API ESPN Configuration
ESPN_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# MAPPAGE COMPLET DES LIGUES ESPN
LEAGUE_MAPPING = {
    "DZA.1": "soccer/dza.1",
    "GER.1": "soccer/ger.1",
    "GER.2": "soccer/ger.2",
    "GER.3": "soccer/ger.cup",
    "ENG.1": "soccer/eng.1",
    "ENG.2": "soccer/eng.2",
    "ENG.FA": "soccer/eng.fa",
    "ENG.LEAGUE_CUP": "soccer/eng.league_cup",
    "KSA.1": "soccer/ksa.1",
    "AUT.1": "soccer/aut.1",
    "BEL.1": "soccer/bel.1",
    "BRA.1": "soccer/bra.1",
    "CMR.1": "soccer/cmr.1",
    "CIV.1": "soccer/civ.1",
    "SCO.1": "soccer/sco.1",
    "EGY.1": "soccer/egy.1",
    "ESP.1": "soccer/esp.1",
    "ESP.2": "soccer/esp.2",
    "ESP.CUP": "soccer/esp.cup",
    "USA.1": "soccer/usa.1",
    "UEFA.EURO_QUAL": "soccer/uefa.euro_qual",
    "UEFA.CL": "soccer/uefa.champions",
    "UEFA.EL": "soccer/uefa.europa",
    "UEFA.ECL": "soccer/uefa.europa_conference",
    "UEFA.NATIONS": "soccer/uefa.nations",
    "FRA.1": "soccer/fra.1",
    "FRA.2": "soccer/fra.2",
    "FRA.3": "soccer/fra.3",
    "FRA.CUP": "soccer/fra.cup",
    "GRE.1": "soccer/gre.1",
    "ITA.1": "soccer/ita.1",
    "ITA.2": "soccer/ita.2",
    "ITA.CUP": "soccer/ita.cup",
    "MAR.1": "soccer/mar.1",
    "MEX.1": "soccer/mex.1",
    "INT.COPA_AMERICA": "soccer/int.copa_america",
    "INT.AFCON": "soccer/int.africa_cup",
    "INT.ASIAN_CUP": "soccer/int.asian_cup",
    "INT.WORLD_CUP": "soccer/fifa.world",
    "INT.FRIENDLY": "soccer/int.friendly",
    "NOR.1": "soccer/nor.1",
    "NED.1": "soccer/ned.1",
    "POR.1": "soccer/por.1",
    "POR.2": "soccer/por.2",
    "POR.CUP": "soccer/por.cup",
    "RUS.1": "soccer/rus.1",
    "SEN.1": "soccer/sen.1",
    "SUI.1": "soccer/sui.1",
    "TUN.1": "soccer/tun.1",
    "TUR.1": "soccer/tur.1",
    "UKR.1": "soccer/ukr.1",
}

# Priorités des ligues
PRIORITY_LEAGUES = [
    "ENG.1", "ESP.1", "GER.1", "ITA.1", "FRA.1",
    "UEFA.CL", "UEFA.EL",
    "INT.WORLD_CUP", "INT.EURO", "INT.AFCON",
]

# Paramètres des modèles depuis environnement
MODEL_CONFIG = {
    "min_h2h_matches": EnvironmentManager.get_int("MIN_H2H_MATCHES", 3),
    "recent_matches_count": EnvironmentManager.get_int("RECENT_MATCHES_COUNT", 10),
    "weight_h2h": EnvironmentManager.get_float("WEIGHT_H2H", 0.30),
    "weight_form": EnvironmentManager.get_float("WEIGHT_FORM", 0.25),
    "weight_stats": EnvironmentManager.get_float("WEIGHT_STATS", 0.25),
    "weight_venue": EnvironmentManager.get_float("WEIGHT_VENUE", 0.20),
    "min_confidence": EnvironmentManager.get_float("MIN_CONFIDENCE", 0.65),
    "data_freshness_days": EnvironmentManager.get_int("DATA_FRESHNESS_DAYS", 30),
}

# Configuration Telegram depuis environnement
TELEGRAM_CONFIG = {
    "bot_token": EnvironmentManager.get_required("TELEGRAM_BOT_TOKEN"),
    "channel_id": EnvironmentManager.get_required("TELEGRAM_CHANNEL_ID"),
    "daily_time": EnvironmentManager.get_optional("DAILY_TIME", "07:00"),
    "admin_user_id": EnvironmentManager.get_optional("TELEGRAM_ADMIN_ID", ""),
}

# Configuration Railway
RAILWAY_CONFIG = {
    "timezone": EnvironmentManager.get_optional("TIMEZONE", "Europe/Paris"),
    "retry_attempts": EnvironmentManager.get_int("RETRY_ATTEMPTS", 3),
    "cache_duration": EnvironmentManager.get_int("CACHE_DURATION", 3600),
    "log_level": LOG_LEVEL,
}

# Configuration base de données
DATABASE_CONFIG = {
    "path": EnvironmentManager.get_optional("DB_PATH", "predictions.db"),
    "cleanup_days": EnvironmentManager.get_int("CLEANUP_DAYS", 30),
    "backup_enabled": EnvironmentManager.get_bool("BACKUP_ENABLED", False),
}

# Variables système
SYSTEM_CONFIG = {
    "version": "2.0.0",
    "name": "ESPN Football Predictor",
    "author": "Railway Bot System",
    "environment": os.getenv("RAILWAY_ENVIRONMENT", "production"),
}