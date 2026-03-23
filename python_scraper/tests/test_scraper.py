from unittest.mock import patch

import pytest

from src.config import ScraperConfig
from src.models import CorsoDiStudi, Dipartimento, Insegnamento, SchedaOpis
from src.scraper import Scraper


class StubApiClient:
    """
    Stub for SmartEduApiClient.
    """

    def __init__(self) -> None:
        self.departments: list[Dipartimento] = []
        self.courses: list[CorsoDiStudi] = []
        self.activities: list[Insegnamento] = []
        self.questions: list[SchedaOpis] = []
        self.questions_error: Exception | None = None

        self.get_departments_call_count: int = 0
        self.get_courses_call_count: int = 0
        self.get_activities_call_count: int = 0
        self.get_questions_call_count: int = 0

    def get_departments(self, year: int) -> list[Dipartimento]:
        self.get_departments_call_count += 1
        return self.departments

    def get_courses(self, year: int, department_code: int) -> list[CorsoDiStudi]:
        self.get_courses_call_count += 1
        return self.courses

    def get_activities(
        self, year: int, dept_code: int, course_code: str
    ) -> list[Insegnamento]:
        self.get_activities_call_count += 1
        return self.activities

    def get_questions(
        self,
        year: int,
        dept_code: int,
        course_code: str,
        activity_code: int,
        professor_tax: str,
    ) -> list[SchedaOpis]:
        self.get_questions_call_count += 1
        if self.questions_error:
            raise self.questions_error
        return self.questions


class StubDatabaseClient:
    """
    stub for MySqlDatabaseClient. Returns preconfigured values for each insertion method, and counts calls to each method via dedicated attributes.
    """

    def __init__(self) -> None:
        self.department_id: int = 1
        self.course_id: int = 2
        self.insegnamento_id: int = 3

        self.insert_department_call_count: int = 0
        self.insert_course_call_count: int = 0
        self.insert_insegnamento_call_count: int = 0
        self.insert_schede_opis_call_count: int = 0

    def insert_department(self, department: Dipartimento) -> int:
        self.insert_department_call_count += 1
        return self.department_id

    def insert_course(self, course: CorsoDiStudi, dipartimento_internal_id: int) -> int:
        self.insert_course_call_count += 1
        return self.course_id

    def insert_insegnamento(
        self, insegnamento: Insegnamento, corso_internal_id: int
    ) -> int:
        self.insert_insegnamento_call_count += 1
        return self.insegnamento_id

    def insert_schede_opis(
        self, schede_opis: list[SchedaOpis], insegnamento_internal_id: int
    ) -> None:
        self.insert_schede_opis_call_count += 1


def _dip(unict_id: int = 1) -> Dipartimento:
    return Dipartimento(unict_id=unict_id, nome="Dip Test", anno_accademico="2021/2022")


def _corso(unict_id: str = "C1") -> CorsoDiStudi:
    return CorsoDiStudi(
        unict_id=unict_id,
        nome="Corso Test",
        classe="L-1",
        anno_accademico="2021/2022",
        dipartimento_id=1,
    )


def _ins(professor_tax: str = "ABC123") -> Insegnamento:
    return Insegnamento(
        codice_gomp=1001,
        id_cds="C1",
        anno_accademico="2021/2022",
        nome="Materia Test",
        docente="Rossi Mario",
        professor_tax=professor_tax,
    )


def _scheda() -> SchedaOpis:
    return SchedaOpis(
        anno_accademico="2021/2022",
        id_insegnamento=1001,
        totale_schede=5,
        totale_schede_nf=0,
        fc=0,
        inatt_nf=0,
        domande=[0] * 60,
        domande_nf=[0] * 60,
        motivo_nf=[],
        sugg=[],
        sugg_nf=[],
    )


def _full_stubs() -> tuple[StubApiClient, StubDatabaseClient]:
    """stubs for Happy Path."""
    api = StubApiClient()
    api.departments = [_dip()]
    api.courses = [_corso()]
    api.activities = [_ins()]
    api.questions = [_scheda()]

    db = StubDatabaseClient()
    return api, db


def _make_scraper(
    api: StubApiClient,
    db: StubDatabaseClient,
    debug: bool = False,
    years: tuple = (2021,),
) -> Scraper:
    config = ScraperConfig(academic_years=years, delay=0.0, debug_mode=debug)
    return Scraper(api_client=api, db_client=db, config=config)


@pytest.fixture(autouse=True)
def no_sleep():
    """time.sleep pathch."""
    with patch("src.scraper.time.sleep"):
        yield


def test_run_calls_get_departments_once_per_year() -> None:
    api, db = StubApiClient(), StubDatabaseClient()

    _make_scraper(api, db, years=(2021, 2022, 2023)).run()

    assert api.get_departments_call_count == 3


@pytest.mark.parametrize(
    "setup, broken_step, next_step_attr",
    [
        # nessun dipartimento → insert_department non chiamato
        (
            lambda api, db: setattr(api, "departments", []),
            None,
            ("db", "insert_department_call_count"),
        ),
        # insert_department fallisce → get_courses non chiamato
        (
            lambda api, db: setattr(db, "department_id", -1),
            None,
            ("api", "get_courses_call_count"),
        ),
        # nessun corso → insert_course non chiamato
        (
            lambda api, db: setattr(api, "courses", []),
            None,
            ("db", "insert_course_call_count"),
        ),
        # insert_course fallisce → get_activities non chiamato
        (
            lambda api, db: setattr(db, "course_id", -1),
            None,
            ("api", "get_activities_call_count"),
        ),
        # nessuna attività → insert_insegnamento non chiamato
        (
            lambda api, db: setattr(api, "activities", []),
            None,
            ("db", "insert_insegnamento_call_count"),
        ),
        # professor_tax mancante → get_questions non chiamato
        (
            lambda api, db: setattr(
                api, "activities", [_ins(professor_tax="")]),
            None,
            ("api", "get_questions_call_count"),
        ),
    ],
    ids=[
        "no_departments",
        "dept_insert_fails",
        "no_courses",
        "course_insert_fails",
        "no_activities",
        "missing_professor_tax",
    ],
)
def test_pipeline_break(setup, broken_step, next_step_attr) -> None:
    api, db = _full_stubs()
    setup(api, db)

    _make_scraper(api, db).run()

    target_name, attr = next_step_attr
    target = api if target_name == "api" else db
    assert getattr(target, attr) == 0


@pytest.mark.parametrize(
    "questions, insegnamento_id, expect_insegnamento, expect_schede",
    [
        ([_scheda()], 3, 1, 1),  # tutto ok → entrambi salvati
        ([], 3, 1, 0),  # schede vuote → insert_schede non chiamato
        ([_scheda()], -1, 1, 0),  # insert_insegnamento fallisce → no schede
    ],
    ids=["full_success", "empty_schede", "insegnamento_insert_fails"],
)
def test_happy_path_variations(
    questions, insegnamento_id, expect_insegnamento, expect_schede
) -> None:
    api, db = _full_stubs()
    api.questions = questions
    db.insegnamento_id = insegnamento_id

    _make_scraper(api, db).run()

    assert db.insert_insegnamento_call_count == expect_insegnamento
    assert db.insert_schede_opis_call_count == expect_schede


@pytest.mark.parametrize(
    "n_departments, n_courses",
    [(3, 4), (1, 1)],
    ids=["multiple_items", "single_item"],
)
def test_debug_mode_samples_one_dept_and_course(n_departments, n_courses) -> None:
    api, db = StubApiClient(), StubDatabaseClient()
    api.departments = [_dip(i) for i in range(n_departments)]
    api.courses = [_corso(str(i)) for i in range(n_courses)]
    api.activities = []
    db.course_id = -1  # stop after insert_course

    _make_scraper(api, db, debug=True).run()

    assert db.insert_department_call_count == 1
    assert db.insert_course_call_count == 1


def test_debug_mode_samples_max_five_activities() -> None:
    api, db = _full_stubs()
    api.activities = [_ins() for _ in range(10)]
    api.questions = []
    db.insegnamento_id = -1

    _make_scraper(api, db, debug=True).run()

    assert api.get_questions_call_count <= 5


def test_concurrent_exception_does_not_crash_scraper() -> None:
    """test anti propagation of exceptions from get_questions."""
    api, db = _full_stubs()
    api.questions_error = RuntimeError("Errore di rete inatteso")

    _make_scraper(api, db).run()  # must not raise exception

    assert db.insert_insegnamento_call_count == 0
    assert db.insert_schede_opis_call_count == 0
