# Setup documentation

ROS2 Humble on an Ubuntu 24.04 Jammy docker image.

Using rclpy for the drone ROS2 node. CVBridge for image processin between ROS2 and openCV. Using fastfapi for the API server.

## Start the server

1. Terminal:
cd my_drone_api/ -> ./start_server.sh

2. Terminal:
ngrok http 8080

**If you want to test the ros2 node and see the outputs on a separate terminal, run:**

1. Terminal:

```sh
./start_server_sin_ros_node.sh
```

1. Terminal:

```sh
ros2 run ros_gz_bridge parameter_bridge \
  /world/lab/model/x500_thesis_0/model/OakD_Lite_Camera/link/camera_link/sensor/IMX214/image@sensor_msgs/msg/Image[gz.msgs.Image \
  /world/lab/model/x500_thesis_0/model/OakD_Lite_Camera/link/camera_link/sensor/IMX214/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo \
  /world/lab/model/x500_thesis_0/model/lidar_sensor/link/link/sensor/lidar_2d_v2/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan \
  /world/lab/model/x500_thesis_0/model/Mono_Camera_Floor/link/camera_link/sensor/camera/image@sensor_msgs/msg/Image[gz.msgs.Image \
  /world/lab/model/x500_thesis_0/model/Mono_Camera_Floor/link/camera_link/sensor/camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo \
```

1. Terminal:

```sh
python3 src/core/ros2_node.py
```

1. Terminal:

```sh
ngrok http 8080
```

## Runing the simulation (Gazebo)

On another terminal, inside the PX4 Autopilot repo, run:

```sh
make px4_sitl gz_x500_thesis_lab
```

this runs the world with the qrcodes and the equipped drone (lidar, camera, etc.)

### Useful commands

- ros2 topics list
- gz topic -l   # Lista de topics que se pueden agregar a ROS2, run in normal terminal

#### Start the simulation

To start the simulator (and client):

1. Open a new terminal in the root of the **PX4 Autopilot** repo that was installed above.

- Start a PX4 [Gazebo](https://docs.px4.io/main/en/sim_gazebo_gz/) simulation using:

  ```sh
  make px4_sitl gz_x500
  ```

The agent and client are now running they should connect.
