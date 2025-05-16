from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Min, Max
from .models import Gambler
from .models import Bet
import numpy as np
import pandas as pd
import joblib
from django.db.models.functions import Coalesce
from django.db.models import FloatField, ExpressionWrapper
import os
from decimal import Decimal
from django.db.models import DecimalField

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'models')
kmeans = joblib.load(os.path.join(MODEL_PATH, 'kmeans_model.pkl'))
scaler = joblib.load(os.path.join(MODEL_PATH, 'scaler.pkl'))


# Create your views here.
def home(request):
    if request.user.is_authenticated:
        if request.user.is_superuser == 0:
            try:
                total_bets = Bet.objects.filter(gambler=request.user.id).count()
                bets_won = Bet.objects.filter(Q(gambler=request.user.id) & Q(bet_status="won")).count()
                win_rate = int((bets_won / total_bets) * 100)
                slip = Bet.objects.filter(gambler=request.user.id)
                context = {
                    "bets": total_bets,
                    "wins": bets_won,
                    "rate": win_rate,
                    "slip": slip,

                }
                return render(request, "index.html", context)

            except Exception as e:
                total_bets = 404
                context = {
                    "bets": total_bets,

                }
                return render(request, "index.html", context)
    else:
        return render(request, "index.html", {})


def loginUser(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        # authentication process
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "You have logged in successfully")
            return redirect('home')
        else:
            messages.success(request, "An error occured during login, please try again")

            return redirect('login')
    else:
        return render(request, "login.html", {})


def activate(request):
    return render(request, "activate.html", {})


def activateUser(request):
    if request.method == 'POST':
        username = request.POST['username']
        password1 = request.POST['password1']
        password2 = request.POST['password2']

        if password1 == password2:
            try:
                user = Gambler.objects.get(Q(username=username))
                if user.username == username:
                    user.set_password(password1)
                    messages.success(request, "Password input complete")
                    user.save()
                    return redirect('login')


            except Exception as e:
                messages.success(request, "User not found")
                return redirect('login')

    else:
        return render(request, "login.html", {})


def predict_cluster(request):
    if request.user.is_authenticated:
        user_stats = Bet.objects.filter(gambler=request.user.id).aggregate(
            total_bets=Count('gambler_id'),
            total_stake=Coalesce(Sum('stake_amount'), Decimal('0.00'), output_field=DecimalField()),
            avg_stake=Coalesce(Avg('stake_amount'), Decimal('0.00'), output_field=DecimalField()),
            total_payout=Coalesce(Sum('payout_amount'), Decimal('0.00'), output_field=DecimalField()),
            max_stake=Coalesce(Max('stake_amount'), Decimal('0.00'), output_field=DecimalField()),
            min_stake=Coalesce(Min('stake_amount'), Decimal('0.00'), output_field=DecimalField()),
            win_count=Count('gambler_id', filter=Q(bet_status='won'))
        )

        if user_stats['total_bets'] == 0:
            return None  # Not enough data to classify

        win_rate = user_stats['win_count'] / user_stats['total_bets']
        total_loss = user_stats['total_stake'] - user_stats['total_payout']
        print("total bets " + str(user_stats['total_bets']))
        print("total stake:" + str(user_stats['total_stake']))
        print("average stake:" + str(user_stats['avg_stake']))
        print("total payout:" + str(user_stats['total_payout']))
        print("max stake:" + str(user_stats['max_stake']))
        print("min stake:" + str(user_stats['min_stake']))
        print("win count" + str(user_stats['win_count']))
        print("win rate:" + str(win_rate))
        print("total loss:" + str(total_loss))

        print(kmeans.n_clusters)

        user_df = pd.DataFrame([{
            "total_bets": user_stats['total_bets'],
            "total_stake": user_stats['total_stake'],
            "avg_stake": user_stats['avg_stake'],
            "max_stake": user_stats['max_stake'],
            "min_stake": user_stats['min_stake'],
            "total_payout": user_stats['total_payout'],
            "win_rate": win_rate,
            "total_loss": total_loss,
        }])

        # Now safely scale and predict
        user_scaled = scaler.transform(user_df)
        cluster = kmeans.predict(user_scaled)[0]

        cluster_label_map = {
            0: "Low-Risk Gambler",
            1: "Moderate-Risk Gambler",
            2: "High-Risk Gambler"
        }
        risk_label = cluster_label_map.get(cluster, "Unknown")

        context = {
            "cluster": risk_label,
            "total_bets": user_stats['total_bets'],
            "total_stake": int(user_stats['total_stake']),
            "avg_stake": int(user_stats['avg_stake']),
            "max_stake": int(user_stats['max_stake']),
            "min_stake": (user_stats['min_stake']),
            "total_payout": int(user_stats['total_payout']),
            "win_count": user_stats["win_count"],
            "win_rate": int(win_rate * 100),
            "total_loss": total_loss,
        }

        return render(request, "scan.html", context)
    else:
        return render(request, "login.html", {})


def scanner(request):
    return render(request, "scan.html", {})
