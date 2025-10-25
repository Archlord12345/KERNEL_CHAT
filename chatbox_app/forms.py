from django import forms


class MessageForm(forms.Form):
    content = forms.CharField(
        label="Message",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control form-control-modern",
                "placeholder": "Écrivez votre message ici...",
            }
        ),
        required=False,
    )
    attachment = forms.FileField(
        label="Fichier",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control form-control-modern",
            }
        ),
    )


class VideoGenerationForm(forms.Form):
    prompt = forms.CharField(
        label="Description vidéo",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control form-control-modern",
                "placeholder": "Décrivez la scène, l'ambiance ou le message de votre vidéo...",
            }
        ),
    )
