import json
import logging
from typing import Any, List, Protocol, runtime_checkable

import mysql.connector
from mysql.connector import Error

from .config import DbConfig
from .models import CorsoDiStudi, Dipartimento, Insegnamento, SchedaOpis

logger = logging.getLogger(__name__)


@runtime_checkable
class DatabaseClient(Protocol):
    """
    interface for database client. enables abstracting away the underlying implementation (e.g. MySqlDatabaseClient) and allows for easier testing (e.g. by mocking this interface).
    """

    def insert_department(self, department: Dipartimento) -> int: ...

    def insert_course(
        self, course: CorsoDiStudi, dipartimento_internal_id: int
    ) -> int: ...

    def insert_insegnamento(
        self, insegnamento: Insegnamento, corso_internal_id: int
    ) -> int: ...

    def insert_schede_opis(
        self, schede_opis: List[SchedaOpis], insegnamento_internal_id: int
    ) -> None: ...


class MySqlDatabaseClient:
    """
    implementation of DatabaseClient using MySQL. It manages the connection lifecycle and provides methods for inserting departments, courses, teachings, and OPIS sheets into the database.
    """

    def __init__(self, config: DbConfig) -> None:
        self._config = config
        self._connection: Any = None

    def connect(self) -> None:
        try:
            self._connection = mysql.connector.connect(
                host=self._config.host,
                port=self._config.port,
                user=self._config.user,
                password=self._config.password,
                database=self._config.database,
            )
            logger.info(f"Connessione al database '{self._config.database}' stabilita.")
        except Error as e:
            logger.error(f"Errore di connessione a MySQL: {e}")
            raise

    def close(self) -> None:
        if self._connection and self._connection.is_connected():
            self._connection.close()
            logger.info("Connessione al database chiusa.")

    def __enter__(self) -> "MySqlDatabaseClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _is_connected(self) -> bool:
        if not self._connection:
            logger.error("Database non connesso. Usa connect() o il context manager.")
            return False
        return True

    def insert_department(self, department: Dipartimento) -> int:
        if not self._is_connected():
            return -1

        try:
            cursor = self._connection.cursor()  # type: ignore[union-attr]
            cursor.execute(
                """
                INSERT IGNORE INTO dipartimento (nome, unict_id, anno_accademico)
                VALUES (%s, %s, %s)
                """,
                (department.nome, department.unict_id, department.anno_accademico),
            )
            self._connection.commit()  # type: ignore[union-attr]

            cursor.execute(
                "SELECT id FROM dipartimento WHERE unict_id = %s AND anno_accademico = %s",
                (department.unict_id, department.anno_accademico),
            )
            result = cursor.fetchone()
            cursor.close()
            if result is None:
                return -1
            raw_id: Any = result[0]
            return int(raw_id)
        except Error as e:
            logger.error(f"Errore DB inserimento dipartimento '{department.nome}': {e}")
            return -1

    def insert_course(self, course: CorsoDiStudi, dipartimento_internal_id: int) -> int:
        if not self._is_connected():
            return -1

        try:
            cursor = self._connection.cursor()  # type: ignore[union-attr]
            cursor.execute(
                """
                INSERT IGNORE INTO corso_di_studi
                    (unict_id, anno_accademico, nome, classe, id_dipartimento)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    course.unict_id,
                    course.anno_accademico,
                    course.nome,
                    course.classe,
                    dipartimento_internal_id,
                ),
            )
            self._connection.commit()

            cursor.execute(
                "SELECT id FROM corso_di_studi WHERE unict_id = %s AND anno_accademico = %s",
                (course.unict_id, course.anno_accademico),
            )
            result = cursor.fetchone()
            cursor.close()
            if result is None:
                return -1
            raw_id: Any = result[0]
            return int(raw_id)
        except Error as e:
            logger.error(f"Errore DB inserimento corso '{course.nome}': {e}")
            return -1

    def insert_insegnamento(
        self, insegnamento: Insegnamento, corso_internal_id: int
    ) -> int:
        if not self._is_connected():
            return -1

        try:
            cursor = self._connection.cursor()  # type: ignore[union-attr]
            cursor.execute(
                """
                INSERT INTO insegnamento
                    (anno_accademico, anno, semestre, nome, docente,
                     codice_gomp, cfu, canale, id_modulo, ssd, id_cds)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    insegnamento.anno_accademico,
                    insegnamento.anno,
                    insegnamento.semestre,
                    insegnamento.nome,
                    insegnamento.docente,
                    insegnamento.codice_gomp,
                    insegnamento.cfu,
                    insegnamento.canale,
                    insegnamento.id_modulo,
                    insegnamento.ssd,
                    corso_internal_id,
                ),
            )
            self._connection.commit()  # type: ignore[union-attr]
            internal_id = cursor.lastrowid
            cursor.close()
            return internal_id  # type: ignore[return-value]
        except Error as e:
            logger.error(
                f"Errore DB inserimento insegnamento '{insegnamento.nome}': {e}"
            )
            return -1

    def insert_schede_opis(
        self, schede_opis: List[SchedaOpis], insegnamento_internal_id: int
    ) -> None:
        if not self._is_connected() or not schede_opis:
            return

        try:
            cursor = self._connection.cursor()  # type: ignore[union-attr]

            # Dynamic SQL query construction based on SchedaOpis fields. Assumes all schede_opis have the same structure.
            first_row = vars(schede_opis[0]).copy()
            first_row["id_insegnamento"] = insegnamento_internal_id
            columns = list(first_row.keys())

            placeholders = ", ".join(["%s"] * len(columns))
            cols_string = ", ".join(columns)
            sql = f"INSERT INTO schede_opis ({cols_string}) VALUES ({placeholders})"

            val_list = []
            for scheda in schede_opis:
                row = vars(scheda).copy()
                row["id_insegnamento"] = insegnamento_internal_id
                val_list.append(
                    tuple(
                        json.dumps(v) if isinstance(v, (list, dict)) else v
                        for v in (row[col] for col in columns)
                    )
                )

            cursor.executemany(sql, val_list)
            self._connection.commit()  # type: ignore[union-attr]
            cursor.close()
        except Error as e:
            logger.error(f"Errore DB salvataggio {len(schede_opis)} schede OPIS: {e}")
