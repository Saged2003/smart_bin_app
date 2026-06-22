from rest_framework import serializers
from .models import Compound, Activity, Reward, Profile, Bin, RedeemedReward

class CompoundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Compound
        fields = '__all__'

class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = '__all__'

class RewardSerializer(serializers.ModelSerializer):
    is_locked = serializers.SerializerMethodField()

    class Meta:
        model = Reward
        fields = '__all__'
        
    def get_is_locked(self, obj):
        request = self.context.get('request', None)
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return request.user.profile.points < obj.required_points
        return True

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'

class BinSerializer(serializers.ModelSerializer):
    distance_km = serializers.FloatField(read_only=True, required=False)
    
    class Meta:
        model = Bin
        fields = '__all__'
        extra_kwargs = {'hardware_token': {'write_only': True}}

class RedeemedRewardSerializer(serializers.ModelSerializer):
    class Meta:
        model = RedeemedReward
        fields = '__all__'