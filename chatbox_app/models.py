import mimetypes
import os

from django.db import models


def message_upload_path(instance, filename):
    session_folder = f"session_{instance.session_id}"
    return os.path.join("uploads", session_folder, filename)


class ChatSession(models.Model):
    name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or f"Session {self.pk}"


class Message(models.Model):
    USER = "user"
    ASSISTANT = "assistant"
    SENDER_CHOICES = [(USER, "Utilisateur"), (ASSISTANT, "Assistant")]

    session = models.ForeignKey(ChatSession, related_name="messages", on_delete=models.CASCADE)
    sender = models.CharField(max_length=20, choices=SENDER_CHOICES, default=USER)
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to=message_upload_path, blank=True, null=True)
    attachment_type = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.attachment and not self.attachment_type:
            mime_type, _ = mimetypes.guess_type(self.attachment.name)
            self.attachment_type = mime_type or "application/octet-stream"
        super().save(*args, **kwargs)


class GeneratedVideo(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_PROCESSING, "En cours"),
        (STATUS_COMPLETED, "Terminé"),
        (STATUS_FAILED, "Échec"),
    ]

    session = models.ForeignKey(ChatSession, related_name="generated_videos", on_delete=models.CASCADE)
    prompt = models.TextField()
    external_id = models.CharField(max_length=255, blank=True)
    video_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Vidéo {self.pk} - {self.status}"
