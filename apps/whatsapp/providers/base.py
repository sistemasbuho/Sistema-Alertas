from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ResultadoEnvio:
    exito: bool
    proveedor: str
    status_code: Optional[int] = None
    detalle: Any = None


class MensajeriaProvider(ABC):
    """Interfaz común de los proveedores de mensajería WhatsApp."""

    nombre = ""

    def disponible(self) -> bool:
        """True si el proveedor tiene la configuración necesaria para operar."""
        return True

    @abstractmethod
    def send_text(self, grupo_id: str, body: str, no_link_preview: bool = True) -> ResultadoEnvio:
        ...
