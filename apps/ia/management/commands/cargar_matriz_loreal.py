"""Seed de la matriz digitalizada de L'Oréal (piloto del sprint IA-first).

Fuente: matriz-clientes-proyectos.md (fila LOREAL). Idempotente:
    python manage.py cargar_matriz_loreal <proyecto_id> [--activar] [--modo sombra|activo]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.ia.models import MatrizCliente
from apps.proyectos.models import Proyecto

MARCAS_LOREAL = [
    "L'Oréal",
    "YSL",
    "Yves Saint Laurent",
    "Lancôme",
    "Giorgio Armani",
    "Kiehl's",
    "Urban Decay",
    "Garnier",
    "Maybelline",
    "NYX",
    "La Roche-Posay",
    "CeraVe",
    "SkinCeuticals",
    "Vichy",
    "Kérastase",
    "Redken",
    "Elvive",
    "Biotherm",
    "Shu Uemura",
    "IT Cosmetics",
    "Ralph Lauren",
    "Cacharel",
    "Youth to the People",
    "Essie",
    "Vogue",
    "Biolage",
    "Pureology",
    "Aesop",
]

VOCEROS_LOREAL = [
    {"nombre": "Gianpaolo Graziani", "notas": "vocero L'Oréal"},
    {"nombre": "Magdalena Zapata", "notas": "vocera L'Oréal"},
    {"nombre": "Gustavo Calvache", "notas": "vocero L'Oréal"},
    {"nombre": "Movipack", "notas": "proveedor de maquila"},
    {"nombre": "Carlos Lejune", "notas": "Movipack"},
    {"nombre": "Pamela Méndez", "notas": "Movipack"},
    {"nombre": "Magdalena Navarro", "notas": "Movipack"},
    {"nombre": "Bligraf", "notas": "proveedor"},
    {"nombre": "Centro de Distribución L'Oréal Chile", "notas": ""},
]

PAISES_LOREAL = [
    "AR", "BO", "BR", "CL", "CO", "CR", "EC", "SV",
    "GT", "MX", "PA", "PY", "PE", "UY", "VE",
]

REGLAS_NO_ALERTAR = [
    {"tipo": "min_seguidores", "valor": 500, "ejecutor": "codigo",
     "descripcion": "No se envían alertas de cuentas con menos de 500 seguidores"},
    {"tipo": "pais_fuera_lista", "ejecutor": "codigo",
     "descripcion": "Las alertas deben ser de cuentas de los países de la medición"},
    {"tipo": "semantica", "clave": "precio_negativo", "ejecutor": "llm",
     "descripcion": "No se envían alertas que mencionen los precios/valor de forma negativa"},
    {"tipo": "semantica", "clave": "producto_no_belleza", "ejecutor": "llm",
     "descripcion": "Menciones a productos que no sean de belleza (téxtil / cirugías estéticas)"},
]

CRITERIOS_SECTOR = [
    {"clave": "belleza", "emoji": "💄",
     "descripcion": "Cualquier hecho que impacte de forma general el sector belleza "
                    "(nuevos productos, quejas, denuncias, demandas, etc.)"},
    {"clave": "empoderamiento_femenino", "emoji": "♀️",
     "descripcion": "Publicaciones relacionadas a mujeres que impacten el sector "
                    "(nueva CEO de Yanbal, embajadoras de crema antiacné, etc.)"},
    {"clave": "ingredientes", "emoji": "🧪",
     "descripcion": "Notas sobre la relación negativa de los ingredientes usados en "
                    "productos de belleza (ingrediente en shampoos que causa cáncer, etc.)"},
    {"clave": "medio_ambiente", "emoji": "🌱",
     "descripcion": "Información que relacione al sector belleza con el medio ambiente "
                    "(la industria del maquillaje genera miles de toneladas de plástico, etc.)"},
    {"clave": "responsabilidad_social", "emoji": "👥",
     "descripcion": "Hechos en materia social relacionados al sector belleza "
                    "(cursos de maquillaje a mujeres en situación de pobreza, etc.)"},
]

ESQUEMA_TONALIDAD = {
    "escala": ["positivo", "neutral", "negativo"],
    "foco": "negativo",
    "definiciones": {
        "negativo": "Mención que atenta contra la reputación de la calidad de los "
                    "productos y/o la integridad de los usuarios de las marcas del grupo",
        "neutral": "Mención informativa sin carga reputacional para las marcas",
        "positivo": "Mención favorable a las marcas o al grupo",
    },
}

CONFIG_SEMAFORO = {
    "tipo": "riesgo_engagement_reach",
    "engagement_alto": {
        "twitter": 100,
        "facebook": 150,
        "instagram": 500,
        "tiktok": 500,
        "default": 500,
    },
    "reach_niveles": {"bajo": [500, 1000], "medio": [1000, 8000], "alto": 8000},
    "emojis": {"bajo": "🟢", "medio": "🟡", "alto": "🔴"},
}


class Command(BaseCommand):
    help = "Carga (o actualiza) la matriz digitalizada de L'Oréal para un proyecto"

    def add_arguments(self, parser):
        parser.add_argument("proyecto_id", help="UUID del proyecto L'Oréal")
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
                    "L'Oréal, grupo global de belleza. Medición en 15 países de LATAM. "
                    "Se monitorean menciones negativas de la marca y sus productos."
                ),
                "voceros": VOCEROS_LOREAL,
                "marcas": MARCAS_LOREAL,
                "menciones_criterio": (
                    "Menciones negativas que atenten contra la reputación de la calidad "
                    "de sus productos y/o contra la integridad de los usuarios, de "
                    "L'Oréal y las marcas del grupo. También son relevantes los hechos "
                    "del sector belleza según las categorías definidas."
                ),
                "paises": PAISES_LOREAL,
                "reglas_no_alertar": REGLAS_NO_ALERTAR,
                "criterios_sector": CRITERIOS_SECTOR,
                "esquema_tonalidad": ESQUEMA_TONALIDAD,
                "config_semaforo": CONFIG_SEMAFORO,
                "umbral_confianza": {
                    "redes": {"auto_envio": 0.85, "descarte": 0.90},
                    "medios": {"auto_envio": 0.85, "descarte": 0.90},
                },
                # Para L'Oréal lo negativo ES el producto: sin reglas nunca-autoenviar
                "reglas_nunca_autoenviar": [],
                "incluir_bandera": True,
                "incluir_semaforo": True,
                "campos_requeridos_envio": {
                    "redes": ["pais", "reach", "engagement"],
                    "medios": ["pais", "titulo"],
                },
                "observaciones": (
                    "Frecuencia: todos los días. Cada publicación enviada debe tener la "
                    "bandera del país del contexto de la publicación y el semáforo de riesgo."
                ),
            },
        )

        accion = "creada" if creada else "actualizada"
        self.stdout.write(
            self.style.SUCCESS(
                f"Matriz L'Oréal {accion} para '{proyecto.nombre}' "
                f"(activo={matriz.activo}, modo={matriz.modo})"
            )
        )
