"""Vistas para los perfiles Enfermero (ve y elimina duplicados) y Super usuario (administra todo y los roles)."""
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Medicamento, PerfilUsuario, RegistroINR, RegistroToma
from .permissions import IsMedico, es_admin, rol_de


class SoloSuperUsuario(BasePermission):
    message = 'Solo el super usuario puede hacer esto.'

    def has_permission(self, request, view):
        return es_admin(request.user)


class StaffPacientesView(APIView):
    """Enfermero / super usuario: pacientes con sus medicamentos y las horas de toma (solo lectura)."""
    permission_classes = [IsAuthenticated, IsMedico]

    def get(self, request):
        hoy = timezone.localdate()
        pacientes = list(User.objects.filter(is_staff=False, is_superuser=False, perfil__rol='paciente')
                         .order_by('first_name', 'id'))
        ids = [p.id for p in pacientes]
        meds = Medicamento.objects.filter(usuario_id__in=ids).order_by('nombre', 'id')
        tomas_por_med = {}
        for t in RegistroToma.objects.filter(medicamento__usuario_id__in=ids).order_by('-fechaHora')[:3000]:
            lista = tomas_por_med.setdefault(t.medicamento_id, [])
            if len(lista) < 7:
                lista.append({'fecha': timezone.localtime(t.fechaHora).isoformat(), 'estado': t.estado, 'dosis': t.dosis})
        meds_por_user = {}
        for m in meds:
            meds_por_user.setdefault(m.usuario_id, []).append({
                'id': m.id, 'nombre': m.nombre, 'unidad': m.unidadPastilla,
                'hora': m.horaProgramada.strftime('%H:%M') if m.horaProgramada else '',
                'horarioSemanal': m.horarioSemanal,
                'tomadaHoy': m.fechaUltimaConfirmacion == hoy,
                'tomas': tomas_por_med.get(m.id, []),
            })
        inr_por_user = {}
        lecturas_por_user = {}
        for r in RegistroINR.objects.filter(usuario_id__in=ids).order_by('-fechaLectura', '-id')[:3000]:
            inr_por_user.setdefault(r.usuario_id, r)
            lista = lecturas_por_user.setdefault(r.usuario_id, [])
            if len(lista) < 20:
                lista.append({'id': r.id, 'valor': r.valorINR, 'min': r.rangoTerapeuticoMin,
                              'max': r.rangoTerapeuticoMax, 'fecha': r.fechaLectura.isoformat()})
        salida = []
        for p in pacientes:
            r = inr_por_user.get(p.id)
            salida.append({
                'id': p.id, 'nombre': p.first_name or p.username, 'email': p.email,
                'ultimoINR': ({'valor': r.valorINR, 'min': r.rangoTerapeuticoMin, 'max': r.rangoTerapeuticoMax,
                               'fecha': r.fechaLectura.isoformat()} if r else None),
                'medicamentos': meds_por_user.get(p.id, []),
                'lecturas': lecturas_por_user.get(p.id, []),
            })
        return Response({'hoy': hoy.isoformat(), 'pacientes': salida})


class UsuariosView(APIView):
    """Super usuario: lista todas las cuentas con su rol."""
    permission_classes = [IsAuthenticated, SoloSuperUsuario]

    def get(self, request):
        usuarios = User.objects.select_related('perfil').order_by('first_name', 'id')[:500]
        return Response([{'id': u.id, 'nombre': u.first_name or u.username, 'email': u.email, 'rol': rol_de(u)}
                         for u in usuarios])


class CambiarRolView(APIView):
    """Super usuario: cambia una cuenta entre Paciente y Enfermero. (El rol super usuario solo se da desde /admin/.)"""
    permission_classes = [IsAuthenticated, SoloSuperUsuario]

    def post(self, request, pk):
        try:
            objetivo = User.objects.get(pk=pk)
        except User.DoesNotExist:
            raise NotFound()
        if es_admin(objetivo):
            raise ValidationError({'rol': ['No se puede cambiar el rol de un super usuario desde aquí.']})
        rol = request.data.get('rol')
        if rol not in (PerfilUsuario.Rol.PACIENTE, PerfilUsuario.Rol.MEDICO):
            raise ValidationError({'rol': ['Rol no válido. Usa "paciente" o "medico" (enfermero).']})
        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=objetivo)
        perfil.rol = rol
        perfil.save(update_fields=['rol'])
        return Response({'id': objetivo.id, 'rol': rol_de(objetivo)})
