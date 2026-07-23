"""Seed de la matriz digitalizada de Gran Tierra Energy.

Fuente: docs/superpowers/specs/matriz-digitalizada-clientes/matriz-clientes.json
(item "PROYECTO": "GRAN TIERRA ENERGY"). Idempotente:
    python manage.py cargar_matriz_gran_tierra <proyecto_id> [--activar] [--modo sombra|activo]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ia.models import MatrizCliente
from apps.proyectos.models import Proyecto

# Menciones de marca a vigilar (la empresa; los voceros van aparte).
MARCAS_GRAN_TIERRA = [
    "Gran Tierra Energy",
    "Gran Tierra",
    "#GranTierraEnergy",
    "grantierra_inc",
]

VOCEROS_GRAN_TIERRA = [
    {"nombre": "Enrique Villalobos", "notas": "vocero Gran Tierra Energy"},
    {"nombre": "Gary Guidry", "notas": "vocero Gran Tierra Energy"},
    {"nombre": "Manuel Buitrago", "notas": "vocero Gran Tierra Energy"},
]

# COLOMBIA-ECUADOR-CANADÁ + USA y UK (añadidos a petición del cliente).
PAISES_GRAN_TIERRA = ["CO", "EC", "CA", "US", "GB"]

REGLAS_NO_ALERTAR = [
    {
        "tipo": "semantica",
        "clave": "gran_tierra_expresion_generica",
        "ejecutor": "llm",
        "descripcion": (
            "No alertar cuando 'gran tierra' se usa como expresión genérica y no se "
            "refiere a la empresa (ej. \"esta es una gran tierra para vivir\")."
        ),
    },
]

# "Criterios sector" del matriz: contexto de hidrocarburos y competidores.
CRITERIOS_SECTOR = [
    {
        "clave": "sector_hidrocarburos",
        "emoji": "",
        "descripcion": (
            "Contexto del sector que impacte a Gran Tierra Energy: petróleo, gasolina, "
            "combustibles, GLP, hidrocarburos y minería."
        ),
    },
    {
        "clave": "competidores",
        "emoji": "",
        "descripcion": "Menciones de competidores relevantes: Canacol, Ecopetrol.",
    },
]

# MENCION del matriz es "todo donde los mencionen" (no filtra por tonalidad),
# así que la tonalidad es informativa. SEMAFORO: NO -> sin semáforo.
ESQUEMA_TONALIDAD = {
    "escala": ["positivo", "neutral", "negativo"],
    "definiciones": {
        "positivo": "Mención favorable a Gran Tierra Energy, su operación o su gestión.",
        "neutral": "Mención informativa sin carga reputacional relevante.",
        "negativo": "Mención que afecta la reputación de Gran Tierra Energy.",
    },
}


class Command(BaseCommand):
    help = "Carga (o actualiza) la matriz digitalizada de Gran Tierra Energy para un proyecto"

    def add_arguments(self, parser):
        parser.add_argument("proyecto_id", help="UUID del proyecto Gran Tierra")
        parser.add_argument(
            "--activar",
            action="store_true",
            help="Activa el pipeline IA para el proyecto (arranca en modo sombra)",
        )
        parser.add_argument(
            "--modo",
            choices=[MatrizCliente.MODO_SOMBRA, MatrizCliente.MODO_ACTIVO],
            default=MatrizCliente.MODO_SOMBRA,
        )

    def handle(self, *args, **options):
        try:
            proyecto = Proyecto.objects.get(id=options["proyecto_id"])
        except (Proyecto.DoesNotExist, ValueError, Exception) as exc:
            raise CommandError(f"Proyecto no encontrado: {exc}")

        matriz, creada = MatrizCliente.objects.update_or_create(
            proyecto=proyecto,
            defaults={
                "activo": options["activar"],
                "modo": options["modo"],
                "descripcion_cliente": (
                    "Gran Tierra Energy, compañía de exploración y producción de "
                    "hidrocarburos (petróleo y gas). Medición en Colombia, Ecuador y "
                    "Canadá; a petición del cliente se añadieron Estados Unidos y Reino "
                    "Unido. Se monitorea todo el contenido donde se mencione a la empresa "
                    "o a sus voceros."
                ),
                "voceros": VOCEROS_GRAN_TIERRA,
                "marcas": MARCAS_GRAN_TIERRA,
                "menciones_criterio": (
                    "Todo el contenido donde mencionen a Gran Tierra Energy (la empresa) "
                    "o a sus voceros. También es relevante el contexto del sector "
                    "hidrocarburos y de competidores cuando impacte a la empresa."
                ),
                "paises": PAISES_GRAN_TIERRA,
                "reglas_no_alertar": REGLAS_NO_ALERTAR,
                "criterios_sector": CRITERIOS_SECTOR,
                "esquema_tonalidad": ESQUEMA_TONALIDAD,
                # SEMAFORO: NO -> sin semáforo ni bandera (el matriz no los pide).
                "config_semaforo": {},
                "incluir_bandera": False,
                "incluir_semaforo": False,
                "umbral_confianza": {
                    "redes": {"auto_envio": 0.85, "descarte": 0.90},
                    "medios": {"auto_envio": 0.85, "descarte": 0.90},
                },
                "reglas_nunca_autoenviar": [],
                "campos_requeridos_envio": {
                    "redes": ["reach", "engagement"],
                    "medios": ["titulo"],
                },
                "prompt_adicional": (
                    "Considera también relevante el contexto del sector hidrocarburos "
                    "(petróleo, gas, combustibles, GLP, minería) y las menciones de "
                    "competidores (Canacol, Ecopetrol) cuando impacten a Gran Tierra Energy."
                ),
                "observaciones": (
                    "Frecuencia: todos los días. Ubicación en Talkwalker: ESTIMADOS. "
                    "Filtros Talkwalker: tipo de contenido medios y redes. "
                    "Las alertas llevan el encabezado '📣 *Brand and Spokesperson*'. "
                    "Semáforo: NO."
                ),
            },
        )

        accion = "creada" if creada else "actualizada"
        self.stdout.write(
            self.style.SUCCESS(
                f"Matriz Gran Tierra Energy {accion} para '{proyecto.nombre}' "
                f"(activo={matriz.activo}, modo={matriz.modo})"
            )
        )
