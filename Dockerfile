FROM python:3.12

# Accept build arguments for platform-specific binaries
ARG TARGET_ARCH=amd64
ARG MKBRR_ARCH=linux/amd64

# Update the package list and install system dependencies including mono
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    mediainfo=23.04-1 \
    git \
    g++ \
    cargo \
    mktorrent \
    rustc \
    mono-complete \
    nano && \
    rm -rf /var/lib/apt/lists/*

# Set up a virtual environment to isolate our Python dependencies
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Install wheel and other Python dependencies
RUN pip install --upgrade pip wheel

# Set the working directory in the container
WORKDIR /Upload-Assistant

# Copy the Python requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Create a directory to store the architecture-specific mkbrr binary
RUN mkdir -p /tmp/mkbrr-binary

# Copy only the relevant mkbrr binary for this architecture to a temporary location
COPY bin/mkbrr/${MKBRR_ARCH}/mkbrr /tmp/mkbrr-binary/

# Copy the rest of the application's code
COPY . .

# Replace all mkbrr binaries with just the one for the target architecture
RUN find /Upload-Assistant/bin/mkbrr -type f -name "mkbrr*" -delete && \
    mkdir -p /Upload-Assistant/bin/mkbrr/${MKBRR_ARCH} && \
    cp /tmp/mkbrr-binary/mkbrr /Upload-Assistant/bin/mkbrr/${MKBRR_ARCH}/ && \
    chmod +x /Upload-Assistant/bin/mkbrr/${MKBRR_ARCH}/mkbrr && \
    rm -rf /tmp/mkbrr-binary

# Create tmp directory with appropriate permissions
RUN mkdir -p /Upload-Assistant/tmp && chmod 777 /Upload-Assistant/tmp

# Set the entry point for the container
ENTRYPOINT ["python", "/Upload-Assistant/upload.py"]