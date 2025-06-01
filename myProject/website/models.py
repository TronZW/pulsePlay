from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


# Create your models here.
class Gambler(AbstractUser):
    ACCOUNT_STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('closed', 'Closed'),
    ]

    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    account_status = models.CharField(max_length=10, choices=ACCOUNT_STATUS_CHOICES, default='active')
    currency_code = models.CharField(max_length=3, default='USD')
    last_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'gamblers'

    def __str__(self):
        return self.username


class Game(models.Model):
    GAME_TYPE_CHOICES = [
        ('roulette', 'Roulette'),
        ('slots', 'Slots'),
        ('blackjack', 'Blackjack'),
        ('poker', 'Poker'),
        ('sports', 'Sports'),
    ]

    game_name = models.CharField(max_length=100, unique=True)
    game_type = models.CharField(max_length=20, choices=GAME_TYPE_CHOICES)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    min_stake = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_stake = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['game_name']),
        ]
        db_table = 'games'

    def __str__(self):
        return self.game_name


# Bets table
class Bet(models.Model):
    BET_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('won', 'Won'),
        ('lost', 'Lost'),
        ('cancelled', 'Cancelled'),
    ]

    bet_id = models.BigAutoField(primary_key=True)
    gambler = models.ForeignKey(Gambler, on_delete=models.CASCADE, related_name='bets')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='bets')
    stake_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payout_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    bet_status = models.CharField(max_length=10, choices=BET_STATUS_CHOICES)
    placed_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    currency_code = models.CharField(max_length=3, default='USD')
    objects = models.manager

    class Meta:
        indexes = [
            models.Index(fields=['gambler', 'placed_at']),
            models.Index(fields=['bet_status']),
        ]
        db_table = 'bets'

    def __str__(self):
        return f"Bet {self.bet_id} - {self.gambler.username}"


class Stats(models.Model):
    calculated_at = models.DateTimeField(auto_now_add=True)  # When these stats were computed
    avg_total_bets = models.FloatField()
    avg_total_stake = models.DecimalField(max_digits=15, decimal_places=2)
    avg_avg_stake = models.DecimalField(max_digits=10, decimal_places=2)
    avg_max_stake = models.DecimalField(max_digits=10, decimal_places=2)
    avg_min_stake = models.DecimalField(max_digits=10, decimal_places=2)
    avg_total_payout = models.DecimalField(max_digits=15, decimal_places=2)
    avg_win_count = models.FloatField()
    avg_total_loss = models.DecimalField(max_digits=15, decimal_places=2)
    avg_win_rate = models.FloatField()
    objects = models.manager

    class Meta:
        db_table = 'stats'

    def __str__(self):
        return f"Aggregate Stats at {self.calculated_at}"


class GamblerScanResult(models.Model):
    gambler = models.OneToOneField(Gambler, on_delete=models.CASCADE, related_name="scan_result")
    has_scan = models.BooleanField(default=False)
    previous_scan = models.DateTimeField(null=True, blank=True)

    loss_chasing_score = models.DecimalField(max_digits=5, decimal_places=2)
    loss_chasing_severity = models.CharField(max_length=20)

    fluctuating_wagers_score = models.DecimalField(max_digits=5, decimal_places=2)
    fluctuating_wagers_severity = models.CharField(max_length=20)

    impulsive_transactions_score = models.DecimalField(max_digits=5, decimal_places=2)
    impulsive_transactions_severity = models.CharField(max_length=20)

    binge_gambling_score = models.DecimalField(max_digits=5, decimal_places=2)
    binge_gambling_severity = models.CharField(max_length=20)

    monetary_consumption_score = models.DecimalField(max_digits=5, decimal_places=2)
    monetary_consumption_severity = models.CharField(max_length=20)

    total_bets = models.IntegerField(default=0)
    total_stake = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    avg_stake = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    max_stake = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    min_stake = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_payout = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    win_rate = models.FloatField(default=0.0)
    total_loss = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    cluster_label = models.CharField(max_length=50)
    objects = models.manager

    class Meta:
        db_table = 'gambler_scan_results'

    def __str__(self):
        return f"Scan Result for {self.gambler.username}"


class Trigger(models.Model):
    TRIGGER_TYPES = [
        ('loss_chasing', 'Loss Chasing'),
        ('binge_gambling', 'Binge Gambling'),
        ('impulsive_transactions', 'Impulsive Transactions'),
        ('fluctuating_wagers', 'Fluctuating Wagers'),
        ('monetary_consumption', 'Monetary Consumption'),
        ('highest_bet', 'Highest Bet'),
    ]

    id = models.AutoField(primary_key=True)
    gambler = models.ForeignKey(Gambler, on_delete=models.CASCADE, related_name='triggers')
    trigger_type = models.CharField(max_length=32, choices=TRIGGER_TYPES)
    explanation = models.TextField()
    actions_taken = models.TextField(blank=True)
    value = models.DecimalField(max_digits=12,
                                decimal_places=2)  # This holds the trigger value (e.g. score or highest bet amount)
    triggered_at = models.DateTimeField(default=timezone.now)
    objects = models.manager

    class Meta:
        unique_together = ('gambler', 'trigger_type')
        ordering = ['-triggered_at']

    def __str__(self):
        return f"{self.gambler} - {self.get_trigger_type_display()}"


class SelfReport(models.Model):
    id = models.AutoField(primary_key=True)
    gambler = models.ForeignKey(Gambler, on_delete=models.CASCADE, related_name='self_reports')
    username = models.CharField(max_length=150)  # Cached snapshot of the username at time of report
    report_message = models.TextField()
    reported_at = models.DateTimeField(default=timezone.now)
    objects = models.manager

    class Meta:
        db_table = 'self_reports'
        ordering = ['-reported_at']

    def __str__(self):
        return f"Self-report by {self.username} at {self.reported_at.strftime('%Y-%m-%d %H:%M')}"
