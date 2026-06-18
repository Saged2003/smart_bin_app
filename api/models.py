from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    points = models.IntegerField(default=0)
    weight = models.FloatField(default=0.0)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    address = models.CharField(max_length=200, null=True, blank=True)
    deposits = models.IntegerField(default=0)
    is_employee = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username

class Compound(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=200)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=50, default='available')

    def __str__(self):
        return self.name

class Bin(models.Model):
    bin_id = models.CharField(max_length=50, unique=True)
    current_qr_code = models.CharField(max_length=100, null=True, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=50, default='idle')
    current_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.bin_id

class Activity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    weight = models.FloatField(default=0.0)
    points = models.IntegerField(default=0)
    date = models.DateTimeField(auto_now_add=True)

class Reward(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=100)
    cost = models.IntegerField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name