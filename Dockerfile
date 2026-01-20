FROM python:3.11-slim

WORKDIR /app

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copier les fichiers requis
COPY requirements.txt .
COPY *.py ./

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Créer le dossier logs
RUN mkdir -p /app/logs

# Exposer le port (pour healthcheck)
EXPOSE 8080

# Commande de démarrage
CMD ["python", "scheduler.py"]