import time

from streaming_hub.backend.crawler_parser import CrawlerCatalogParser


# Generate a synthetic catalog page HTML with N movie cards
def generate_catalog_html(num_cards: int = 100) -> str:
    cards = []
    for i in range(num_cards):
        card = f"""
        <div class="card mp-post horizontal">
            <div class="card-image"><img src="https://example.com/poster_{i}.jpg" /></div>
            <h3 class="card-title"><a href="https://example.com/movie-{i}/"> Test Movie {i} (2024) [HD] [VM 14] - FILM GRATIS </a></h3>
            <strong>DURATA 120 - ITALIA - Action</strong><br />
            Description for movie {i} with <span>tags</span> and <a href="#">link</a>
        </div></div></div>
        """
        cards.append(card)
    return "\n".join(cards)


# Generate a synthetic TV series page HTML with multiple seasons/episodes
def generate_tv_html(num_episodes: int = 50) -> str:
    episodes = []
    for i in range(1, num_episodes + 1):
        ep = f"""
        <p>Stagione 1 - 1x{i:02d} <a href="https://mixdrop.co/e/123">Mixdrop</a> <a href="https://maxstream.video/e/456">Maxstream</a></p>
        """
        episodes.append(ep)

    return f"""
    <html>
    <head>
        <title>Test TV Series (2023) [HD]</title>
        <script type="application/ld+json" class="yoast-schema-graph">
        {{
            "@graph": [
                {{
                    "@type": "Article",
                    "headline": "Test TV Series",
                    "thumbnailUrl": "https://example.com/poster.jpg",
                    "articleSection": ["Action", "Drama", "2023", "Serie TV"]
                }}
            ]
        }}
        </script>
    </head>
    <body>
        <div class="ignore-css"><p><strong>Meta</strong></p><p>Plot summary of the series <br /><a href="#">more</a></p></div>
        {"".join(episodes)}
    </body>
    </html>
    """


def run_benchmark(iterations: int = 200):
    catalog_html = generate_catalog_html(100)
    tv_html = generate_tv_html(50)

    # Warmup
    for _ in range(5):
        CrawlerCatalogParser.parse_catalog_page(catalog_html)
        CrawlerCatalogParser.parse_tv_series_page(tv_html)

    # Benchmark parse_catalog_page
    t0 = time.perf_counter()
    for _ in range(iterations):
        CrawlerCatalogParser.parse_catalog_page(catalog_html)
    t_catalog = time.perf_counter() - t0

    # Benchmark parse_tv_series_page
    t0 = time.perf_counter()
    for _ in range(iterations):
        CrawlerCatalogParser.parse_tv_series_page(tv_html)
    t_tv = time.perf_counter() - t0

    print(f"Benchmark Results ({iterations} iterations):")
    print(
        f"  parse_catalog_page (100 cards/iter): {t_catalog:.4f} seconds ({t_catalog / iterations * 1000:.3f} ms/iter)"
    )
    print(f"  parse_tv_series_page (50 eps/iter):  {t_tv:.4f} seconds ({t_tv / iterations * 1000:.3f} ms/iter)")
    print(f"  Total time:                          {t_catalog + t_tv:.4f} seconds")


if __name__ == "__main__":
    run_benchmark()
