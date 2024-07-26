# frigate_in_sophgo_bm1684x
NVR with realtime local object detection for IP cameras, deployed on sophgo bm1684x
<a name="xfcQ0"></a>
## 一、原项目复现
> 原项目地址：[https://github.com/blakeblackshear/frigate](https://github.com/blakeblackshear/frigate)

本项目旨在为frigate项目适配sophgo的bm1684x TPU，我们首先对原项目进行复现。
<a name="Fxg52"></a>
### 1.1 摄像头准备
配置你的ip摄像头，并配置好rtsp流的URL。<br />这里本文在计算机上使用[OBS Studio](https://obsproject.com/download)搭配[RTSP server plugin](https://github.com/iamscottxu/obs-rtspserver)进行模拟。使用本地摄像头、窗口采集或者视频文件作为直播源，打开`工具-->RTSP 服务器`设置URL的端口和目录，如`rtsp://localhost:554/rtsp`，点击`启动`。<br />![image.png](https://cdn.nlark.com/yuque/0/2024/png/38480019/1721964427815-2bc05b41-d26c-461b-b0de-c6a62d17b1e6.png#averageHue=%23272a33&clientId=u65dba835-b3fb-4&from=paste&height=892&id=g4AK5&originHeight=892&originWidth=1061&originalType=binary&ratio=1&rotation=0&showTitle=false&size=282368&status=done&style=none&taskId=ub19b9676-ea1e-4ca8-8a47-ae1871e4c75&title=&width=1061)
<a name="sHh5v"></a>
### 1.2 连接bm1684x soc（以Airbox为例）
将AirBox的LAN链接网线，WAN口与计算机相连。然后在计算机端配置IP地址，以windows操作系统为例，打开`设置\网络和Internet\更改适配器选项`，点击`以太网——>属性`，手动设置IP地址为`192.168.150.2`，子网掩码`255.255.255.0`。连接成功后，AirBox的IP即是`192.168.150.1`。<br />使用ssh远程工具，连接Airbox。以Termius为例：`NEW HOST`--> IP or Hostname：`192.168.150.1`，Username：`linaro`，Password：`linaro`。<br />Airbox产品已经配置好驱动和libsophon（在 /opt/sophon目录下），可以直接使用`bm-smi`命令查看tpu信息。
<a name="hkOeB"></a>
### 1.3 环境配置
原项目提供了docker镜像进行快捷的配置，因此我们先装好docker。
```bash
# 1. 更新软件包索引
sudo apt update 
# 2. 安装所需的软件包
sudo apt install apt-transport-https ca-certificates curl software-properties-common
# 3. 添加Docker的官方GPG密钥
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
# 4. 向sources.list添加Docker仓库
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
$(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
# 5.安装Docker CE（社区版）
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io
```
安装docker-compose，创建容器更加方便。
```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
sudo ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
docker-compose --version #查看版本信息
```
新建`docker-compose.yml`文档用于创建容器；根据frigate使用要求，我们在同级目录下建立`config`和 `storage`文件夹并挂载到docker。`docker-compose.yml`内容如下：
```bash
services:
  frigate:
    container_name: frigate
    privileged: true
    restart: unless-stopped
    image: ghcr.io/blakeblackshear/frigate:stable-standard-arm64
    shm_size: "64mb" 
    devices:
      - /dev/bm-tach-0 :/dev/bm-tach-0
      - /dev/bm-tach-1 :/dev/bm-tach-1
      - /dev/bm-top :/dev/bm-top
      - /dev/bm-tpu0 :/dev/bm-tpu0
      - /dev/bm-vpp :/dev/bm-vpp
      - /dev/bm-wdt-0 :/dev/bm-wdt-0
      - /dev/bm_efuse :/dev/bm_efuse
      - /dev/bmdev-ctl :/dev/bmdev-ctl
    volumes:
      - /opt/sophon:/opt/sophon
      - /etc/profile.d:/etc/profile.d
      - /usr/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu
      - /etc/ld.so.conf.d:/etc/ld.so.conf.d  # 前四项是为了在docker中正常使用TPU
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
在`./config`文件夹下，应有frigate的配置文件`config.yml`，其内容可以编写如下：
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
    
detectors:  # <--- 先使用默认cpu作为detector
  cpu1:
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
在`docker-compose.yml`文档的同级目录下，使用docker-compose工具创建容器。
```bash
docker-compose up
```
在本地计算机打开[http://192.168.150.1:5000/](http://192.168.150.1:5000/)可查看frigate管理页面。<br />现在我们创建好容器，并在一直运行中。我们建立新的ssh连接，用下面命令使TPU环境生效。
```bash
# 进入 Docker 容器
sudo docker exec -it frigate bash
# 在 Docker 容器中运行此命令以确保 libsophon 动态库能被找到
ldconfig
# 在 Docker 容器中运行此命令以确保 libsophon 工具可使用
for f in /etc/profile.d/*sophon*; do source $f; done
```
使用`bm-smi`命令验证一下，正常情况如下：<br />![image.png](https://cdn.nlark.com/yuque/0/2024/png/38480019/1721963652268-c124005b-81ac-44cc-b556-b2d8f9341b89.png#averageHue=%2340435b&clientId=u65dba835-b3fb-4&from=paste&height=294&id=u9790f00f&originHeight=294&originWidth=907&originalType=binary&ratio=1&rotation=0&showTitle=false&size=39808&status=done&style=none&taskId=u03b918e7-8d79-40ba-a666-ff4f7baa324&title=&width=907)<br />接下来，我们先停止docker，进行其他准备。
```bash
docker stop frigate
```
<a name="fc6U0"></a>
## 二、适配 bm1684x TPU
<a name="XjLVc"></a>
### 2.1 模型转换（可选，项目已提供[yolov8n_320_1684x_f32.bmodel](https://github.com/wlc952/frigate_in_sophgo_bm1684x/blob/main/yolov8n_320_1684x_f32.bmodel)）
需要将pt、tflite、onnx等模型转为bmodel，具体过程参考[tpu-mlir](https://tpumlir.org/docs/quick_start/index.html)。<br />本文将转换yolov8n的模型，先下载yolov8n的onnx模型：
```bash
from ultralytics import YOLO
model = YOLO("yolov8n.pt")
model.export(format="onnx", imgsz=320)
# onnx_model = YOLO("yolov10n.onnx")
# result = onnx_model("https://ultralytics.com/images/bus.jpg", imgsz=320)
# result[0].show()
```
<a name="Ge71v"></a>
#### 2.1.1 tpu-mlir开发环境配置
在windows计算机安装docker-desktop，下载所需的镜像：
```bash
docker pull sophgo/tpuc_dev:latest
```
创建容器：
```bash
docker run --privileged --name mlir_dev -v $PWD:/workspace -it sophgo/tpuc_dev:latest
```
安装tpu-mlir：
```bash
pip install tpu-mlir
```
准备工作目录：<br />建立工作目录`yolov8`，并把模型文件`yolov8n_320.onnx`和图片文件`image/bus.jpg`都放入`yolov8`目录中。
<a name="Wd8Rr"></a>
#### 2.1.2 编译onnx模型
```bash
# 模型转mlir
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
  
# mlir模型转bmodel F32
model_deploy.py \
    --mlir yolov8n_320.mlir \
    --quantize F32 \
    --chip bm1684x \
    --test_input yolov8n_320_in_f32.npz \
    --test_reference yolov8n_top_outputs.npz \
    --tolerance 0.99,0.99 \
    --model yolov8n_320_1684x_f32.bmodel
```
<a name="J9add"></a>
### 2.2 为frigate docker编译sophon-sail（可选，项目已提供[sophon_arm-3.7.0-py39-none-any-glibc2.31.whl](https://github.com/wlc952/frigate_in_sophgo_bm1684x/blob/main/sophon_arm-3.7.0-py39-none-any-glibc2.31.whl)）
查看frigate docker中的python版本和GLIBC的版本。
```bash
linaro@bm1684:~$ python3 --version
Python 3.8.2
linaro@bm1684:~$ ldd --version
ldd (Ubuntu GLIBC 2.31-0ubuntu9) 2.31
```
<a name="QflGe"></a>
#### 2.2.1 准备相应的版本Linux环境和python
本文在Windows系统下，安装Ubuntu 20.04进行编译。（在Microsoft Store中搜索ubuntu20并下载安装）。<br />打开Ubuntu 20.04，可以看到GLIBC版本合适，python需要另装。
```bash
:~$ python3 --version
Python 3.8.10
:~$ ldd --version
ldd (Ubuntu GLIBC 2.31-0ubuntu9.9) 2.31
```
下载python3.9.2的源码编译安装。
```bash
sudo apt update
# 安装依赖程序
sudo apt install build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev wget
# 下载并解压
wget https://www.python.org/ftp/python/3.9.2/Python-3.9.2.tgz
tar -xf Python-3.9.2.tgz
cd Python-3.9.2
# 编译安装
./configure --enable-optimizations
make
sudo make altinstall
```
<a name="XGore"></a>
#### 2.2.2 编译sophon-sail
本地计算机在[算能官网](https://developer.sophgo.com/site/index/material/77/all.html)下载sophon sdk压缩包。本文采用v23.10.01版本。<br />![image.png](https://cdn.nlark.com/yuque/0/2024/png/38480019/1721965727488-c07458ed-1cd9-4f89-978d-5a34d5d23f66.png#averageHue=%23fdfdfd&clientId=u15daea81-5619-4&from=paste&height=817&id=ufc7d2a66&originHeight=817&originWidth=1545&originalType=binary&ratio=1&rotation=0&showTitle=false&size=133731&status=done&style=none&taskId=u8c1df18d-acdf-458a-b9cc-8774963e1c6&title=&width=1545)<br />解压后在sophon-sail_xxxxx目录下找到sophon-sail_3.7.0.tar.gz，在sophon-img_xxxxx目录下找到libsophon_soc_0.5.1_aarch64.tar.gz，在sophon-mw_xxxxx目录下找到sophon-mw-soc_0.7.3_aarch64.tar.gz。<br />进入wsl中安装g++-aarch64-linux-gnu工具链：
```bash
sudo apt-get install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu cmake
```
将sophon-sail_3.7.0.tar.gz复制到wsl的目录下并解压：
```bash
tar -zxvf sophon-sail_3.7.0.tar.gz
cd sophon-sail
mkdir build
cd build
tar -zxvf libsophon_soc_0.5.0_aarch64.tar.gz
tar -zxvf sophon-mw-soc_0.7.3_aarch64.tar.gz
```
编译：
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
制作安装包：
```bash
cd ../python/soc
# 修改 sophon_soc_whl.sh 中的Python3为python3.9
chmod +x sophon_soc_whl.sh
 python3.9 -m pip install wheel
./sophon_soc_whl.sh
```
生成的安装包`sophon_arm-xxxxx.whl`在`/dist`目录下。
<a name="gaE1U"></a>
### 2.3 在tpu上实现frigate的模型推理
<a name="G3AG4"></a>
#### 2.3.1 安装sophon-sail
ssh连接Airbox，重新启动docker，打开docker中的bash：
```bash
docker start frigate
docker exec -it frigate bash
```
使用sftp将`sophon_arm-3.7.0-py39-none-any-glibc2.31.whl`复制到Airbox，并移动到frigate docker的`/config`对应挂载目录。<br />在docker中安装sophon-sail:
```bash
pip3 install sophon_arm-3.7.0-py39-none-any-glibc2.31.whl
```
<a name="xKiyS"></a>
#### 2.3.2 推理代码替换
将前面转换好的bmodel放在docker的`/config/model_cache`文件夹下。<br />基于friagte环境，使用sail库编写了推理程序[sophgo.py](https://github.com/wlc952/frigate_in_sophgo_bm1684x/blob/main/sophgo.py)。由于算能TPU还没有官方的支持，在使用原项目docker时，这里我们替换其他detector的标签，如`openvino`。在docker中执行下面命令：
```bash
cp /config/sophgo.py /opt/frigate/frigate/detectors/plugins/sophgo.py
rm -f /opt/frigate/frigate/detectors/plugins/openvino.py
```
然后编辑frigate配置文件`/config/config.yml`，或者在网页上（[http://192.168.150.1:5000/](http://192.168.150.1:5000/)）修改detectors部分如下：
```bash
detectors:
  sophgo:
    type: openvino
    device: AUTO
    model:
      path: /config/model_cache/yolov8n_320_1684x_f32.bmodel
```



