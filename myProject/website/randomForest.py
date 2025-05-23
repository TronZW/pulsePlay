import pandas as pd
import numpy as np
import joblib
from datetime import timedelta
from django.utils.timezone import make_naive
from .models import Bet
import os

# Load trained model
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'models')
model = joblib.load(os.path.join(MODEL_PATH, 'random_forest_gambling_risk_model.pkl'))


# Define the feature extraction function
def extract_features_for_gambler(gambler_id):
    bets = Bet.objects.filter(gambler__id=gambler_id).order_by('placed_at')
    if not bets.exists():
        return None

    data = []
    for bet in bets:
        data.append({
            "gambler_id": bet.gambler.id,
            "placed_at": make_naive(bet.placed_at),
            "amount": float(bet.stake_amount),
        })
    df = pd.DataFrame(data)

    df['time_diff'] = df['placed_at'].diff().dt.total_seconds() / 60.0
    df['hour'] = df['placed_at'].dt.hour
    df['day'] = df['placed_at'].dt.date

    def assign_sessions(times, threshold=30):
        session_id = 0
        sessions = []
        last_time = None
        for t in times:
            if last_time is None or (t - last_time).total_seconds() > threshold * 60:
                session_id += 1
            sessions.append(session_id)
            last_time = t
        return sessions

    df["session_id"] = assign_sessions(df["placed_at"])

    features = {}
    features["total_amount_spent"] = df["amount"].sum()
    features["avg_transaction_amount"] = df["amount"].mean()
    features["std_transaction_amount"] = df["amount"].std()
    features["min_transaction_amount"] = df["amount"].min()
    features["max_transaction_amount"] = df["amount"].max()
    features["avg_time_between_txn"] = df["time_diff"].mean()
    features["min_time_between_txn"] = df["time_diff"].min()
    features["night_txn_ratio"] = np.mean((df["hour"] >= 0) & (df["hour"] < 6))
    features["txn_burst_ratio"] = np.mean(df["time_diff"] <= 10)
    features["avg_txn_per_day"] = len(df) / len(set(df["day"]))
    features["amount_cv"] = features["std_transaction_amount"] / (features["avg_transaction_amount"] or 1)
    features["range_transaction_amount"] = features["max_transaction_amount"] - features["min_transaction_amount"]

    session_stats = df.groupby("session_id").agg(
        session_txn_count=("amount", "count"),
        session_duration=("placed_at", lambda x: (x.max() - x.min()).total_seconds() / 60)
    )

    features["avg_txn_per_session"] = session_stats["session_txn_count"].mean()
    features["max_txn_per_session"] = session_stats["session_txn_count"].max()
    features["avg_session_duration"] = session_stats["session_duration"].mean()
    features["long_session_ratio"] = np.mean(session_stats["session_duration"] >= 60)

    return pd.DataFrame([features])


# Predict gambling behavior patterns
def predict_gambler_behavior(gambler_id):
    feature_df = extract_features_for_gambler(gambler_id)
    if feature_df is None:
        return {"error": "No bets found for this gambler."}

    predictions = model.predict(feature_df)
    risk_targets = [
        "loss_chasing_score",
        "fluctuating_wagers_score",
        "impulsive_transactions_score",
        "binge_gambling_score",
        "monetary_consumption_score"
    ]
    return dict(zip(risk_targets, predictions[0].round(3)))


# this code is used to label the risk scores
def get_severity_label(score_percent):
    if score_percent <= 40:
        return "Low"
    elif 41 <= score_percent <= 60:
        return "Moderate"
    elif 61 <= score_percent <= 79:
        return "High"
    else:  # score_percent >= 80
        return "Extremely High"


def label_risk_severity(predictions):
    labeled_results = {}
    for pattern, score in predictions.items():
        score_percent = round(score * 100, 2)
        severity = get_severity_label(score_percent)
        labeled_results[pattern] = {
            "score_percent": score_percent,
            "severity": severity
        }
    return labeled_results


def get_user_messages(results):
    messages = []

    for result in results:
        pattern = result["pattern"]
        score = result["score"]
        severity = result["severity"]

        if score <= 40:
            continue  # No message for low severity

        if pattern == "loss_chasing_score":
            if severity == "Moderate":
                messages.append(
                    "We've noticed you sometimes try to recover losses quickly. It's okay to take breaks — not every loss needs to be chased.")
            elif severity == "High":
                messages.append(
                    "It looks like you're often trying to win back losses. Consider setting limits or stepping away for a bit.")
            elif severity == "Extremely High":
                messages.append(
                    "You may be chasing losses too often. Please consider using our support tools to stay in control.")

        elif pattern == "fluctuating_wagers_score":
            if severity == "Moderate":
                messages.append(
                    "Your bet sizes vary a lot. Try setting a comfortable betting amount that works for you.")
            elif severity == "High":
                messages.append(
                    "We’ve seen big ups and downs in how much you bet. Keeping things consistent may help you stay in control.")
            elif severity == "Extremely High":
                messages.append(
                    "You’re placing bets that change dramatically. Consider setting bet limits or using our budgeting tools.")

        elif pattern == "impulsive_transactions_score":
            if severity == "Moderate":
                messages.append(
                    "You’ve placed several quick bets in short periods. Taking a moment to think between bets can help you stay in control.")
            elif severity == "High":
                messages.append(
                    "You seem to be betting quite impulsively. Consider using our tools to set timeouts or reminders.")
            elif severity == "Extremely High":
                messages.append(
                    "You’re placing many bets in rapid succession. We recommend pausing and using our support features.")

        elif pattern == "binge_gambling_score":
            if severity == "Moderate":
                messages.append(
                    "You’ve had some long playing sessions. Remember to take regular breaks — your wellbeing comes first.")
            elif severity == "High":
                messages.append(
                    "You’re playing for extended periods without many breaks. Taking short rests can improve your experience.")
            elif severity == "Extremely High":
                messages.append(
                    "You’ve spent a lot of time gambling in long bursts. Consider using our session limit features to help you take breaks.")

        elif pattern == "monetary_consumption_score":
            if severity == "Moderate":
                messages.append(
                    "Your spending is starting to go up. Consider reviewing your budget to make sure you're comfortable.")
            elif severity == "High":
                messages.append(
                    "You’ve been spending more than usual. Our tools can help you set spending limits and stay in control.")
            elif severity == "Extremely High":
                messages.append(
                    "We’ve noticed very high spending on your account. Please consider setting strong limits or reaching out for support.")

    return messages
