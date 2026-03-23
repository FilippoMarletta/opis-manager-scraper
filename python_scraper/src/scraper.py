import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple

from .api_client import ApiClient
from .config import ScraperConfig
from .database import DatabaseClient
from .models import CorsoDiStudi, Dipartimento, Insegnamento, SchedaOpis

logger = logging.getLogger(__name__)


class Scraper:
    """
    Orchestrator of the scraping process. It coordinates the API client and the database client to extract data from the SmartEdu API and store it in the database.
    It implements a pipeline that processes each academic year, department, course, and activity sequentially, with support for concurrent fetching of activity data to improve performance.
    The scraper is designed to be robust and efficient, with configurable parameters for delay between requests, debug mode, and maximum workers for concurrency.

    Use:
        config = ScraperConfig.from_env()
        with MySqlDatabaseClient(DbConfig.from_env()) as db:
            scraper = Scraper(SmartEduApiClient.create(), db, config)
            scraper.run()
    """

    def __init__(
        self,
        api_client: ApiClient,
        db_client: DatabaseClient,
        config: ScraperConfig,
    ) -> None:
        self._api: ApiClient = api_client
        self._db = db_client
        self._config = config

    def run(self) -> None:
        logger.info("Avvio estrazione dati OPIS...")
        for year in self._config.academic_years:
            self._process_year(year)

    def _process_year(self, year: int) -> None:
        logger.info(f"{'=' * 42}")
        logger.info(f" ANNO ACCADEMICO {year}/{year + 1}")
        logger.info(f"{'=' * 42}")

        departments = self._api.get_departments(year)
        time.sleep(self._config.delay)

        if not departments:
            logger.info(f"Nessun dipartimento trovato per {year}.")
            return

        if self._config.debug_mode:
            departments = [random.choice(departments)]

        logger.info(f"Trovati {len(departments)} dipartimenti per il {year}.")
        for department in departments:
            self._process_department(year, department)

    def _process_department(self, year: int, department: Dipartimento) -> None:
        dip_internal_id = self._db.insert_department(department)
        if dip_internal_id == -1:
            logger.error(f"[ERRORE DB] Impossibile salvare '{department.nome}'. Salto.")
            return

        logger.info(
            f"--- Dipartimento: {department.nome} "
            f"({department.unict_id}) [DB id: {dip_internal_id}] ---"
        )

        courses = self._api.get_courses(year, department.unict_id)
        time.sleep(self._config.delay)

        if self._config.debug_mode and courses:
            courses = [random.choice(courses)]

        for course in courses:
            self._process_course(year, department.unict_id, course, dip_internal_id)

    def _process_course(
        self,
        year: int,
        dept_code: int,
        course: CorsoDiStudi,
        dip_internal_id: int,
    ) -> None:
        corso_internal_id = self._db.insert_course(course, dip_internal_id)
        if corso_internal_id == -1:
            logger.error(
                f"[ERRORE DB] Impossibile salvare il corso '{course.nome}'. Salto."
            )
            return

        logger.info(
            f"  > Corso: {course.nome} ({course.unict_id}) [DB id: {corso_internal_id}]"
        )

        activities = self._api.get_activities(year, dept_code, course.unict_id)
        time.sleep(self._config.delay)

        if not activities:
            logger.info(f"    Nessuna materia per {course.unict_id} nell'anno {year}.")
            return

        if self._config.debug_mode:
            activities = random.sample(activities, min(5, len(activities)))

        self._process_activities_concurrently(
            year, dept_code, course.unict_id, activities, corso_internal_id
        )

    def _process_activities_concurrently(
        self,
        year: int,
        dept_code: int,
        course_code: str,
        activities: list[Insegnamento],
        corso_internal_id: int,
    ) -> None:
        with ThreadPoolExecutor(max_workers=self._config.max_workers) as executor:
            futures = {
                executor.submit(
                    self._fetch_activity_data, year, dept_code, course_code, activity
                ): activity
                for activity in activities
            }

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result is None:
                        continue
                    activity, schede_opis = result
                    insegnamento_id = self._db.insert_insegnamento(
                        activity, corso_internal_id
                    )
                    if insegnamento_id != -1 and schede_opis:
                        self._db.insert_schede_opis(schede_opis, insegnamento_id)
                except Exception as e:
                    logger.error(
                        f"Errore inatteso nell'elaborazione di una materia: {e}"
                    )

    def _fetch_activity_data(
        self,
        year: int,
        dept_code: int,
        course_code: str,
        activity: Insegnamento,
    ) -> Optional[Tuple[Insegnamento, list[SchedaOpis]]]:
        """
        Fetches the OPIS sheets for a given activity. If the professor's tax code is missing, it logs a warning and skips the activity.
        Otherwise, it makes an API call to retrieve the OPIS sheets, logs the result, and returns a tuple of the activity and its corresponding OPIS sheets.
        The method is designed to be used concurrently for multiple activities to improve performance while respecting the API's rate limits.
        """
        if not activity.professor_tax:
            logger.warning(f"    [SKIP] {activity.nome}: codice docente mancante.")
            return None

        logger.info(f"    [FETCH] {activity.nome}...")
        schede_opis = self._api.get_questions(
            year, dept_code, course_code, activity.codice_gomp, activity.professor_tax
        )
        time.sleep(0.5)

        if schede_opis:
            logger.info(
                f"    [OK] {len(schede_opis)} schede scaricate per '{activity.nome} con docente: {activity.docente}'."
            )
        else:
            logger.info(
                f"    [VUOTO] Nessuna scheda per '{activity.nome}' con docente: {activity.docente}."
            )

        return activity, schede_opis
