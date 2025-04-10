# core/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from .forms import SignUpForm
from django.contrib.auth import login
import logging
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

def dashboard(request):
    logging.info('Calling Dashboard')
    return render(request, 'core/dashboard.html', {'user': request.user})

def login_view(request):
    logging.info('CoreView : Calling Login')
    if request.method == 'POST':
        logging.info('CoreView : Calling Login - POST')
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            logging.info('CoreView : Calling Login - POST - Valid')
            user = form.get_user()
            login(request, user)
            logging.info('CoreView : Calling Login - POST - Valid - Login')
            return redirect('core:dashboard')  # Redirect to your dashboard view after login
    else:
        logging.info('CoreView : Calling Login - GET')
        form = AuthenticationForm()
    return render(request, 'core/login.html', {'form': form})

def logout_view(request):
    logging.info('CoreView : Calling Logout')
    logout(request)
    return redirect('core:login')

def signup_view(request):
    logging.info('CoreView : Calling Signup')
    if request.method == 'POST':
        logging.info('CoreView : Calling Signup - POST')
        form = SignUpForm(request.POST)
        if form.is_valid():
            logging.info('CoreView : Calling Signup - POST - Valid')
            user = form.save()
            login(request, user, backend='social_core.backends.google.GoogleOAuth2')  # Specify the backend
            return redirect('core:dashboard')  # Redirect to your dashboard view
    else:
        logging.info('CoreView : Calling Signup - GET')
        form = SignUpForm()
    return render(request, 'core/signup.html', {'form': form})