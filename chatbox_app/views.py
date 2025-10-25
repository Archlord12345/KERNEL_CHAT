from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages as django_messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

import requests

from .forms import MessageForm, VideoGenerationForm
from .models import ChatSession, GeneratedVideo, Message


logger = logging.getLogger(__name__)


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
                message = Message.objects.create(
                    session=session,
                    sender=Message.USER,
                    content=message_form.cleaned_data.get("content", ""),
                    attachment=message_form.cleaned_data.get("attachment"),
                )
                try:
                    _dispatch_message_webhook(request, message)
                except requests.RequestException:
                    django_messages.error(
                        request,
                        "L'envoi du message au service distant a échoué. Veuillez réessayer plus tard.",
                    )
                except ValueError:
                    django_messages.warning(
                        request,
                        "Réponse inattendue du service distant. Consultez les journaux pour plus de détails.",
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
        logger.info(
            "Dispatching video generation",
            extra={
                "session_id": session.pk,
                "video_id": video.pk,
                "endpoint": api_url,
                "payload": payload,
            },
        )
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        logger.info(
            "Webhook response received",
            extra={
                "session_id": session.pk,
                "video_id": video.pk,
                "status": data.get("status"),
                "video_url": data.get("video_url"),
                "external_id": data.get("id") or data.get("job_id"),
            },
        )
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
        logger.exception(
            "Webhook call failed",
            extra={"session_id": session.pk, "video_id": video.pk, "endpoint": api_url},
        )
        raise exc

    return video


def _dispatch_message_webhook(request: HttpRequest, message: Message) -> None:
    webhook_url = getattr(settings, "AI_MESSAGE_WEBHOOK_URL", "")
    webhook_key = getattr(settings, "AI_MESSAGE_WEBHOOK_KEY", "")
    webhook_method = getattr(settings, "AI_MESSAGE_WEBHOOK_METHOD", "POST").upper()

    if not webhook_url:
        logger.warning(
            "No message webhook configured; skipping dispatch",
            extra={"session_id": message.session_id, "message_id": message.pk},
        )
        return

    headers = {"Content-Type": "application/json"}
    if webhook_key:
        headers["Authorization"] = f"Bearer {webhook_key}"

    payload = {
        "message_id": message.pk,
        "session_id": message.session_id,
        "session_name": message.session.name,
        "sender": message.sender,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }

    if message.attachment:
        payload["attachment_url"] = request.build_absolute_uri(message.attachment.url)
        payload["attachment_type"] = message.attachment_type

    logger.info(
        "Dispatching chat message",
        extra={
            "session_id": message.session_id,
            "message_id": message.pk,
            "endpoint": webhook_url,
            "method": webhook_method,
        },
    )

    if webhook_method == "GET":
        response = requests.get(webhook_url, params=payload, headers=headers, timeout=30)
    elif webhook_method == "POST":
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=30)
    else:
        logger.warning(
            "Unsupported webhook method; defaulting to POST",
            extra={"session_id": message.session_id, "message_id": message.pk, "method": webhook_method},
        )
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        logger.warning(
            "Webhook response is not JSON",
            extra={"session_id": message.session_id, "message_id": message.pk},
        )
        raise ValueError("Réponse JSON invalide") from exc

    logger.info(
        "Message webhook delivered",
        extra={
            "session_id": message.session_id,
            "message_id": message.pk,
            "status": data.get("status"),
            "http_status": response.status_code,
        },
    )

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "prompt": prompt,
        "session_id": session.pk,
        "session_name": session.name,
    }

    try:
        logger.info(
            "Dispatching video generation",
            extra={
                "session_id": session.pk,
                "video_id": video.pk,
                "endpoint": api_url,
                "payload": payload,
            },
        )
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        logger.info(
            "Webhook response received",
            extra={
                "session_id": session.pk,
                "video_id": video.pk,
                "status": data.get("status"),
                "video_url": data.get("video_url"),
                "external_id": data.get("id") or data.get("job_id"),
            },
        )
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
        logger.exception(
            "Webhook call failed",
            extra={"session_id": session.pk, "video_id": video.pk, "endpoint": api_url},
        )
        raise exc

    return video
