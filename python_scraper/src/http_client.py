from typing import Any, Dict, Protocol, runtime_checkable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import ApiConfig


@runtime_checkable
class HttpClient(Protocol):
    """
    Interface for HTTP client. enable astracting away the underlying implementation (e.g. requests, httpx, aiohttp)
     and allows for easier testing (e.g. by mocking this interface).
    """

    def post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]: ...


class RequestsHttpClient:
    """
    Implementation of HttpClient using the requests library. It supports retries and custom headers as defined in the ApiConfig.
    """

    def __init__(self, config: ApiConfig) -> None:
        self._config = config
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:  # pragma: no cover
        retry_strategy = Retry(
            total=self._config.retry.total,
            backoff_factor=self._config.retry.backoff_factor,
            status_forcelist=list(self._config.retry.status_forcelist),
            allowed_methods=list(self._config.retry.allowed_methods),
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.headers.update(self._config.headers)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def post(
        self, url: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:  # pragma: no cover
        response = self._session.post(url, json=payload, timeout=self._config.timeout)
        response.raise_for_status()
        return response.json()
