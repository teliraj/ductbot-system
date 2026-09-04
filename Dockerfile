# ==============================================================================
# DuctBot Inspection & Localization System
# Multi-Architecture Dockerfile (x86_64, aarch64 / ARM64 for Jetson & Raspberry Pi)
# Base: ROS 2 Humble on Ubuntu 22.04 LTS (Jammy)
# ==============================================================================

FROM ros:humble-ros-base-jammy

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 1. Install System Dependencies, GUI (OpenGL/Mesa/X11), and Media Codecs
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    python3-setuptools \
    python3-wheel \
    python3-colcon-common-extensions \
    python3-rosdep \
    # GUI & Graphics / OpenGL / X11
    python3-kivy \
    libgl1-mesa-dri \
    libgl1-mesa-glx \
    libgles2-mesa-dev \
    libegl1-mesa-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    x11-xserver-utils \
    xauth \
    # OpenCV / Video & Codec Dependencies
    python3-opencv \
    python3-pil \
    python3-numpy \
    python3-scipy \
    python3-pandas \
    python3-serial \
    ffmpeg \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    # System Utilities
    udev \
    usbutils \
    net-tools \
    iputils-ping \
    nano \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Additional Python Dependencies
RUN pip3 install --no-cache-dir \
    ffpyplayer \
    moviepy==1.0.3 \
    imageio==2.31.1 \
    imageio-ffmpeg==0.4.9 \
    proglog \
    tqdm

# 3. Setup Workspace Environment
WORKDIR /app/ductbot-system

# Copy ROS 2 package sources & UI sources
COPY ductbot_localization_ros2/ /app/ductbot-system/ductbot_localization_ros2/
COPY DuctbotsUI/ /app/ductbot-system/DuctbotsUI/
COPY run_system.sh /app/ductbot-system/run_system.sh
COPY .gitignore /app/ductbot-system/.gitignore
COPY README.md /app/ductbot-system/README.md

# Make scripts executable
RUN chmod +x /app/ductbot-system/run_system.sh

# 4. Build ROS 2 ductbot_localization package
WORKDIR /app/ductbot-system/ductbot_localization_ros2
RUN . /opt/ros/humble/setup.sh && \
    colcon build --symlink-install

# 5. Entrypoint & Execution
WORKDIR /app/ductbot-system
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Set environment variables for Kivy display & ROS
ENV DISPLAY=:0
ENV KIVY_WINDOW=sdl2
ENV KIVY_GL_BACKEND=gl

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["/app/ductbot-system/run_system.sh"]
