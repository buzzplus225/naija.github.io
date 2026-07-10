# scraper_traducteur.py
# Version avec XPaths spécifiques pour NaijaNews

import requests
from lxml import html
import logging
import time
import random
from datetime import datetime, timezone
from typing import List, Optional
import json
import os
from feedgen.feed import FeedGenerator
from deep_translator import GoogleTranslator

# -------------------- CONFIGURATION --------------------
SOURCE_URL = "https://www.naijanews.com/"
MAX_ARTICLES = 20
MIN_DELAY = 0.5
MAX_DELAY = 1.5
CACHE_FILE = "articles_cache.json"
FEED_FILE = "feed.xml"
DEBUG = True  # Mode debug (peut être désactivé)

# -------------------- LOGGING --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# -------------------- TRADUCTION --------------------
def translate_text(text: str, target_lang: str = 'fr') -> str:
    """Traduit un texte en français avec gestion d'erreur."""
    if not text:
        return ""
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        if len(text) > 5000:
            text = text[:5000]
        return translator.translate(text)
    except Exception as e:
        logger.warning(f"Erreur de traduction: {e}")
        return text

# -------------------- FONCTIONS UTILITAIRES --------------------
def fetch_page(url: str) -> Optional[html.HtmlElement]:
    """Télécharge la page et retourne un arbre lxml."""
    try:
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper()
            response = scraper.get(url, timeout=10)
        except ImportError:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
        response.raise_for_status()
        return html.fromstring(response.content)
    except Exception as e:
        logger.error(f"Erreur lors du fetch de {url}: {e}")
        return None

def clean_date(date_str: str) -> Optional[datetime]:
    """Nettoie une chaîne de date et retourne un objet datetime (non utilisé ici, mais gardé)."""
    if not date_str:
        return datetime.now(timezone.utc)
    date_str = date_str.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%d %B %Y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str[:19], fmt)
        except (ValueError, TypeError):
            continue
    return datetime.now(timezone.utc)

def load_cache() -> List[str]:
    """Charge les URLs déjà scrapées depuis le cache."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('urls', [])
        except Exception as e:
            logger.warning(f"Erreur de chargement du cache: {e}")
    return []

def save_cache(urls: List[str]):
    """Sauvegarde les URLs scrapées dans le cache."""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'urls': urls, 'updated': datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Erreur de sauvegarde du cache: {e}")

# -------------------- EXTRACTION AVEC XPATHS SPÉCIFIQUES --------------------
def scrape_naijanews_com() -> List[dict]:
    """
    Parse la page d'accueil de NaijaNews en utilisant les XPaths fournis :
      - Article : //article[contains(@class, 'nn-post-card')]
      - Titre   : ./div[contains(@class, 'nn-post-card-body')]/h3
      - URL     : ./a[contains(@class, 'nn-post-card-link')]/@href
      - Image   : ./a/figure/picture/img/@src
      - Description (alt) : ./a/figure/picture/img/@alt
      - Date    : non disponible -> datetime actuel
    """
    articles = []
    cache_urls = load_cache()
    new_urls = []
    
    tree = fetch_page(SOURCE_URL)
    if tree is None:
        return articles

    # Sélection des articles avec le XPath exact
    article_nodes = tree.xpath('//article[contains(@class, "nn-post-card")]')
    logger.info(f"📌 Nombre d'articles détectés : {len(article_nodes)}")

    for node in article_nodes[:MAX_ARTICLES]:
        try:
            # --- TITRE ---
            title_elem = node.xpath('./div[contains(@class, "nn-post-card-body")]/h3')
            title = title_elem[0].text_content().strip() if title_elem else ""
            if not title:
                continue

            # --- URL ---
            url_elem = node.xpath('./a[contains(@class, "nn-post-card-link")]/@href')
            url = url_elem[0].strip() if url_elem else ""
            if not url:
                continue
            # Normalisation
            if url.startswith('/'):
                url = 'https://www.naijanews.com' + url
            elif not url.startswith('http'):
                continue

            # Vérification du cache et doublons
            if url in cache_urls:
                logger.debug(f"⏭️ Article déjà scrapé: {url}")
                continue
            if any(a['url'] == url for a in articles):
                continue

            # --- IMAGE ---
            img_elem = node.xpath('./a/figure/picture/img/@src')
            image = img_elem[0].strip() if img_elem else ""
            if image and image.startswith('/'):
                image = 'https://www.naijanews.com' + image

            # --- DESCRIPTION (alt de l'image) ---
            alt_elem = node.xpath('./a/figure/picture/img/@alt')
            description = alt_elem[0].strip() if alt_elem else title

            # --- DATE (non disponible) ---
            date_obj = datetime.now(timezone.utc)

            # --- TRADUCTION ---
            logger.info(f"🌐 Traduction de: {title[:30]}...")
            title_fr = translate_text(title)
            description_fr = translate_text(description)

            article = {
                'title': title,
                'title_fr': title_fr,
                'url': url,
                'image': image,
                'description': description,
                'description_fr': description_fr,
                'date': date_obj,
                'date_str': date_obj.isoformat()
            }

            articles.append(article)
            new_urls.append(url)
            logger.info(f"✨ Article ajouté: {title_fr[:40]}...")
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        except Exception as e:
            logger.debug(f"Erreur sur un article : {e}")
            continue

    # Mise à jour du cache
    if new_urls:
        all_urls = cache_urls + new_urls
        if len(all_urls) > 500:
            all_urls = all_urls[-500:]
        save_cache(all_urls)

    return articles

# -------------------- GÉNÉRATION DU FEED RSS --------------------
def generate_feed(articles: List[dict], output_file: str = FEED_FILE):
    """Génère un fichier feed.xml à partir des articles."""
    if not articles:
        logger.warning("Aucun article à mettre dans le feed")
        fg = FeedGenerator()
        fg.title("Naija News - Actualités traduites en français")
        fg.description("Aucun article disponible actuellement")
        fg.link(href="https://buzzplus225.github.io/naija.github.io/", rel="alternate")
        fg.link(href="https://buzzplus225.github.io/naija.github.io/feed.xml", rel="self")
        fg.language("fr")
        fg.lastBuildDate(datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"))
        rss_str = fg.rss_str(pretty=True)
        with open(output_file, 'wb') as f:
            f.write(rss_str)
        logger.info(f"✅ Feed RSS vide créé: {output_file}")
        return

    fg = FeedGenerator()
    fg.title("Naija News - Actualités traduites en français")
    fg.description("Flux RSS des actualités de NaijaNews automatiquement traduites en français")
    fg.link(href="https://buzzplus225.github.io/naija.github.io/", rel="alternate")
    fg.link(href="https://buzzplus225.github.io/naija.github.io/feed.xml", rel="self")
    fg.language("fr")
    fg.lastBuildDate(datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"))
    fg.generator("Scraper Traducteur NaijaNews v2.0")

    for article in articles[:20]:
        fe = fg.add_entry()
        fe.title(article.get('title_fr', article.get('title', '')))
        fe.link(href=article['url'])
        fe.guid(article['url'], permalink=True)
        fe.description(article.get('description_fr', article.get('description', '')))
        
        content = f"<p>{article.get('description_fr', article.get('description', ''))}</p>"
        if article.get('image'):
            content = f'<img src="{article["image"]}" alt="{article.get("title", "")}" style="max-width:100%;"/><br/>{content}'
        fe.content(content, type="CDATA")
        
        if article.get('date'):
            fe.pubDate(article['date'].strftime("%a, %d %b %Y %H:%M:%S +0000"))
        else:
            fe.pubDate(datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"))

    rss_str = fg.rss_str(pretty=True)
    with open(output_file, 'wb') as f:
        f.write(rss_str)
    
    logger.info(f"✅ Feed RSS généré: {output_file} ({len(articles)} articles)")

# -------------------- SAUVEGARDE JSON --------------------
def save_json(articles: List[dict], output_file: str = "articles.json"):
    """Sauvegarde les articles en JSON pour débogage."""
    try:
        articles_serializable = []
        for a in articles:
            a_copy = a.copy()
            if 'date' in a_copy and a_copy['date']:
                a_copy['date'] = a_copy['date'].isoformat()
            articles_serializable.append(a_copy)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(articles_serializable, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ JSON sauvegardé: {output_file}")
    except Exception as e:
        logger.error(f"Erreur de sauvegarde JSON: {e}")

# -------------------- POINT D'ENTRÉE --------------------
if __name__ == "__main__":
    print("🚀 Début du scraping avec XPaths personnalisés...")
    start_time = time.time()
    
    articles = scrape_naijanews_com()
    
    elapsed = time.time() - start_time
    print(f"✅ Scraping terminé. {len(articles)} articles récupérés en {elapsed:.2f}s")
    
    if articles:
        generate_feed(articles)
        save_json(articles)
        print(f"✅ Fichiers générés:")
        print(f"   - {FEED_FILE}")
        print(f"   - articles.json")
    else:
        print("❌ Aucun article trouvé")
        generate_feed([], "feed.xml")
        print("⚠️ Feed vide créé")
