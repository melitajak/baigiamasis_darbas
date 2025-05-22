FROM python:3.9-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/home/brewuser/.linuxbrew/bin:/home/brewuser/.linuxbrew/sbin:$PATH"
RUN uname -m

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    wget \
    sudo \
    unzip \ 
    ca-certificates \
    file \
    gcc \
    g++ \
    make \
    nodejs \
    default-jre \
    && apt-get clean

# === Set up Homebrew (non-root user) ===
RUN useradd -m brewuser
USER brewuser
ENV HOME=/home/brewuser
ENV PATH="$HOME/.linuxbrew/bin:$HOME/.linuxbrew/sbin:$PATH"
ENV HOMEBREW_NO_INSTALL_CLEANUP=1

# Install Homebrew
RUN git clone https://github.com/Homebrew/brew "$HOME/.linuxbrew/Homebrew" && \
    mkdir -p "$HOME/.linuxbrew/bin" && \
    ln -s ../Homebrew/bin/brew "$HOME/.linuxbrew/bin/" && \
    echo 'eval "$($HOME/.linuxbrew/bin/brew shellenv)"' >> "$HOME/.profile" && \
    echo 'eval "$($HOME/.linuxbrew/bin/brew shellenv)"' >> "$HOME/.bashrc"

# Refresh shellenv for current layer
ENV PATH="$HOME/.linuxbrew/bin:$HOME/.linuxbrew/sbin:$PATH"


# Switch back to root
USER root
ENV PATH="/home/brewuser/.linuxbrew/bin:/home/brewuser/.linuxbrew/sbin:$PATH"

# === Install SPAdes (direct download) ===
RUN wget https://github.com/ablab/spades/releases/download/v3.15.5/SPAdes-3.15.5-Linux.tar.gz && \
    tar -xzf SPAdes-3.15.5-Linux.tar.gz && \
    mv SPAdes-3.15.5-Linux/bin/* /usr/local/bin/ && \
    rm -rf SPAdes-3.15.5-Linux*

# === Install Miniforge (Conda) ===
RUN curl -sSL -o miniforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh && \
    bash miniforge.sh -b -p /opt/conda && \
    rm miniforge.sh
ENV PATH="/opt/conda/bin:$PATH"
RUN conda config --set always_yes yes --set changeps1 no && \
    conda update -q conda

# === Install FastQC ===
RUN wget -qO fastqc.zip https://www.bioinformatics.babraham.ac.uk/projects/fastqc/fastqc_v0.11.9.zip && \
    unzip fastqc.zip -d /opt/tools && \
    chmod +x /opt/tools/FastQC/fastqc && \
    ln -s /opt/tools/FastQC/fastqc /usr/local/bin/fastqc && \
    rm fastqc.zip

# === Python dependencies ===
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# === Project files ===
COPY . /app/
WORKDIR /app

# === Final config ===
WORKDIR /app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]