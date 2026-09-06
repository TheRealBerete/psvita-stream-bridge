FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py build_channels.py health.py ./

# Genere data/channels.json, categories.json, countries.json a partir de
# l'API iptv-org au moment du build -> l'image contient une liste figee ;
# relancer `docker build` (ou le script refresh, voir README) pour la rafraichir.
RUN python build_channels.py

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
