FROM alpine:latest

# Add mono repository and install mono
RUN apk add --no-cache mono --repository http://dl-cdn.alpinelinux.org/alpine/edge/testing

# Install system dependencies including Python 3.11 and tools
RUN apk add --no-cache --upgrade ffmpeg mediainfo python3=3.11.5-r0 git py3-pip python3-dev=3.11.5-r0 g++ cargo mktorrent rust

# Set up a virtual environment to isolate our Python dependencies
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Install wheel and other Python dependencies
RUN pip install wheel

# Set the working directory in the container
WORKDIR /Upload-Assistant

# Copy the Python requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the application's code
COPY . .

# Set the entry point for the container
ENTRYPOINT ["python3", "/Upload-Assistant/upload.py"]