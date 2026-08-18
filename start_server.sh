#!/bin/bash
# Start the Sserver

export PYTHONPATH=$(pwd)
export MAVLINK_PORT=${MAVLINK_PORT:-14540}
export CLOUD_API_KEY=${CLOUD_API_KEY:-"default-dev-key"}

if [[ "$1" == "--silent" ]]; then
  export LOG_LEVEL="WARNING"
else
  export LOG_LEVEL=${LOG_LEVEL:-"INFO"}
fi

echo "==========================================================="
echo "Starting drone server for cloud services"
#echo "API Key required for access (default: default-dev-key)"
echo "Options: Pass --silent to disable connection logs"
echo "Docs available at: http://0.0.0.0:8080/docs"
echo "==========================================================="

# Source ROS2 and start ros_gz_bridge
echo "Sourcing ROS2..."
source /opt/ros/humble/setup.bash || echo "Failed to source setup.bash, continuing anyway..."

echo "Starting ros_gz_bridge in the background..."
ros2 run ros_gz_bridge parameter_bridge \
  /world/lab/model/x500_thesis_0/model/OakD_Lite_Camera/link/camera_link/sensor/IMX214/image@sensor_msgs/msg/Image[gz.msgs.Image \
  /world/lab/model/x500_thesis_0/model/OakD_Lite_Camera/link/camera_link/sensor/IMX214/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo \
  /world/lab/model/x500_thesis_0/model/lidar_sensor/link/link/sensor/lidar_2d_v2/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan \
  /world/lab/model/x500_thesis_0/model/Mono_Camera_Floor/link/camera_link/sensor/camera/image@sensor_msgs/msg/Image[gz.msgs.Image \
  /world/lab/model/x500_thesis_0/model/Mono_Camera_Floor/link/camera_link/sensor/camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo \
  &
BRIDGE_PID=$!

echo "Starting ROS2 Node in another terminal..."
python3 src/core/ros2_node.py >ros2_node.log 2>&1 &
NODE_PID=$!

# Ensure both are killed when the script exits
trap "kill $BRIDGE_PID $NODE_PID 2>/dev/null" EXIT

uv run uvicorn src.server.server:app --host 0.0.0.0 --port 8080 --reload
