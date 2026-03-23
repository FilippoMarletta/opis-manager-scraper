from typing import Any, Dict, List, Optional

import pytest

from src.api_client import SmartEduApiClient
from src.config import ApiConfig
from src.models import CorsoDiStudi, Dipartimento, Insegnamento, SchedaOpis


class StubHttpClient:
    """
    Stub for HttpClient. It records calls made to it and can be configured to return a specific value or raise an exception.
    This allows for testing the SmartEduApiClient without making real HTTP requests.
    """

    def __init__(
        self,
        return_value: Optional[Dict[str, Any]] = None,
        raises: Optional[Exception] = None,
    ) -> None:
        self._return_value = return_value or {}
        self._raises = raises
        self.calls: List[tuple[str, Dict[str, Any]]] = []

    def post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append((url, payload))
        if self._raises:
            raise self._raises
        return self._return_value


def make_client(
    return_value: Optional[Dict[str, Any]] = None,
    raises: Optional[Exception] = None,
) -> tuple[SmartEduApiClient, StubHttpClient]:
    """Helper: create a client with a stubbed HTTP client."""
    stub = StubHttpClient(return_value=return_value, raises=raises)
    client = SmartEduApiClient(http_client=stub, config=ApiConfig())
    return client, stub


@pytest.mark.parametrize(
    "year, mock_response_data, expected_result",
    [
        (
            2024,
            [
                {"code": "1001", "name": "Dipartimento di Matematica"},
                {"code": None, "name": "TOTALE"},
            ],
            [
                Dipartimento(
                    unict_id=1001,
                    nome="Dipartimento di Matematica",
                    anno_accademico="2024/2025",
                )
            ],
        ),
        (
            2024,
            [{"code": None, "name": "TOTALE"}],
            [],
        ),
        (
            2021,
            [
                {"code": "1002", "name": "Dipartimento di Informatica"},
                {"code": None, "name": "TOTALE"},
            ],
            [
                Dipartimento(
                    unict_id=1002,
                    nome="Dipartimento di Informatica",
                    anno_accademico="2021/2022",
                )
            ],
        ),
    ],
)
def test_get_departments(
    year: int,
    mock_response_data: List[Dict[str, Any]],
    expected_result: List[Dipartimento],
) -> None:
    expected_url = "https://public.smartedu.unict.it/EnqaDataViewer/getDepartments"
    client, stub = make_client(return_value={"data": mock_response_data})

    result = client.get_departments(year)

    assert result == expected_result
    assert all(isinstance(r, Dipartimento) for r in result)
    assert len(stub.calls) == 1
    url, payload = stub.calls[0]
    assert url == expected_url
    assert payload["academicYear"] == year
    assert payload["surveys"] == ""


@pytest.mark.parametrize("year", [2024, 2023, 2022, 2021])
def test_get_departments_api_failure(year: int) -> None:
    client, stub = make_client(raises=Exception("API non raggiungibile"))

    result = client.get_departments(year)

    assert result == []
    assert len(stub.calls) == 1
    _, payload = stub.calls[0]
    assert payload["academicYear"] == year


@pytest.mark.parametrize(
    "year, dept_code, mock_response_data, expected_result",
    [
        (
            2024,
            12345,
            [
                {"code": "M12", "name": "Matematica LM-40"},
                {"code": None, "name": "TOTALE"},
            ],
            [
                CorsoDiStudi(
                    unict_id="M12",
                    nome="Matematica",
                    classe="LM-40",
                    anno_accademico="2024/2025",
                    dipartimento_id=12345,
                )
            ],
        ),
        (
            2024,
            12345,
            [{"code": None, "name": "TOTALE"}],
            [],
        ),
        (
            2021,
            98765,
            [
                {"code": "F34", "name": "Fisica L-30"},
                {"code": None, "name": "TOTALE"},
            ],
            [
                CorsoDiStudi(
                    unict_id="F34",
                    nome="Fisica",
                    classe="L-30",
                    anno_accademico="2021/2022",
                    dipartimento_id=98765,
                )
            ],
        ),
    ],
)
def test_get_courses(
    year: int,
    dept_code: int,
    mock_response_data: List[Dict[str, Any]],
    expected_result: List[CorsoDiStudi],
) -> None:
    expected_url = "https://public.smartedu.unict.it/EnqaDataViewer/getCourses"
    client, stub = make_client(return_value={"data": mock_response_data})

    result = client.get_courses(year, dept_code)

    assert result == expected_result
    assert all(isinstance(c, CorsoDiStudi) for c in result)
    assert len(stub.calls) == 1
    url, payload = stub.calls[0]
    assert url == expected_url
    assert payload["academicYear"] == year
    assert payload["departmentCode"] == str(dept_code)


@pytest.mark.parametrize("year, dept_code", [(2024, 12345), (2023, 67890)])
def test_get_courses_api_failure(year: int, dept_code: int) -> None:
    client, stub = make_client(raises=Exception("API non raggiungibile"))

    result = client.get_courses(year, dept_code)

    assert result == []
    assert len(stub.calls) == 1
    _, payload = stub.calls[0]
    assert payload["departmentCode"] == str(dept_code)


@pytest.mark.parametrize(
    "year, dept_code, course_code, mock_response_data, expected_result",
    [
        (
            2023,
            190141,
            "W82",
            [
                {
                    "activityCode": "1001829",
                    "activityName": "ULTERIORI ATTIVITA'",
                    "professorName": "FRANCESCO",
                    "professorLastName": "GUARNERA",
                    "professorTaxCode": "",
                    "channel": None,
                    "partCode": None,
                    "SSDsigla": "INF/01",
                },
                {
                    "activityCode": "A3688",
                    "activityName": "MATERIA SPORCA",
                    "professorName": "MARIO",
                    "professorLastName": "ROSSI",
                },
                {"activityCode": None, "activityName": "TOTALE"},
            ],
            [
                Insegnamento(
                    codice_gomp=1001829,
                    id_cds="W82",
                    anno_accademico="2023/2024",
                    nome="ULTERIORI ATTIVITA'",
                    docente="GUARNERA FRANCESCO",
                    canale="no",
                    id_modulo=0,
                    ssd="INF/01",
                    professor_tax="",
                )
            ],
        )
    ],
)
def test_get_activities(
    year: int,
    dept_code: int,
    course_code: str,
    mock_response_data: List[Dict[str, Any]],
    expected_result: List[Insegnamento],
) -> None:
    expected_url = "https://public.smartedu.unict.it/EnqaDataViewer/getActivities"
    client, stub = make_client(return_value={"data": mock_response_data})

    result = client.get_activities(year, dept_code, course_code)

    assert result == expected_result
    assert all(isinstance(a, Insegnamento) for a in result)
    assert len(stub.calls) == 1
    url, payload = stub.calls[0]
    assert url == expected_url
    assert payload["courseCode"] == course_code
    assert payload["departmentCode"] == str(dept_code)


@pytest.mark.parametrize(
    "year, dept_code, course_code",
    [(2024, 12345, "M12"), (2023, 67890, "F34")],
)
def test_get_activities_api_failure(
    year: int, dept_code: int, course_code: str
) -> None:
    client, stub = make_client(raises=Exception("API non raggiungibile"))

    result = client.get_activities(year, dept_code, course_code)

    assert result == []
    assert len(stub.calls) == 1


@pytest.mark.parametrize(
    "year, dept_code, course_code, activity_code, prof_tax, mock_response, expected_result",
    [
        (
            2023,
            190141,
            "W82",
            1014456,
            "PROFCF123",
            {
                "clusterData": [
                    {
                        "cluster": {"Text": "Test Cluster"},
                        "questions": [
                            {"questionCode": "1", "submissions": 10, "answers": []}
                        ],
                    }
                ],
                "graphPieList": [],
            },
            [
                SchedaOpis(
                    anno_accademico="2023/2024",
                    id_insegnamento=1014456,
                    totale_schede=10,
                    totale_schede_nf=0,
                    fc=0,
                    inatt_nf=0,
                    domande=[0] * 60,
                    domande_nf=[0] * 60,
                    motivo_nf=[],
                    sugg=[],
                    sugg_nf=[],
                )
            ],
        ),
        (
            2023,
            190141,
            "W82",
            9999999,
            "",
            {"clusterData": [], "graphPieList": []},
            [
                SchedaOpis(
                    anno_accademico="2023/2024",
                    id_insegnamento=9999999,
                    totale_schede=0,
                    totale_schede_nf=0,
                    fc=0,
                    inatt_nf=0,
                    domande=[0] * 60,
                    domande_nf=[0] * 60,
                    motivo_nf=[],
                    sugg=[],
                    sugg_nf=[],
                )
            ],
        ),
    ],
)
def test_get_questions(
    year: int,
    dept_code: int,
    course_code: str,
    activity_code: int,
    prof_tax: str,
    mock_response: Dict[str, Any],
    expected_result: List[SchedaOpis],
) -> None:
    expected_url = "https://public.smartedu.unict.it/EnqaDataViewer/getQuestions"
    client, stub = make_client(return_value=mock_response)

    result = client.get_questions(
        year, dept_code, course_code, activity_code, prof_tax)

    assert result == expected_result
    assert len(stub.calls) == 1
    url, payload = stub.calls[0]
    assert url == expected_url
    assert payload["activityCode"] == str(activity_code)
    assert payload["professor"] == prof_tax
    assert payload["courseCode"] == course_code
    assert payload["departmentCode"] == str(dept_code)


@pytest.mark.parametrize(
    "year, dept_code, course_code, activity_code, prof_tax",
    [(2024, 12345, "M12", 987654, "PROFCF1"),
     (2023, 67890, "F34", 112233, "PROFCF2")],
)
def test_get_questions_failure(
    year: int,
    dept_code: int,
    course_code: str,
    activity_code: int,
    prof_tax: str,
) -> None:
    client, stub = make_client(raises=Exception("API non raggiungibile"))

    result = client.get_questions(
        year, dept_code, course_code, activity_code, prof_tax)

    assert result == []
    assert len(stub.calls) == 1
