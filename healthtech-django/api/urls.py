from django.urls import path
from rest_framework.routers import SimpleRouter

from . import cuidador, staff, views

router = SimpleRouter()
router.register('medicamentos', views.MedicamentoViewSet, basename='medicamento')
router.register('registros-inr', views.RegistroINRViewSet, basename='registroinr')
router.register('tomas', views.RegistroTomaViewSet, basename='registrotoma')
router.register('pacientes', views.PacienteViewSet, basename='paciente')

urlpatterns = [
    path('', views.ApiRootView.as_view(), name='api-root'),
    path('auth/registro/', views.RegistroView.as_view(), name='auth-registro'),
    path('auth/login/', views.LoginView.as_view(), name='auth-login'),
    path('auth/refresh/', views.RefrescarTokenView.as_view(), name='auth-refresh'),
    path('auth/logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('auth/perfil/', views.PerfilView.as_view(), name='auth-perfil'),
    path('cuidador/enlace/', cuidador.EnlaceCuidadorView.as_view(), name='cuidador-enlace'),
    path('cuidador/ficha/', cuidador.FichaCuidadorView.as_view(), name='cuidador-ficha'),
    path('cuidador/ver/<str:token>/', cuidador.VerCuidadorView.as_view(), name='cuidador-ver'),
    path('staff/pacientes/', staff.StaffPacientesView.as_view(), name='staff-pacientes'),
    path('staff/usuarios/', staff.UsuariosView.as_view(), name='staff-usuarios'),
    path('staff/usuarios/<int:pk>/rol/', staff.CambiarRolView.as_view(), name='staff-rol'),
    path('recetas/analizar/', views.AnalizarRecetaView.as_view(), name='recetas-analizar'),
] + router.urls
