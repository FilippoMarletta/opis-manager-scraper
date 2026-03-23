import logging

from src.api_client import SmartEduApiClient
from src.config import ApiConfig, DbConfig, ScraperConfig
from src.database import MySqlDatabaseClient
from src.scraper import Scraper

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> None:  # pragma: no cover
    logger.info("Inizializzazione OPIS Manager Scraper...")

    api_config = ApiConfig()
    db_config = DbConfig.from_env()
    scraper_config = ScraperConfig.from_env()

    api_client = SmartEduApiClient.create(api_config)

    try:
        # Context manager grants automatic connection management for the database client.
        with MySqlDatabaseClient(db_config) as db_client:
            scraper = Scraper(api_client, db_client, scraper_config)
            scraper.run()
        logger.info("Estrazione dati completata con successo.")
    except KeyboardInterrupt:
        logger.warning("Estrazione interrotta manualmente.")
    except Exception as e:
        logger.error(f"Errore critico: {e}", exc_info=True)


if __name__ == "__main__":  # pragma: no cover
    main()
