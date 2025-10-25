from django.urls import path

from . import views

app_name = "chatbox_app"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sessions/<int:session_id>/", views.chat_session, name="chat_session"),
    path("videos/<int:video_id>/status/", views.video_status, name="video_status"),
]
