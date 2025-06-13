from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.loginUser, name='login'),
    path('logout/', views.logoutUser, name='logout'),
    path('activate/', views.activate, name='activate'),
    path('activateUser/', views.activateUser, name='activateUser'),
    path('scan/', views.scanner, name='scanner'),
    path('predict/', views.predict_cluster, name='predict'),
    path('mybets/', views.mybets, name='mybets'),
    path('home/', views.homeAdmin, name='homeAdmin'),
    path('report/', views.selfReport, name='report'),
    path('submitreport/', views.submit_self_report, name='submitreport'),
    path('profile/', views.myProfile, name='profile'),
    path('gambler/', views.getGambler, name='gambler'),
    path('close/<int:id>/', views.closeAccount, name='close_account'),
    path('suspend/<int:id>/', views.suspendAccount, name='suspend_account'),
    path('activate/<int:id>/', views.activateAccount, name='activate_account'),
    path('profiles/', views.profileAdmin, name='profilesAdmin'),
    path('triggers/', views.gamblerTriggers, name='triggers'),
    path('act/<int:user_id>/', views.resolve_trigger, name='resolve_trigger')

]
