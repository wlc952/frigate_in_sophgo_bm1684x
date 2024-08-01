# frigate_in_sophgo_bm1684x

NVR with realtime local object detection for IP cameras, deployed on sophgo bm1684x.
Chinese manual: [README_cn.md](https://github.com/wlc952/frigate_in_sophgo_bm1684x/blob/main/README_cn.md).

## 1、Reproduction of the original project

> Original project address: [https://github.com/blakeblackshear/frigate](https://github.com/blakeblackshear/frigate)

This project aims to adapt sophgo's bm1684x TPU for the frigate project, and we start by replicating the original project.

### 1.1 Camera Preparation

Configure your ip camera and configure the URL for the rtsp stream.

Here in this article, we use OBS Studio with RTSP server plugin on computer for simulation. Use a local camera, window capture or video file as the live stream source, open `Tools-->RTSP Server` to set the port and directory of the URL, such as `rtsp://localhost:554/rtsp`, click `Start`.

![image.png](https://cdn.nlark.com/yuque/0/2024/png/38480019/1721964427815-2bc05b41-d26c-461b-b0de-c6a62d17b1e6.png#averageHue=%23272a33&clientId=u65dba835-b3fb-4&from=paste&height=892&id=g4AK5&originHeight=892&originWidth=1061&originalType=binary&ratio=1&rotation=0&showTitle=false&size=282368&status=done&style=none&taskId=ub19b9676-ea1e-4ca8-8a47-ae1871e4c75&title=&width=1061)

### 1.2 Connecting the bm1684x soc (using Airbox as an example)

Connect the LAN of AirBox to the network cable and the WAN port to the computer. Then configure the IP address on the computer side, take windows operating system as an example, open `Settings\Network and Internet\Change Adapter Options`, click `Ethernet\Properties`, manually set the IP address to `192.168.150.2`, subnet mask `255.255.255.0`. After successful connection, the IP of AirBox is `192.168.150.1`.

Use ssh remote tool to connect to Airbox, take Termius as an example: NEW HOST--> IP or Hostname fill in `192.168.150.1`.
Username: `linaro`, Password: `linaro`.

Airbox product has been configured with driver and libsophon (in `/opt/sophon` directory), you can use `bm-smi` command to view tpu information directly.

### 1.3 Environment Configuration

The original project provides a docker image for quick configuration. In Airbox, docker is already installed. Installing docker-compose to create containers more easily.

```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
sudo ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
docker-compose --version
```

Create a new `docker-compose.yml` document for creating containers; according to the requirements of frigate usage, we create `config` and `storage` folders in the same level directory and mount them to docker. `docker-compose.yml` has the following contents:

```bash
services:
  frigate:
    container_name: frigate
    privileged: true
    restart: unless-stopped
    image: ghcr.io/blakeblackshear/frigate:stable-standard-arm64
    shm_size: "64mb" 
    devices:
      - /dev/jpu :/dev/jpu
      - /dev/bm-tpu0 :/dev/bm-tpu0
    volumes:
      - /opt/sophon:/opt/sophon
      - /etc/profile.d:/etc/profile.d
      - /usr/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu
      - /etc/ld.so.conf.d:/etc/ld.so.conf.d
      - ./config:/config
      - ./storage:/media/frigate
      - type: tmpfs
        target: /tmp/cache
        tmpfs:
          size: 1000000000
    ports:
      - "5000:5000"
      - "8554:8554" # RTSP feeds
      - "8555:8555/tcp" # WebRTC over tcp
      - "8555:8555/udp" # WebRTC over udp
    tty: true
    stdin_open: true
```

In the `. /config` folder, there should be the configuration file `config.yml` for frigate, the contents of which can be written as follows:

```bash
mqtt:
  enabled: False

record:
  enabled: True
  retain:
    days: 0
    mode: all
  events:
    retain:
      default: 1
      mode: motion
      
snapshots:
  enabled: True
  retain:
    default: 1
    
detectors:  
  cpu1:    # <--- This will be replaced by sophgo tpu.
    type: cpu
    num_threads: 3

cameras:
  HP_camera: # <--- this will be changed to your actual camera later
    enabled: True
    ffmpeg:
      inputs:
        - path: rtsp://192.168.150.2:554/rtsp # <--- your actual url
          roles:
            - detect

    motion:
      mask:
        - 0,461,3,0,1919,0,1919,843,1699,492,1344,458,1346,336,973,317,869,375,866,432
```

Create the container using the docker-compose tool in the same directory as the `docker-compose.yml` document.

```bash
docker-compose up
```

Open [http://192.168.150.1:5000/](http://192.168.150.1:5000/) on your local computer to see the frigate administration page.

Now we have created the container and it is running all the time. We create a new ssh connection and enable the TPU environment with the following command.

```bash
sudo docker exec -it frigate bash
ldconfig
for f in /etc/profile.d/*sophon*; do source $f; done
```

Use the `bm-smi` command to verify that the normal situation is as follows:

![image.png](https://cdn.nlark.com/yuque/0/2024/png/38480019/1721963652268-c124005b-81ac-44cc-b556-b2d8f9341b89.png#averageHue=%2340435b&clientId=u65dba835-b3fb-4&from=paste&height=294&id=u9790f00f&originHeight=294&originWidth=907&originalType=binary&ratio=1&rotation=0&showTitle=false&size=39808&status=done&style=none&taskId=u03b918e7-8d79-40ba-a666-ff4f7baa324&title=&width=907)

Next, let's stop docker and make other preparations.

```bash
docker stop frigate
```

## 2、Adaptation for bm1684x TPUs

### 2.1 Model conversion (optional, [yolov8n_320_1684x_f32.bmodel](https://github.com/wlc952/frigate_in_sophgo_bm1684x/raw/main/yolov8n_320_1684x_f32.bmodel) file is provided in this repository)

Models such as pt, tflite, onnx, etc. need to be converted to bmodel, refer to [tpu-mlir](https://tpumlir.org/docs/quick_start/index.html) for the process.
This note will convert the model of yolov8n, first download the onnx model of yolov8n:

```bash
from ultralytics import YOLO
model = YOLO("yolov8n.pt")
model.export(format="onnx", imgsz=320)
# onnx_model = YOLO("yolov10n.onnx")
# result = onnx_model("https://ultralytics.com/images/bus.jpg", imgsz=320)
# result[0].show()
```

#### 2.1.1 tpu-mlir development environment configuration

Install docker-desktop on windows computer and download the required image:

```bash
docker pull sophgo/tpuc_dev:latest
```

Create the container:

```bash
docker run --privileged --name mlir_dev -v $PWD:/workspace -it sophgo/tpuc_dev:latest
```

Install tpu-mlir:

```bash
pip install tpu-mlir
```

Prepare the working directory:
Create the working directory `workspace` and put both the model file `yolov8n_320.onnx` and the image file `image/bus.jpg` into `workspace` directory.

#### 2.1.2 Compiling the onnx model

```bash
# onnx to mlir
model_transform.py \
    --model_name yolov8n_320 \
    --model_def  ./yolov8n_320.onnx \
    --input_shapes [[1,3,320,320]] \
    --mean 0.0,0.0,0.0 \
    --scale 0.0039216,0.0039216,0.0039216 \
    --pixel_format rgb \
    --test_input ./image/bus.jpg \
    --test_result yolov8n_top_outputs.npz \
    --mlir yolov8n_320.mlir
  
# mlir to bmodel F32
model_deploy.py \
    --mlir yolov8n_320.mlir \
    --quantize F32 \
    --chip bm1684x \
    --test_input yolov8n_320_in_f32.npz \
    --test_reference yolov8n_top_outputs.npz \
    --tolerance 0.99,0.99 \
    --model yolov8n_320_1684x_f32.bmodel
```

### 2.2 Compile sophon-sail for frigate docker (optional, [sophon_arm-3.7.0-py3-none-any.whl](https://github.com/wlc952/frigate_in_sophgo_bm1684x/raw/main/sophon_arm-3.7.0-py3-none-any.whl) is already provided in this repository)

Check the python version and GLIBC version in frigate docker.

```bash
linaro@bm1684:~$ python3 --version
Python 3.8.2
linaro@bm1684:~$ ldd --version
ldd (Ubuntu GLIBC 2.31-0ubuntu9) 2.31
```

#### 2.2.1 Prepare the appropriate version of Linux environment and python

This tutorial is for compiling sophon-sail on Windows with WSL (Ubuntu 20.04) installed. (Search ubuntu20 in Microsoft Store and download and install it).
Open Ubuntu 20.04, you can see the appropriate version of GLIBC, python needs to be installed separately.

```bash
:~$ python3 --version
Python 3.8.10
:~$ ldd --version
ldd (Ubuntu GLIBC 2.31-0ubuntu9.9) 2.31
```

Download the source code of python 3.9.2 to compile and install it.

```bash
sudo apt update
sudo apt install build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev wget
wget https://www.python.org/ftp/python/3.9.2/Python-3.9.2.tgz
tar -xf Python-3.9.2.tgz
cd Python-3.9.2
./configure --enable-optimizations
make
sudo make altinstall
```

#### 2.2.2 Compiling sophon-sail

The local computer downloads the sophon sdk zip from the [SOPHGO](https://developer.sophon.ai/site/index/material/all/all.html) website. This tutorial uses version SDK-23.10.01.

![image.png](https://cdn.nlark.com/yuque/0/2024/png/38480019/1721965727488-c07458ed-1cd9-4f89-978d-5a34d5d23f66.png#averageHue=%23fdfdfd&clientId=u15daea81-5619-4&from=paste&height=817&id=ufc7d2a66&originHeight=817&originWidth=1545&originalType=binary&ratio=1&rotation=0&showTitle=false&size=133731&status=done&style=none&taskId=u8c1df18d-acdf-458a-b9cc-8774963e1c6&title=&width=1545)

Unzip it and find `sophon-sail_3.7.0.tar.gz` in the sophon-sail_xxxxx directory, `libsophon_soc_0.5.1_aarch64.tar.gz`in the sophon-img_xxxxx directory, and`sophon-mw-soc_0.7.3_aarch64.tar.gz`in sophon-mw_xxxxx directory.
Go into WSL (Ubuntu 20.04) and install the g++-aarch64-linux-gnu toolchain:

```bash
sudo apt-get install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu cmake
```

Copy `sophon-sail_3.7.0.tar.gz` to WSL's directory and extract it:

```bash
tar -zxvf sophon-sail_3.7.0.tar.gz
cd sophon-sail
mkdir build
cd build
tar -zxvf libsophon_soc_0.5.0_aarch64.tar.gz
tar -zxvf sophon-mw-soc_0.7.3_aarch64.tar.gz
```

Compiling:

```bash
cmake -DBUILD_TYPE=soc  \
    -DCMAKE_TOOLCHAIN_FILE=../cmake/BM168x_SOC/ToolChain_aarch64_linux.cmake \
    -DPYTHON_EXECUTABLE=/usr/local/bin/python3.9 \
    -DCUSTOM_PY_LIBDIR=/usr/local/lib \
    -DLIBSOPHON_BASIC_PATH=libsophon_soc_0.5.0_aarch64/opt/sophon/libsophon-0.5.0 \
    -DFFMPEG_BASIC_PATH=sophon-mw-soc_0.7.3_aarch64/opt/sophon/sophon-ffmpeg_0.7.3 \
    -DOPENCV_BASIC_PATH=sophon-mw-soc_0.7.3_aarch64/opt/sophon/sophon-opencv_0.7.3 ..

make pysail
```

Making a whl package:

```bash
cd ../python/soc
# Change Python3 in sophon_soc_whl.sh to python3.9
chmod +x sophon_soc_whl.sh
 python3.9 -m pip install wheel
./sophon_soc_whl.sh
```

The generated installation package `sophon_arm-3.7.0-py3-none-any.whl` is in the `dist` directory.

### 2.3 Model inference for frigate on tpu

#### 2.3.1 Install sophon-sail

SSH connect to Airbox, restart container, open bash in container:

```bash
docker start frigate
docker exec -it frigate bash
```

Copy `sophon_arm-3.7.0-py3-none-any.whl` to Airbox using SFTP and move it to frigate container's `/config` corresponding mount directory.
Install sophon-sail in container.

```bash
pip3 install sophon_arm-3.7.0-py3-none-any.whl
```

#### 2.3.2 Inference Plugin Configuration

Put the previously converted bmodel in the `/config/model_cache` folder of the container.
Based on the friagte environment, the inference program [sophgo.py](https://github.com/wlc952/frigate_in_sophgo_bm1684x/raw/main/sophgo.py) is written using the sophon-sail library.

```bash
cp /config/sophgo.py /opt/frigate/frigate/detectors/plugins/sophgo.py
```

Then edit the frigate configuration file `/config/config.yml`, or edit it on the web page ([http://192.168.150.1:5000/).](http://192.168.150.1:5000/).) Mainly change the `detectors` section to the following:

```bash
detectors:
  sophgo:
    type: sophgo
    model:
      path: /config/model_cache/yolov8n_320.bmodel
```

#### 2.3.3 Restart frigate

```bash
docker start -i frigate
```

At this point, you can use sophgo TPUs to accelerate NVR frigate project.
