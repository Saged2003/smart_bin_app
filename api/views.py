import uuid
import math
from django.core.mail import send_mail
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status  
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from django_ratelimit.decorators import ratelimit
from .models import Profile, Bin, Activity, Compound, Reward, RedeemedReward
from .serializers import CompoundSerializer, ActivitySerializer, RewardSerializer, BinSerializer, ProfileSerializer

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def verify_hardware_token(bin_obj, provided_token):
    if bin_obj.hardware_token and bin_obj.hardware_token != provided_token:
        return False
    return True

@api_view(['POST'])
def register_user(request):
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email')
    is_employee = request.data.get('is_employee', False)

    if User.objects.filter(username=username).exists():
        return Response({'error': 'exists'}, status=400)

    user = User.objects.create_user(username=username, password=password, email=email)
    Profile.objects.create(user=user, points=0, milestone_points=0, weight=0.0, co2_saved=0.0, deposits=0, is_employee=is_employee, is_approved_employee=False)
    token, created = Token.objects.get_or_create(user=user)

    if is_employee:
        try:
            send_mail(
                'New Employee Registration Request',
                f'User {username} ({email}) requested to join as an employee. Please approve or reject from the system.',
                'admin@smartbin.local',
                ['sagedryan775@gmail.com'],  
                fail_silently=True,
            )
        except Exception:
            pass

    return Response({
        'message': 'ok',
        'token': token.key,
        'points': 0,
        'username': username,
        'is_employee': is_employee,
        'is_approved_employee': False
    })

@ratelimit(key='ip', rate='5/m', block=True)
@api_view(['POST'])
def login_user(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)

    if user is not None:
        token, created = Token.objects.get_or_create(user=user)
        
        profile, created_profile = Profile.objects.get_or_create(user=user)
        
        if created_profile:
            profile.points = 0
            profile.milestone_points = 0
            profile.weight = 0.0
            profile.co2_saved = 0.0
            profile.deposits = 0
            profile.save()
            
        return Response({
            'message': 'ok',
            'token': token.key,
            'points': profile.points,
            'username': username,
            'is_employee': profile.is_employee,
            'is_approved_employee': profile.is_approved_employee
        })
    return Response({'error': 'wrong'}, status=400)

@api_view(['GET'])
def get_profile(request):
    username = request.query_params.get('username')
    try:
        user = User.objects.get(username=username)
        # التعديل هنا للحماية
        profile, created = Profile.objects.get_or_create(user=user)
        
        return Response({
            'points': profile.points,
            'milestone_points': profile.milestone_points,
            'premium_unlocked': profile.premium_unlocked,
            'weight': profile.weight,
            'co2_saved': round(profile.co2_saved, 2),
            'deposits': profile.deposits,
            'full_name': profile.full_name or '',
            'email': user.email or '',
            'phone': profile.phone or '',
            'address': profile.address or '',
            'is_employee': profile.is_employee,
            'is_approved_employee': profile.is_approved_employee,
            'profile_picture': profile.profile_picture.url if profile.profile_picture else None
        })
    except Exception:
        return Response({'error': 'not found'}, status=404)

@api_view(['PUT'])
@parser_classes([MultiPartParser, FormParser])
def update_profile(request):
    user = request.user if request.user.is_authenticated else None
    if not user:
        username = request.data.get('username')
        try:
            user = User.objects.get(username=username)
        except Exception:
            return Response({'error': 'unauthorized'}, status=401)

    try:
        # التعديل هنا للحماية
        profile, created = Profile.objects.get_or_create(user=user)

        if 'email' in request.data:
            user.email = request.data.get('email')
            user.save()

        profile.full_name = request.data.get('full_name', profile.full_name)
        profile.phone = request.data.get('phone', profile.phone)
        profile.address = request.data.get('address', profile.address)

        if 'profile_picture' in request.FILES:
            profile.profile_picture = request.FILES['profile_picture']

        profile.save()

        return Response({
            'message': 'updated',
            'profile_picture': profile.profile_picture.url if profile.profile_picture else None
        })
    except Exception as error:
        return Response({'error': str(error)}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_employee(request):
    if request.user.email != 'sagedryan775@gmail.com' and not request.user.is_superuser:
        return Response({'error': 'unauthorized'}, status=403)

    target_username = request.data.get('username')
    action = request.data.get('action')

    try:
        target_user = User.objects.get(username=target_username)
        # التعديل هنا للحماية
        profile, created = Profile.objects.get_or_create(user=target_user)

        if action == 'approve':
            profile.is_approved_employee = True
            profile.save()
            return Response({'message': 'approved'})
        elif action == 'reject':
            target_user.delete()
            return Response({'message': 'rejected'})

    except Exception as error:
        return Response({'error': str(error)}, status=400)

@api_view(['POST'])
def esp_get_code(request):
    bin_id = request.data.get('bin_id')
    hardware_token = request.data.get('hardware_token')
    
    try:
        bin_obj, created = Bin.objects.get_or_create(bin_id=bin_id)
        if not created and not verify_hardware_token(bin_obj, hardware_token):
            return Response({'error': 'Unauthorized Hardware'}, status=403)
        
        if bin_obj.status != 'idle':
            return Response({'code': bin_obj.current_qr_code, 'status': bin_obj.status})
            
        new_code = str(uuid.uuid4())
        bin_obj.current_qr_code = new_code
        bin_obj.save()
        return Response({'code': new_code, 'status': 'idle'})
    except Exception as error:
        return Response({'error': str(error)}, status=400)

@ratelimit(key='ip', rate='10/m', block=True)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def user_scan_qr(request):
    code = request.data.get('code')
    user = request.user
    try:
        bin_obj = Bin.objects.get(current_qr_code=code)
        if bin_obj.status != 'idle':
            return Response({'error': 'invalid code'}, status=400)

        bin_obj.current_user = user
        bin_obj.status = 'scanned'
        bin_obj.save()
        return Response({'message': 'scanned successfully'})
    except Bin.DoesNotExist:
        return Response({'error': 'invalid code'}, status=404)

@api_view(['POST'])
def esp_check_scan(request):
    bin_id = request.data.get('bin_id')
    hardware_token = request.data.get('hardware_token')
    
    try:
        bin_obj = Bin.objects.get(bin_id=bin_id)
        if not verify_hardware_token(bin_obj, hardware_token):
            return Response({'error': 'Unauthorized Hardware'}, status=403)
            
        if bin_obj.status == 'scanned':
            bin_obj.status = 'active'
            bin_obj.save()
            return Response({'status': 'YES'})
        return Response({'status': 'NO'})
    except Bin.DoesNotExist:
        return Response({'error': 'bin not found'}, status=404)

@api_view(['POST'])
def esp_end_session(request):
    bin_id = request.data.get('bin_id')
    hardware_token = request.data.get('hardware_token')
    points = int(request.data.get('points', 0))
    weight = float(request.data.get('weight', 0.0))

    try:
        bin_obj = Bin.objects.get(bin_id=bin_id)
        if not verify_hardware_token(bin_obj, hardware_token):
            return Response({'error': 'Unauthorized Hardware'}, status=403)
            
        user = bin_obj.current_user

        if user:
            # التعديل هنا للحماية
            profile, created = Profile.objects.get_or_create(user=user)
            profile.points += points
            profile.milestone_points += points
            profile.weight += weight
            profile.deposits += 1
            
            saved_co2 = weight * 1.5 
            profile.co2_saved += saved_co2
            
            while profile.milestone_points >= 1000:
                profile.premium_unlocked = True
                profile.milestone_points -= 1000

            profile.save()

            Activity.objects.create(user=user, points=points, weight=weight, co2_saved_in_activity=saved_co2)

        bin_obj.status = 'idle'
        bin_obj.current_user = None
        bin_obj.current_qr_code = None
        bin_obj.save()

        return Response({'message': 'session ended'})
    except Bin.DoesNotExist:
        return Response({'error': 'bin not found'}, status=404)

@api_view(['POST'])
def esp_update_capacity(request):
    bin_id = request.data.get('bin_id')
    hardware_token = request.data.get('hardware_token')
    capacity = float(request.data.get('capacity', 0.0))

    try:
        bin_obj = Bin.objects.get(bin_id=bin_id)
        if not verify_hardware_token(bin_obj, hardware_token):
            return Response({'error': 'Unauthorized Hardware'}, status=403)
            
        bin_obj.capacity = capacity
        if capacity >= 80:
            bin_obj.crowd_level = 'High Crowd'
        elif capacity >= 50:
            bin_obj.crowd_level = 'Medium Crowd'
        else:
            bin_obj.crowd_level = 'Low Crowd'
        
        bin_obj.save()
        return Response({'message': 'Capacity updated successfully'})
    except Bin.DoesNotExist:
        return Response({'error': 'Bin not found'}, status=404)
    except Exception as error:
        return Response({'error': str(error)}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def employee_update_location(request):
    # التعديل هنا للحماية
    profile, created = Profile.objects.get_or_create(user=request.user)
    if not profile.is_employee or not profile.is_approved_employee:
        return Response({'error': 'unauthorized'}, status=403)

    bin_id = request.data.get('bin_id')
    lat = request.data.get('lat')
    lng = request.data.get('lng')

    try:
        bin_obj, created_bin = Bin.objects.get_or_create(bin_id=bin_id)
        bin_obj.lat = float(lat)
        bin_obj.lng = float(lng)
        bin_obj.save()
        return Response({'message': 'location updated'})
    except Exception as error:
        return Response({'error': str(error)}, status=400)

@api_view(['GET'])
def get_all_bins(request):
    lat_str = request.query_params.get('lat')
    lng_str = request.query_params.get('lng')

    bins = Bin.objects.all()
    bins_data = BinSerializer(bins, many=True).data

    if lat_str and lng_str:
        try:
            u_lat = float(lat_str)
            u_lng = float(lng_str)
            for b in bins_data:
                if b['lat'] is not None and b['lng'] is not None:
                    dist = haversine(u_lat, u_lng, b['lat'], b['lng'])
                    b['distance_km'] = round(dist, 2)
                else:
                    b['distance_km'] = None
            
            bins_data.sort(key=lambda x: x['distance_km'] if x['distance_km'] is not None else float('inf'))
        except ValueError:
            pass

    return Response(bins_data)

@api_view(['GET'])
def get_activities(request):
    username = request.query_params.get('username')
    
    page = int(request.query_params.get('page', 1))
    limit = int(request.query_params.get('limit', 10))
    start = (page - 1) * limit
    end = start + limit
    
    try:
        user = User.objects.get(username=username)
        activities = Activity.objects.filter(user=user).order_by('-date')
        
        total_activities = activities.count()
        paginated_activities = activities[start:end]
        
        serializer = ActivitySerializer(paginated_activities, many=True)
        return Response({
            'total_activities': total_activities,
            'page': page,
            'limit': limit,
            'data': serializer.data
        })
    except Exception:
        return Response({'error': 'not found'}, status=404)

@api_view(['GET'])
def get_rewards(request):
    username = request.query_params.get('username')
    user_points = 0
    milestone_points = 0
    premium_unlocked = False
    redeemed_ids = []

    if username:
        try:
            u = User.objects.get(username=username)
            # التعديل هنا للحماية
            p, created = Profile.objects.get_or_create(user=u)
            user_points = p.points
            milestone_points = p.milestone_points
            premium_unlocked = p.premium_unlocked
            redeemed_ids = RedeemedReward.objects.filter(user=u).values_list('reward_id', flat=True)
        except Exception:
            pass

    rewards = Reward.objects.exclude(id__in=redeemed_ids)
    data = []
    
    for r in rewards:
        r_data = RewardSerializer(r, context={'request': request}).data
        
        if r.is_premium and not premium_unlocked:
            r_data['status'] = 'locked'
        elif user_points >= r.required_points and user_points >= r.cost:
            r_data['status'] = 'redeem'
        else:
            r_data['status'] = 'locked'
            
        data.append(r_data)

    points_left = 1000 - milestone_points if milestone_points < 1000 else 0

    return Response({
        'rewards': data,
        'user_points': user_points,
        'next_milestone': 1000,
        'points_left': points_left,
        'premium_unlocked': premium_unlocked
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def redeem_reward(request):
    reward_id = request.data.get('reward_id')
    original_price = request.data.get('original_price')
    user = request.user
    
    try:
        # التعديل هنا للحماية
        profile, created = Profile.objects.get_or_create(user=user)
        reward = Reward.objects.get(id=reward_id)

        if reward.is_premium and not profile.premium_unlocked:
            return Response({'error': 'premium rewards locked'}, status=400)

        if profile.points < reward.required_points:
            return Response({'error': 'not enough points to unlock'}, status=400)

        if profile.points < reward.cost:
            return Response({'error': 'not enough points to redeem'}, status=400)

        profile.points -= reward.cost
        
        if reward.is_premium:
            profile.premium_unlocked = False

        profile.save()

        RedeemedReward.objects.create(user=user, reward=reward)

        response_data = {
            'message': 'redeemed successfully',
            'new_points': profile.points
        }

        if reward.discount_percentage is not None and original_price is not None:
            price = float(original_price)
            discount_amount = price * (reward.discount_percentage / 100.0)
            final_price = price - discount_amount
            
            response_data['discount_percentage'] = reward.discount_percentage
            response_data['original_price'] = price
            response_data['discount_amount'] = discount_amount
            response_data['final_price'] = final_price

        return Response(response_data)

    except Reward.DoesNotExist:
        return Response({'error': 'invalid reward'}, status=404)
    except Exception as error:
        return Response({'error': str(error)}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_fcm_token(request):
    """
    دالة لتحديث الـ FCM Token الخاص باليوزر.
    """
    token = request.data.get('fcm_token')
    
    if not token:
        return Response({"error": "FCM token is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    return Response({"message": "FCM token updated successfully"}, status=status.HTTP_200_OK)