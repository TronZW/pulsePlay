from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Count, Sum, Avg, Min, Max, F
from .models import Gambler
from .models import Bet
from .models import Stats
from .models import Trigger
from .models import SelfReport
import numpy as np
import pandas as pd
import joblib
from django.db.models.functions import Coalesce
from django.db.models import FloatField, ExpressionWrapper
import os
from decimal import Decimal
from django.db.models import DecimalField
from .randomForest import *
from .models import GamblerScanResult
from django.utils.timezone import now
from django.core.paginator import Paginator

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
                try:
                    scan = GamblerScanResult.objects.filter(gambler=request.user.id).latest('previous_scan')
                    has_scan = True
                    # Extract previous scores from the scan object, adjust attribute names accordingly
                    patterns = {
                        "loss chasing": float(scan.loss_chasing_score),
                        "binge gambling": float(scan.binge_gambling_score),
                        "fluctuating wagers": float(scan.fluctuating_wagers_score),
                        "impulsive transactions": float(scan.impulsive_transactions_score),
                        "monetary consumption": float(scan.monetary_consumption_score)
                    }
                    high_risk_patterns = {k: v for k, v in patterns.items() if v > 40}

                    pattern_scores = [
                        float(scan.loss_chasing_score),
                        float(scan.binge_gambling_score),
                        float(scan.fluctuating_wagers_score),
                        float(scan.impulsive_transactions_score),
                        float(scan.monetary_consumption_score)
                    ]
                except Exception as e:
                    has_scan = False
                    pattern_scores = []
                    high_risk_patterns = {}

                context = {
                    "bets": total_bets,
                    "wins": bets_won,
                    "rate": win_rate,
                    "slip": slip,
                    "has_scan": has_scan,
                    "pattern_scores": pattern_scores,
                    "high_risk_patterns": high_risk_patterns,
                    "risk_cluster": scan.cluster_label

                }
                return render(request, "index.html", context)

            except Exception as e:

                total_bets = 404

                context = {
                    "bets": total_bets,

                }
                return render(request, "index.html", context)
    else:
        messages.success(request, "You are not allowed to access this location")
        return redirect('login')


def loginUser(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        # authentication process
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if request.user.is_superuser == 0:
                return redirect('home')
            else:
                return redirect('homeAdmin')
        else:
            messages.success(request, "Incorrect username or password. Please try again")
            return redirect('login')
    else:
        return render(request, "login.html", {})


def logoutUser(request):
    logout(request)
    messages.success(request, "You have logged out")
    return redirect('login')


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
                    user.save()
                    return redirect('login')


            except Exception as e:
                messages.success(request, "User not found")
                return redirect('login')

    else:
        messages.success(request, "An error occured, please try again")
        return redirect('login')


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
        stats = Stats.objects.order_by('-calculated_at').first()

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
        scores = predict_gambler_behavior(request.user.id)
        raw_results = label_risk_severity(scores)

        results = []
        for pattern, data in raw_results.items():
            display_name = pattern.replace("_", " ").title()
            results.append({
                "pattern": display_name,
                "score": data["score_percent"],
                "severity": data["severity"]
            })
        recommendations = get_user_messages(results)
        # Save or update scan results
        scan_data = {
            "gambler": request.user,
            "cluster_label": risk_label,
            "loss_chasing_score": raw_results["loss_chasing_score"]["score_percent"],
            "loss_chasing_severity": raw_results["loss_chasing_score"]["severity"],
            "fluctuating_wagers_score": raw_results["fluctuating_wagers_score"]["score_percent"],
            "fluctuating_wagers_severity": raw_results["fluctuating_wagers_score"]["severity"],
            "impulsive_transactions_score": raw_results["impulsive_transactions_score"]["score_percent"],
            "impulsive_transactions_severity": raw_results["impulsive_transactions_score"]["severity"],
            "binge_gambling_score": raw_results["binge_gambling_score"]["score_percent"],
            "binge_gambling_severity": raw_results["binge_gambling_score"]["severity"],
            "monetary_consumption_score": raw_results["monetary_consumption_score"]["score_percent"],
            "monetary_consumption_severity": raw_results["monetary_consumption_score"]["severity"],
            "total_bets": user_stats['total_bets'],
            "total_stake": user_stats['total_stake'],
            "avg_stake": user_stats['avg_stake'],
            "max_stake": user_stats['max_stake'],
            "min_stake": user_stats['min_stake'],
            "total_payout": user_stats['total_payout'],
            "win_rate": win_rate,
            "total_loss": total_loss,
            "has_scan": True,
            "previous_scan": now(),
        }
        GamblerScanResult.objects.update_or_create(gambler=request.user.id, defaults=scan_data)

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
            'avg_total_bets': int(stats.avg_total_bets),
            'avg_total_stake': int(stats.avg_total_stake),
            'avg_avg_stake': int(stats.avg_avg_stake),
            'avg_max_stake': int(stats.avg_max_stake),
            'avg_min_stake': int(stats.avg_min_stake),
            'avg_total_payout': int(stats.avg_total_payout),
            'avg_win_count': int(stats.avg_win_count),
            'avg_total_loss': int(stats.avg_total_loss),
            'avg_win_rate': int(stats.avg_win_rate * 100),
            'results': results,
            'recommendations': recommendations
        }

        return render(request, "scan.html", context)
    else:
        messages.success(request, "You are not allowed to access this location")
        return redirect('login')


def scanner(request):
    return render(request, "scan.html", {})


def mybets(request):
    if request.user.is_authenticated:
        bets = Bet.objects.filter(gambler=request.user.id).order_by('-placed_at')

        paginator = Paginator(bets, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        elided_range = paginator.get_elided_page_range(
            number=page_obj.number, on_each_side=2, on_ends=1
        )

        return render(request, "mybets.html", {

            'page_obj': page_obj,
            'elided_range': elided_range
        })

    else:
        messages.success(request, "You are not allowed to access this location")
        return redirect('login')


def homeAdmin(request):
    if request.user.is_authenticated:
        # Step 1: Annotate per-user stats
        user_stats = (
            Bet.objects.values('gambler')
            .annotate(
                total_bets=Count('gambler_id'),
                total_stake=Coalesce(Sum('stake_amount'), Decimal('0.00'), output_field=DecimalField()),
                avg_stake=Coalesce(Avg('stake_amount'), Decimal('0.00'), output_field=DecimalField()),
                total_payout=Coalesce(Sum('payout_amount'), Decimal('0.00'), output_field=DecimalField()),
                max_stake=Coalesce(Max('stake_amount'), Decimal('0.00'), output_field=DecimalField()),
                min_stake=Coalesce(Min('stake_amount'), Decimal('0.00'), output_field=DecimalField()),
                win_count=Count('gambler_id', filter=Q(bet_status='won')),
                total_loss=Coalesce(Sum(
                    ExpressionWrapper(F('stake_amount') - F('payout_amount'), output_field=FloatField())
                    , filter=~Q(bet_status='won')), 0.0),
            )
            .annotate(
                win_rate=ExpressionWrapper(
                    F('win_count') * 1.0 / F('total_bets'),
                    output_field=FloatField()
                )
            )
            .filter(total_bets__gte=15)
        )

        # Step 2: Compute average of each stat across users
        user_count = user_stats.count() or 1  # avoid division by zero

        # Convert QuerySet to list to iterate multiple times
        user_stats_list = list(user_stats)

        # Step 3: Sum all per-user values
        aggregate_sums = {
            'avg_total_bets': sum(u['total_bets'] for u in user_stats_list) / user_count,
            'avg_total_stake': sum(u['total_stake'] for u in user_stats_list) / user_count,
            'avg_avg_stake': sum(u['avg_stake'] for u in user_stats_list) / user_count,
            'avg_max_stake': sum(u['max_stake'] for u in user_stats_list) / user_count,
            'avg_min_stake': sum(u['min_stake'] for u in user_stats_list) / user_count,
            'avg_total_payout': sum(u['total_payout'] for u in user_stats_list) / user_count,
            'avg_win_count': sum(u['win_count'] for u in user_stats_list) / user_count,
            'avg_total_loss': sum(u['total_loss'] for u in user_stats_list) / user_count,
            'avg_win_rate': sum(u['win_rate'] for u in user_stats_list) / user_count,
        }

        # Round results (optional)
        aggregate_sums = {k: round(v, 4) for k, v in aggregate_sums.items()}
        Stats.objects.update_or_create(
            id=1,  # or some known identifier
            defaults={
                'avg_total_bets': aggregate_sums['avg_total_bets'],
                'avg_total_stake': aggregate_sums['avg_total_stake'],
                'avg_avg_stake': aggregate_sums['avg_avg_stake'],
                'avg_max_stake': aggregate_sums['avg_max_stake'],
                'avg_min_stake': aggregate_sums['avg_min_stake'],
                'avg_total_payout': aggregate_sums['avg_total_payout'],
                'avg_win_count': aggregate_sums['avg_win_count'],
                'avg_total_loss': aggregate_sums['avg_total_loss'],
                'avg_win_rate': aggregate_sums['avg_win_rate'],
            }
        )
        # code for detecting the triggers found in the gambler's data
        HIGH_STAKE_THRESHOLD = Decimal('450.00')

        # Get all bets above the threshold
        high_bets = Bet.objects.filter(stake_amount__gte=HIGH_STAKE_THRESHOLD)

        for bet in high_bets:
            gambler = bet.gambler
            highest_bet = Bet.objects.filter(gambler=gambler).aggregate(Max('stake_amount'))['stake_amount__max']
            # Checking  if a 'highest_bet' trigger already exists for this gambler
            trigger_exists = Trigger.objects.filter(
                gambler=gambler,
                trigger_type='highest_bet'
            ).exists()

            if not trigger_exists:
                Trigger.objects.create(
                    gambler=gambler,
                    trigger_type='highest_bet',
                    value=highest_bet,
                    explanation="Extremely high stake detected",
                    actions_taken="None"
                )

        all_triggers = Trigger.objects.select_related('gambler').order_by('-triggered_at')
        self_reports = SelfReport.objects.all().order_by('-reported_at')[:3]

        context = {
            'avg_total_bets': int(aggregate_sums['avg_total_bets']),
            'avg_total_stake': int(aggregate_sums['avg_total_stake']),
            'avg_avg_stake': int(aggregate_sums['avg_avg_stake']),
            'avg_max_stake': int(aggregate_sums['avg_max_stake']),
            'avg_min_stake': int(aggregate_sums['avg_min_stake']),
            'avg_total_payout': int(aggregate_sums['avg_total_payout']),
            'avg_win_count': int(aggregate_sums['avg_win_count']),
            'avg_total_loss': int(aggregate_sums['avg_total_loss']),
            'avg_win_rate': int((aggregate_sums['avg_win_rate']) * 100),
            'triggers': all_triggers,
            'self_reports': self_reports

        }
        return render(request, "indexAdmin.html", context)

    else:
        messages.success(request, "You are not allowed to access this location")
        return redirect('login')


def selfReport(request):
    has_reported = SelfReport.objects.filter(gambler=request.user.id).exists()

    context = {
        "has_reported": has_reported
    }

    return render(request, "self-reporting.html", context)


def submit_self_report(request):
    if request.method == 'POST':
        report_message = request.POST.get('report_message', '').strip()

        if not report_message:
            messages.error(request, "Please provide a reason for self-reporting.")
            return redirect('report')

        # Create self-report record
        SelfReport.objects.create(
            gambler=request.user,
            username=request.user.username,
            report_message=report_message,
            reported_at=now()
        )

        messages.success(request, "Your self-report has been submitted successfully.")
        return redirect('report')
    else:
        messages.success(request, "Invalid request")
        return redirect('home')


def myProfile(request):
    user_profile = request.user
    scan_results = GamblerScanResult.objects.get(gambler=request.user.id)

    context = {
        'user_profile': user_profile,
        'scan_results': scan_results,
        'win_rate_percent': scan_results.win_rate * 100
    }

    return render(request, 'Profile.html', context)


def getGambler(request):
    query = request.GET.get('username', '')
    user_profile = None
    scan_results = None

    if query:
        user_profile = get_object_or_404(Gambler, username=query)
        scan_results = GamblerScanResult.objects.get(gambler=user_profile.id)

    return render(request, 'GamblerProfile.html', {
        'query': query,
        'user_profile': user_profile,
        'scan_results': scan_results,
        'win_rate_percent': scan_results.win_rate * 100,
    })


def profileAdmin(request):
    return render(request, "GamblerProfile.html", {})


def closeAccount(request, id):
    gambler = get_object_or_404(Gambler, id=id)
    if request.method == 'POST':
        gambler.account_status = 'closed'
        gambler.save()
        messages.success(request, f"Account for {gambler.username} has been closed.")
    return redirect('profilesAdmin')


def suspendAccount(request, id):
    gambler = get_object_or_404(Gambler, id=id)
    if request.method == 'POST':
        gambler.account_status = 'suspended'
        gambler.save()
        messages.warning(request, f"Account for {gambler.username} has been suspended.")
    return redirect('profilesAdmin')


def activateAccount(request, id):
    gambler = get_object_or_404(Gambler, id=id)
    if request.method == 'POST':
        gambler.account_status = 'active'
        gambler.save()
        messages.success(request, f"Account for {gambler.username} has been activated.")
    return redirect('profilesAdmin')


def gamblerTriggers(request):
    return render(request, "Triggers.html", {})
