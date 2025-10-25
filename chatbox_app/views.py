from __future__ import annotations

from django.conf import settings
from django.contrib import messages as django_messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

import requests

from .forms import MessageForm, VideoGenerationForm
from .models import ChatSession, GeneratedVideo, Message


def dashboard(request: HttpRequest) -> HttpResponse:
    sessions = ChatSession.objects.order_by("-created_at")
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        session = ChatSession.objects.create(name=name)
        return redirect("chatbox_app:chat_session", session_id=session.pk)
    return render(request, "chatbox_app/dashboard.html", {"sessions": sessions})


def chat_session(request: HttpRequest, session_id: int) -> HttpResponse:
    session = get_object_or_404(ChatSession, pk=session_id)
    message_form = MessageForm()
    video_form = VideoGenerationForm()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "send_message":
            message_form = MessageForm(request.POST, request.FILES)
            if message_form.is_valid():
                Message.objects.create(
                    session=session,
                    sender=Message.USER,
                    content=message_form.cleaned_data.get("content", ""),
                    attachment=message_form.cleaned_data.get("attachment"),
                )
                return redirect(request.path)
        elif action == "generate_video":
            video_form = VideoGenerationForm(request.POST)
            if video_form.is_valid():
                prompt = video_form.cleaned_data["prompt"]
                video = _trigger_video_generation(session, prompt)
                if video.status == GeneratedVideo.STATUS_FAILED:
                    django_messages.error(request, "La génération vidéo a échoué. Veuillez réessayer.")
                else:
                    django_messages.success(request, "Génération vidéo lancée.")
                return redirect(request.path)

    chat_messages = session.messages.order_by("created_at")
    videos = session.generated_videos.order_by("-created_at")
    context = {
        "session": session,
        "sessions": ChatSession.objects.order_by("-created_at")[:10],
        "chat_messages": chat_messages,
        "videos": videos,
        "message_form": message_form,
        "video_form": video_form,
    }
    return render(request, "chatbox_app/chat_session.html", context)


def video_status(request: HttpRequest, video_id: int) -> JsonResponse:
    video = get_object_or_404(GeneratedVideo, pk=video_id)
    data = {
        "status": video.status,
        "video_url": video.video_url,
        "external_id": video.external_id,
    }
    return JsonResponse(data)


def _trigger_video_generation(session: ChatSession, prompt: str) -> GeneratedVideo:
    video = GeneratedVideo.objects.create(
        session=session,
        prompt=prompt,
        status=GeneratedVideo.STATUS_PROCESSING,
    )

    api_url = getattr(settings, "AI_VIDEO_API_URL", "")
    api_key = getattr(settings, "AI_VIDEO_API_KEY", "")

    if not api_url:
        video.status = GeneratedVideo.STATUS_PENDING
        video.save(update_fields=["status"])
        return video

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "prompt": prompt,
        "session_id": session.pk,
        "session_name": session.name,
    }

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        video.external_id = data.get("id") or data.get("job_id", "")
        video.video_url = data.get("video_url", "")
        api_status = (data.get("status") or "").lower()
        if video.video_url:
            video.status = GeneratedVideo.STATUS_COMPLETED
        elif api_status in {GeneratedVideo.STATUS_PENDING, GeneratedVideo.STATUS_PROCESSING}:
            video.status = GeneratedVideo.STATUS_PENDING
        elif api_status == GeneratedVideo.STATUS_FAILED:
            video.status = GeneratedVideo.STATUS_FAILED
        else:
            video.status = GeneratedVideo.STATUS_PROCESSING
        video.save(update_fields=["external_id", "video_url", "status"])
    except requests.RequestException as exc:
        video.status = GeneratedVideo.STATUS_FAILED
        video.save(update_fields=["status"])
        raise exc

    return video
