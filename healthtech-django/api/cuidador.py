"""Vista de cuidador: enlace permanente (QR) de SOLO LECTURA a la ficha del paciente."""
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import EnlaceCuidador, Medicamento, RegistroINR


class EnlaceInvalido(APIException):
    status_code = 404
    default_detail = 'Este código QR ya no es válido. Pide uno nuevo al paciente.'
    default_code = 'enlace_invalido'
    usar_detalle = True


def _texto(v, largo=120):
    return str(v).strip()[:largo] if v is not None else ''


def limpiar_ficha(datos):
    """Solo se guardan campos conocidos y con largo acotado (el cliente no es de fiar)."""
    datos = datos if isinstance(datos, dict) else {}
    diag = datos.get('diagnosticos')
    diag = [_texto(d, 200) for d in diag[:15]] if isinstance(diag, list) else []
    return {
        'medico': _texto(datos.get('medico')),
        'ultimoControl': _texto(datos.get('ultimoControl'), 10),
        'proximoControl': _texto(datos.get('proximoControl'), 10),
        'diagnosticos': [d for d in diag if d],
    }


class EnlaceCuidadorView(APIView):
    """GET: devuelve el token (lo crea la primera vez). POST: genera uno nuevo (el anterior deja de servir)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        enlace, _ = EnlaceCuidador.objects.get_or_create(usuario=request.user)
        return Response({'token': enlace.token})

    def post(self, request):
        enlace, _ = EnlaceCuidador.objects.get_or_create(usuario=request.user)
        enlace.regenerar()
        return Response({'token': enlace.token})


class FichaCuidadorView(APIView):
    """El paciente sincroniza aquí los datos de su ficha que solo viven en su navegador."""
    permission_classes = [IsAuthenticated]

    def put(self, request):
        enlace, _ = EnlaceCuidador.objects.get_or_create(usuario=request.user)
        enlace.ficha = limpiar_ficha(request.data)
        enlace.save(update_fields=['ficha'])
        return Response({'mensaje': 'Ficha sincronizada.'})


class LimiteCuidador(AnonRateThrottle):
    scope = 'cuidador_publico'
    rate = '60/min'


class VerCuidadorView(APIView):
    """Público (sin login) y de solo lectura. El token del QR es la llave."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LimiteCuidador]

    def get(self, request, token):
        try:
            enlace = EnlaceCuidador.objects.select_related('usuario').get(token=token)
        except EnlaceCuidador.DoesNotExist:
            raise EnlaceInvalido()
        u = enlace.usuario
        hoy = timezone.localdate()
        inr = RegistroINR.objects.filter(usuario=u).order_by('-fechaLectura', '-id')[:30]
        meds = Medicamento.objects.filter(usuario=u)
        return Response({
            'paciente': (u.first_name or u.username)[:80],
            'hoy': hoy.isoformat(),
            'ficha': enlace.ficha or {},
            'inr': [{'fecha': r.fechaLectura.isoformat(), 'valor': r.valorINR,
                     'min': r.rangoTerapeuticoMin, 'max': r.rangoTerapeuticoMax} for r in inr],
            'medicamentos': [{
                'nombre': m.nombre, 'unidad': m.unidadPastilla,
                'hora': m.horaProgramada.strftime('%H:%M') if m.horaProgramada else '',
                'horarioSemanal': m.horarioSemanal,
                'tomadaHoy': m.fechaUltimaConfirmacion == hoy,
            } for m in meds],
        })
