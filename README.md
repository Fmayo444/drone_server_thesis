# drone_server
....

## Content:

- **src/** contains the source code for the RPC server, which allows the connection between the simulated drone and the cloud-based Process Engine, through several endpoints.
- **products_manager/** contains the server and the database setup for the processing and storing product data scanned by the drone at flight time.
- **evidence/** contains evidence of the execution of the whole system (videos and images)
- **worlds_and_models/** contains all the files and folders for the customized simulation scenario in Gazebo (see "PX4 setup" below)
## Setup documentation

### Start the servers

#### Drone server

1. Terminal:
```sh
cd /drone_server_prak
./start_server.sh
```
2. Terminal:
```sh
ngrok http 8080
```

#### Product manager server

  Note: Install all the required python dependencies first.
  
- First create the SQLite tables by running:
  ```sh
  python3 /drone_server_prak/product_manager/data/db_creator.py
  ```
- After creating the table you can run:
  ```sh
  python3 /drone_server_prak/product_manager/data/connect.py
  ```
  for verifying the tables were created.

3. Terminal:
   ```sh
   cd /drone_server_prak/product_manager
   chmod +x products_server.py
   ./products_server.py
   ```
  

**If you want to test the ros2 node and see the outputs on a separate terminal, run:**

1. Terminal:

```sh
./start_server_sin_ros_node.sh
```

2. Terminal:

```sh
ros2 run ros_gz_bridge parameter_bridge \
  /world/lab/model/x500_thesis_0/model/OakD_Lite_Camera/link/camera_link/sensor/IMX214/image@sensor_msgs/msg/Image[gz.msgs.Image \
  /world/lab/model/x500_thesis_0/model/OakD_Lite_Camera/link/camera_link/sensor/IMX214/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo \
  /world/lab/model/x500_thesis_0/model/lidar_sensor/link/link/sensor/lidar_2d_v2/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan \
  /world/lab/model/x500_thesis_0/model/Mono_Camera_Floor/link/camera_link/sensor/camera/image@sensor_msgs/msg/Image[gz.msgs.Image \
  /world/lab/model/x500_thesis_0/model/Mono_Camera_Floor/link/camera_link/sensor/camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo \
```

3. Terminal:

```sh
python3 src/core/ros2_node.py
```

4. Terminal:

```sh
ngrok http 8080
```

### Runing the simulation (Gazebo)

On another terminal, inside the PX4 Autopilot repo, run:

```sh
make px4_sitl gz_x500_thesis_lab
```

this runs the world with the qrcodes and the equipped drone (lidar, camera, etc.)

### PX4 setup

1. Install the PX4 Repository ( see https://docs.px4.io/main/en/dev_setup/dev_env )
2. Copy the file at /drone_server_prak/worlds_and_models/lab.sdf and paste to the following path inside PX4-Repo: .../PX4-Autopilot/Tools/simulation/gz/worlds
3. Copy the folder /drone_server_prak/worlds_and_models/qrs and paste also to the same path from before: .../PX4-Autopilot/Tools/simulation/gz/worlds
4. Copy the folder /drone_server_prak/worlds_and_models/x500_thesis and paste to the following path inside PX4-Repo: .../PX4-Autopilot/Tools/simulation/gz/models
5. Copy the folders from ArucoTags also at /drone_server_prak/worlds_and_models/ and paste to the path: .../PX4-Autopilot/Tools/simulation/gz/models
6. Copy the file at /drone_server_prak/worlds_and_models/4012_gz_x500_thesis and paste to this path: .../PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/
7. Inside the path .../PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/ edit the CMakeLists.txt by adding inside the 'px4_add_romfs_files' the name 4012_gz_x500_thesis
8. For testing run the following command inside /PX4-Autopilot: make px4_sitl gz_x500_thesis_lab. You should see then the customized drone and world.


### Useful commands

- ros2 topics list
- gz topic -l   # Lista de topics que se pueden agregar a ROS2, run in normal terminal

### Start the simulation

To start the simulator (and client):

1. Open a new terminal in the root of the **PX4 Autopilot** repo that was installed above.

- Start a PX4 [Gazebo](https://docs.px4.io/main/en/sim_gazebo_gz/) simulation using:

  ```sh
  make px4_sitl gz_x500
  ```

