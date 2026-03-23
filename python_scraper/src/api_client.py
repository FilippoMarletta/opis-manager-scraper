import logging
from typing import List, Protocol, runtime_checkable

from .config import ApiConfig
from .http_client import HttpClient, RequestsHttpClient
from .models import CorsoDiStudi, Dipartimento, Insegnamento, SchedaOpis
from .transformers import (
    parse_course_name,
    parse_insegnamento_data,
    parse_scheda_opis_data,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class ApiClient(Protocol):
    """
    Interface for API client. enables abstracting away the underlying implementation (e.g. SmartEduApiClient).
    """

    def get_departments(self, year: int) -> List[Dipartimento]: ...

    def get_courses(self, year: int, department_code: int) -> List[CorsoDiStudi]: ...

    def get_activities(
        self, year: int, dept_code: int, course_code: str
    ) -> List[Insegnamento]: ...

    def get_questions(
        self,
        year: int,
        dept_code: int,
        course_code: str,
        activity_code: int,
        professor_tax: str,
    ) -> List[SchedaOpis]: ...


class SmartEduApiClient:
    """
    implementation of ApiClient. It uses an HttpClient to perform the actual HTTP requests.
    """

    def __init__(self, http_client: HttpClient, config: ApiConfig) -> None:
        self._http = http_client
        self._config = config

    @classmethod
    def create(cls, config: ApiConfig | None = None) -> "SmartEduApiClient":
        """Factory method for creating an instance of SmartEduApiClient with a RequestsHttpClient and the given configuration."""
        cfg = config or ApiConfig()
        return cls(http_client=RequestsHttpClient(cfg), config=cfg)

    def _url(self, endpoint: str) -> str:
        return f"{self._config.base_url}/{endpoint}"

    @staticmethod
    def _format_year(year: int) -> str:
        return f"{year}/{year + 1}"

    @staticmethod
    def _base_payload() -> dict:
        return {"surveys": ""}

    def get_departments(self, year: int) -> List[Dipartimento]:
        payload = {**self._base_payload(), "academicYear": year}
        formatted_year = self._format_year(year)

        try:
            data = self._http.post(self._url("getDepartments"), payload)
        except Exception as e:
            logger.error(f"Errore API dipartimenti (anno {year}): {e}")
            return []

        return [
            Dipartimento(
                unict_id=int(item["code"]),
                nome=item["name"],
                anno_accademico=formatted_year,
            )
            for item in data.get("data", [])
            if item.get("code") is not None
        ]

    def get_courses(self, year: int, department_code: int) -> List[CorsoDiStudi]:
        payload = {
            **self._base_payload(),
            "academicYear": year,
            "departmentCode": str(department_code),
        }
        formatted_year = self._format_year(year)

        try:
            data = self._http.post(self._url("getCourses"), payload)
        except Exception as e:
            logger.error(
                f"Errore API corsi (dipartimento {department_code}, anno {year}): {e}"
            )
            return []

        corsi = []
        for item in data.get("data", []):
            if item.get("code") is None:
                continue
            nome, classe = parse_course_name(item["name"])
            corsi.append(
                CorsoDiStudi(
                    unict_id=item["code"],
                    nome=nome,
                    classe=classe,
                    anno_accademico=formatted_year,
                    dipartimento_id=department_code,
                )
            )
        return corsi

    def get_activities(
        self, year: int, dept_code: int, course_code: str
    ) -> List[Insegnamento]:
        payload = {
            **self._base_payload(),
            "academicYear": year,
            "departmentCode": str(dept_code),
            "courseCode": course_code,
        }
        formatted_year = self._format_year(year)

        try:
            data = self._http.post(self._url("getActivities"), payload)
        except Exception as e:
            logger.error(
                f"Errore API insegnamenti (corso {course_code}, "
                f"dipartimento {dept_code}, anno {year}): {e}"
            )
            return []

        insegnamenti = []
        for item in data.get("data", []):
            parsed = parse_insegnamento_data(item)
            if parsed is None:
                logger.warning(
                    f"[SKIP] '{item.get('activityName')}' codice docente: {item.get('professorTaxCode', 'N/A')} ignorata — "
                    f"codice GOMP vuoto o alfanumerico: {item.get('activityCode')}"
                )
                continue
            insegnamenti.append(
                Insegnamento(
                    codice_gomp=parsed["codice_gomp"],
                    id_cds=course_code,
                    anno_accademico=formatted_year,
                    nome=parsed["nome"],
                    docente=parsed["docente"],
                    professor_tax=parsed["professor_tax"],
                    canale=parsed["canale"],
                    id_modulo=parsed["id_modulo"],
                    ssd=parsed["ssd"],
                )
            )
        return insegnamenti

    def get_questions(
        self,
        year: int,
        dept_code: int,
        course_code: str,
        activity_code: int,
        professor_tax: str,
    ) -> List[SchedaOpis]:
        payload = {
            **self._base_payload(),
            "academicYear": year,
            "departmentCode": str(dept_code),
            "courseCode": course_code,
            "activityCode": str(activity_code),
            "partCode": "null",
            "professor": professor_tax,
        }
        formatted_year = self._format_year(year)

        try:
            data = self._http.post(self._url("getQuestions"), payload)
        except Exception as e:
            logger.error(
                f"Errore API schede OPIS (activity {activity_code}, "
                f"corso {course_code}, dipartimento {dept_code}, anno {year}): {e}"
            )
            return []

        return [
            SchedaOpis(
                **item,
                anno_accademico=formatted_year,
                id_insegnamento=activity_code,
            )
            for item in parse_scheda_opis_data(data)
        ]
