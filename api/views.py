import uuid
from django.core.mail import send_mail
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from .models import Profile, Bin, Activity, Compound, Reward
from .serializers import CompoundSerializer, ActivitySerializer, RewardSerializer, BinSerializer, ProfileSerializer

SYSTEM_AUTHOR = "SAGED RYAN"

@api_view(['POST'])
def register_user(request):
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email')
    is_employee = request.data.get('is_employee', False)

    if User.objects.filter(username=username).exists():
        return Response({'error': 'exists'}, status=400)

    user = User.objects.create_user(username=username, password=password, email=email)
    Profile.objects.create(user=user, points=0, weight=0.0, deposits=0, is_employee=is_employee, is_approved_employee=False)
    token, created = Token.objects.get_or_create(user=user)

    if is_employee:
        try:
            send_mail(
                'New Employee Registration Request',
                f'User {username} ({email}) requested to join as an employee. Please approve or reject from the system.',
                'sagedryan775@gmail.com',
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

@api_view(['POST'])
def login_user(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)

    if user is not None:
        token, created = Token.objects.get_or_create(user=user)
        profile = Profile.objects.get(user=user)
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
        profile = Profile.objects.get(user=user)
        return Response({
            'points': profile.points,
            'weight': profile.weight,
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
        profile = Profile.objects.get(user=user)

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
    if request.user.email != 'sagedryan775@gmail.com':
        return Response({'error': 'unauthorized'}, status=403)

    target_username = request.data.get('username')
    action = request.data.get('action')

    try:
        target_user = User.objects.get(username=target_username)
        profile = Profile.objects.get(user=target_user)

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
    try:
        bin_obj, created = Bin.objects.get_or_create(bin_id=bin_id)
        
        if bin_obj.status != 'idle':
            return Response({'code': bin_obj.current_qr_code, 'status': bin_obj.status})
            
        new_code = str(uuid.uuid4())
        bin_obj.current_qr_code = new_code
        bin_obj.save()
        return Response({'code': new_code, 'status': 'idle'})
    except Exception as error:
        return Response({'error': str(error)}, status=400)

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
    try:
        bin_obj = Bin.objects.get(bin_id=bin_id)
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
    points = int(request.data.get('points', 0))
    weight = float(request.data.get('weight', 0.0))

    try:
        bin_obj = Bin.objects.get(bin_id=bin_id)
        user = bin_obj.current_user

        if user:
            profile = Profile.objects.get(user=user)
            profile.points += points
            profile.weight += weight
            profile.deposits += 1
            profile.save()

            Activity.objects.create(user=user, points=points, weight=weight)

        bin_obj.status = 'idle'
        bin_obj.current_user = None
        bin_obj.current_qr_code = None
        bin_obj.save()

        return Response({'message': 'session ended'})
    except Bin.DoesNotExist:
        return Response({'error': 'bin not found'}, status=404)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def employee_update_location(request):
    profile = Profile.objects.get(user=request.user)
    if not profile.is_employee or not profile.is_approved_employee:
        return Response({'error': 'unauthorized'}, status=403)

    bin_id = request.data.get('bin_id')
    lat = request.data.get('lat')
    lng = request.data.get('lng')

    try:
        bin_obj, created = Bin.objects.get_or_create(bin_id=bin_id)
        bin_obj.lat = float(lat)
        bin_obj.lng = float(lng)
        bin_obj.save()
        return Response({'message': 'location updated'})
    except Exception as error:
        return Response({'error': str(error)}, status=400)

@api_view(['GET'])
def get_all_bins(request):
    bins = Bin.objects.all()
    serializer = BinSerializer(bins, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def get_activities(request):
    username = request.query_params.get('username')
    try:
        user = User.objects.get(username=username)
        activities = Activity.objects.filter(user=user).order_by('-date')
        serializer = ActivitySerializer(activities, many=True)
        return Response(serializer.data)
    except Exception:
        return Response({'error': 'not found'}, status=404)

@api_view(['GET'])
def get_rewards(request):
    username = request.query_params.get('username')
    user_points = 0
    if username:
        try:
            u = User.objects.get(username=username)
            p = Profile.objects.get(user=u)
            user_points = p.points
        except Exception:
            pass

    rewards = Reward.objects.all()
    data = []
    for r in rewards:
        r_data = RewardSerializer(r).data
        if user_points >= r.required_points:
            r_data['status'] = 'redeem'
        else:
            r_data['status'] = 'locked'
        data.append(r_data)

    milestone_step = 1000
    current_level = user_points // milestone_step
    next_milestone = (current_level + 1) * milestone_step
    points_left = next_milestone - user_points

    return Response({
        'rewards': data,
        'user_points': user_points,
        'next_milestone': next_milestone,
        'points_left': points_left
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def redeem_reward(request):
    reward_id = request.data.get('reward_id')
    original_price = request.data.get('original_price')
    user = request.user
    
    try:
        profile = Profile.objects.get(user=user)
        reward = Reward.objects.get(id=reward_id)

        if profile.points < reward.required_points:
            return Response({'error': 'not enough points to unlock'}, status=400)

        if profile.points < reward.cost:
            return Response({'error': 'not enough points to redeem'}, status=400)

        profile.points -= reward.cost
        profile.save()

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