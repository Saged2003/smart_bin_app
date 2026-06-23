import json
import uuid
import paho.mqtt.client as mqtt
from django.conf import settings
from api.models import Bin, Profile, Activity

def process_payload(client, bin_obj, action, payload):
    bin_id = bin_obj.bin_id
    hw_token = payload.get('hardware_token')
    if bin_obj.hardware_token and bin_obj.hardware_token != hw_token:
        return
    if action == 'request_qr':
        new_code = str(uuid.uuid4())
        bin_obj.current_qr_code = new_code
        bin_obj.status = 'idle'
        bin_obj.save()
        client.publish(f"smartbin/{bin_id}/qr_code", json.dumps({"code": new_code}))
    elif action == 'update':
        capacity = float(payload.get('capacity', 0.0))
        bin_obj.capacity = capacity
        if capacity >= 80:
            bin_obj.crowd_level = 'High Crowd'
        elif capacity >= 50:
            bin_obj.crowd_level = 'Medium Crowd'
        else:
            bin_obj.crowd_level = 'Low Crowd'
        bin_obj.save()
        if capacity >= 90.0:
            from api.views import send_fcm_notification
            employee_profiles = Profile.objects.filter(is_employee=True, is_approved_employee=True)
            for emp in employee_profiles:
                if emp.fcm_token:
                    send_fcm_notification(emp.fcm_token, "Bin Full Alert", f"Bin {bin_id} has reached {capacity}% capacity.")
    elif action == 'session_end':
        points = int(payload.get('points', 0))
        weight = float(payload.get('weight', 0.0))
        user = bin_obj.current_user
        if user:
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
                if profile.fcm_token:
                    from api.views import send_fcm_notification
                    send_fcm_notification(profile.fcm_token, "Premium Unlocked!", "You have reached 1000 points!")
            profile.save()
            Activity.objects.create(user=user, points=points, weight=weight, co2_saved_in_activity=saved_co2)
        bin_obj.status = 'idle'
        bin_obj.current_user = None
        bin_obj.current_qr_code = None
        bin_obj.save()

def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("smartbin/+/update")
    client.subscribe("smartbin/+/session_end")
    client.subscribe("smartbin/+/request_qr")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        topic_parts = msg.topic.split('/')
        bin_id = topic_parts[1]
        action = topic_parts[2]
        bin_obj = Bin.objects.filter(bin_id=bin_id).first()
        if not bin_obj:
            return
        if isinstance(payload, list):
            for item in payload:
                process_payload(client, bin_obj, action, item)
        else:
            process_payload(client, bin_obj, action, payload)
    except Exception:
        pass

def start_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    broker_url = getattr(settings, 'MQTT_BROKER_URL', '127.0.0.1')
    broker_port = getattr(settings, 'MQTT_BROKER_PORT', 1883)
    try:
        client.connect(broker_url, broker_port, 60)
        client.loop_start()
    except Exception:
        pass