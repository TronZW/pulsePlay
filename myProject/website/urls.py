from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.loginUser, name='login'),
    path('activate/', views.activate, name='activate'),
    path('activateUser/', views.activateUser, name='activateUser'),
    path('scan/', views.scanner, name='scanner'),
    path('predict/', views.predict_cluster, name='predict'),
    path('mybets/', views.mybets, name='mybets'),
]
