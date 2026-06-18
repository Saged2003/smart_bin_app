from django.contrib import admin
from .models import Profile, Compound, Bin, Activity, Reward

admin.site.register(Profile)
admin.site.register(Compound)
admin.site.register(Bin)
admin.site.register(Activity)
admin.site.register(Reward)