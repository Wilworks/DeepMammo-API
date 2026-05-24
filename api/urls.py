from django.urls import path
from .views import PredictView, HealthView, home, dashboard, tutorial, faq

urlpatterns = [
    # Pages
    path('',           home,      name='home'),
    path('dashboard',  dashboard, name='dashboard'),
    path('tutorial',   tutorial,  name='tutorial'),
    path('faq',        faq,       name='faq'),
    # API
    path('api/predict/', PredictView.as_view(), name='predict'),
    path('api/health/',  HealthView.as_view(),  name='health'),
]
