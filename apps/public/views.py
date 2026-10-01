from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def welcome(request: HttpRequest) -> HttpResponse:
    """Página pública de inicio."""
    return render(request, 'public/welcome.html')
