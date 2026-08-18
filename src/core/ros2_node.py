import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, LaserScan
from cv_bridge import CvBridge
import cv2
import numpy as np
import pyzbar.pyzbar as pyzbar
import msgpack
import umsgpack
import base64
import urllib.request
import urllib.error
import json
import time
import threading

class StandaloneSensorNode(Node):
    def __init__(self, api_url="http://127.0.0.1:8080"):
        super().__init__("drone_sensor_node")
        self.api_url = api_url
        
        # Topics
        camera_topic = "/world/lab/model/x500_thesis_0/model/OakD_Lite_Camera/link/camera_link/sensor/IMX214/image"
        floor_camera_topic = "/world/lab/model/x500_thesis_0/model/Mono_Camera_Floor/link/camera_link/sensor/camera/image"
        lidar_topic = "/world/lab/model/x500_thesis_0/model/lidar_sensor/link/link/sensor/lidar_2d_v2/scan"
        
        # Subscribers
        self.camera_sub = self.create_subscription(Image, camera_topic, self.image_callback, 10)
        self.floor_camera_sub = self.create_subscription(Image, floor_camera_topic, self.floor_camera_callback, 10)
        self.lidar_sub = self.create_subscription(LaserScan, lidar_topic, self.lidar_callback, 10)
        
        self.br = CvBridge() 
        
        # State
        self.state = {
            "product_detected": False,
            "product_bbox": None,
            "closest_obstacle_distance": float('inf'),
            "obstacle_front_m": float('inf'),
            "obstacle_left_m": float('inf'),
            "obstacle_right_m": float('inf'),
            "latest_image_base64": None,
            "latest_floor_image_base64": None,
            "qr_data": None,
            "aruco_data": None
        }
        self.state_lock = threading.Lock()
        
        # ArUco Detectors (Supports standard OpenCV dictionaries)
        self.aruco_dicts = [
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100),
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250),
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_ARUCO_ORIGINAL)
        ]
        self.aruco_params = cv2.aruco.DetectorParameters()

        cv2.namedWindow("Drone POV", cv2.WINDOW_NORMAL)
        cv2.namedWindow("Floor Camera POV", cv2.WINDOW_NORMAL)
        
        # Publisher thread (to not block ROS2 callbacks if HTTP is slow)
        self.pub_thread = threading.Thread(target=self.publish_loop, daemon=True)
        self.pub_thread.start()
        
        self.get_logger().info("Standalone ROS2 Node started. Pushing to FastAPI...")

    def image_callback(self, data):
        '''
        These method receives data from the ros nodes for the sensor and camera and translates to 'bgr8' for openCV.
        It detects QR codes and saves them on the self.state["qr_data"], which is updated with a frequency of 10 Hz.
        The self.state["qr_data"] is a list of dictionaries, which contains the json data from the QR code.
        The qr data can be retrieved from the endpoint /sensors/vision/qr_code
        '''
        try:
            current_frame = self.br.imgmsg_to_cv2(data, "bgr8")
            parsed_qrs = []
            product_detected = False
            product_bbox = None

            # Detect QR Code 
            try:
                from pyzbar.pyzbar import ZBarSymbol
                decoded_objects = pyzbar.decode(current_frame, symbols=[ZBarSymbol.QRCODE])
                if decoded_objects:
                    product_detected = True
                    for obj in decoded_objects:
                        raw_binary_data = obj.data
                        parsed_data = None
                        
                        try:
                            string_repr = obj.data.decode('utf-8')
                            for enc in ['shift_jis', 'latin-1']:
                                try:
                                    candidate = string_repr.encode(enc)
                                    unpacker = msgpack.Unpacker(raw=False)
                                    unpacker.feed(candidate)
                                    parsed_data = next(unpacker)
                                    raw_binary_data = candidate  
                                    break
                                except Exception:
                                    pass
                        except UnicodeDecodeError:
                            pass # Not UTF-8 corrupted
       
                        if parsed_data is None:
                            try:
                                unpacker = msgpack.Unpacker(raw=False)
                                unpacker.feed(raw_binary_data)
                                parsed_data = next(unpacker)
                            except Exception as e:
                                self.get_logger().error(f"Failed to unpack msgpack: {e}")
                                # If msgpack fails, try fallback JSON
                                try:
                                    fallback_str = raw_binary_data.decode('utf-8')
                                    fallback_data = json.loads(fallback_str)
                                    parsed_data = fallback_data
                                except Exception:
                                    pass
                                    
                        if parsed_data is not None:
                            # Handle potential string/bytes layers from older encoder versions
                            if isinstance(parsed_data, bytes):
                                parsed_data = parsed_data.decode('utf-8')
                            if isinstance(parsed_data, str):
                                try:
                                    parsed_data = json.loads(parsed_data)
                                except json.JSONDecodeError:
                                    pass
                                    
                            if isinstance(parsed_data, (dict, list, str)):
                                parsed_qrs.append(parsed_data)
                            else:
                                # FastAPI schema strictly expects dict | str | list
                                parsed_qrs.append(str(parsed_data))
                            
                        # 2. Draw bounding box from polygon
                        points = obj.polygon
                        if points and len(points) == 4:
                            n = len(points)
                            for i in range(n):
                                pt1 = (points[i].x, points[i].y)
                                pt2 = (points[(i + 1) % n].x, points[(i + 1) % n].y)
                                cv2.line(current_frame, pt1, pt2, (255, 0, 0), 3)
                            
                            pt1 = (points[0].x, points[0].y)
                            cv2.putText(current_frame, "QR Detected", (pt1[0], pt1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                            
                            # Derive product bounding box from the first detected QR
                            if product_bbox is None:
                                xs = [p.x for p in points]
                                ys = [p.y for p in points]
                                x, y = int(min(xs)), int(min(ys))
                                w, h = int(max(xs) - x), int(max(ys) - y)
                                product_bbox = {"x": x, "y": y, "w": w, "h": h}
                                
            except Exception as e:
                self.get_logger().error(f"QR Error: {e}")

            # Display image
            cv2.imshow("Drone POV :)", current_frame)
            cv2.waitKey(1)

            # Encode image
            _, buffer = cv2.imencode('.jpg', current_frame)
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            with self.state_lock:
                self.state["product_detected"] = product_detected
                self.state["product_bbox"] = product_bbox
                self.state["latest_image_base64"] = img_base64
                
                # Accumulate QR data
                if parsed_qrs:
                    existing = self.state["qr_data"]
                    if existing is None:
                        current_qrs = []
                    elif isinstance(existing, list):
                        current_qrs = list(existing)
                    else:
                        current_qrs = [existing]

                    for item in parsed_qrs:
                        if item not in current_qrs:
                            current_qrs.append(item)

                    self.state["qr_data"] = current_qrs[0] if len(current_qrs) == 1 else current_qrs
                
        except Exception as e:
            self.get_logger().error(f"Image Error: {e}")

    def floor_camera_callback(self, data):
        '''
        Receives data from the floor camera, detects ArUco markers,
        calculates center pixel coordinates and process flags (shelf start, shelf end, landing pad).
        '''
        try:
            current_frame = self.br.imgmsg_to_cv2(data, "bgr8")
            detected_markers = []

            for aruco_dict in self.aruco_dicts:
                if hasattr(cv2.aruco, "ArucoDetector"):
                    detector = cv2.aruco.ArucoDetector(aruco_dict, self.aruco_params)
                    corners, ids, _ = detector.detectMarkers(current_frame)
                else:
                    corners, ids, _ = cv2.aruco.detectMarkers(current_frame, aruco_dict, parameters=self.aruco_params)

                if ids is not None and len(ids) > 0:
                    cv2.aruco.drawDetectedMarkers(current_frame, corners, ids)
                    for marker_corners, marker_id in zip(corners, ids.flatten()):
                        pts = marker_corners[0]
                        cx = int(sum(pt[0] for pt in pts) / 4)
                        cy = int(sum(pt[1] for pt in pts) / 4)
                        marker_info = {
                            "id": int(marker_id),
                            "center": {"x": cx, "y": cy}
                        }
                        if marker_info not in detected_markers:
                            detected_markers.append(marker_info)

            # classify markers
            marker_ids = [m["id"] for m in detected_markers]
            is_shelf_start = 2 in marker_ids
            is_shelf_right = 4 in marker_ids
            is_shelf_left = 3 in marker_ids
            is_landing_pad = 0 in marker_ids

            aruco_payload = {
                "stages": {
                    "is_shelf_start": is_shelf_start,
                    "is_shelf_right": is_shelf_right,
                    "is_shelf_left": is_shelf_left,
                    "is_landing_pad": is_landing_pad
                },
                "markers": detected_markers,
                "resolution": {
                    "width": current_frame.shape[1],
                    "height": current_frame.shape[0]
                }
            }

            cv2.imshow("Floor Camera POV", current_frame)
            cv2.waitKey(1)

            _, buffer = cv2.imencode('.jpg', current_frame)
            img_base64 = base64.b64encode(buffer).decode('utf-8')

            with self.state_lock:
                self.state["aruco_data"] = aruco_payload
                self.state["latest_floor_image_base64"] = img_base64

        except Exception as e:
            self.get_logger().error(f"Floor Camera Error: {e}")

    def lidar_callback(self, msg):
        try:
            valid_ranges = [r for r in msg.ranges if not np.isinf(r) and not np.isnan(r) and r > msg.range_min and r <= msg.range_max]
            closest_dist = min(valid_ranges) if valid_ranges else float('inf')

            front_ranges = []
            left_ranges = []
            right_ranges = []

            for i, r in enumerate(msg.ranges):
                if np.isinf(r) or np.isnan(r) or r < msg.range_min or r > msg.range_max:
                    continue

                angle_rad = msg.angle_min + (i * msg.angle_increment)
                angle_deg = np.degrees(angle_rad)

                if -45 <= angle_deg <= 45:
                    front_ranges.append(r)
                elif 45 < angle_deg <= 135:
                    left_ranges.append(r)
                elif -135 <= angle_deg < -45:
                    right_ranges.append(r)

            with self.state_lock:
                self.state["closest_obstacle_distance"] = closest_dist
                self.state["obstacle_front_m"] = min(front_ranges) if front_ranges else float('inf')
                self.state["obstacle_left_m"] = min(left_ranges) if left_ranges else float('inf')
                self.state["obstacle_right_m"] = min(right_ranges) if right_ranges else float('inf')

        except Exception as e:
            self.get_logger().error(f"Lidar Error: {e}")

    # Este metodo manda constatemente la informacion de los sensores al endpoint /sensors/internal/update y actualiza el array con la informacion
    def publish_loop(self):
        req = urllib.request.Request(
            f"{self.api_url}/sensors/internal/update",
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        while rclpy.ok():
            try:
                with self.state_lock:
                    payload = self.state.copy()
                
                # Fast fallback for INF
                for k in ["closest_obstacle_distance", "obstacle_front_m", "obstacle_left_m", "obstacle_right_m"]:
                    if payload.get(k) == float('inf'):
                        payload[k] = -1.0
                    
                data = json.dumps(payload).encode('utf-8')
                
                try:
                    with urllib.request.urlopen(req, data=data, timeout=0.5) as response:
                        pass
                except urllib.error.HTTPError as e:
                    self.get_logger().error(f"HTTP Post error {e.code}: {e.read().decode('utf-8')}")
                except Exception as e:
                    self.get_logger().debug(f"HTTP Post error: {e}")

            except Exception as e:
                self.get_logger().error(f"Publish loop error: {e}")
            time.sleep(0.1) # 10Hz updates

def main(args=None):
    rclpy.init(args=args)
    node = StandaloneSensorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
