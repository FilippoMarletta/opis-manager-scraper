import pytest
import mysql.connector

from src.config import DbConfig
from src.database import MySqlDatabaseClient
from src.models import CorsoDiStudi, Dipartimento, Insegnamento, SchedaOpis


class StubCursor:
    """
    Stub for mysql.connector.cursor.

    configurable attributes:
        fetchone_return  — value returned by fetchone()
        lastrowid        — id of the last inserted row
        execute_error    — if setted, execute() raises this error
        executemany_error — if setted, executemany() raises this error

    inspection attributes:
        execute_calls    — list of (query, params) received by execute()
        executemany_calls — list of (query, params) received by executemany()
        closed           — True if close() has been called
    """

    def __init__(self) -> None:
        self.fetchone_return: object = None
        self.lastrowid: int | None = None
        self.execute_error: Exception | None = None
        self.executemany_error: Exception | None = None

        self.execute_calls: list[tuple] = []
        self.executemany_calls: list[tuple] = []
        self.closed: bool = False

    def execute(self, query: str, params: tuple = ()) -> None:
        if self.execute_error:
            raise self.execute_error
        self.execute_calls.append((query, params))

    def executemany(self, query: str, params: list) -> None:
        if self.executemany_error:
            raise self.executemany_error
        self.executemany_calls.append((query, params))

    def fetchone(self) -> object:
        return self.fetchone_return

    def close(self) -> None:
        self.closed = True


class StubConnection:
    """
    Stub for mysql.connector.connect().

    Inspection attributes:
        committed — True if commit() has been called
        closed    — True if close() has been called
    """

    def __init__(self, cursor: StubCursor) -> None:
        self._cursor = cursor
        self.committed: bool = False
        self.closed: bool = False

    def cursor(self) -> StubCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True

    def is_connected(self) -> bool:
        return not self.closed


@pytest.fixture
def connected_client(mocker):
    """
    Returns a tuple (MySqlDatabaseClient, StubCursor).

    The MySQL connector is mocked with a typed StubConnection.
    The client is already connected and ready for assertions.
    """
    cursor = StubCursor()
    conn = StubConnection(cursor)
    mocker.patch("src.database.mysql.connector.connect", return_value=conn)

    client = MySqlDatabaseClient(DbConfig())
    client.connect()
    return client, cursor


def test_connect_opens_connection(mocker) -> None:
    cursor = StubCursor()
    mock_connect = mocker.patch(
        "src.database.mysql.connector.connect",
        return_value=StubConnection(cursor),
    )

    client = MySqlDatabaseClient(DbConfig())
    client.connect()

    mock_connect.assert_called_once()
    assert client._connection is not None


def test_connect_failure_raises_and_logs(mocker, caplog) -> None:
    mocker.patch(
        "src.database.mysql.connector.connect",
        side_effect=mysql.connector.Error("Credenziali errate"),
    )

    with pytest.raises(mysql.connector.Error):
        MySqlDatabaseClient(DbConfig()).connect()

    assert "Errore di connessione a MySQL" in caplog.text


def test_close_calls_connection_close(mocker) -> None:
    cursor = StubCursor()
    conn = StubConnection(cursor)
    mocker.patch("src.database.mysql.connector.connect", return_value=conn)

    client = MySqlDatabaseClient(DbConfig())
    client.connect()
    client.close()

    assert conn.closed


def test_context_manager_closes_on_exit(mocker) -> None:
    cursor = StubCursor()
    conn = StubConnection(cursor)
    mocker.patch("src.database.mysql.connector.connect", return_value=conn)

    with MySqlDatabaseClient(DbConfig()):
        pass

    assert conn.closed


@pytest.mark.parametrize(
    "fetchone_return, expected_id",
    [
        ((99,), 99),  # row found → returns the id
        (None, -1),  # INSERT IGNORE did not insert, SELECT found nothing
    ],
    ids=["found", "not_found"],
)
def test_insert_department(connected_client, fetchone_return, expected_id) -> None:
    client, cursor = connected_client
    cursor.fetchone_return = fetchone_return

    dip = Dipartimento(unict_id=123, nome="Informatica",
                       anno_accademico="2023/2024")
    result = client.insert_department(dip)

    assert result == expected_id
    assert len(cursor.execute_calls) == 2  # INSERT + SELECT
    assert cursor.closed


def test_insert_department_db_error(connected_client, caplog) -> None:
    client, cursor = connected_client
    cursor.execute_error = mysql.connector.Error("Errore DB")

    dip = Dipartimento(unict_id=123, nome="Informatica",
                       anno_accademico="2023/2024")

    assert client.insert_department(dip) == -1
    assert "Errore DB inserimento dipartimento" in caplog.text


def test_insert_department_without_connection() -> None:
    client = MySqlDatabaseClient(DbConfig())
    dip = Dipartimento(unict_id=1, nome="Dip", anno_accademico="23/24")

    assert client.insert_department(dip) == -1


@pytest.mark.parametrize(
    "fetchone_return, expected_id",
    [
        ((42,), 42),
        (None, -1),
    ],
    ids=["found", "not_found"],
)
def test_insert_course(connected_client, fetchone_return, expected_id) -> None:
    client, cursor = connected_client
    cursor.fetchone_return = fetchone_return

    corso = CorsoDiStudi(
        unict_id="M12",
        nome="Matematica",
        classe="LM-40",
        anno_accademico="2023/2024",
        dipartimento_id=123,
    )
    result = client.insert_course(corso, dipartimento_internal_id=99)

    assert result == expected_id
    assert len(cursor.execute_calls) == 2  # INSERT + SELECT


def test_insert_course_db_error(connected_client, caplog) -> None:
    client, cursor = connected_client
    cursor.execute_error = mysql.connector.Error("Errore DB")

    corso = CorsoDiStudi(
        unict_id="M12",
        nome="Matematica",
        classe="LM-40",
        anno_accademico="2023/2024",
        dipartimento_id=123,
    )

    assert client.insert_course(corso, dipartimento_internal_id=99) == -1
    assert "Errore DB inserimento corso" in caplog.text


def test_insert_course_without_connection() -> None:
    client = MySqlDatabaseClient(DbConfig())
    corso = CorsoDiStudi(
        unict_id="C1",
        nome="Corso",
        classe="L",
        anno_accademico="23/24",
        dipartimento_id=1,
    )

    assert client.insert_course(corso, 1) == -1


def test_insert_insegnamento_success(connected_client) -> None:
    client, cursor = connected_client
    cursor.lastrowid = 100

    ins = Insegnamento(
        codice_gomp=1010,
        id_cds="M12",
        anno_accademico="2023/2024",
        nome="Analisi I",
        docente="Mario Rossi",
        professor_tax="",
    )

    result = client.insert_insegnamento(ins, corso_internal_id=42)

    assert result == 100
    assert len(cursor.execute_calls) == 1


def test_insert_insegnamento_db_error(connected_client, caplog) -> None:
    client, cursor = connected_client
    cursor.execute_error = mysql.connector.Error("Errore DB")

    ins = Insegnamento(
        codice_gomp=1010,
        id_cds="M12",
        anno_accademico="2023/2024",
        nome="Analisi I",
        docente="Mario Rossi",
        professor_tax="",
    )

    assert client.insert_insegnamento(ins, corso_internal_id=42) == -1
    assert "Errore DB inserimento insegnamento" in caplog.text


def test_insert_insegnamento_without_connection() -> None:
    client = MySqlDatabaseClient(DbConfig())
    ins = Insegnamento(
        codice_gomp=1,
        id_cds="C1",
        anno_accademico="23/24",
        nome="Materia",
        docente="Doc",
        professor_tax="",
    )

    assert client.insert_insegnamento(ins, 1) == -1


def test_insert_schede_opis_success(connected_client) -> None:
    client, cursor = connected_client

    scheda = SchedaOpis(
        anno_accademico="2023/2024",
        id_insegnamento=1010,
        totale_schede=5,
        totale_schede_nf=0,
        fc=0,
        inatt_nf=0,
        domande=[1, 2, 3],
        domande_nf=[],
        motivo_nf=[],
        sugg=[],
        sugg_nf=[],
    )

    client.insert_schede_opis([scheda], insegnamento_internal_id=100)

    assert len(cursor.executemany_calls) == 1
    query, val_list = cursor.executemany_calls[0]
    assert "INSERT INTO schede_opis" in query
    assert len(val_list) == 1
    assert "[1, 2, 3]" in val_list[0]


def test_insert_schede_opis_db_error(connected_client, caplog) -> None:
    client, cursor = connected_client
    cursor.executemany_error = mysql.connector.Error("Errore DB")

    scheda = SchedaOpis(
        anno_accademico="2023/2024",
        id_insegnamento=1010,
        totale_schede=5,
        totale_schede_nf=0,
        fc=0,
        inatt_nf=0,
        domande=[1, 2, 3],
        domande_nf=[],
        motivo_nf=[],
        sugg=[],
        sugg_nf=[],
    )

    client.insert_schede_opis([scheda], insegnamento_internal_id=100)

    assert "Errore DB salvataggio" in caplog.text


@pytest.mark.parametrize(
    "schede, disconnect_before",
    [
        ([], False),  # empty list → no executemany
        (None, True),  # no connection → no executemany
    ],
    ids=["empty_list", "no_connection"],
)
def test_insert_schede_opis_skipped(
    connected_client, schede, disconnect_before
) -> None:
    client, cursor = connected_client

    if disconnect_before:
        client._connection = None

    client.insert_schede_opis(schede or [], insegnamento_internal_id=100)

    assert len(cursor.executemany_calls) == 0


def test_all_inserts_without_connection(caplog) -> None:
    """Without a connection, all insert methods should return -1 or do nothing, and log an error."""
    client = MySqlDatabaseClient(DbConfig())

    dip = Dipartimento(unict_id=1, nome="Dip", anno_accademico="23/24")
    corso = CorsoDiStudi(
        unict_id="C1",
        nome="Corso",
        classe="L",
        anno_accademico="23/24",
        dipartimento_id=1,
    )
    ins = Insegnamento(
        codice_gomp=1,
        id_cds="C1",
        anno_accademico="23/24",
        nome="Mat",
        docente="Doc",
        professor_tax="",
    )
    scheda = SchedaOpis(
        anno_accademico="23/24",
        id_insegnamento=1,
        totale_schede=0,
        totale_schede_nf=0,
        fc=0,
        inatt_nf=0,
        domande=[],
        domande_nf=[],
        motivo_nf=[],
        sugg=[],
        sugg_nf=[],
    )

    assert client.insert_department(dip) == -1
    assert client.insert_course(corso, 1) == -1
    assert client.insert_insegnamento(ins, 1) == -1
    client.insert_schede_opis([scheda], 1)  # must end silently

    assert "Database non connesso" in caplog.text
