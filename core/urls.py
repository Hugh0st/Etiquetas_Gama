from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', views.pedido_list, name='pedido_list'),
    path('pedidos/nuevo/', views.pedido_create, name='pedido_create'),
    path('pedidos/<int:pk>/', views.pedido_detail, name='pedido_detail'),
    path('pedidos/<int:pk>/editar/', views.pedido_edit, name='pedido_edit'),
    path('pedidos/<int:pk>/resultados/', views.pedido_resultados, name='pedido_resultados'),
    path('pedidos/<int:pk>/emitir/', views.pedido_emitir, name='pedido_emitir'),
    path('pedidos/<int:pk>/etiquetas/', views.pedido_etiquetas, name='pedido_etiquetas'),
    path('pedidos/<int:pk>/etiquetas/pdf/', views.pedido_etiquetas_pdf, name='pedido_etiquetas_pdf'),
    path('pedidos/<int:pk>/certificados/', views.pedido_certificados_pdf, name='pedido_certificados_pdf'),
    path(
        'pedidos/<int:pedido_pk>/renglones/<int:renglon_pk>/certificado/',
        views.renglon_certificado_pdf,
        name='renglon_certificado_pdf',
    ),
    path('calibracion/', views.calibracion, name='calibracion'),
    path('api/clientes/', views.api_clientes_buscar, name='api_clientes_buscar'),
    path('api/productos/', views.api_productos_buscar, name='api_productos_buscar'),
]
