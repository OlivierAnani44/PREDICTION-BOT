#!/bin/bash
# Script de configuration Railway

echo "🚀 Configuration du Bot Football ESPN"
echo "======================================"

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 n'est pas installé"
    exit 1
fi

echo "✅ Python3 détecté"

# Créer l'environnement
echo "📁 Création de la structure..."
mkdir -p logs backups

# Installer les dépendances
echo "📦 Installation des dépendances..."
pip install -r requirements.txt

# Vérifier les variables d'environnement
echo "🔍 Vérification des variables d'environnement..."

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "⚠️  TELEGRAM_BOT_TOKEN non défini"
    echo "   Obtenez-le via @BotFather sur Telegram"
fi

if [ -z "$TELEGRAM_CHANNEL_ID" ]; then
    echo "⚠️  TELEGRAM_CHANNEL_ID non défini"
    echo "   Format: @nomducanal ou -1001234567890"
fi

# Générer fichier .env template
echo "📝 Génération du template .env..."
cat > .env.template << EOF
# Railway Environment Variables
# Copiez ce fichier en .env et remplissez les valeurs

# REQUIRED - Obtention via @BotFather
TELEGRAM_BOT_TOKEN=votre_bot_token_ici

# REQUIRED - Votre canal Telegram (@nom ou ID numérique)
TELEGRAM_CHANNEL_ID=@votre_canal

# OPTIONAL - Configuration
TIMEZONE=Europe/Paris
DAILY_TIME=07:00
MIN_CONFIDENCE=0.65
LOG_LEVEL=INFO
CLEANUP_DAYS=30
EOF

echo "✅ Configuration terminée"
echo ""
echo "📋 PROCHAINES ÉTAPES:"
echo "1. Remplissez les variables dans Railway Dashboard"
echo "2. Settings → Variables → New Variable"
echo "3. Déployez avec: railway up"
echo ""
echo "🔄 Pour tester: python scheduler_secure.py --test"