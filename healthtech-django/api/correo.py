"""Envío del control del paciente por correo.

Render (plan gratis) bloquea el correo normal (SMTP), así que se usa la API web de Brevo
(HTTPS, plan gratis de 300 correos al día). Variables de entorno en Render:
  BREVO_API_KEY   -> llave de la API de Brevo
  MAIL_FROM       -> correo remitente ya verificado en Brevo
  MAIL_FROM_NAME  -> (opcional) nombre que ve quien recibe. Por defecto "HealthTech TACO"
"""
import base64
import json
import logging
import os
import urllib.error
import urllib.request
from html import escape

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .exceptions import ErrorServicioExterno, ServicioNoDisponible
from .models import EnlaceCuidador, Medicamento, Receta, RegistroINR
from .recetas import reducir

logger = logging.getLogger(__name__)

DIAS = [('lunes', 'Lunes'), ('martes', 'Martes'), ('miercoles', 'Miércoles'), ('jueves', 'Jueves'),
        ('viernes', 'Viernes'), ('sabado', 'Sábado'), ('domingo', 'Domingo')]


def enviar_correo(destino, asunto, html, texto, adjuntos=()):
    llave = os.environ.get('BREVO_API_KEY', '').strip()
    remitente = os.environ.get('MAIL_FROM', '').strip()
    if not llave or not remitente:
        raise ServicioNoDisponible('El envío por correo aún no está configurado en el servidor.')
    cuerpo = json.dumps({
        'sender': {'name': os.environ.get('MAIL_FROM_NAME', 'HealthTech TACO'), 'email': remitente},
        'to': [{'email': destino}],
        'subject': asunto,
        'htmlContent': html,
        'textContent': texto,
        **({'attachment': [{'name': n, 'content': base64.b64encode(b).decode()} for n, b in adjuntos]} if adjuntos else {}),
    }).encode('utf-8')
    req = urllib.request.Request('https://api.brevo.com/v3/smtp/email', data=cuerpo, method='POST', headers={
        'api-key': llave, 'content-type': 'application/json', 'accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status >= 300:
                raise ErrorServicioExterno('No se pudo enviar el correo.')
    except urllib.error.HTTPError as e:
        logger.error('Brevo respondió %s: %s', e.code, e.read()[:300])
        raise ErrorServicioExterno('No se pudo enviar el correo. Intenta más tarde.')
    except (urllib.error.URLError, TimeoutError, OSError):
        logger.exception('No se pudo conectar con Brevo')
        raise ErrorServicioExterno('No se pudo enviar el correo. Intenta más tarde.')


def _fmt(v):
    return escape(str(v)) if v not in (None, '') else '—'


def armar_control(usuario):
    """Devuelve (asunto, html, texto) con el resumen actual del paciente."""
    ficha = {}
    enlace = EnlaceCuidador.objects.filter(usuario=usuario).first()
    if enlace and isinstance(enlace.ficha, dict):
        ficha = enlace.ficha
    lecturas = list(RegistroINR.objects.filter(usuario=usuario).order_by('-fechaLectura', '-id')[:10])
    meds = list(Medicamento.objects.filter(usuario=usuario))
    nombre = usuario.first_name or usuario.username
    hoy = timezone.localdate().strftime('%d-%m-%Y')

    filas_inr = ''.join(
        f'<tr><td>{timezone.localtime(r.fechaLectura):%d-%m-%Y}</td><td><b>{_fmt(r.valorINR)}</b></td>'
        f'<td>{_fmt(r.rangoTerapeuticoMin)} - {_fmt(r.rangoTerapeuticoMax)}</td></tr>' for r in lecturas
    ) or '<tr><td colspan="3">Sin lecturas guardadas.</td></tr>'

    bloques_meds = ''
    texto_meds = ''
    for m in meds:
        sem = m.horarioSemanal if isinstance(m.horarioSemanal, dict) else {}
        dosis = ''.join(f'<td>{_fmt(sem.get(k) or "—")}</td>' for k, _ in DIAS)
        cab = ''.join(f'<th>{n[:2]}</th>' for _, n in DIAS)
        hora = m.horaProgramada.strftime('%H:%M') if m.horaProgramada else '—'
        bloques_meds += (f'<p><b>{_fmt(m.nombre)}</b> ({_fmt(m.unidadPastilla)}) · hora: {hora}</p>'
                         f'<table class="t"><tr>{cab}</tr><tr>{dosis}</tr></table>')
        texto_meds += f'\n- {m.nombre} ({m.unidadPastilla}) a las {hora}: ' + ', '.join(
            f'{n[:2]} {sem.get(k) or "-"}' for k, n in DIAS)
    bloques_meds = bloques_meds or '<p>Sin medicamentos guardados.</p>'

    diag = ficha.get('diagnosticos') or []
    html = f'''<div style="font-family:Arial,sans-serif;color:#073B30;max-width:640px;margin:auto">
<h2 style="color:#0C8F68">HealthTech TACO · Mi control</h2>
<p>Paciente: <b>{_fmt(nombre)}</b><br>Fecha del envío: {hoy}</p>
<h3>Ficha médica</h3>
<p>Médico tratante: {_fmt(ficha.get("medico"))}<br>Último control: {_fmt(ficha.get("ultimoControl"))}<br>
Próximo control: <b>{_fmt(ficha.get("proximoControl"))}</b><br>
Diagnósticos: {_fmt(", ".join(str(d) for d in diag)) if diag else "—"}</p>
<h3>Últimas lecturas de INR</h3>
<table class="t"><tr><th>Fecha</th><th>INR</th><th>Rango</th></tr>{filas_inr}</table>
<h3>Medicamentos y dosis semanal</h3>{bloques_meds}
<p style="font-size:12px;color:#666">Este resumen es solo informativo y no reemplaza la indicación de tu médico.
Verifica siempre con tu hoja original.</p>
<style>.t{{border-collapse:collapse}}.t td,.t th{{border:1px solid #ccc;padding:6px 10px;text-align:center}}</style></div>'''
    texto = (f'HealthTech TACO - Mi control ({hoy})\nPaciente: {nombre}\n'
             f'Médico: {ficha.get("medico") or "-"}\nUltimo control: {ficha.get("ultimoControl") or "-"}\n'
             f'Proximo control: {ficha.get("proximoControl") or "-"}\n\nLecturas INR:\n' +
             ('\n'.join(f'{timezone.localtime(r.fechaLectura):%d-%m-%Y}: INR {r.valorINR} (rango {r.rangoTerapeuticoMin}-{r.rangoTerapeuticoMax})' for r in lecturas) or 'Sin lecturas') +
             f'\n\nMedicamentos:{texto_meds or " ninguno"}\n\nResumen informativo; no reemplaza la indicacion de tu medico.')
    return f'Mi control · HealthTech TACO ({hoy})', html, texto


class EnviarControlView(APIView):
    """POST: envía el resumen del paciente al correo con el que se registró (nunca a otra dirección)."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'correo'

    def post(self, request):
        destino = (request.user.email or '').strip()
        if not destino:
            raise ServicioNoDisponible('Tu cuenta no tiene un correo registrado.')
        asunto, html, texto = armar_control(request.user)
        # Se adjuntan las fotos de las últimas recetas (reducidas: el correo admite ~4 MB en total).
        adjuntos, total = [], 0
        for r in Receta.objects.filter(usuario=request.user)[:5]:
            foto = reducir(bytes(r.imagen), 1100, 70)
            if total + len(foto) > 3 * 1024 * 1024:
                break
            total += len(foto)
            adjuntos.append((f'receta_{timezone.localtime(r.creada):%Y-%m-%d}_{r.id}.jpg', foto))
        enviar_correo(destino, asunto, html, texto, adjuntos)
        extra = f' con {len(adjuntos)} foto(s) de tus recetas' if adjuntos else ''
        return Response({'mensaje': f'Listo. Te lo enviamos a {destino}{extra}. Revisa también la carpeta de spam.'})
