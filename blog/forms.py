from django import forms
from tinymce.widgets import TinyMCE
from django.core.validators import validate_email
from .models import Blog


class BlogForm(forms.ModelForm):

    content = forms.CharField(widget=TinyMCE())

    class Meta:
        model = Blog
        fields = ("title", "content", "preview", "category", "is_published")


class ContactForm(forms.Form):
    name = forms.CharField(max_length=128, required=True, label="Имя")
    email = forms.EmailField(required=True, label="Email")
    message = forms.CharField(widget=forms.Textarea, required=True, label="Сообщение")

    def clean_email(self):
        email = self.cleaned_data.get("email")
        validate_email(email)
        return email
