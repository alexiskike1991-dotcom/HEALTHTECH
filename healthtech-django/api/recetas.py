"""Biblioteca de recetas: guarda la foto de cada hoja (y lo que leyó la IA) como respaldo del paciente."""
import io
import json

from django.http import HttpResponse
from PIL import Image, UnidentifiedImageError
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from .ia import normalizar_imagen
from .models import Receta
from .permissions import es_admin, es_medico

MAX_RECETAS = 60
TIPOS_PERMITIDOS = {'JPEG', 'PNG', 'WEBP'}


def _t(v, largo=120):
    return str(v).strip()[:largo] if v is not None else ''


def _n(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def limpiar_datos(crudo):
    """Solo campos conocidos y con largo acotado (el cliente no es de fiar)."""
    d = crudo if isinstance(crudo, dict) else {}
    meds = d.get('medicamentos')
    meds = [_t(m, 120) for m in meds[:20]] if isinstance(meds, list) else []
    return {
        'medico': _t(d.get('medico')),
        'ultimoControl': _t(d.get('ultimoControl'), 10),
        'proximoControl': _t(d.get('proximoControl'), 10),
        'inr': _n(d.get('inr')), 'min': _n(d.get('min')), 'max': _n(d.get('max')),
        'medicamentos': [m for m in meds if m],
    }


def reducir(jpeg, lado, calidad):
    img = Image.open(io.BytesIO(jpeg)).convert('RGB')
    img.thumbnail((lado, lado))
    b = io.BytesIO()
    img.save(b, format='JPEG', quality=calidad)
    return b.getvalue()


def _ficha(r):
    return {'id': r.id, 'creada': r.creada.isoformat(), 'datos': r.datos or {}}


class RecetasView(APIView):
    """GET: lista de mis recetas (sin la foto). POST: guarda una receta nueva (foto + datos)."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        return Response([_ficha(r) for r in Receta.objects.filter(usuario=request.user).defer('imagen')])

    def post(self, request):
        archivo = request.FILES.get('imagen')
        if not archivo:
            raise ValidationError({'imagen': ['No se envió ninguna imagen.']})
        if archivo.size > settings.RECETA_MAX_BYTES:
            raise ValidationError({'imagen': [f'La imagen supera los {settings.RECETA_MAX_BYTES // 1048576} MB.']})
        if Receta.objects.filter(usuario=request.user).count() >= MAX_RECETAS:
            raise ValidationError({'imagen': [f'Llegaste al máximo de {MAX_RECETAS} recetas guardadas.']})
        try:
            if Image.open(archivo).format not in TIPOS_PERMITIDOS:
                raise ValidationError({'imagen': ['Formato no permitido. Usa JPEG, PNG o WEBP.']})
            archivo.seek(0)
            jpeg = reducir(normalizar_imagen(archivo), 1600, 80)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise ValidationError({'imagen': ['Archivo de imagen inválido o corrupto.']})
        try:
            crudo = json.loads(request.data.get('datos') or '{}')
        except ValueError:
            crudo = {}
        receta = Receta.objects.create(usuario=request.user, imagen=jpeg, datos=limpiar_datos(crudo))
        return Response(_ficha(receta), status=status.HTTP_201_CREATED)


def _obtener(request, pk):
    try:
        r = Receta.objects.get(pk=pk)
    except Receta.DoesNotExist:
        raise NotFound('La receta no existe.')
    if r.usuario_id != request.user.id and not (es_medico(request.user) or es_admin(request.user)):
        raise NotFound('La receta no existe.')
    return r


class RecetaImagenView(APIView):
    """GET: la foto de la receta (la ve su dueño y el personal)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        r = _obtener(request, pk)
        resp = HttpResponse(bytes(r.imagen), content_type='image/jpeg')
        resp['Cache-Control'] = 'private, max-age=86400'
        return resp


class RecetaDetalleView(APIView):
    """DELETE: solo el personal (enfermero/a o super usuario) puede borrar una receta repetida."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        if not (es_medico(request.user) or es_admin(request.user)):
            raise PermissionDenied('Solo el personal puede eliminar recetas.')
        _obtener(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
