"""Middlewares Scrapy communs aux scrapers."""
import logging

logger = logging.getLogger(__name__)

CODES_LIMITE = (429, 503)


class PauseSurLimiteMiddleware:
    """Limitation de débit (429 / 503) : pause de tout le spider puis nouvelle tentative.

    Le RetryMiddleware de Scrapy réessaie immédiatement, ce qui prolonge le blocage
    (Mubawab renvoyait des 429 pendant des heures). Ici : respect de Retry-After,
    sinon attente exponentielle (30 s, 60 s, 120 s... 10 min max), et la requête
    est replanifiée après la reprise.
    """

    PAUSE_INITIALE_S = 30
    PAUSE_MAX_S = 600
    TENTATIVES_MAX = 5

    def __init__(self, crawler):
        self.crawler = crawler
        self.limites_consecutives = 0
        self.en_pause = False
        self.stats = {"limites": 0, "abandons": 0}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def delai(self, response):
        retry_after = response.headers.get("Retry-After")
        try:
            if retry_after:
                return min(int(retry_after.decode() if isinstance(retry_after, bytes) else retry_after), self.PAUSE_MAX_S)
        except ValueError:
            pass
        return min(self.PAUSE_INITIALE_S * 2 ** max(self.limites_consecutives - 1, 0), self.PAUSE_MAX_S)

    def process_response(self, request, response, spider=None):
        if response.status not in CODES_LIMITE:
            if 200 <= response.status < 300:
                self.limites_consecutives = 0
            return response

        tentatives = request.meta.get("tentatives_limite", 0)
        self.stats["limites"] += 1
        if tentatives >= self.TENTATIVES_MAX:
            self.stats["abandons"] += 1
            logger.warning("Limitation persistante, abandon de %s", request.url)
            return response

        self.limites_consecutives += 1
        delai = self.delai(response)
        self._pause(delai)
        nouvelle = request.replace(dont_filter=True, priority=request.priority + 10)
        nouvelle.meta["tentatives_limite"] = tentatives + 1
        logger.warning("HTTP %s sur %s : pause de %s s (tentative %s)", response.status, request.url, delai, tentatives + 1)
        return nouvelle

    def _pause(self, delai):
        if self.en_pause:
            return
        engine = getattr(self.crawler, "engine", None)
        if engine is None:
            return
        from twisted.internet import reactor

        self.en_pause = True
        engine.pause()
        reactor.callLater(delai, self._reprendre)

    def _reprendre(self):
        self.en_pause = False
        self.crawler.engine.unpause()


# Réglages à fusionner dans custom_settings des spiders
REGLAGES_LIMITE = {
    "DOWNLOADER_MIDDLEWARES": {"scrapers.middlewares.PauseSurLimiteMiddleware": 590},
    # 429/503 gérés ci-dessus (pause) : retirés des réessais immédiats de Scrapy
    "RETRY_HTTP_CODES": [500, 502, 504, 522, 524, 408],
}
